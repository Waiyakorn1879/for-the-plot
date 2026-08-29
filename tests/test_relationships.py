"""Addressee resolution (v1.5).

The suite is organized around the property the feature actually has to hold:
it answers only from evidence it can name, and it says "I don't know" the rest
of the time. Every tier gets a positive case AND the case just outside it.
"""
import json
import shutil
import subprocess
import sys

import pytest
from conftest import FIXTURES, SCRIPTS_DIR

import extract_strings
import relationships
from relationships import AddresseeResolver, build_resolver, relationships_config

SPEAKERS = {
    "mc": {"name": "Ethan", "called": ["Mr. Reed"],
           "to": {"nora": {"address_pronoun": "you"}}},
    "nora": {"name": "Nora"},
    "prof": {"name": "Sandra"},
    "emma": {"name": "Emma"},
    "n2": {"name": "???", "alias_of": "nora"},
}

PROFILE = {"game_name": "Fixture", "language_id": "greek", "speakers": SPEAKERS}


@pytest.fixture(scope="module")
def scene_strings():
    return extract_strings.extract(FIXTURES / "scenes.rpy")


@pytest.fixture(scope="module")
def resolver(scene_strings):
    return build_resolver(PROFILE, scene_strings)


def line(strings, text):
    for entry in strings:
        if entry["text"] == text:
            return entry
    raise AssertionError(f"fixture line not found: {text}")


def say(text, speaker, line_no=1, file="a.rpy", label="l1"):
    return {"text": text, "speaker": speaker, "file": file,
            "line": line_no, "kind": "say", "label": label}


def with_cast(strings):
    """Stamp `label_cast` the way the extractor does.

    Deriving the cast from the list is only sound because in a test the list
    IS the whole script — which is exactly what stops being true after
    extraction deduplicates, and why the resolver refuses to derive it itself.
    """
    cast = {}
    for entry in strings:
        if entry.get("label"):
            key = (entry.get("file"), entry["label"])
            cast.setdefault(key, set()).add(entry["speaker"])
    for entry in strings:
        if entry.get("label"):
            entry["label_cast"] = sorted(cast[(entry.get("file"), entry["label"])])
    return strings


class TestLabelExtraction:
    """The dyad tier's whole foundation: labels come from the script."""

    def test_every_entry_carries_a_label(self, scene_strings):
        assert all("label" in e for e in scene_strings)

    def test_labels_follow_the_script(self, scene_strings):
        assert line(scene_strings, "Could not sleep.")["label"] == "dorm_room"
        assert line(scene_strings, "Take a seat, Mr. Reed.")["label"] == "lecture_hall"

    def test_label_runs_until_the_next_one(self, scene_strings):
        # Ren'Py falls through; a label owns every line up to the next label.
        assert line(scene_strings, "Nobody here but me.")["label"] == "empty_office"

    def test_local_label_is_qualified_by_its_parent(self, scene_strings):
        assert line(scene_strings,
                    "Let me try that once more.")["label"] == "branch_point.retry"

    def test_mini_game_still_extracts_identically_apart_from_label(self):
        entries = extract_strings.extract(FIXTURES / "mini_game.rpy")
        assert {e["label"] for e in entries} == {"start"}
        stripped = [{k: v for k, v in e.items()
                     if k not in ("label", "label_cast")} for e in entries]
        assert stripped[0] == {"text": "Hello there, [partner_name]!",
                               "speaker": "hero", "file": "mini_game.rpy",
                               "line": 16, "kind": "say"}


