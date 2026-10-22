"""Minimal client for OpenAI-compatible chat-completions APIs.

Supported: Claude (Anthropic API, paid, through the official SDK in claude_provider.py) and the free
tiers with function calling: Groq, Cerebras, Mistral, Google Gemini, NVIDIA NIM, Hugging Face and
OpenRouter. The free ones expose the same /chat/completions endpoint, so one small client covers them. Every provider with a key is used, in order, and a provider's *_MODEL setting may list
several models ("a,b"): free quotas are often per model, so each model is its own entry.

A rate-limited entry is put on cooldown for as long as it asked (seconds or hours) and the next one is
tried at once; the client only waits when every entry is cooling down, and only for a short time.
Busy servers and timeouts get a short cooldown; a rejected key a long one. When nothing can answer,
the user sees one plain "busy, try again shortly" message; the reasons go to the server log.

API keys are read from environment variables or Streamlit secrets and are never
logged, returned in error messages or sent anywhere except the provider's endpoint.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
import hashlib
import logging
from typing import Callable, Mapping

import requests

from . import config

PROVIDERS = {
    # name: (base URL, default model(s), API-key variable, model-override variable)
    # Claude first when its key is set; the free providers below take over if it is rate limited or down.
    "anthropic": ("https://api.anthropic.com", "claude-opus-5-5", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"),
    # Groq's free limits are per model, so a second model adds a second daily allowance on the same key.
    # gpt-oss-20b passed the demo and attack questions in testing; it is the backup before other providers.
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b,openai/gpt-oss-20b", "GROQ_API_KEY", "GROQ_MODEL"),
    "cerebras": ("https://api.cerebras.ai/v1", "gpt-oss-120b", "CEREBRAS_API_KEY", "CEREBRAS_MODEL"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-small-latest", "MISTRAL_API_KEY", "MISTRAL_MODEL"),
    # Gemini's free tier counts requests per model per day (the flash model allows only ~20), so two
    # models double the daily allowance. gemini-2.5-flash is closed to new keys.
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite,gemini-3.5-flash",
               "GEMINI_API_KEY", "GEMINI_MODEL"),
    "nvidia": ("https://integrate.api.nvidia.com/v1", "moonshotai/kimi-k2.6", "NVIDIA_API_KEY", "NVIDIA_MODEL"),
    "huggingface": ("https://router.huggingface.co/v1", "openai/gpt-oss-120b", "HF_TOKEN", "HF_MODEL"),
    # OpenRouter's free roster changes often; override OPENROUTER_MODEL with any ":free" model that supports tools.
    "openrouter": ("https://openrouter.ai/api/v1", "nvidia/nemotron-3-super-120b-a12b:free",
                   "OPENROUTER_API_KEY", "OPENROUTER_MODEL"),
}
DEFAULT_RATE_LIMIT_COOLDOWN_S = 20  # when a 429 doesn't say how long to wait
BUSY_COOLDOWN_S = 30                # a busy server (5xx) or a timeout: skip it for a little while
BAD_KEY_COOLDOWN_S = 3600           # a rejected key won't fix itself during this session
BUSY_MESSAGE = ("The AI analyst is busy right now. Please try again in a minute or two. "
                "The dashboard and every calculation still work in the meantime.")
log = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    model: str
    api_key: str = field(repr=False)

    @property
    def key(self) -> str:
        """One entry per provider and model: free quotas are usually counted per model."""
        return f"{self.name}:{self.model}"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str
    extra: dict | None = None  # provider-specific data to echo back, e.g. Gemini's thought_signature


@dataclass
class ChatResponse:
    content: str | None
    tool_calls: list[ToolCall]
    usage: dict
    provider: str
    model: str
    native: list[dict] | None = None  # Claude's original content blocks, replayed unchanged (thinking)

    def assistant_message(self) -> dict:
        msg: dict = {"role": "assistant", "content": self.content}
        if self.native:
            msg["anthropic_content"] = self.native
        if self.tool_calls:
            msg["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments},
                 **({"extra_content": c.extra} if c.extra else {})}
                for c in self.tool_calls
            ]
        return msg


class LLMError(Exception):
    """Raised when no configured provider could answer. The message is the plain one users see;
    `details` holds the per-provider reasons for logs and tests."""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message)
        self.details = details


class _ProviderFailure(Exception):
    def __init__(self, reason: str, retry_same: bool, wait_s: float | None = None, rate_limited: bool = False,
                 busy: bool = False, bad_key: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.retry_same = retry_same
        self.rate_limited = rate_limited
        self.busy = busy
        self.bad_key = bad_key
        self.wait_s = wait_s  # set when the provider told us exactly how long to back off


_DURATION = re.compile(r"(?:try again|retry) in\s+((?:\d+h)?(?:\d+m(?!s))?(?:[\d.]+(?:ms|s))?)", re.I)


def _parse_duration(text: str) -> float | None:
    """'1.3125s', '850ms', '7m12s', '16h59m33.79s' -> seconds."""
    if not text:
        return None
    total, found = 0.0, False
    for value, unit in re.findall(r"([\d.]+)(h|ms|m|s)", text):
        found = True
        total += float(value) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unit]
    return total if found else None


def _rate_limit_wait(resp) -> float | None:
    """Seconds the provider asks us to wait: Retry-After, Google's RetryInfo, or "try again / retry in …"."""
    headers = getattr(resp, "headers", None) or {}
    try:
        if headers.get("retry-after"):
            return float(headers["retry-after"])
    except (TypeError, ValueError):
        pass
    try:
        body = resp.json()
    except Exception:
        return None
    if isinstance(body, list):  # Gemini wraps its error in a list
        body = body[0] if body else {}
    error = (body or {}).get("error") or {}
    if not isinstance(error, dict):
        return None
    for detail in error.get("details") or []:
        if isinstance(detail, dict) and str(detail.get("@type", "")).endswith("RetryInfo"):
            wait = _parse_duration(str(detail.get("retryDelay", "")))
            if wait is not None:
                return wait
    m = _DURATION.search(str(error.get("message", "")))
    return _parse_duration(m.group(1)) if m else None


