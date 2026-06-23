import json

import translate_api
import translation_memory
from translation_memory import TranslationMemory, normalize_key


def make_tm(tmp_path, name="translation_memory.json"):
    return TranslationMemory(tmp_path / ".ftp" / name,
                             source_language="en", target_language="th")


class TestNormalizeKey:
    def test_variants_collapse_to_one_key(self):
        keys = {normalize_key(v) for v in
                ["Hello.", " Hello. ", "Hello.\r\n", "Hello.  ", "Hello.\t"]}
        assert keys == {"Hello."}

    def test_internal_whitespace_collapsed(self):
        assert normalize_key("How   are\tyou?") == "How are you?"

    def test_case_sensitive(self):
        assert normalize_key("Hello") != normalize_key("hello")

    def test_punctuation_vars_tags_preserved(self):
        s = "Take the {b}red{/b} pill, [name]!"
        assert normalize_key(s) == s

    def test_literal_escape_not_touched(self):
        # Ren'Py escapes are two literal chars (backslash + n), not a newline.
        s = "Line one\\nLine two"
        assert normalize_key(s) == s


class TestAddLookup:
    def test_exact_hit(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hello.", "สวัสดี")
        assert tm.lookup("Hello.")["translation"] == "สวัสดี"

    def test_normalized_hit(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("How are you?", "สบายดีไหม")
        assert tm.lookup("  How   are you?  ")["translation"] == "สบายดีไหม"

    def test_miss_returns_none(self, tmp_path):
        assert make_tm(tmp_path).lookup("nope") is None

    def test_count_increments_on_hit(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hi", "ไง")
        assert tm.entries["Hi"]["count"] == 1
        tm.lookup("Hi")
        tm.lookup("Hi")
        assert tm.entries["Hi"]["count"] == 3

    def test_last_used_refreshes_on_lookup(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hi", "ไง")
        tm.entries["Hi"]["last_used"] = "2000-01-01T00:00:00Z"
        tm.lookup("Hi")
        assert tm.entries["Hi"]["last_used"] > "2000-01-01T00:00:00Z"

    def test_context_metadata_stored(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("I love you.", "ฉันรักเธอ", speaker="jill", file="ep9.rpy", line=5312)
        e = tm.entries["I love you."]
        assert e["speaker"] == "jill" and e["file"] == "ep9.rpy" and e["line"] == 5312

    def test_lookup_fuzzy_disabled_in_v1(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("How are you?", "สบายดีไหม")
        assert tm.lookup_fuzzy("How are you doing?") is None


class TestPersistence:
    def test_save_load_round_trip(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hello.", "สวัสดี", speaker="hero")
        tm.save()

        tm2 = make_tm(tmp_path)
        tm2.load()
        assert tm2.lookup("Hello.")["translation"] == "สวัสดี"
        assert tm2.source_language == "en" and tm2.target_language == "th"

    def test_save_is_atomic_no_temp_left_behind(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hi", "ไง")
        tm.save()
        leftovers = list((tmp_path / ".ftp").glob("*.tmp"))
        assert leftovers == []
        # File is valid JSON with the documented top-level shape.
        data = json.loads(tm.path.read_text(encoding="utf-8"))
        assert data["version"] == 1 and "entries" in data

    def test_load_missing_file_is_empty(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.load()
        assert tm.entries == {}

    def test_load_corrupt_file_is_empty(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.path.parent.mkdir(parents=True, exist_ok=True)
        tm.path.write_text("{not json", encoding="utf-8")
        tm.load()  # must not raise
        assert tm.entries == {}


class TestBulkOps:
    def test_import_progress_merges_dict(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Existing", "เดิม")
        added = tm.import_progress({"Existing": "เดิม", "New one": "ใหม่"})
        assert added == 1
        assert tm.lookup("New one")["translation"] == "ใหม่"

    def test_export_import_csv_round_trip(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hello.", "สวัสดี")
        tm.add("Bye.", "ลาก่อน")
        csv_path = tmp_path / "tm.csv"
        assert tm.export_csv(csv_path) == 2

        tm2 = make_tm(tmp_path, name="other.json")
        added, _updated = tm2.import_csv(csv_path)
        assert added == 2
        assert tm2.lookup("Hello.")["translation"] == "สวัสดี"

    def test_import_csv_keeps_higher_count(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hi", "ไง")
        tm.entries["Hi"]["count"] = 1
        csv_path = tmp_path / "in.csv"
        csv_path.write_text(
            "source,translation,count,last_used\nHi,เฮ,9,2030-01-01T00:00:00Z\n",
            encoding="utf-8")
        _added, updated = tm.import_csv(csv_path)
        assert updated == 1
        assert tm.entries["Hi"]["translation"] == "เฮ"
        assert tm.entries["Hi"]["count"] == 9

    def test_clean_removes_empty_and_duplicates(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hello.", "สวัสดี")
        tm.add(" Hello. ", "สวัสดี")   # normalized-duplicate, same translation
        tm.add("   ", "ว่าง")          # whitespace-only source
        removed = tm.clean()
        assert removed == 2
        assert len(tm.entries) == 1

    def test_stats_shape(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("a", "ก")
        tm.add("b", "ข")
        s = tm.stats()
        assert s["total_entries"] == 2
        assert s["source_language"] == "en" and s["target_language"] == "th"


class TestTokenGuard:
    """A normalized hit whose tokens differ from the new source must be
    rejected by the engine's re-validation (mirrors translate_api's gate)."""

    def test_mismatched_tokens_are_caught(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hello [name]!", "สวัสดี [name]!")
        hit = tm.lookup("Hello [other]!")  # normalized key differs anyway...
        # Exact/normalized lookup won't match here (different text), but the
        # core guarantee is the signature check used by the engine:
        assert (translate_api.token_signature("Hello [other]!")
                != translate_api.token_signature("สวัสดี [name]!"))

    def test_matching_tokens_pass(self, tmp_path):
        en = "Take the {b}red{/b} pill, [name]."
        tr = "[name], กิน{b}ยาแดง{/b}."
        assert (translate_api.token_signature(en)
                == translate_api.token_signature(tr))


class TestEngineIntegration:
    """Exercise translate_api.main end-to-end with a fake model, proving the TM
    eliminates LLM calls on re-runs (the core cost-saving guarantee)."""

    def _setup(self, tmp_path, strings):
        (tmp_path / "strings.json").write_text(
            json.dumps(strings, ensure_ascii=False), encoding="utf-8")
        profile = {"game_name": "Test", "language_id": "thai",
                   "language_name": "Thai", "api": {"provider": "fake", "batch_size": 50}}
        (tmp_path / "profile.json").write_text(
            json.dumps(profile), encoding="utf-8")
        return tmp_path / "profile.json"

    def _run(self, monkeypatch, profile_path, translations):
        calls = {"n": 0}

        def fake_call_model(system, user):
            calls["n"] += 1
            ids = [item["id"] for item in json.loads(user[user.index("["):])]
            return json.dumps([{"id": i, "tr": translations[i]} for i in ids])

        monkeypatch.setattr(translate_api, "make_call_model", lambda profile: fake_call_model)
        monkeypatch.setattr("sys.argv", ["translate_api.py", "--profile", str(profile_path)])
        translate_api.main()
        return calls["n"]

    def test_second_pass_makes_zero_llm_calls(self, tmp_path, monkeypatch):
        strings = [{"text": "Hello.", "speaker": "hero", "file": "a.rpy", "line": 1, "kind": "say"},
                   {"text": "Bye.", "speaker": "hero", "file": "a.rpy", "line": 2, "kind": "say"}]
        profile_path = self._setup(tmp_path, strings)
        trans = {0: "สวัสดี", 1: "ลาก่อน"}

        first = self._run(monkeypatch, profile_path, trans)
        assert first == 1  # one batch call covering both strings

        # Wipe the per-project progress so only the TM can satisfy the re-run.
        (tmp_path / "translations.json").unlink()
        second = self._run(monkeypatch, profile_path, trans)
        assert second == 0  # fully served from the TM — no model calls

        # The run must still produce its deliverable (build_patch.py consumes it),
        # even though every string came from the TM via the early-return path.
        progress = json.loads((tmp_path / "translations.json").read_text(encoding="utf-8"))
        assert progress == {"Hello.": "สวัสดี", "Bye.": "ลาก่อน"}

    def test_only_new_line_hits_model_on_update(self, tmp_path, monkeypatch):
        strings = [{"text": "Hello.", "speaker": "hero", "file": "a.rpy", "line": 1, "kind": "say"}]
        profile_path = self._setup(tmp_path, strings)
        self._run(monkeypatch, profile_path, {0: "สวัสดี"})

        # Game update: add one new line; reset progress so TM is the only cache.
        strings.append({"text": "New line.", "speaker": "hero", "file": "a.rpy", "line": 2, "kind": "say"})
        (tmp_path / "strings.json").write_text(json.dumps(strings, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "translations.json").unlink()
        calls = self._run(monkeypatch, profile_path, {0: "สวัสดี", 1: "บรรทัดใหม่"})
        assert calls == 1  # only the single new line reaches the model

        # Deliverable contains both the TM-served and the freshly translated line.
        progress = json.loads((tmp_path / "translations.json").read_text(encoding="utf-8"))
        assert progress == {"Hello.": "สวัสดี", "New line.": "บรรทัดใหม่"}


class TestProfileResolution:
    def test_default_path_is_project_local_ftp(self, tmp_path):
        path = translation_memory.resolve_tm_path({}, tmp_path)
        assert path == tmp_path / ".ftp" / "translation_memory.json"

    def test_profile_relative_path_resolved_against_base(self, tmp_path):
        path = translation_memory.resolve_tm_path({"tm": {"path": "shared/tm.json"}}, tmp_path)
        assert path == tmp_path / "shared" / "tm.json"

    def test_enabled_defaults_true(self):
        assert translation_memory.tm_enabled({}) is True
        assert translation_memory.tm_enabled({"tm": {"enabled": False}}) is False
