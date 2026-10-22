"""Claude (Anthropic API) provider: request shape, format translation, thinking replay, error mapping
and failover. Uses a fake SDK client; no network calls and no key needed."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from fin_analyst import claude_provider, llm


class Block(SimpleNamespace):
    def model_dump(self, **_):
        return {k: v for k, v in vars(self).items() if v is not None}


def message(content, stop_reason="end_turn"):
    return SimpleNamespace(content=content, stop_reason=stop_reason, model="claude-opus-5-5",
                           usage=SimpleNamespace(input_tokens=100, output_tokens=40,
                                                 cache_read_input_tokens=900, cache_creation_input_tokens=0))


class FakeSDK:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def claude_only():
    return llm.load_providers({"ANTHROPIC_API_KEY": "sk-ant-test"})


def install(monkeypatch, responses):
    fake = FakeSDK(responses)
    monkeypatch.setattr(claude_provider, "_client", lambda key: fake)
    return fake


def _err(cls, status, headers=None):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("x", response=httpx2.Response(status, headers=headers or {}, request=req), body=None)


TOOLS = [{"type": "function", "function": {"name": "get_period_summary", "description": "Totals",
                                            "parameters": {"type": "object", "properties": {}, "required": []}}}]


def test_claude_is_first_and_uses_opus_5_5():
    providers = llm.load_providers({"ANTHROPIC_API_KEY": "a", "GROQ_API_KEY": "g"})
    assert [p.key for p in providers][:2] == ["anthropic:claude-opus-5-5", "groq:openai/gpt-oss-120b"]


def test_request_shape_follows_opus_5_5_rules(monkeypatch):
    fake = install(monkeypatch, [message([Block(type="text", text="Revenue was ₹1,000 [E1].")])])
    msgs = [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "Q?"}]
    resp = llm.ChatClient(claude_only(), sleep=lambda s: None).complete(msgs, TOOLS)
    sent = fake.calls[0]
    assert sent["model"] == "claude-opus-5-5" and sent["system"] == "SYSTEM"
    assert sent["messages"] == [{"role": "user", "content": "Q?"}]
    assert "temperature" not in sent and "tool_choice" not in sent and "thinking" not in sent
    assert sent["fallbacks"] == "default" and sent["betas"] == ["server-side-fallback-2026-07-01"]
    assert sent["output_config"] == {"effort": "medium"} and sent["cache_control"] == {"type": "ephemeral"}
    assert sent["tools"][0]["name"] == "get_period_summary" and "input_schema" in sent["tools"][0]
    assert resp.content.startswith("Revenue") and resp.usage["prompt_tokens"] == 1000


def test_tool_calls_round_trip_with_thinking_replayed_unchanged(monkeypatch):
    thinking = Block(type="thinking", thinking="", signature="sig-abc")
    use = Block(type="tool_use", id="toolu_01", name="get_period_summary", input={"start_month": "2025-01"})
    fake = install(monkeypatch, [message([thinking, use], "tool_use"), message([Block(type="text", text="Done")])])
    client = llm.ChatClient(claude_only(), sleep=lambda s: None)
    history = [{"role": "user", "content": "Q?"}]
    first = client.complete(history, TOOLS)
    assert first.tool_calls[0].name == "get_period_summary" and '"start_month": "2025-01"' in first.tool_calls[0].arguments
    history += [first.assistant_message(), {"role": "tool", "tool_call_id": "toolu_01", "content": "{}"}]
    client.complete(history, TOOLS)
    replayed = fake.calls[1]["messages"]
    assert replayed[1] == {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "", "signature": "sig-abc"},
        {"type": "tool_use", "id": "toolu_01", "name": "get_period_summary", "input": {"start_month": "2025-01"}}]}
    assert replayed[2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_01", "content": "{}"}]}


def test_turns_from_other_providers_are_translated_and_parallel_results_grouped():
    msgs = [{"role": "user", "content": "Q?"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "fc.1", "type": "function", "function": {"name": "a", "arguments": "{\"x\": 1}"}},
                {"id": "fc.2", "type": "function", "function": {"name": "b", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "fc.1", "content": "r1"},
            {"role": "tool", "tool_call_id": "fc.2", "content": "r2"}]
    system, out = claude_provider.to_anthropic(msgs)
    assert system == "" and [b["id"] for b in out[1]["content"]] == ["fc_1", "fc_2"]
    assert out[1]["content"][0]["input"] == {"x": 1}
    assert len(out) == 3 and [b["tool_use_id"] for b in out[2]["content"]] == ["fc_1", "fc_2"]


def test_fallback_boundary_echo_rules():
    blocks = [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "text", "text": "partial"},
              {"type": "fallback"}, {"type": "thinking", "thinking": "", "signature": "t"}, {"type": "text", "text": "ok"}]
    assert claude_provider.echo_content(blocks) == [
        {"type": "text", "text": "partial"}, {"type": "thinking", "thinking": "", "signature": "t"},
        {"type": "text", "text": "ok"}]


def test_other_providers_never_receive_claude_replay_data():
    msg = {"role": "assistant", "content": "x", "anthropic_content": [{"type": "text", "text": "x"}]}
    assert "anthropic_content" not in llm._messages_for("groq", [msg])[0]


@pytest.mark.parametrize("error,expect", [
    (_err(anthropic.RateLimitError, 429, {"retry-after": "7"}), "rate"),
    (_err(anthropic.AuthenticationError, 401), "bad_key"),
    (_err(anthropic.InternalServerError, 500), "busy"),
])
def test_errors_map_onto_failover_rules(monkeypatch, error, expect):
    install(monkeypatch, [error])
    with pytest.raises(llm._ProviderFailure) as exc:
        claude_provider.call(claude_only()[0], [{"role": "user", "content": "Q?"}], None)
    f = exc.value
    assert {"rate": f.rate_limited and f.wait_s == 7, "bad_key": f.bad_key, "busy": f.busy}[expect]


def test_rate_limited_claude_fails_over_to_groq_and_user_never_sees_internals(monkeypatch):
    install(monkeypatch, [_err(anthropic.RateLimitError, 429, {"retry-after": "30"})])
    providers = llm.load_providers({"ANTHROPIC_API_KEY": "a", "GROQ_API_KEY": "g"})
    groq_reply = SimpleNamespace(status_code=200, headers={}, json=lambda: {
        "choices": [{"message": {"content": "from groq"}}], "usage": {}})
    resp = llm.ChatClient(providers, post=lambda *a, **k: groq_reply, sleep=lambda s: None).complete([])
    assert resp.provider == "groq" and resp.content == "from groq"


def test_refusal_moves_to_the_next_provider(monkeypatch):
    install(monkeypatch, [message([], "refusal")])
    with pytest.raises(llm.LLMError) as exc:
        llm.ChatClient(claude_only(), sleep=lambda s: None).complete([{"role": "user", "content": "Q?"}])
    assert str(exc.value) == llm.BUSY_MESSAGE and "declined" in exc.value.details