class TestDyadTier:
    def test_two_party_label_resolves(self, resolver, scene_strings):
        finding = resolver.resolve(line(scene_strings, "Could not sleep."))
        assert (finding.code, finding.tier) == ("mc", "dyad")

    def test_resolution_is_symmetric(self, resolver, scene_strings):
        finding = resolver.resolve(line(scene_strings, "Were you talking about me?"))
        assert (finding.code, finding.tier) == ("mc", "dyad")

    def test_three_party_label_refuses(self, resolver, scene_strings):
        finding = resolver.resolve(line(scene_strings, "You are late again."))
        assert finding.code is None and finding.reason == "multi-party"

    def test_solo_label_refuses(self, resolver, scene_strings):
        finding = resolver.resolve(line(scene_strings, "Nobody here but me."))
        assert finding.code is None and finding.reason == "solo"

    def test_the_dyad_is_computed_over_the_whole_label(self):
        # A third speaker anywhere in the label refuses the WHOLE label, even
        # for lines nowhere near them. A sliding window would have resolved the
        # first two lines confidently and wrongly.
        strings = with_cast([say("One.", "mc", 1), say("Two.", "nora", 2),
                             say("Three.", "mc", 3), say("Four.", "prof", 99)])
        r = AddresseeResolver(SPEAKERS, strings, {"enabled": True})
        assert all(r.resolve(e).reason == "multi-party" for e in strings)

    def test_aliases_count_as_one_character(self):
        strings = with_cast([say("One.", "mc", 1), say("Two.", "nora", 2),
                             say("Three.", "n2", 3)])
        r = AddresseeResolver(SPEAKERS, strings, {"enabled": True})
        assert r.resolve(strings[0]).code == "nora"
        assert r.resolve(strings[2]).code == "mc"   # canonical, via alias_of

    def test_missing_label_refuses(self):
        # A v1.4 strings.json has no `label` — the tier is unavailable, and
        # unavailable means unresolved, never a fallback guess.
        strings = [say("One.", "mc", 1, label=None), say("Two.", "nora", 2, label=None)]
        r = AddresseeResolver(SPEAKERS, strings, {"enabled": True})
        assert [r.resolve(e).reason for e in strings] == ["no-label", "no-label"]

    def test_a_label_without_a_stated_cast_refuses(self):
        # Distinguished from "no label at all", because the fix is different:
        # one needs a re-extraction, the other is narration or init text.
        strings = [say("One.", "mc", 1), say("Two.", "nora", 2)]   # no with_cast
        r = AddresseeResolver(SPEAKERS, strings, {"enabled": True})
        assert [r.resolve(e).reason for e in strings] == ["no-cast", "no-cast"]

    def test_a_speaker_outside_the_stated_cast_refuses(self):
        strings = with_cast([say("One.", "mc", 1), say("Two.", "nora", 2)])
        stray = say("Three.", "prof", 3)
        stray["label_cast"] = ["mc", "nora"]
        assert AddresseeResolver(SPEAKERS, strings + [stray],
                                 {"enabled": True}).resolve(stray).reason             == "cast-mismatch"

    def test_labels_do_not_leak_across_files(self):
        strings = with_cast([say("One.", "mc", 1, file="a.rpy"),
                             say("Two.", "nora", 2, file="b.rpy")])
        r = AddresseeResolver(SPEAKERS, strings, {"enabled": True})
        assert all(r.resolve(e).reason == "solo" for e in strings)