def load_providers(*sources: Mapping) -> list[ProviderConfig]:
    """Build the provider list from env vars / secrets (first non-empty value wins)."""

    def get(key: str) -> str:
        for src in sources:
            try:
                val = src.get(key)
            except Exception:  # streamlit secrets raise if no secrets file exists
                val = None
            if val:
                return str(val).strip()
        return ""

    # Default order is the table order (Claude first when its key is set); LLM_PROVIDER moves one to the front.
    primary = get("LLM_PROVIDER").lower()
    order = [primary] + [p for p in PROVIDERS if p != primary] if primary in PROVIDERS else list(PROVIDERS)
    configs = []
    for name in order:
        base_url, default_models, key_var, model_var = PROVIDERS[name]
        key = get(key_var)
        if key:
            for model in [m.strip() for m in (get(model_var) or default_models).split(",") if m.strip()]:
                configs.append(ProviderConfig(name, base_url, model, key))
    return configs


# Google's documented placeholder for tool calls the model didn't make itself (e.g. made by
# another provider earlier in the conversation): https://ai.google.dev/gemini-api/docs/thought-signatures
_GEMINI_SKIP_SIGNATURE = {"google": {"thought_signature": "skip_thought_signature_validator"}}


def _mistral_id(call_id: str) -> str:
    """Mistral only accepts tool-call ids of exactly 9 letters and digits."""
    if re.fullmatch(r"[A-Za-z0-9]{9}", call_id or ""):
        return call_id
    return hashlib.md5((call_id or "").encode()).hexdigest()[:9]


def _messages_for(provider: str, messages: list[dict]) -> list[dict]:
    """Adapt one provider-neutral conversation to a provider's quirks.

    Gemini 3 requires each earlier tool call's thought_signature (other providers may reject the
    field); Mistral requires 9-character tool-call ids. Both matter when a question fails over from
    one provider to another halfway through.
    """
    out = []
    for m in messages:
        if "anthropic_content" in m:  # Claude-only replay data; OpenAI-style providers reject unknown keys
            m = {k: v for k, v in m.items() if k != "anthropic_content"}
        calls = m.get("tool_calls")
        if provider == "mistral" and m.get("role") == "tool":
            out.append({**m, "tool_call_id": _mistral_id(m.get("tool_call_id", ""))})
            continue
        if not calls:
            out.append(m)
            continue
        fixed = []
        for c in calls:
            c = {k: v for k, v in c.items() if k != "extra_content"} if provider != "gemini" else \
                {**c, "extra_content": c.get("extra_content") or _GEMINI_SKIP_SIGNATURE}
            if provider == "mistral":
                c = {**c, "id": _mistral_id(c.get("id", ""))}
            fixed.append(c)
        out.append({**m, "tool_calls": fixed})
    return out


