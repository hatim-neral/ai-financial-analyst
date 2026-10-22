"""Claude (Anthropic API) as a provider, through the official `anthropic` SDK.

The rest of the app speaks the OpenAI-style chat format that the free providers share. This module
translates at the boundary, so the agent loop, the tools and the number guard stay provider-neutral:

- the system message becomes the top-level `system` field (cached with the tool definitions);
- assistant turns made by Claude are replayed with their original content blocks, so thinking
  blocks go back unchanged (Claude Opus 5.5 always thinks; dropping or editing them breaks the turn);
  assistant turns made by another provider become plain text + `tool_use` blocks;
- consecutive tool results go back together in one user message (parallel tool calls);
- the server-side refusal fallback is on (`fallbacks: "default"`).

Claude Opus 5.5 takes no sampling parameters and forced `tool_choice` is a 400, so neither is sent.
Errors map onto the client's failover rules: rate limits cool down, busy servers are skipped, a bad
key is set aside, and the user only ever sees the plain "busy" message from llm.py.
"""

from __future__ import annotations

import json
import re

import anthropic

MAX_TOKENS = 16000          # thinking counts toward max_tokens, so leave room beyond the answer
EFFORT = "medium"           # Opus 5.5 default, set explicitly; enough for multi-tool analysis questions
TIMEOUT_S = 120             # an always-thinking model can take longer than the free providers' 30s
FALLBACK_BETA = "server-side-fallback-2026-07-01"
_DROP_BEFORE_FALLBACK = {"thinking", "redacted_thinking", "tool_use"}

_clients: dict[str, anthropic.Anthropic] = {}


def _client(api_key: str) -> anthropic.Anthropic:
    # Retries are owned by ChatClient (it fails over to the next provider), so the SDK's are off.
    if api_key not in _clients:
        _clients[api_key] = anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=TIMEOUT_S)
    return _clients[api_key]


def _tool_id(call_id: str) -> str:
    """Anthropic tool ids allow letters, digits, '_' and '-' only (ids may come from other providers)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", call_id or "call") or "call"


def _tools(specs: list[dict] | None) -> list[dict]:
    out = []
    for spec in specs or []:
        fn = spec.get("function") or {}
        out.append({"name": fn["name"], "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}})
    return out


def echo_content(blocks: list[dict]) -> list[dict]:
    """Assistant content to replay: unchanged, except across a mid-output fallback boundary, where
    model-internal blocks before the last `fallback` marker are omitted (the marker itself too)."""
    last = max((i for i, b in enumerate(blocks) if b.get("type") == "fallback"), default=-1)
    out = []
    for i, b in enumerate(blocks):
        if b.get("type") == "fallback" or (i < last and b.get("type") in _DROP_BEFORE_FALLBACK):
            continue
        out.append(b)
    return out


def to_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    """OpenAI-style messages -> (system, Anthropic messages)."""
    system_parts, out = [], []
    for m in messages:
        role = m.get("role")
        if role == "system":
            system_parts.append(m.get("content") or "")
            continue
        if role == "tool":
            block = {"type": "tool_result", "tool_use_id": _tool_id(m.get("tool_call_id", "")),
                     "content": m.get("content") or ""}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) \
                    and all(b.get("type") == "tool_result" for b in out[-1]["content"]):
                out[-1]["content"].append(block)  # all results of one turn in a single user message
            else:
                out.append({"role": "user", "content": [block]})
            continue
        if role == "assistant":
            if m.get("anthropic_content"):
                out.append({"role": "assistant", "content": echo_content(m["anthropic_content"])})
                continue
            blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
            for c in m.get("tool_calls") or []:
                fn = c.get("function") or {}
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                blocks.append({"type": "tool_use", "id": _tool_id(c.get("id", "")), "name": fn.get("name", ""),
                               "input": args if isinstance(args, dict) else {}})
            out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "…"}]})
            continue
        out.append({"role": "user", "content": m.get("content") or ""})
    return "\n\n".join(p for p in system_parts if p), out


def call(provider, messages: list[dict], tools: list[dict] | None):
    """One Messages API request. Returns llm.ChatResponse or raises llm._ProviderFailure."""
    from .llm import ChatResponse, ToolCall, _ProviderFailure

    system, msgs = to_anthropic(messages)
    try:
        response = _client(provider.api_key).beta.messages.create(
            model=provider.model,
            max_tokens=MAX_TOKENS,
            system=system or anthropic.NOT_GIVEN,
            messages=msgs,
            tools=_tools(tools) or anthropic.NOT_GIVEN,
            output_config={"effort": EFFORT},
            cache_control={"type": "ephemeral"},  # the system prompt and tools repeat on every call
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.RateLimitError as exc:
        try:
            wait = float(exc.response.headers.get("retry-after", ""))
        except (TypeError, ValueError):
            wait = None
        raise _ProviderFailure("rate limit reached", retry_same=False, wait_s=wait, rate_limited=True)
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise _ProviderFailure("API key rejected", retry_same=False, bad_key=True)
    except anthropic.BadRequestError as exc:
        raise _ProviderFailure(f"request rejected (400): {exc.message[:160]}", retry_same=False)
    except anthropic.APITimeoutError:
        raise _ProviderFailure("request timed out", retry_same=False, busy=True)
    except anthropic.APIConnectionError as exc:
        raise _ProviderFailure(f"network error ({type(exc).__name__})", retry_same=True, busy=True)
    except anthropic.APIStatusError as exc:  # 5xx, 529 overloaded
        raise _ProviderFailure(f"server error ({exc.status_code})", retry_same=False, busy=True)

    if response.stop_reason == "refusal":
        # The server-side fallback already ran; let the next provider try rather than show a refusal.
        raise _ProviderFailure("declined by safety classifier", retry_same=False)

    blocks = [b.model_dump(mode="json", exclude_none=True) for b in response.content]
    text = "".join(b.text for b in response.content if b.type == "text")
    calls = [ToolCall(_tool_id(b.id), b.name, json.dumps(b.input)) for b in response.content if b.type == "tool_use"]
    usage = response.usage
    prompt_tokens = (usage.input_tokens or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0) \
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    return ChatResponse(content=text or None, tool_calls=calls,
                        usage={"prompt_tokens": prompt_tokens, "completion_tokens": usage.output_tokens or 0},
                        provider=provider.name, model=response.model or provider.model, native=blocks)