class TestVocativeTier:
    def test_name_in_vocative_position_resolves(self, resolver, scene_strings):
        finding = resolver.resolve(line(scene_strings, "Hey, Nora. You are up early."))
        assert (finding.code, finding.tier) == ("nora", "vocative")

    def test_called_names_are_recognized(self, resolver, scene_strings):
        # `called` covers what the script actually says, not the profile key.
        finding = resolver.resolve(line(scene_strings, "Take a seat, Mr. Reed."))
        assert (finding.code, finding.tier) == ("mc", "vocative")

    def test_a_bare_mention_is_not_an_address(self, resolver, scene_strings):
        # "I saw Nora yesterday" describes a third party. It happens to fall
        # back to the same answer here via the dyad, but not as a vocative.
        finding = resolver.resolve(line(scene_strings, "I saw Nora yesterday."))
        assert finding.tier == "dyad"
        assert "vocative" not in finding.alternatives

    @pytest.mark.parametrize("text", [
        "Nora, look at this.", "Well done, Nora!", "Nora?",
        "Are you coming, Nora, or not?",
    ])
    def test_vocative_positions(self, text):
        assert AddresseeResolver._is_vocative(text, "Nora")

    @pytest.mark.parametrize("text", [
        "I told Nora about it.", "That is Nora's bag.", "Norah is someone else.",
        "Ask Nora tomorrow.",
    ])
    def test_non_vocative_positions(self, text):
        assert not AddresseeResolver._is_vocative(text, "Nora")

    def test_markup_cannot_fake_a_vocative_edge(self):
        entry = say("I mentioned {i}Nora{/i} once to him.", "mc")
        r = AddresseeResolver(SPEAKERS, [entry], {"enabled": True})
        assert "vocative" not in r.resolve(entry).alternatives

    def test_two_addressees_is_not_one_addressee(self):
        entry = say("Nora, Emma, come here.", "mc")
        r = AddresseeResolver(SPEAKERS, [entry], {"enabled": True})
        finding = r.resolve(entry)
        assert finding.code is None and finding.reason == "multi-vocative"

    def test_a_name_two_characters_share_is_no_evidence(self):
        speakers = {"a": {"name": "Sam"}, "b": {"name": "Sam"}, "mc": {"name": "Ethan"}}
        entry = say("Sam, wait.", "mc")
        r = AddresseeResolver(speakers, [entry], {"enabled": True})
        assert "vocative" not in r.resolve(entry).alternatives

    def test_self_address_is_not_an_addressee(self):
        entry = say("Ethan, get a grip.", "mc")
        r = AddresseeResolver(SPEAKERS, [entry], {"enabled": True})
        assert "vocative" not in r.resolve(entry).alternatives

    def test_tier_is_english_only(self):
        entry = say("Hey, Nora.", "mc")
        r = AddresseeResolver(SPEAKERS, [entry], {"enabled": True},
                              source_language="ja")
        assert r.vocatives == {}
        assert "vocative" not in r.resolve(entry).alternatives


class TestDeclaredTier:
    SCOPES = [{"label": "study_room", "pairs": {"mc": "prof"}}]

    def test_declared_outranks_everything(self, scene_strings):
        r = build_resolver({**PROFILE, "relationships": {"declared": self.SCOPES}},
                           scene_strings)
        finding = r.resolve(line(scene_strings, "Emma, are you there?"))
        assert (finding.code, finding.tier) == ("prof", "declared")

    def test_cast_shorthand_declares_a_dyad(self):
        strings = with_cast([say("One.", "mc", 1), say("Two.", "nora", 2),
                             say("Three.", "prof", 3)])
        r = AddresseeResolver(SPEAKERS, strings,
                              {"enabled": True, "declared": [{"cast": ["mc", "prof"]}]})
        assert r.resolve(strings[0]).code == "prof"
        assert r.resolve(strings[2]).code == "mc"
        assert r.resolve(strings[1]).reason == "multi-party"   # nora is not in the cast

    def test_line_range_bounds_a_scope(self):
        strings = [say("One.", "mc", 5), say("Two.", "mc", 50)]
        r = AddresseeResolver(SPEAKERS, strings, {
            "enabled": True,
            "declared": [{"file": "a.rpy", "lines": [1, 10], "pairs": {"mc": "emma"}}]})
        assert r.resolve(strings[0]).code == "emma"
        assert r.resolve(strings[1]).code is None

    def test_first_matching_scope_wins(self):
        entry = say("One.", "mc", 5)
        r = AddresseeResolver(SPEAKERS, [entry], {
            "enabled": True,
            "declared": [{"pairs": {"mc": "emma"}}, {"pairs": {"mc": "prof"}}]})
        assert r.resolve(entry).code == "emma"

    def test_malformed_scopes_are_ignored_not_fatal(self):
        entry = say("One.", "mc", 5)
        r = AddresseeResolver(SPEAKERS, [entry], {
            "enabled": True,
            "declared": ["nonsense", {"pairs": "also nonsense"}, {}, {"cast": ["mc"]}]})
        assert r.resolve(entry).code is None


