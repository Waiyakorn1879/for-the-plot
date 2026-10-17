import json
import subprocess
import sys

from conftest import SCRIPTS_DIR

import terminology as T
import translate_api
from validation import validate_translation, validation_policy


def term(source, target=None, stage="ENFORCED", priority=10, scope="translate", **kw):
    t = {"source": source, "scope": scope, "stage": stage, "priority": priority,
         "provenance": "human", **kw}
    if target or scope == "keep":
        t["target"] = target or source
    return t


def names(match_result):
    return [(t["source"], s) for t, s, _ in match_result[0]]


class TestMatcher:
    def test_word_bounded_and_case_sensitive(self):
        terms = [term("Rust", "สนิม")]
        assert names(T.match("Rusty pipes", terms)) == []
        assert names(T.match("rust and Rust", terms)) == [("Rust", 9)]

    def test_never_matches_inside_tokens(self):
        assert names(T.match("[Rush] {Rush}", [term("Rush", "x")])) == []

    def test_longest_match_wins_left_to_right(self):
        terms = [term("Rush", "a"), term("Dark Rush", "b"), term("York City", "c"),
                 term("New York", "d")]
        got = names(T.match("Dark Rush and Rush; New York City", terms))
        assert got == [("Dark Rush", 0), ("Rush", 14), ("New York", 20)]

    def test_priority_decides_identical_triggers(self):
        got = T.match("Rush", [term("Rush", "low", priority=1), term("Rush", "high", priority=5)])
        assert [t["target"] for t, *_ in got[0]] == ["high"]

    def test_equal_priority_tie_is_unresolved_not_picked(self):
        winners, unresolved = T.match("Rush", [term("Rush", "a"), term("Rush", "b")])
        assert winners == [] and len(unresolved) == 1


class TestGate:
    def test_missing_and_forbidden(self):
        terms = [term("Rush", "รัช", forbidden=["รัซ"])]
        assert T.violations("Rush!", "รัช!", terms) == []
        assert [k for k, _ in T.violations("Rush!", "ผม!", terms)] == ["missing"]
        assert "forbidden" in [k for k, _ in T.violations("Rush!", "รัชรัซ", terms)]

    def test_keep_scope_needs_verbatim_source(self):
        terms = [term("Eternum", scope="keep")]
        assert T.violations("Eternum", "เอเทอร์นัม", terms)
        assert not T.violations("Eternum", "ที่ Eternum", terms)

    def test_below_enforced_never_blocks(self):
        for stage in T.STAGES[:-1]:
            assert T.violations("Rush", "x", [term("Rush", "รัช", stage=stage)]) == []

    def test_policy_gate_returns_term(self, tmp_path):
        (tmp_path / "terminology.json").write_text(json.dumps(
            {"terms": [term("Rush", "รัช")]}), encoding="utf-8")
        policy = validation_policy({"language_id": "thai"}, tmp_path)
        assert validate_translation("Rush!", "ผม!", policy) == (False, "TERM")
        assert validate_translation("Rush!", "รัช!", policy) == (True, None)

    def test_no_dictionary_means_no_change(self, tmp_path):
        profile = {"language_id": "thai", "keep_untranslated": ["Eternum"]}
        with_base = validation_policy(profile, tmp_path)
        assert with_base["keep_untranslated"] == ["Eternum"]
        assert validate_translation("Rush!", "ผม!", with_base) == validate_translation(
            "Rush!", "ผม!", validation_policy(profile))