class ChatClient:
    def __init__(self, providers: list[ProviderConfig], post: Callable | None = None,
                 sleep: Callable[[float], None] = time.sleep, timeout: float = config.LLM_TIMEOUT_S,
                 clock: Callable[[], float] = time.monotonic):
        self.providers = providers
        self._post = post or requests.post
        self._sleep = sleep
        self._clock = clock
        self.timeout = timeout
        self._cooldown_until: dict[str, float] = {}  # provider:model -> monotonic time it may be used again

    @property
    def label(self) -> str:
        if not self.providers:
            return "not configured"
        names = [f"{p.name} · {p.model}" for p in self.providers]
        return names[0] + (f" (+{len(names) - 1} backup{'s' if len(names) > 2 else ''})" if len(names) > 1 else "")

    def cooling(self) -> list[str]:
        """Entries currently skipped because they asked us to wait (for a status line)."""
        now = self._clock()
        return [k for k, until in self._cooldown_until.items() if until > now]

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResponse:
        if not self.providers:
            raise LLMError("No LLM API key is configured.")
        reasons: list[str] = []
        failed: set[str] = set()  # entries that failed in this call (not rate limits)
        waits = 0
        while True:
            candidates = [p for p in self.providers if p.key not in failed]
            if not candidates:
                break
            now = self._clock()
            ready = [p for p in candidates if self._cooldown_until.get(p.key, 0.0) <= now]
            if not ready:
                # Everyone is cooling down. Per-minute limits refill continuously, so a short wait beats failing.
                wait = min(self._cooldown_until[p.key] for p in candidates) - now
                if wait <= config.LLM_MAX_RATE_LIMIT_WAIT_S and waits < config.LLM_RATE_LIMIT_RETRIES:
                    waits += 1
                    self._sleep(max(wait, 0.0) + 0.25)
                    continue
                break
            provider = ready[0]
            try:
                return self._call_with_retry(provider, messages, tools)
            except _ProviderFailure as exc:
                reasons.append(f"{provider.key}: {exc.reason}")
                if exc.rate_limited:
                    self._cooldown_until[provider.key] = self._clock() + (exc.wait_s or DEFAULT_RATE_LIMIT_COOLDOWN_S)
                    continue
                failed.add(provider.key)
                cooldown = BAD_KEY_COOLDOWN_S if exc.bad_key else BUSY_COOLDOWN_S if exc.busy else 0
                if cooldown:
                    self._cooldown_until[provider.key] = self._clock() + cooldown
        details = "; ".join(reasons) or "no provider could be reached"
        log.warning("LLM unavailable: %s", details)
        raise LLMError(BUSY_MESSAGE, details)

    def _call_with_retry(self, p: ProviderConfig, messages: list[dict], tools: list[dict] | None) -> ChatResponse:
        try:
            return self._call(p, messages, tools)
        except _ProviderFailure as exc:
            if not exc.retry_same:
                raise
            self._sleep(1.5)
            return self._call(p, messages, tools)

    def _call(self, p: ProviderConfig, messages: list[dict], tools: list[dict] | None) -> ChatResponse:
        if p.name == "anthropic":
            from . import claude_provider
            return claude_provider.call(p, messages, tools)
        body = {
            "model": p.model,
            "messages": _messages_for(p.name, messages),
            "temperature": 0,
            "max_tokens": config.LLM_MAX_OUTPUT_TOKENS,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        try:
            resp = self._post(f"{p.base_url}/chat/completions",
                              headers={"Authorization": f"Bearer {p.api_key}", "Content-Type": "application/json"},
                              json=body, timeout=self.timeout)
        except requests.Timeout:
            # A slow provider stays slow for a while: move to the next one instead of waiting again.
            raise _ProviderFailure("request timed out", retry_same=False, busy=True)
        except requests.RequestException as exc:
            raise _ProviderFailure(f"network error ({type(exc).__name__})", retry_same=True, busy=True)

        status = resp.status_code
        if status == 429:
            raise _ProviderFailure("rate limit reached", retry_same=False, wait_s=_rate_limit_wait(resp),
                                   rate_limited=True)
        if status in (401, 403):
            raise _ProviderFailure("API key rejected", retry_same=False, bad_key=True)
        if status == 400:
            # Typically a malformed tool call from the model (e.g. Groq "tool_use_failed"); retrying usually works.
            raise _ProviderFailure("request rejected (400)", retry_same=True)
        if status >= 500:
            raise _ProviderFailure(f"server error ({status})", retry_same=True, busy=True)
        if status != 200:
            raise _ProviderFailure(f"unexpected status {status}", retry_same=False)

        try:
            data = resp.json()
            message = data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise _ProviderFailure("unreadable response", retry_same=True)

        calls = []
        for i, c in enumerate(message.get("tool_calls") or []):
            fn = c.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, dict):
                args = json.dumps(args)
            calls.append(ToolCall(c.get("id") or f"call_{i}", fn.get("name") or "", args or "{}",
                                  c.get("extra_content") or None))
        usage = data.get("usage") or {}
        return ChatResponse(
            content=message.get("content"),
            tool_calls=calls,
            usage={"prompt_tokens": int(usage.get("prompt_tokens") or 0),
                   "completion_tokens": int(usage.get("completion_tokens") or 0)},
            provider=p.name,
            model=p.model,
        )