class TestRefusals:
    def test_monologue_has_no_addressee(self, resolver, scene_strings):
        finding = resolver.resolve(line(scene_strings, "(She looks exhausted today.)"))
        assert finding.code is None and finding.reason == "monologue"

    def test_narration_has_no_addressee(self, resolver, scene_strings):
        finding = resolver.resolve(line(scene_strings, "Narration that belongs to nobody."))
        assert finding.code is None and finding.reason == "pseudo"

    @pytest.mark.parametrize("speaker", ["_menu", "_screen", "_ui", "_text"])
    def test_pseudo_speakers_never_resolve(self, speaker):
        entry = say("Continue", speaker)
        r = AddresseeResolver(SPEAKERS, [entry, say("Hi.", "mc")], {"enabled": True})
        assert r.resolve(entry).reason == "pseudo"


class TestConflicts:
    def test_vocative_beats_dyad_but_the_disagreement_is_recorded(
            self, resolver, scene_strings):
        finding = resolver.resolve(line(scene_strings, "Emma, are you there?"))
        assert (finding.code, finding.tier) == ("emma", "vocative")
        assert finding.conflict is True
        assert finding.alternatives == {"vocative": "emma", "dyad": "nora"}

    def test_agreement_is_not_a_conflict(self, resolver, scene_strings):
        finding = resolver.resolve(line(scene_strings, "Hey, Nora. You are up early."))
        assert finding.conflict is False


class TestConfidenceGate:
    def test_default_admits_every_tier(self, resolver, scene_strings):
        assert resolver.min_confidence == "dyad"
        assert resolver.target_for(line(scene_strings, "Could not sleep.")) == "mc"

    def test_raising_the_bar_withholds_weaker_answers(self, scene_strings):
        r = build_resolver(
            {**PROFILE, "relationships": {"min_confidence": "vocative"}}, scene_strings)
        dyad_line = line(scene_strings, "Could not sleep.")
        assert r.resolve(dyad_line).code == "mc"        # still known
        assert r.target_for(dyad_line) is None          # but not acted on
        assert r.target_for(line(scene_strings, "Take a seat, Mr. Reed.")) == "mc"

    def test_declared_only_is_the_strictest_setting(self, scene_strings):
        r = build_resolver(
            {**PROFILE, "relationships": {"min_confidence": "declared"}}, scene_strings)
        assert all(r.target_for(e) is None for e in scene_strings)

    def test_an_unknown_setting_falls_back_to_the_default(self, scene_strings):
        r = build_resolver({**PROFILE, "relationships": {"min_confidence": "vibes"}},
                           scene_strings)
        assert r.min_confidence == "dyad"


class TestEnableRule:
    """A profile that never mentions relationships must behave exactly as v1.4."""

    def test_off_when_nothing_is_declared(self, scene_strings):
        profile = {"speakers": {"mc": {"name": "Ethan"}, "nora": {"name": "Nora"}}}
        r = build_resolver(profile, scene_strings)
        assert r.enabled is False
        assert all(r.target_for(e) is None for e in scene_strings)
        assert r.resolve(scene_strings[0]).reason == "disabled"

    def test_on_when_a_character_declares_a_relationship(self, scene_strings):
        assert build_resolver(PROFILE, scene_strings).enabled is True

    def test_on_when_scopes_are_declared_without_any_to_map(self, scene_strings):
        profile = {"speakers": {"mc": {"name": "Ethan"}},
                   "relationships": {"declared": [{"pairs": {"mc": "nora"}}]}}
        assert build_resolver(profile, scene_strings).enabled is True

    def test_explicit_setting_wins_both_ways(self, scene_strings):
        assert build_resolver({**PROFILE, "relationships": {"enabled": False}},
                              scene_strings).enabled is False
        assert build_resolver({"speakers": {}, "relationships": {"enabled": True}},
                              scene_strings).enabled is True

    def test_config_defaults(self):
        cfg = relationships_config({})
        assert cfg == {"enabled": False, "min_confidence": "dyad", "declared": []}