class TestMigrationAndGuidance:
    def test_keep_untranslated_migrates_as_approved_keep(self, tmp_path):
        terms, authored = T.load_terms({"keep_untranslated": ["Eternum"]}, tmp_path)
        assert authored == 0
        assert terms[0]["stage"] == "APPROVED" and terms[0]["scope"] == "keep"
        assert terms[0]["provenance"] == "human" and terms[0]["priority"] == 0

    def test_authored_term_wins_over_migrated_duplicate(self, tmp_path):
        (tmp_path / "terminology.json").write_text(json.dumps(
            {"terms": [term("Eternum", scope="keep", stage="REVIEWED")]}), encoding="utf-8")
        terms, _ = T.load_terms({"keep_untranslated": ["Eternum"]}, tmp_path)
        assert [t["stage"] for t in terms] == ["REVIEWED"]

    def test_guidance_only_reviewed_up_and_only_when_present(self):
        terms = [term("Rush", "รัช", stage="REVIEWED"), term("Rust", "สนิม", stage="CANDIDATE"),
                 term("Gold", "ทอง", stage="APPROVED")]
        block = T.guidance_block(["Rush and Rust"], terms)
        assert "Rush -> รัช" in block and "Rust" not in block and "Gold" not in block
        assert T.guidance_block(["nothing here"], terms) == ""
        assert T.guidance_block(["Rush"], []) == ""

    def test_unconfigured_profile_prompt_has_no_terminology(self):
        seen = {}
        translate_api.translate_batch(
            lambda s, u: seen.setdefault("u", u) and "[]", "sys", {}, "Thai",
            [{"id": 1, "speaker": "mc", "kind": "say", "text": "Rush"}], terms=[])
        assert "TERMINOLOGY" not in seen["u"]
        translate_api.translate_batch(
            lambda s, u: seen.update(u=u) or "[]", "sys", {}, "Thai",
            [{"id": 1, "speaker": "mc", "kind": "say", "text": "Rush"}],
            terms=[term("Rush", "รัช", stage="APPROVED")])
        assert "TERMINOLOGY IN THIS BATCH" in seen["u"] and "MANDATORY" not in seen["u"]


class TestPreflight:
    def test_blocking_only_for_enforced_conflicts(self):
        r = T.preflight([term("Rush", "a", stage="APPROVED"), term("Rush", "b", stage="APPROVED")])
        assert len(r["conflicts"]) == 1 and r["blocking"] == []
        r = T.preflight([term("Rush", "a"), term("Rush", "b", stage="APPROVED")])
        assert len(r["blocking"]) == 1

    def test_priority_resolves_the_pair(self):
        r = T.preflight([term("Rush", "a", priority=2), term("Rush", "b", priority=1)])
        assert r["conflicts"] == []

    def test_shadow_is_informational(self):
        r = T.preflight([term("Rush", "a"), term("Dark Rush", "b")])
        assert len(r["shadows"]) == 1 and r["blocking"] == []

    def test_invalid_terms_reported_and_excluded(self):
        bad = term("Rush", "a", stage="APPROVED", priority=None)
        r = T.preflight([bad])
        assert r["invalid"] and not T.active([bad], "APPROVED")


class TestSweep:
    def test_finds_phrases_and_midsentence_names(self):
        strings = [{"text": t} for t in [
            "We went to Dark Harbor again.", "Dark Harbor is cold.", "Nobody likes Dark Harbor.",
            "She met Zorin at noon.", "I told Zorin, and Zorin left.", "Zorin smiled."]]
        found = T.sweep(strings, known_sources=set(), ignore=["Nobody"], min_count=3)
        assert found.get("Dark Harbor") == 3 and "Harbor" not in found and found.get("Zorin") == 3
        assert "We" not in found and "Nobody" not in found
        assert "Dark Harbor" not in T.sweep(strings, {"Dark Harbor"})


class TestSweepStopwords:
    def sweep(self, *texts, **kw):
        return T.sweep([{"text": t} for t in texts], set(), **kw)

    def test_leading_stopword_is_stripped(self):
        found = self.sweep("To Dark Harbor", "Back to Dark Harbor", "In Dark Harbor")
        assert found == {"Dark Harbor": 3}

    def test_several_leading_stopwords_and_case(self):
        found = self.sweep("In The Dark Harbor", "From the Dark Harbor", "At Dark Harbor")
        assert found == {"Dark Harbor": 3}

    def test_internal_connectors_are_kept(self):
        found = self.sweep("Bank of England", "The Bank of England")
        assert found == {"Bank of England": 2}

    def test_remainder_of_one_word_counts_as_a_single(self):
        assert self.sweep("The Harbor", "To Harbor") == {}                 # below min_count
        assert self.sweep("The Harbor", "To Harbor", "In Harbor") == {"Harbor": 3}

    def test_phrase_of_only_stopwords_is_dropped(self):
        assert self.sweep("The In", "To The", "At On") == {}

    def test_stopword_stripping_merges_with_clean_sightings(self):
        found = self.sweep("To Dark Harbor", "Go to Dark Harbor")
        assert found == {"Dark Harbor": 2}


