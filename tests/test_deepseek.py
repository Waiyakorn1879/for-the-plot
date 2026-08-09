"""DeepSeek preset + the reasoning-token exhaustion safeguards.

Background: DeepSeek V4 enables thinking mode by default, reasoning tokens
count against `max_tokens`, and thinking mode rejects `temperature`. A large
prompt could therefore burn the whole budget on a chain of thought and return
an EMPTY answer — which previously looked like an unparseable reply.
"""
import json

import pytest

import translate_api


def fake_response(content=None, finish="stop", reasoning=None,
                  reasoning_tokens=0, completion_tokens=0):
    message = {"content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {
            "completion_tokens": completion_tokens,
            "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
        },
    }


def install_transport(monkeypatch, responses):
    """Fake urlopen; returns the list that captures each request sent."""
    import urllib.request
    sent = []
    queue = list(responses)

    class FakeResp:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def fake_urlopen(req, timeout=None):
        sent.append({"url": req.full_url,
                     "headers": dict(req.headers),
                     "body": json.loads(req.data.decode())})
        return FakeResp(queue.pop(0))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    return sent


class TestReadCompletion:
    """An empty answer must never come back as an empty string: the caller
    would hand it on as a translation-shaped nothing."""

    def test_normal_reply(self):
        content, problem = translate_api.read_completion(fake_response("[]"))
        assert content == "[]" and problem is None

    def test_reasoning_exhaustion_named_specifically(self):
        content, problem = translate_api.read_completion(fake_response(
            "", finish="length", reasoning="thinking...",
            reasoning_tokens=2000, completion_tokens=2048))
        assert content is None
        assert problem["truncated"] is True
        assert "2000 reasoning" in problem["message"]
        assert "api.thinking = false" in problem["message"]

    def test_plain_truncation_distinguished_from_reasoning(self):
        _, problem = translate_api.read_completion(fake_response(
            "", finish="length", completion_tokens=8192))
        assert problem["truncated"] is True
        assert "reasoning" not in problem["message"]
        assert "batch_size" in problem["message"]

    def test_reasoning_content_is_never_the_answer(self):
        content, problem = translate_api.read_completion(fake_response(
            "", finish="stop", reasoning="I should translate these..."))
        assert content is None
        assert "only reasoning_content" in problem["message"]

    def test_content_filter_named_and_not_retryable(self):
        _, problem = translate_api.read_completion(
            fake_response("", finish="content_filter"))
        assert problem["truncated"] is False
        assert "content filter" in problem["message"]

    def test_null_content(self):
        content, problem = translate_api.read_completion(
            fake_response(None, finish="stop"))
        assert content is None and problem is not None

    def test_whitespace_only_counts_as_empty(self):
        content, problem = translate_api.read_completion(fake_response("  \n "))
        assert content is None and problem is not None