class TestAudit:
    def test_counts_add_up(self, resolver, scene_strings):
        stats = resolver.audit(scene_strings)
        resolved = sum(stats["tiers"].values())
        unresolved = sum(stats["reasons"].values())
        assert resolved + unresolved == stats["character_lines"]

    def test_label_classification(self, resolver, scene_strings):
        labels = resolver.audit(scene_strings)["labels"]
        assert labels["dyad"] == 3        # dorm_room, hallway, study_room
        assert labels["multi"] == 1       # lecture_hall
        assert labels["solo"] == 2        # empty_office, branch_point.retry

    def test_pairs_are_canonical(self, resolver, scene_strings):
        pairs = resolver.audit(scene_strings)["pairs"]
        assert pairs[("nora", "mc")] == 4

    def test_below_threshold_lines_are_reported_not_hidden(self, scene_strings):
        r = build_resolver(
            {**PROFILE, "relationships": {"min_confidence": "declared"}}, scene_strings)
        stats = r.audit(scene_strings)
        assert stats["below_threshold"] > 0
        assert stats["reasons"]["below-threshold"] == stats["below_threshold"]

    def test_unknown_speaker_codes_are_surfaced(self, scene_strings):
        # v1.4 left this open: a recognizable name landing in the generic
        # bucket used to be invisible.
        profile = {"speakers": {"mc": {"name": "Ethan"},
                                "nora": {"name": "Nora", "to": {"mc": {}}}}}
        r = build_resolver(profile, scene_strings)
        assert r.unknown_speakers["prof"] == 1
        assert "mc" not in r.unknown_speakers


class TestReportCLI:
    def run(self, tmp_path, profile, strings, *args):
        (tmp_path / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
        (tmp_path / "strings.json").write_text(
            json.dumps(strings, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "relationships.py"),
             "--profile", str(tmp_path / "profile.json"), *args],
            capture_output=True, text=True, encoding="utf-8")

    def test_report_runs_and_names_its_evidence(self, tmp_path, scene_strings):
        proc = self.run(tmp_path, PROFILE, scene_strings)
        assert proc.returncode == 0, proc.stderr
        for expected in ("ADDRESSEE RESOLUTION", "RESOLVED", "UNRESOLVED",
                         "LABELS", "PAIRS RESOLVED", "dyad", "vocative"):
            assert expected in proc.stdout

    def test_report_flags_undeclared_pairs(self, tmp_path, scene_strings):
        proc = self.run(tmp_path, PROFILE, scene_strings)
        assert "NOT DECLARED" in proc.stdout        # Nora -> Ethan is undeclared

    def test_report_names_unknown_speaker_codes(self, tmp_path, scene_strings):
        profile = {**PROFILE, "speakers": {k: v for k, v in SPEAKERS.items()
                                           if k != "prof"}}
        proc = self.run(tmp_path, profile, scene_strings)
        assert "UNKNOWN SPEAKER CODES" in proc.stdout and "prof" in proc.stdout

    def test_report_tells_you_to_re_extract(self, tmp_path):
        strings = [say("One.", "mc", 1, label=None)]
        proc = self.run(tmp_path, PROFILE, strings)
        assert "re-extract" in proc.stdout

    def test_report_file_is_written(self, tmp_path, scene_strings):
        out = tmp_path / "addressees.txt"
        proc = self.run(tmp_path, PROFILE, scene_strings, "--report", str(out))
        assert proc.returncode == 0
        assert "ADDRESSEE RESOLUTION" in out.read_text(encoding="utf-8")

    def test_missing_strings_file_is_a_clean_error(self, tmp_path):
        (tmp_path / "profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "relationships.py"),
             "--profile", str(tmp_path / "profile.json")],
            capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode != 0 and "strings file not found" in proc.stderr


