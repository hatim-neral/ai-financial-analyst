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
    return llm.load_providers({"GROQ_API_KEY": "g-key", "GEMINI_API_KEY": "m-key"})


def test_load_providers_order_and_defaults():
    providers = both()
    assert [p.name for p in providers] == ["groq", "gemini"]
    assert providers[0].model == "llama-3.3-70b-versatile"
    swapped = llm.load_providers({"LLM_PROVIDER": "gemini", "GROQ_API_KEY": "g", "GEMINI_API_KEY": "m",
                                  "GEMINI_MODEL": "gemini-x"})
    assert [p.name for p in swapped] == ["gemini", "groq"] and swapped[0].model == "gemini-x"
    assert llm.load_providers({}) == []


def test_load_providers_tolerates_broken_secrets_source():
    class Broken:
        def get(self, key):
            raise FileNotFoundError("no secrets.toml")

    providers = llm.load_providers({"GROQ_API_KEY": "g"}, Broken())
    assert [p.name for p in providers] == ["groq"]


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
    msg = str(exc.value)
    assert "API key rejected" in msg and "g-key" not in msg and "m-key" not in msg


def test_timeouts_and_network_errors():
    post = Recorder([requests.Timeout(), requests.ConnectionError(), ok("late")])
    resp = llm.ChatClient(both(), post=post, sleep=lambda s: None).complete([])
    assert resp.provider == "gemini"


def test_dict_arguments_are_serialised():
    post = Recorder([ok(tool_calls=[{"function": {"name": "t", "arguments": {"month": "2026-03"}}}])])
    resp = llm.ChatClient(both(), post=post, sleep=lambda s: None).complete([])
    assert json.loads(resp.tool_calls[0].arguments) == {"month": "2026-03"} and resp.tool_calls[0].id == "call_0"