class TestDeepSeekPreset:
    def test_registered(self):
        assert "deepseek" in translate_api.PROVIDERS

    def test_preset_defaults(self, monkeypatch):
        sent = install_transport(monkeypatch, [fake_response("[]")])
        call = translate_api.make_call_model({"api": {"provider": "deepseek"}})
        assert call("SYS", "USER") == "[]"
        assert sent[0]["url"] == "https://api.deepseek.com/chat/completions"
        assert sent[0]["headers"]["Authorization"] == "Bearer sk-ds"
        assert sent[0]["body"]["model"] == "deepseek-v4-flash"

    def test_thinking_off_by_default_so_temperature_applies(self, monkeypatch):
        sent = install_transport(monkeypatch, [fake_response("[]")])
        translate_api.make_call_model({"api": {"provider": "deepseek"}})("S", "U")
        body = sent[0]["body"]
        assert body["thinking"] == {"type": "disabled"}
        assert body["temperature"] == 0.3
        assert "reasoning_effort" not in body

    def test_thinking_opt_in_omits_temperature(self, monkeypatch):
        """Thinking mode rejects temperature; sending it would be discarded."""
        sent = install_transport(monkeypatch, [fake_response("[]")])
        translate_api.make_call_model(
            {"api": {"provider": "deepseek", "thinking": True,
                     "reasoning_effort": "max"}})("S", "U")
        body = sent[0]["body"]
        assert body["thinking"] == {"type": "enabled"}
        assert body["reasoning_effort"] == "max"
        assert "temperature" not in body

    def test_model_selection(self, monkeypatch):
        sent = install_transport(monkeypatch, [fake_response("[]")])
        translate_api.make_call_model(
            {"api": {"provider": "deepseek", "model": "deepseek-v4-pro"}})("S", "U")
        assert sent[0]["body"]["model"] == "deepseek-v4-pro"

    def test_retired_alias_warns_but_still_sends(self, monkeypatch, capsys):
        sent = install_transport(monkeypatch, [fake_response("[]")])
        call = translate_api.make_call_model(
            {"api": {"provider": "deepseek", "model": "deepseek-reasoner"}})
        out = capsys.readouterr().out
        assert "retired" in out and "2026-07-24" in out
        call("S", "U")
        assert sent[0]["body"]["model"] == "deepseek-reasoner"

    def test_profile_overrides_preset(self, monkeypatch):
        sent = install_transport(monkeypatch, [fake_response("[]")])
        monkeypatch.setenv("MY_KEY", "sk-other")
        translate_api.make_call_model(
            {"api": {"provider": "deepseek", "api_key_env": "MY_KEY",
                     "base_url": "https://proxy.example/v1"}})("S", "U")
        assert sent[0]["url"] == "https://proxy.example/v1/chat/completions"
        assert sent[0]["headers"]["Authorization"] == "Bearer sk-other"

    def test_missing_key_exits(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(SystemExit) as excinfo:
            translate_api.make_call_model({"api": {"provider": "deepseek"}})
        assert "DEEPSEEK_API_KEY" in str(excinfo.value)

    def test_generic_provider_sends_no_thinking_key(self, monkeypatch):
        """`thinking` is DeepSeek-specific; OpenAI/Ollama would 400 on it."""
        sent = install_transport(monkeypatch, [fake_response("[]")])
        monkeypatch.setenv("OPENAI_API_KEY", "sk-o")
        translate_api.make_call_model(
            {"api": {"provider": "openai-compatible"}})("S", "U")
        assert "thinking" not in sent[0]["body"]
        assert sent[0]["body"]["temperature"] == 0.3


class TestMaxTokenEscalation:
    TRUNCATED = staticmethod(lambda: fake_response(
        "", finish="length", reasoning="...", reasoning_tokens=990,
        completion_tokens=1000))

    def call_with(self, monkeypatch, responses, api=None):
        sent = install_transport(monkeypatch, responses)
        profile = {"api": dict({"provider": "deepseek", "max_tokens": 1000},
                               **(api or {}))}
        return sent, translate_api.make_call_model(profile)

    def test_escalates_once_then_succeeds(self, monkeypatch):
        sent, call = self.call_with(
            monkeypatch, [self.TRUNCATED(), fake_response("[]")])
        assert call("SYS", "USER") == "[]"
        assert [r["body"]["max_tokens"] for r in sent] == [1000, 4000]

    def test_learned_budget_persists_across_calls(self, monkeypatch):
        """The run pays the discovery cost once, not once per batch."""
        sent, call = self.call_with(monkeypatch, [
            self.TRUNCATED(), fake_response("[]"), fake_response("[]")])
        call("SYS", "USER")          # discovers 1000 is too small
        call("SYS", "USER")          # must start from the learned value
        assert [r["body"]["max_tokens"] for r in sent] == [1000, 4000, 4000]

    def test_no_escalation_once_the_ceiling_is_reached(self, monkeypatch):
        sent, call = self.call_with(
            monkeypatch, [fake_response("", finish="length", completion_tokens=1)],
            api={"max_tokens": translate_api.MAX_TOKEN_CEILING})
        with pytest.raises(RuntimeError):
            call("SYS", "USER")
        assert len(sent) == 1, "already at the cap — retrying identically is waste"

    def test_raises_rather_than_returning_empty(self, monkeypatch):
        sent, call = self.call_with(
            monkeypatch, [self.TRUNCATED(), self.TRUNCATED()])
        with pytest.raises(RuntimeError, match="reasoning"):
            call("SYS", "USER")
        assert len(sent) == 2, "escalates exactly once, then gives up"

    def test_no_escalation_for_non_budget_failures(self, monkeypatch):
        sent, call = self.call_with(
            monkeypatch, [fake_response("", finish="content_filter")])
        with pytest.raises(RuntimeError, match="content filter"):
            call("SYS", "USER")
        assert len(sent) == 1, "a filtered reply must not be retried"

    def test_escalation_can_be_disabled(self, monkeypatch):
        sent, call = self.call_with(
            monkeypatch, [fake_response("", finish="length", completion_tokens=1000)],
            api={"escalate_max_tokens": False})
        with pytest.raises(RuntimeError):
            call("SYS", "USER")
        assert len(sent) == 1

    def test_escalation_is_capped(self, monkeypatch):
        sent, call = self.call_with(
            monkeypatch,
            [fake_response("", finish="length", completion_tokens=99),
             fake_response("[]")],
            api={"max_tokens": 60000})
        call("SYS", "USER")
        assert sent[1]["body"]["max_tokens"] == translate_api.MAX_TOKEN_CEILING


class TestNothingEmptyIsEverSaved:
    """End-to-end: a model that only ever returns empty must leave the
    progress store and the Translation Memory untouched."""

    def test_exhausted_batch_saves_nothing(self, tmp_path, monkeypatch):
        (tmp_path / "strings.json").write_text(json.dumps(
            [{"text": "Hello.", "speaker": "hero", "file": "a.rpy",
              "line": 1, "kind": "say"}]), encoding="utf-8")
        (tmp_path / "profile.json").write_text(json.dumps({
            "game_name": "T", "language_id": "thai", "language_name": "Thai",
            "strings_file": "strings.json", "progress_file": "tr.json",
            "speakers": {"hero": {"name": "Hero"}},
            "api": {"provider": "deepseek", "max_tokens": 100},
        }), encoding="utf-8")

        install_transport(monkeypatch, [self_truncated() for _ in range(8)])
        monkeypatch.setattr(translate_api.time, "sleep", lambda *_: None)
        monkeypatch.setattr(translate_api.sys, "argv",
                            ["x", "--profile", str(tmp_path / "profile.json")])
        translate_api.main()

        # Nothing translated, so the progress file is either absent or empty —
        # what must never happen is an entry mapping the source to "".
        tr = tmp_path / "tr.json"
        if tr.exists():
            assert json.loads(tr.read_text(encoding="utf-8")) == {}
        tm = tmp_path / ".ftp" / "translation_memory.json"
        if tm.exists():
            assert json.loads(tm.read_text(encoding="utf-8"))["entries"] == {}


def self_truncated():
    return fake_response("", finish="length", reasoning="...",
                         reasoning_tokens=95, completion_tokens=100)