class TestRobustness:
    def test_empty_inputs(self):
        r = AddresseeResolver({}, [], {"enabled": True})
        assert r.audit([])["character_lines"] == 0

    def test_entries_missing_fields_never_raise(self):
        r = AddresseeResolver(SPEAKERS, [{}], {"enabled": True})
        assert r.resolve({}).code is None
        assert r.resolve({"speaker": "mc"}).code is None

    def test_tier_order_is_least_to_most_certain(self):
        assert relationships.TIERS == ("dyad", "vocative", "declared")
        assert relationships.TIER_RANK["declared"] > relationships.TIER_RANK["vocative"]


class TestDedupeCannotShrinkACast:
    """The trap this whole field exists for.

    `extract_strings.main()` deduplicates globally by text, first occurrence
    wins. A minor character whose only line in a scene is "Yeah." loses it to
    an earlier duplicate — so counting who still *speaks* in the corpus turns a
    three-person scene into an apparent two-person one. Dedupe can only remove
    speakers, never add them, so the error runs in exactly one direction: the
    one that resolves confidently to the wrong person.
    """

    def extract_via_cli(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        shutil.copy(FIXTURES / "crowd_scene.rpy", src)
        out = tmp_path / "strings.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "extract_strings.py"),
             "--src", str(src), "--out", str(out)],
            capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        return json.loads(out.read_text(encoding="utf-8"))

    def test_the_duplicate_line_really_is_dropped(self, tmp_path):
        strings = self.extract_via_cli(tmp_path)
        busy = [e for e in strings if e["label"] == "busy_hallway"]
        assert "prof" not in {e["speaker"] for e in busy}, \
            "fixture no longer exercises the trap"

    def test_the_stated_cast_survives_dedupe(self, tmp_path):
        strings = self.extract_via_cli(tmp_path)
        busy = next(e for e in strings if e["label"] == "busy_hallway")
        assert busy["label_cast"] == ["mc", "nora", "prof"]

    def test_the_scene_is_refused_not_resolved(self, tmp_path):
        strings = self.extract_via_cli(tmp_path)
        r = build_resolver(PROFILE, strings)
        busy = [e for e in strings if e["label"] == "busy_hallway"]
        assert [r.resolve(e).reason for e in busy] == ["multi-party", "multi-party"]

    def test_a_genuine_dyad_in_the_same_file_still_resolves(self, tmp_path):
        strings = self.extract_via_cli(tmp_path)
        quiet = next(e for e in strings if e["label"] == "quiet_corner")
        finding = build_resolver(PROFILE, strings).resolve(quiet)
        assert (finding.code, finding.tier) == ("nora", "dyad")


class TestLabelKeyCollisions:
    """The one path where two scenes can share a label key, and its direction.

    A local `.retry` before any global label qualifies to a bare `.retry`, so a
    second one in the same file lands in the same bucket. That only happens in a
    malformed script, and the effect is a *union* of casts — which can turn a
    dyad into a multi-party refusal but never a multi-party scene into a dyad.
    The collision over-refuses; it cannot mis-resolve, which is the only
    property that matters here.
    """

    SRC = (
        "label .retry:\n\n    mc \"One.\"\n    nora \"Two.\"\n\n"
        "label .other:\n\n    mc \"Three.\"\n\n"
        "label .retry:\n\n    prof \"Four.\"\n"
    )

    def entries(self, tmp_path):
        path = tmp_path / "odd.rpy"
        path.write_text(self.SRC, encoding="utf-8")
        return extract_strings.extract(path)

    def test_the_collided_casts_are_unioned(self, tmp_path):
        entries = self.entries(tmp_path)
        retry = [e for e in entries if e["label"] == ".retry"]
        assert all(e["label_cast"] == ["mc", "nora", "prof"] for e in retry)

    def test_the_collision_refuses_rather_than_resolving(self, tmp_path):
        entries = self.entries(tmp_path)
        r = AddresseeResolver(SPEAKERS, entries, {"enabled": True})
        retry = [e for e in entries if e["label"] == ".retry"]
        assert {r.resolve(e).reason for e in retry} == {"multi-party"}
