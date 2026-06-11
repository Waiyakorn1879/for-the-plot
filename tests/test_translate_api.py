import json

import translate_api


class TestTokenSignature:
    def test_equal_when_tokens_match(self):
        en = "Take the {b}red{/b} pill, [name]."
        tr = "[name], πάρε το {b}κόκκινο{/b} χάπι."
        assert translate_api.token_signature(en) == translate_api.token_signature(tr)

    def test_missing_var_detected(self):
        assert translate_api.token_signature("Hi [name]") != \
            translate_api.token_signature("Hi")

    def test_missing_tag_detected(self):
        assert translate_api.token_signature("{i}soft{/i}") != \
            translate_api.token_signature("{i}soft")

    def test_escape_detected(self):
        assert translate_api.token_signature("line\\nbreak") != \
            translate_api.token_signature("line break")

    def test_order_insensitive_but_count_sensitive(self):
        assert translate_api.token_signature("[a] [b]") == \
            translate_api.token_signature("[b] [a]")
        assert translate_api.token_signature("[a] [a]") != \
            translate_api.token_signature("[a]")


class TestTranslateBatch:
    BATCH = [
        {"id": 0, "text": "Hello!", "speaker": "hero", "kind": "say"},
        {"id": 1, "text": "Bye!", "speaker": "hero", "kind": "say"},
    ]
    SPEAKERS = {"hero": {"name": "Hero", "gender": "male", "role": "protagonist"}}

    def test_plain_json_reply(self):
        def fake(system, user):
            assert "Hello!" in user
            return json.dumps([{"id": 0, "tr": "Salut !"}, {"id": 1, "tr": "Ciao !"}])
        result = translate_api.translate_batch(fake, "sys", self.SPEAKERS,
                                               "French", self.BATCH)
        assert result == [{"id": 0, "tr": "Salut !"}, {"id": 1, "tr": "Ciao !"}]

    def test_fenced_reply_stripped(self):
        def fake(system, user):
            return "```json\n[{\"id\": 0, \"tr\": \"Salut !\"}]\n```"
        result = translate_api.translate_batch(fake, "sys", self.SPEAKERS,
                                               "French", self.BATCH)
        assert result == [{"id": 0, "tr": "Salut !"}]

    def test_garbage_reply_returns_empty(self):
        result = translate_api.translate_batch(lambda s, u: "not json at all",
                                               "sys", self.SPEAKERS, "French", self.BATCH)
        assert result == []

    def test_retry_flag_adds_warning(self):
        seen = {}
        def fake(system, user):
            seen["user"] = user
            return "[]"
        translate_api.translate_batch(fake, "sys", self.SPEAKERS, "French",
                                      self.BATCH, retry=True)
        assert "mismatched Ren'Py tokens" in seen["user"]


class TestSystemInstruction:
    def test_includes_profile_pieces(self, tmp_path):
        (tmp_path / "guide.md").write_text("REGISTER GUIDE BODY", encoding="utf-8")
        profile = {"game_name": "Pocket Cafe", "language_name": "French",
                   "keep_untranslated": ["Espresso", "Latte"],
                   "style_guide_file": "guide.md"}
        out = translate_api.build_system_instruction(profile, tmp_path)
        assert "Pocket Cafe" in out and "French" in out
        assert "Espresso, Latte" in out
        assert "REGISTER GUIDE BODY" in out
        assert "TOKEN PRESERVATION" in out


class TestProviderRegistry:
    def test_known_providers_registered(self):
        assert set(translate_api.PROVIDERS) >= {"gemini", "anthropic", "claude-cli"}
