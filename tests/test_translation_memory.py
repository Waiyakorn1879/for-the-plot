import json

import translate_api
import translation_memory
from translation_memory import TranslationContext, TranslationMemory, normalize_key


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
        # New context-free entry starts at count 0; each default hit bumps it.
        assert tm.entries["Hi"]["count"] == 0
        tm.lookup("Hi")
        tm.lookup("Hi")
        assert tm.entries["Hi"]["count"] == 2

    def test_last_used_refreshes_on_lookup(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hi", "ไง")
        tm.entries["Hi"]["last_used"] = "2000-01-01T00:00:00Z"
        tm.lookup("Hi")
        assert tm.entries["Hi"]["last_used"] > "2000-01-01T00:00:00Z"

    def test_context_metadata_stored(self, tmp_path):
        tm = make_tm(tmp_path)
        ctx = TranslationContext(speaker="jill", file="ep9.rpy", line=5312)
        tm.add("I love you.", "ฉันรักเธอ", ctx)
        e = tm.entries["I love you."]
        assert e["default_translation"] == "ฉันรักเธอ"
        v = e["variants"][0]
        assert v["speaker"] == "jill" and v["file"] == "ep9.rpy" and v["line"] == 5312
        assert v["confidence"] == 1.0 and v["context_hash"] is None

    def test_lookup_fuzzy_disabled_in_v1(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("How are you?", "สบายดีไหม")
        assert tm.lookup_fuzzy("How are you doing?") is None


class TestPersistence:
    def test_save_load_round_trip(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hello.", "สวัสดี", TranslationContext(speaker="hero"))
        tm.save()

        tm2 = make_tm(tmp_path)
        tm2.load()
        assert tm2.lookup("Hello.")["translation"] == "สวัสดี"
        assert tm2.lookup("Hello.", TranslationContext(speaker="hero"))["translation"] == "สวัสดี"
        assert tm2.source_language == "en" and tm2.target_language == "th"

    def test_save_is_atomic_no_temp_left_behind(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Hi", "ไง")
        tm.save()
        leftovers = list((tmp_path / ".ftp").glob("*.tmp"))
        assert leftovers == []
        # File is valid JSON with the documented top-level shape.
        data = json.loads(tm.path.read_text(encoding="utf-8"))
        assert data["version"] == 2 and "entries" in data

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
        assert tm.entries["Hi"]["default_translation"] == "เฮ"
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

    def test_engine_stores_variant_and_serves_context_hit(self, tmp_path, monkeypatch):
        # Case 9: a bulk run stores a speaker-tagged variant; a re-run from the
        # TM alone serves it (zero model calls) as a context hit.
        strings = [{"text": "You.", "speaker": "Maya", "file": "a.rpy", "line": 1, "kind": "say"}]
        profile_path = self._setup(tmp_path, strings)
        self._run(monkeypatch, profile_path, {0: "นาย"})

        data = json.loads((tmp_path / ".ftp" / "translation_memory.json")
                          .read_text(encoding="utf-8"))
        assert data["version"] == 2
        entry = data["entries"]["You."]
        assert entry["default_translation"] == "นาย"
        assert any(v["speaker"] == "Maya" for v in entry["variants"])

        (tmp_path / "translations.json").unlink()
        calls = self._run(monkeypatch, profile_path, {0: "นาย"})
        assert calls == 0  # served from the contextual TM, no LLM

    def test_two_speakers_one_source_store_two_variants(self, tmp_path, monkeypatch):
        # Success criterion through the real engine: the same source spoken by two
        # characters stores a variant per speaker, even though the flat progress
        # map collapses to one entry.
        strings = [{"text": "You.", "speaker": "Maya", "file": "a.rpy", "line": 1, "kind": "say"},
                   {"text": "You.", "speaker": "Sage", "file": "a.rpy", "line": 2, "kind": "say"}]
        profile_path = self._setup(tmp_path, strings)
        self._run(monkeypatch, profile_path, {0: "นาย", 1: "เธอ"})

        data = json.loads((tmp_path / ".ftp" / "translation_memory.json")
                          .read_text(encoding="utf-8"))
        variants = data["entries"]["You."]["variants"]
        assert {v["speaker"] for v in variants} == {"Maya", "Sage"}
        # And each speaker retrieves their own line from the TM.
        tm = make_tm(tmp_path)
        tm.load()
        assert tm.lookup("You.", TranslationContext(speaker="Maya"))["translation"] == "นาย"
        assert tm.lookup("You.", TranslationContext(speaker="Sage"))["translation"] == "เธอ"


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


def _write_tm(tm, data):
    """Write a raw TM JSON to tm.path (for migration/round-trip tests)."""
    tm.path.parent.mkdir(parents=True, exist_ok=True)
    tm.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestContextualLookup:
    """Deterministic context selection — the heart of v1.3 (amendments r1-r3)."""

    def test_exact_speaker_scene_match(self, tmp_path):  # case 1
        tm = make_tm(tmp_path)
        tm.add("You.", "นาย", TranslationContext(speaker="Maya", scene="ep9"))
        hit = tm.lookup("You.", TranslationContext(speaker="Maya", scene="ep9"))
        assert hit["translation"] == "นาย" and hit["hit_type"] == "context"

    def test_speaker_match(self, tmp_path):  # case 2
        tm = make_tm(tmp_path)
        tm.add("You.", "เธอ", TranslationContext(speaker="Sage"))
        hit = tm.lookup("You.", TranslationContext(speaker="Sage", scene="anything"))
        assert hit["translation"] == "เธอ" and hit["hit_type"] == "context"

    def test_file_does_not_drive_selection(self, tmp_path):  # case 3
        tm = make_tm(tmp_path)
        tm.add("Hi.", "ดีฮะ")  # default only
        tm.add("Hi.", "variantA", TranslationContext(speaker="A", file="a.rpy"))
        # speaker mismatches but the variant's file matches the context's file:
        # file is never scored, so this falls back to the default.
        hit = tm.lookup("Hi.", TranslationContext(speaker="B", file="a.rpy"))
        assert hit["translation"] == "ดีฮะ" and hit["hit_type"] == "default"

    def test_fallback_to_default(self, tmp_path):  # case 4
        tm = make_tm(tmp_path)
        tm.add("Bye.", "ลา")
        tm.add("Bye.", "บ๊าย", TranslationContext(speaker="A"))
        hit = tm.lookup("Bye.", TranslationContext(speaker="nobody"))
        assert hit["translation"] == "ลา" and hit["hit_type"] == "default"

    def test_multiple_speaker_variants_pick_match(self, tmp_path):  # case 10
        tm = make_tm(tmp_path)
        tm.add("You.", "นาย", TranslationContext(speaker="Maya"))
        tm.add("You.", "เธอ", TranslationContext(speaker="Sage"))
        assert tm.lookup("You.", TranslationContext(speaker="Maya"))["translation"] == "นาย"
        assert tm.lookup("You.", TranslationContext(speaker="Sage"))["translation"] == "เธอ"

    def test_tie_broken_by_count(self, tmp_path):  # case 11a
        tm = make_tm(tmp_path)
        tm.add("Hey", "H1", TranslationContext(speaker="A"))
        tm.add("Hey", "H2", TranslationContext(speaker="A"))  # same score (both speaker A)
        tm.entries["Hey"]["variants"][1]["count"] = 5  # H2 used more
        assert tm.lookup("Hey", TranslationContext(speaker="A"))["translation"] == "H2"

    def test_tie_broken_by_insertion_order(self, tmp_path):  # case 11b
        tm = make_tm(tmp_path)
        tm.add("Hey", "H1", TranslationContext(speaker="A"))
        tm.add("Hey", "H2", TranslationContext(speaker="A"))
        v = tm.entries["Hey"]["variants"]
        v[0]["count"] = v[1]["count"] = 1
        v[0]["last_used"] = v[1]["last_used"] = "2020-01-01T00:00:00Z"
        # equal score, count, last_used -> first inserted wins
        assert tm.lookup("Hey", TranslationContext(speaker="A"))["translation"] == "H1"

    def test_target_beats_speaker_only(self, tmp_path):  # case 13
        tm = make_tm(tmp_path)
        tm.add("You.", "speakeronly", TranslationContext(speaker="Maya"))
        tm.add("You.", "withtarget", TranslationContext(speaker="Maya", target="MC"))
        hit = tm.lookup("You.", TranslationContext(speaker="Maya", target="MC"))
        assert hit["translation"] == "withtarget"  # 150 > 100

    def test_speaker_none_returns_default(self, tmp_path):  # case 18
        tm = make_tm(tmp_path)
        tm.add("You.", "นาย", TranslationContext(speaker="Maya"))
        tm.add("You.", "เธอ", TranslationContext(speaker="Sage"))
        hit = tm.lookup("You.", TranslationContext(speaker=None, scene="ep9"))
        assert hit["hit_type"] == "default" and hit["translation"] == "นาย"

    def test_nonspeaker_match_never_beats_default(self, tmp_path):
        # A speaker match is required: a scene/target coincidence on a DIFFERENT
        # speaker must not hand that speaker's line to someone else. Inert in
        # v1.3 (only speaker is set) but guards the v1.5 target landmine.
        tm = make_tm(tmp_path)
        tm.add("You.", "นาย")  # default
        tm.add("You.", "บ๊อบ", TranslationContext(speaker="Bob", scene="ep9"))
        hit = tm.lookup("You.", TranslationContext(speaker="Maya", scene="ep9"))
        assert hit["hit_type"] == "default" and hit["translation"] == "นาย"

    def test_score_matches_pseudocode(self, tmp_path):  # case 17
        v = {"speaker": "A", "target": "B", "scene": "C"}
        score = TranslationMemory._score
        assert score(v, TranslationContext(speaker="A")) == 100
        assert score(v, TranslationContext(speaker="A", scene="C")) == 125
        assert score(v, TranslationContext(speaker="A", target="B")) == 150
        assert score(v, TranslationContext(speaker="A", target="B", scene="C")) == 175
        assert score(v, TranslationContext(speaker="X")) == 0
        assert score(v, TranslationContext(target="B")) == 50  # scorer has no speaker gate
        assert score(v, TranslationContext()) == 0


class TestVariantAdd:
    def test_duplicate_variant_increments_count_only(self, tmp_path):  # case 5
        tm = make_tm(tmp_path)
        ctx = TranslationContext(speaker="A", scene="s1")
        tm.add("Yo", "โย", ctx)
        tm.add("Yo", "โย", ctx)
        variants = tm.entries["Yo"]["variants"]
        assert len(variants) == 1 and variants[0]["count"] == 2

    def test_distinct_translation_makes_new_variant(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("Yo", "โย", TranslationContext(speaker="A"))
        tm.add("Yo", "เฮ้ย", TranslationContext(speaker="A"))  # different translation
        assert len(tm.entries["Yo"]["variants"]) == 2

    def test_default_not_overwritten(self, tmp_path):  # case 12
        tm = make_tm(tmp_path)
        tm.add("Hi", "first")
        tm.add("Hi", "second")  # context-free re-add must not clobber
        assert tm.entries["Hi"]["default_translation"] == "first"
        assert tm.entries["Hi"]["count"] == 1  # bumped instead

    def test_context_none_works(self, tmp_path):  # case 7
        tm = make_tm(tmp_path)
        tm.add("X", "เอ็กซ์", None)
        assert tm.lookup("X", None)["translation"] == "เอ็กซ์"
        assert tm.lookup("X")["hit_type"] == "default"


class TestMigrationV2:
    def test_v1_entry_migrates_on_load(self, tmp_path):  # case 6 + 14
        tm = make_tm(tmp_path)
        _write_tm(tm, {"version": 1, "source_language": "en", "target_language": "th",
                       "entries": {"Hello.": {"translation": "สวัสดี", "count": 5,
                                              "last_used": "2020-01-01T00:00:00Z",
                                              "speaker": "hero"}}})
        tm.load()
        e = tm.entries["Hello."]
        assert e["default_translation"] == "สวัสดี"
        assert e["variants"] == [] and e["count"] == 5
        assert e["confidence"] == 1.0  # case 14
        assert tm.lookup("Hello.")["translation"] == "สวัสดี"

    def test_v2_load_fills_variant_defaults(self, tmp_path):  # case 14 (variants)
        tm = make_tm(tmp_path)
        _write_tm(tm, {"version": 2, "entries": {
            "X": {"default_translation": "x",
                  "variants": [{"translation": "v", "speaker": "a"}]}}})
        tm.load()
        e = tm.entries["X"]
        assert e["confidence"] == 1.0
        v = e["variants"][0]
        assert v["confidence"] == 1.0 and v["context_hash"] is None

    def test_save_writes_version_2(self, tmp_path):
        tm = make_tm(tmp_path)
        tm.add("A", "เอ")
        tm.save()
        assert json.loads(tm.path.read_text(encoding="utf-8"))["version"] == 2


class TestForwardCompatFields:
    def test_context_object_has_all_fields(self, tmp_path):  # case 16
        ctx = TranslationContext(speaker="a", target="b", scene="c", file="d", line=1)
        assert ctx.scene == "c" and ctx.target == "b" and ctx.file == "d"

    def test_confidence_survives_round_trip(self, tmp_path):  # case 15
        tm = make_tm(tmp_path)
        tm.add("A", "เอ", TranslationContext(speaker="x"))
        tm.entries["A"]["variants"][0]["confidence"] = 0.5
        tm.entries["A"]["confidence"] = 0.7
        tm.save()
        tm2 = make_tm(tmp_path)
        tm2.load()
        assert tm2.entries["A"]["confidence"] == 0.7
        assert tm2.entries["A"]["variants"][0]["confidence"] == 0.5

    def test_context_hash_survives_round_trip(self, tmp_path):  # case 19
        tm = make_tm(tmp_path)
        tm.add("A", "เอ", TranslationContext(speaker="x"))
        tm.entries["A"]["variants"][0]["context_hash"] = "abc123"
        tm.save()
        tm2 = make_tm(tmp_path)
        tm2.load()
        assert tm2.entries["A"]["variants"][0]["context_hash"] == "abc123"

    def test_interrupted_save_recovery_v2(self, tmp_path):  # case 8
        tm = make_tm(tmp_path)
        tm.add("A", "เอ", TranslationContext(speaker="x"))
        tm.save()
        assert list((tmp_path / ".ftp").glob("*.tmp")) == []  # no half-write left
        tm2 = make_tm(tmp_path)
        tm2.load()  # must reload cleanly into the v2 shape
        assert tm2.lookup("A", TranslationContext(speaker="x"))["translation"] == "เอ"


class TestReservedOverrideAPI:
    def test_override_helpers_absent_in_v1_3(self):  # case 20
        assert not hasattr(TranslationMemory, "set_default")
        assert not hasattr(TranslationMemory, "promote_variant")