def cli(tmp_path, *args):
    return subprocess.run([sys.executable, str(SCRIPTS_DIR / "terminology.py"), args[0],
                           "--profile", str(tmp_path / "profile.json"), *args[1:]],
                          capture_output=True, text=True, encoding="utf-8")


class TestLifecycleCli:
    def setup_profile(self, tmp_path, **extra):
        (tmp_path / "profile.json").write_text(json.dumps(
            {"language_id": "thai", "keep_untranslated": ["Eternum"], **extra}), encoding="utf-8")
        (tmp_path / "strings.json").write_text("[]", encoding="utf-8")

    def stage_of(self, tmp_path, source):
        data = json.loads((tmp_path / "terminology.json").read_text(encoding="utf-8"))
        return next(t["stage"] for t in data["terms"] if t["source"] == source)

    def test_one_step_at_a_time_with_requirements(self, tmp_path):
        self.setup_profile(tmp_path)
        assert cli(tmp_path, "add", "Rush", "--target", "รัช").returncode == 0
        assert self.stage_of(tmp_path, "Rush") == "CANDIDATE"
        refused = cli(tmp_path, "promote", "Rush")                          # no priority yet
        assert refused.returncode != 0 and "priority" in refused.stderr
        assert cli(tmp_path, "promote", "Rush", "--priority", "10").returncode == 0   # REVIEWED
        assert self.stage_of(tmp_path, "Rush") == "REVIEWED"
        assert cli(tmp_path, "promote", "Rush").returncode == 0             # APPROVED
        assert self.stage_of(tmp_path, "Rush") == "APPROVED"
        assert cli(tmp_path, "promote", "Rush").returncode == 0
        assert self.stage_of(tmp_path, "Rush") == "ENFORCED"
        assert cli(tmp_path, "promote", "Rush").returncode != 0             # nowhere further

    def test_cannot_enforce_into_an_unresolved_tie(self, tmp_path):
        self.setup_profile(tmp_path)
        (tmp_path / "terminology.json").write_text(json.dumps({"terms": [
            term("Rush", "a", stage="APPROVED"), term("Rush", "b", stage="APPROVED")]}),
            encoding="utf-8")
        refused = cli(tmp_path, "promote", "Rush")
        assert refused.returncode != 0 and "unresolved conflict" in refused.stderr

    def test_migrated_keep_term_can_be_promoted(self, tmp_path):
        self.setup_profile(tmp_path)
        assert cli(tmp_path, "promote", "Eternum").returncode == 0
        assert self.stage_of(tmp_path, "Eternum") == "ENFORCED"

    def test_preflight_exit_codes(self, tmp_path):
        self.setup_profile(tmp_path)
        assert cli(tmp_path, "preflight").returncode == 0
        (tmp_path / "terminology.json").write_text(json.dumps({"terms": [
            term("Rush", "a"), term("Rush", "b")]}), encoding="utf-8")
        proc = cli(tmp_path, "preflight")
        assert proc.returncode == 1 and "BLOCKING" in proc.stdout

    def test_import_never_arrives_above_candidate(self, tmp_path):
        self.setup_profile(tmp_path)
        (tmp_path / "other.json").write_text(json.dumps([term("Rush", "รัช")]), encoding="utf-8")
        assert cli(tmp_path, "import", "other.json" if False else str(tmp_path / "other.json")).returncode == 0
        data = json.loads((tmp_path / "terminology.json").read_text(encoding="utf-8"))
        assert data["terms"][0]["stage"] == "CANDIDATE"
        assert data["terms"][0]["provenance"] == "imported"

    def test_sweep_adds_discovered_and_never_overwrites(self, tmp_path):
        self.setup_profile(tmp_path)
        (tmp_path / "strings.json").write_text(json.dumps(
            [{"text": "Go to Dark Harbor"}, {"text": "Back from Dark Harbor"}]), encoding="utf-8")
        assert cli(tmp_path, "sweep").returncode == 0
        first = (tmp_path / "terminology.json").read_text(encoding="utf-8")
        assert self.stage_of(tmp_path, "Dark Harbor") == "DISCOVERED"
        assert cli(tmp_path, "sweep").returncode == 0
        assert (tmp_path / "terminology.json").read_text(encoding="utf-8") == first


