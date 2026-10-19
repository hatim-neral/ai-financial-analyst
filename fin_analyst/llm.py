"""Minimal client for OpenAI-compatible chat-completions APIs (Groq, Gemini).

Both providers expose the same /chat/completions endpoint with function calling, so
one small client covers both. The primary provider is tried first; on rate limits,
outages or auth errors the client falls back to the other one if a key is configured.

API keys are read from environment variables or Streamlit secrets and are never
logged, returned in error messages or sent anywhere except the provider's endpoint.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping

import requests

from . import config

PROVIDERS = {
    # name: (base URL, default model, API-key variable, model-override variable)
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY", "GROQ_MODEL"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash",
               "GEMINI_API_KEY", "GEMINI_MODEL"),
}


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    model: str
    api_key: str = field(repr=False)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class ChatResponse:
    content: str | None
    tool_calls: list[ToolCall]
    usage: dict
    provider: str
    model: str

    def assistant_message(self) -> dict:
        msg: dict = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ]
        return msg


class LLMError(Exception):
    """Raised when no configured provider could answer. Message is safe to display."""


class _ProviderFailure(Exception):
    def __init__(self, reason: str, retry_same: bool):
        super().__init__(reason)
        self.reason = reason
        self.retry_same = retry_same


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

    primary = get("LLM_PROVIDER").lower() or "groq"
    order = [primary] + [p for p in PROVIDERS if p != primary] if primary in PROVIDERS else list(PROVIDERS)
    configs = []
    for name in order:
        base_url, default_model, key_var, model_var = PROVIDERS[name]
        key = get(key_var)
        if key:
            configs.append(ProviderConfig(name, base_url, get(model_var) or default_model, key))
    return configs


class ChatClient:
    def __init__(self, providers: list[ProviderConfig], post: Callable | None = None,
                 sleep: Callable[[float], None] = time.sleep, timeout: float = config.LLM_TIMEOUT_S):
        self.providers = providers
        self._post = post or requests.post
        self._sleep = sleep
        self.timeout = timeout

    @property
    def label(self) -> str:
        if not self.providers:
            return "not configured"
        names = [f"{p.name} · {p.model}" for p in self.providers]
        return names[0] + (f" (fallback: {', '.join(names[1:])})" if len(names) > 1 else "")

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResponse:
        if not self.providers:
            raise LLMError("No LLM API key is configured.")
        reasons = []
        for provider in self.providers:
            for attempt in range(2):
                try:
                    return self._call(provider, messages, tools)
                except _ProviderFailure as exc:
                    reasons.append(f"{provider.name}: {exc.reason}")
                    if exc.retry_same and attempt == 0:
                        self._sleep(1.5)
                        continue
                    break
        raise LLMError("The AI service is unavailable right now (" + "; ".join(reasons) +
                       "). The dashboard and calculations still work; try the question again in a minute.")

    def _call(self, p: ProviderConfig, messages: list[dict], tools: list[dict] | None) -> ChatResponse:
        body = {
            "model": p.model,
            "messages": messages,
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
            raise _ProviderFailure("request timed out", retry_same=True)
        except requests.RequestException as exc:
            raise _ProviderFailure(f"network error ({type(exc).__name__})", retry_same=True)

        status = resp.status_code
        if status == 429:
            raise _ProviderFailure("rate limit reached", retry_same=False)
        if status in (401, 403):
            raise _ProviderFailure("API key rejected", retry_same=False)
        if status == 400:
            # Typically a malformed tool call from the model (e.g. Groq "tool_use_failed"); retrying usually works.
            raise _ProviderFailure("request rejected (400)", retry_same=True)
        if status >= 500:
            raise _ProviderFailure(f"server error ({status})", retry_same=True)
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
            calls.append(ToolCall(c.get("id") or f"call_{i}", fn.get("name") or "", args or "{}"))
        usage = data.get("usage") or {}
        return ChatResponse(
            content=message.get("content"),
            tool_calls=calls,
            usage={"prompt_tokens": int(usage.get("prompt_tokens") or 0),
                   "completion_tokens": int(usage.get("completion_tokens") or 0)},
            provider=p.name,
            model=p.model,
        )
