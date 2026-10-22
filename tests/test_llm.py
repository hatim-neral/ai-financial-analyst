import json

import pytest
import requests

from fin_analyst import llm


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


def ok(content=None, tool_calls=None):
    msg = {"content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return Resp(200, {"choices": [{"message": msg}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


class Recorder:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []
        self.bodies = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.urls.append(url)
        self.bodies.append(json)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def both():
    # One Gemini model keeps these failover tests to two entries.
    return llm.load_providers({"GROQ_API_KEY": "g-key", "GROQ_MODEL": "openai/gpt-oss-120b",
                               "GEMINI_API_KEY": "m-key", "GEMINI_MODEL": "gemini-3.5-flash"})


def test_load_providers_order_and_defaults():
    providers = both()
    assert [p.name for p in providers] == ["groq", "gemini"]
    assert providers[0].model == "openai/gpt-oss-120b"
    # by default Groq brings two models (separate free daily limits), the larger first
    default = llm.load_providers({"GROQ_API_KEY": "g"})
    assert [p.key for p in default] == ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b"]
    swapped = llm.load_providers({"LLM_PROVIDER": "gemini", "GROQ_API_KEY": "g", "GEMINI_API_KEY": "m",
                                  "GEMINI_MODEL": "gemini-x"})
    assert [p.name for p in swapped] == ["gemini", "groq", "groq"] and swapped[0].model == "gemini-x"
    assert llm.load_providers({}) == []


def test_load_providers_tolerates_broken_secrets_source():
    class Broken:
        def get(self, key):
            raise FileNotFoundError("no secrets.toml")

    providers = llm.load_providers({"GROQ_API_KEY": "g"}, Broken())
    assert {p.name for p in providers} == {"groq"}


def test_api_key_not_in_repr():
    assert "g-key" not in repr(both()[0])


def test_parses_tool_calls_and_usage():
    post = Recorder([ok(tool_calls=[{"id": "abc", "type": "function",
                                     "function": {"name": "get_period_summary", "arguments": "{}"}}])])
    client = llm.ChatClient(both(), post=post, sleep=lambda s: None)
    resp = client.complete([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    assert resp.tool_calls[0].name == "get_period_summary" and resp.tool_calls[0].id == "abc"
    assert resp.usage == {"prompt_tokens": 10, "completion_tokens": 5} and resp.provider == "groq"
    assert post.bodies[0]["temperature"] == 0 and post.bodies[0]["tool_choice"] == "auto"
    assert resp.assistant_message()["tool_calls"][0]["function"]["name"] == "get_period_summary"


def test_rate_limit_falls_back_to_second_provider():
    post = Recorder([Resp(429), ok("hello")])
    resp = llm.ChatClient(both(), post=post, sleep=lambda s: None).complete([])
    assert resp.provider == "gemini" and resp.content == "hello"
    assert "api.groq.com" in post.urls[0] and "generativelanguage.googleapis.com" in post.urls[1]


def test_bad_request_is_retried_once_on_same_provider():
    post = Recorder([Resp(400), ok("fine")])
    resp = llm.ChatClient(both(), post=post, sleep=lambda s: None).complete([])
    assert resp.provider == "groq" and len(post.urls) == 2


def test_all_providers_failing_raises_safe_error():
    post = Recorder([Resp(401), Resp(500), Resp(500)])
    with pytest.raises(llm.LLMError) as exc:
        llm.ChatClient(both(), post=post, sleep=lambda s: None).complete([])
    msg, details = str(exc.value), exc.value.details
    assert msg == llm.BUSY_MESSAGE  # users see one plain sentence, never provider internals
    assert "API key rejected" in details and "g-key" not in details + msg and "m-key" not in details + msg


def test_timeouts_and_network_errors():
    post = Recorder([requests.Timeout(), requests.ConnectionError(), ok("late")])
    resp = llm.ChatClient(both(), post=post, sleep=lambda s: None).complete([])
    assert resp.provider == "gemini"


def test_dict_arguments_are_serialised():
    post = Recorder([ok(tool_calls=[{"function": {"name": "t", "arguments": {"month": "2026-03"}}}])])
    resp = llm.ChatClient(both(), post=post, sleep=lambda s: None).complete([])
    assert json.loads(resp.tool_calls[0].arguments) == {"month": "2026-03"} and resp.tool_calls[0].id == "call_0"


class LimitedResp(Resp):
    def __init__(self, message):
        super().__init__(429, {"error": {"message": message}})


def test_short_rate_limit_switches_to_next_provider_without_waiting():
    sleeps = []
    post = Recorder([LimitedResp("Rate limit reached ... Please try again in 1.3125s."), ok("from gemini")])
    resp = llm.ChatClient(both(), post=post, sleep=sleeps.append).complete([])
    assert resp.provider == "gemini" and sleeps == []


def test_single_provider_waits_out_a_short_rate_limit():
    sleeps, now = [], [0.0]
    groq = llm.load_providers({"GROQ_API_KEY": "g", "GROQ_MODEL": "openai/gpt-oss-120b"})
    post = Recorder([LimitedResp("Please try again in 1.3125s."), ok("after wait")])

    def sleep(s):
        sleeps.append(s)
        now[0] += s

    resp = llm.ChatClient(groq, post=post, sleep=sleep, clock=lambda: now[0]).complete([])
    assert resp.content == "after wait" and len(sleeps) == 1 and 1.3 < sleeps[0] < 2


def test_cooldown_is_remembered_across_calls():
    now = [0.0]
    post = Recorder([LimitedResp("try again in 10s"), ok("gemini 1"), ok("gemini 2")])
    client = llm.ChatClient(both(), post=post, sleep=lambda s: None, clock=lambda: now[0])
    client.complete([])
    client.complete([])  # groq still cooling down: goes straight to gemini
    assert [u.split("/")[2] for u in post.urls] == ["api.groq.com", "generativelanguage.googleapis.com",
                                                    "generativelanguage.googleapis.com"]


def test_all_providers_are_supported_in_order_and_gemini_rotates_models():
    providers = llm.load_providers({"GROQ_API_KEY": "g", "CEREBRAS_API_KEY": "c", "MISTRAL_API_KEY": "s",
                                    "GEMINI_API_KEY": "m", "NVIDIA_API_KEY": "n", "HF_TOKEN": "h",
                                    "OPENROUTER_API_KEY": "o"})
    assert [p.key for p in providers] == [
        "groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b", "cerebras:gpt-oss-120b", "mistral:mistral-small-latest",
        "gemini:gemini-3.5-flash-lite", "gemini:gemini-3.5-flash", "nvidia:moonshotai/kimi-k2.6",
        "huggingface:openai/gpt-oss-120b", "openrouter:nvidia/nemotron-3-super-120b-a12b:free"]
    assert providers[3].base_url == "https://api.mistral.ai/v1"
    assert providers[6].base_url == "https://integrate.api.nvidia.com/v1"


def test_model_lists_become_separate_entries():
    providers = llm.load_providers({"GROQ_API_KEY": "g", "GROQ_MODEL": "a, b ,c"})
    assert [p.model for p in providers] == ["a", "b", "c"] and len({p.key for p in providers}) == 3


def test_daily_quota_on_one_gemini_model_moves_to_the_next_model():
    quota = Resp(429, [{"error": {"message": "Quota exceeded ... Please retry in 16h59m33.79s.", "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "61173s"}]}}])
    sleeps = []
    post = Recorder([quota, ok("from flash")])
    gem = llm.load_providers({"GEMINI_API_KEY": "m"})
    resp = llm.ChatClient(gem, post=post, sleep=sleeps.append).complete([])
    assert resp.model == "gemini-3.5-flash" and sleeps == []
    assert '"model": "gemini-3.5-flash-lite"' in str(post.bodies[0]).replace("'", '"')


def test_wait_parsing_understands_hours_retry_and_retryinfo():
    assert llm._parse_duration("16h59m33.5s") == pytest.approx(61173.5)
    assert llm._rate_limit_wait(LimitedResp("Please retry in 2m5s.")) == pytest.approx(125)
    assert llm._rate_limit_wait(LimitedResp("try again in 1.3125s")) == pytest.approx(1.3125)
    info = Resp(429, [{"error": {"message": "x", "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "61173s"}]}}])
    assert llm._rate_limit_wait(info) == pytest.approx(61173)


def test_long_quota_is_not_waited_out_and_the_user_sees_the_busy_message():
    sleeps = []
    post = Recorder([LimitedResp("Please retry in 16h59m33s.")])
    one = llm.load_providers({"GEMINI_API_KEY": "m", "GEMINI_MODEL": "gemini-3.5-flash"})
    with pytest.raises(llm.LLMError) as exc:
        llm.ChatClient(one, post=post, sleep=sleeps.append).complete([])
    assert sleeps == [] and len(post.urls) == 1 and str(exc.value) == llm.BUSY_MESSAGE


def test_busy_server_is_skipped_on_the_next_question():
    now = [0.0]
    post = Recorder([Resp(503), Resp(503), ok("gemini 1"), ok("gemini 2")])
    client = llm.ChatClient(both(), post=post, sleep=lambda s: None, clock=lambda: now[0])
    client.complete([])
    client.complete([])  # groq is still cooling down after its 503s
    assert [u.split("/")[2] for u in post.urls].count("api.groq.com") == 2


def test_mistral_gets_nine_character_tool_call_ids():
    msgs = [{"role": "assistant", "content": None,
             "tool_calls": [{"id": "fc_7d1f9a2b-long-groq-id", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "fc_7d1f9a2b-long-groq-id", "content": "{}"}]
    out = llm._messages_for("mistral", msgs)
    new_id = out[0]["tool_calls"][0]["id"]
    assert len(new_id) == 9 and new_id.isalnum() and out[1]["tool_call_id"] == new_id
    assert llm._messages_for("groq", msgs)[0]["tool_calls"][0]["id"] == "fc_7d1f9a2b-long-groq-id"

def test_long_rate_limit_falls_back_instead_of_waiting():
    sleeps = []
    post = Recorder([LimitedResp("Please try again in 7m12s."), ok("from gemini")])
    resp = llm.ChatClient(both(), post=post, sleep=sleeps.append).complete([])
    assert resp.provider == "gemini" and sleeps == []


def test_rate_limit_wait_parses_milliseconds():
    assert llm._rate_limit_wait(LimitedResp("try again in 850ms")) == pytest.approx(0.85)


def test_gemini_thought_signature_is_echoed_only_to_gemini():
    sig = {"google": {"thought_signature": "abc"}}
    post = Recorder([ok(tool_calls=[{"id": "t1", "function": {"name": "f", "arguments": "{}"}, "extra_content": sig}])])
    gem = llm.load_providers({"GEMINI_API_KEY": "m"})
    resp = llm.ChatClient(gem, post=post, sleep=lambda s: None).complete([])
    msg = resp.assistant_message()
    assert msg["tool_calls"][0]["extra_content"] == sig
    to_gemini = llm._messages_for("gemini", [msg])[0]["tool_calls"][0]
    to_groq = llm._messages_for("groq", [msg])[0]["tool_calls"][0]
    assert to_gemini["extra_content"] == sig and "extra_content" not in to_groq


def test_tool_calls_from_other_providers_get_geminis_skip_signature():
    msg = {"role": "assistant", "content": None,
           "tool_calls": [{"id": "x", "type": "function", "function": {"name": "f", "arguments": "{}"}}]}
    fixed = llm._messages_for("gemini", [msg])[0]["tool_calls"][0]
    assert fixed["extra_content"]["google"]["thought_signature"] == "skip_thought_signature_validator"