class TestQaIntegration:
    def run_qa(self, tmp_path, *args):
        (tmp_path / "profile.json").write_text(json.dumps({
            "language_id": "thai", "strings_file": "strings.json", "progress_file": "tr.json"}),
            encoding="utf-8")
        (tmp_path / "strings.json").write_text(json.dumps([
            {"text": "Rush!", "speaker": "mc", "file": "a.rpy", "line": 1, "kind": "say"}]),
            encoding="utf-8")
        (tmp_path / "tr.json").write_text(json.dumps({"Rush!": "ผม!"}), encoding="utf-8")
        (tmp_path / "terminology.json").write_text(json.dumps(
            {"terms": [term("Rush", "รัช")]}), encoding="utf-8")
        return subprocess.run([sys.executable, str(SCRIPTS_DIR / "qa_check.py"),
                               "--profile", str(tmp_path / "profile.json"), *args],
                              capture_output=True, text=True, encoding="utf-8")

    def test_enforced_term_is_category_one_even_technical_only(self, tmp_path):
        for extra in ((), ("--technical-only",)):
            proc = self.run_qa(tmp_path, *extra)
            assert proc.returncode == 1 and "TERM:missing:Rush" in proc.stdout


class TestRetryFeedback:
    TERMS = [term("Dark Harbor", "ท่าเรือมืด", forbidden=["ฮาร์เบอร์"]),
             term("Eternum", scope="keep")]

    def test_feedback_names_term_and_form(self):
        fb = T.feedback("To Dark Harbor", "ไป ฮาร์เบอร์", self.TERMS)
        assert fb == ['"Dark Harbor" must appear as "ท่าเรือมืด"',
                      '"Dark Harbor": do not use "ฮาร์เบอร์"']
        assert T.feedback("Eternum", "เอเทอร์นัม", self.TERMS) == [
            '"Eternum" must appear exactly as written "Eternum"']
        assert T.feedback("To Dark Harbor", "ไป ท่าเรือมืด", self.TERMS) == []
        assert T.feedback("To Dark Harbor", "x", []) == []

    def retry_message(self, previous, terms):
        seen = {}
        translate_api.translate_batch(
            lambda s, u: seen.setdefault("u", u) and "[]", "sys", {}, "Thai",
            [{"id": 7, "speaker": "mc", "kind": "say", "text": "To Dark Harbor"},
             {"id": 8, "speaker": "mc", "kind": "say", "text": "Hello"}],
            retry=True, reasons=["TERM"], terms=terms, previous=previous)
        return seen["u"]

    def test_retry_prompt_lists_each_violating_line(self):
        msg = self.retry_message({7: "ไป ฮาร์เบอร์", 8: "สวัสดี"}, self.TERMS)
        assert "Fix these terminology errors:" in msg
        assert '- line 7: "Dark Harbor" must appear as "ท่าเรือมืด"' in msg
        assert '- line 7: "Dark Harbor": do not use "ฮาร์เบอร์"' in msg
        assert "line 8" not in msg.split("Fix these terminology errors:")[1]
        assert "mandatory terminology" in msg                    # the generic nag stays

    def test_no_feedback_when_nothing_violated_or_no_terms(self):
        assert "Fix these" not in self.retry_message({7: "ไป ท่าเรือมืด"}, self.TERMS)
        assert "Fix these" not in self.retry_message({7: "x"}, [])

    def test_missing_previous_output_still_names_the_required_form(self):
        assert '- line 7: "Dark Harbor" must appear as' in self.retry_message({}, self.TERMS)

    def test_ordinary_retry_unchanged_without_terms(self):
        seen = {}
        translate_api.translate_batch(
            lambda s, u: seen.setdefault("u", u) and "[]", "sys", {}, "Thai",
            [{"id": 1, "speaker": "mc", "kind": "say", "text": "Hi"}],
            retry=True, reasons=["ECHO"])
        assert "returned the English source unchanged" in seen["u"]
        assert "Fix these" not in seen["u"]
