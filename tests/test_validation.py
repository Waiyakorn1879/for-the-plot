import os

import pytest

import validation
from validation import (
    is_echo, multiset_diff, parse_ranges, policy_banner, resolve_target_script,
    tag_nesting_ok, translatable_residue, validate_translation,
    validation_policy, write_text_atomic,
)

THAI = [(0x0E00, 0x0E7F)]


def policy(**profile):
    return validation_policy(profile)


class TestParseRanges:
    def test_hex_string_range(self):
        assert parse_ranges("0E00-0E7F") == THAI

    def test_int_pair(self):
        assert parse_ranges([0x0E00, 0x0E7F]) == THAI

    def test_hex_string_pair(self):
        assert parse_ranges(["0E00", "0E7F"]) == THAI

    def test_list_of_range_strings(self):
        assert parse_ranges(["0E00-0E7F", "1000-109F"]) == THAI + [(0x1000, 0x109F)]

    def test_empty(self):
        assert parse_ranges([]) == []


class TestResolveTargetScript:
    def test_explicit_name(self):
        ranges, origin = resolve_target_script(
            {"language_id": "french", "validation": {"target_script": "thai"}})
        assert (ranges, origin) == (THAI, "explicit")

    def test_explicit_ranges(self):
        ranges, origin = resolve_target_script(
            {"validation": {"target_script": {"ranges": ["0E00-0E7F"]}}})
        assert (ranges, origin) == (THAI, "explicit")

    def test_inferred_from_language_id(self):
        ranges, origin = resolve_target_script({"language_id": "thai"})
        assert (ranges, origin) == (THAI, "inferred")

    def test_unknown_language_gives_nothing(self):
        assert resolve_target_script({"language_id": "klingon"}) == (None, "none")

    def test_latin_target_has_no_discriminating_ranges(self):
        ranges, origin = resolve_target_script({"language_id": "french"})
        assert ranges == [] and origin == "inferred"


class TestPolicy:
    def test_echo_on_by_default(self):
        assert policy(language_id="thai")["echo_check"] is True

    def test_script_check_needs_explicit_opt_in(self):
        """Inference must never switch on a new hard failure by itself."""
        assert policy(language_id="thai")["script_check"] is False
        assert policy(language_id="thai",
                      validation={"target_script": "thai"})["script_check"] is True

    def test_script_check_off_when_disabled_explicitly(self):
        p = policy(validation={"target_script": "thai", "script_check": False})
        assert p["script_check"] is False

    def test_banner_mentions_inference_hint(self):
        assert "target_script" in policy_banner(policy(language_id="thai"))

    def test_banner_does_not_promise_a_latin_check(self):
        banner = policy_banner(policy(language_id="french"))
        assert "n/a" in banner and "set validation.target_script" not in banner


class TestIsEcho:
    def test_identical(self):
        assert is_echo("Hello there.", "Hello there.")

    def test_whitespace_only_difference(self):
        assert is_echo("Hello  there.", "Hello there.")

    def test_case_only_difference(self):
        assert is_echo("HELLO THERE.", "hello there.")

    def test_genuinely_different(self):
        assert not is_echo("Hello there.", "Bonjour.")


class TestTranslatableResidue:
    @pytest.mark.parametrize("text", ["[points]", "...", "{i}{/i}", "   ", "%%"])
    def test_no_residue(self, text):
        assert translatable_residue(text) == ""

    def test_kept_name_alone_has_no_residue(self):
        assert translatable_residue("Maya", ["Maya"]) == ""

    def test_kept_name_with_punctuation_has_no_residue(self):
        """The case that would otherwise false-positive: "Maya!" is a whole line."""
        assert translatable_residue("Maya!", ["Maya"]) == ""

    def test_kept_names_with_a_real_word_between_them_do_have_residue(self):
        """"and" is genuinely untranslated — this SHOULD be flagged."""
        assert translatable_residue("Sage and Maya", ["Sage", "Maya"]) != ""

    def test_kept_name_matching_is_case_insensitive(self):
        assert translatable_residue("MAYA", ["Maya"]) == ""

    def test_ordinary_line_has_residue(self):
        assert translatable_residue("Hello Maya", ["Maya"]) != ""


class TestValidateTranslation:
    THAI_POLICY = {"echo_check": True, "script_check": True,
                   "script_ranges": THAI, "min_script_chars": 1,
                   "allow_identical": set(), "keep_untranslated": []}

    def test_good_translation(self):
        assert validate_translation("Hello there.", "สวัสดี", self.THAI_POLICY) == (True, None)

    def test_echo_rejected(self):
        assert validate_translation("Hello there.", "Hello there.",
                                    self.THAI_POLICY) == (False, "ECHO")

    def test_wrong_script_rejected(self):
        assert validate_translation("Hello there.", "Bonjour.",
                                    self.THAI_POLICY) == (False, "SCRIPT")

    def test_wrong_script_allowed_when_check_disabled(self):
        p = dict(self.THAI_POLICY, script_check=False)
        assert validate_translation("Hello there.", "Bonjour.", p) == (True, None)

    def test_empty_rejected(self):
        assert validate_translation("Hello", "", self.THAI_POLICY) == (False, "EMPTY")
        assert validate_translation("Hello", None, self.THAI_POLICY) == (False, "EMPTY")

    def test_kept_name_passes_through_unchanged(self):
        p = dict(self.THAI_POLICY, keep_untranslated=["Maya"])
        assert validate_translation("Maya", "Maya", p) == (True, None)
        assert validate_translation("Maya!", "Maya!", p) == (True, None)

    def test_token_only_source_passes(self):
        assert validate_translation("[points]", "[points]", self.THAI_POLICY) == (True, None)

    def test_allow_identical_is_the_escape_hatch(self):
        src = "Sage and Maya"
        assert validate_translation(src, src, self.THAI_POLICY)[1] == "ECHO"
        p = dict(self.THAI_POLICY, allow_identical={src})
        assert validate_translation(src, src, p) == (True, None)


class TestTagNesting:
    def test_well_formed(self):
        assert tag_nesting_ok("{i}soft{/i} and {b}loud{/b}")
        assert tag_nesting_ok("{b}{i}both{/i}{/b}")
        assert tag_nesting_ok("plain text, no tags")

    def test_unclosed_is_tolerated(self):
        # Ren'Py auto-closes at end of string — NOT a failure.
        assert tag_nesting_ok("{i}whispered")
        assert tag_nesting_ok("{b}{i}still open")

    def test_mismatched_close_fails(self):
        # Same tag multiset as "{i}a{/i} {b}b{/b}", but crosses the nesting.
        assert not tag_nesting_ok("{i}a {b}b{/i} {/b}")

    def test_close_without_open_fails(self):
        assert not tag_nesting_ok("done{/i}")

    def test_standalone_and_unknown_tags_ignored(self):
        assert tag_nesting_ok("wait{w=0.5}{p}now{nw}")
        assert tag_nesting_ok("{unknown}x{/unknown}")

    def test_tag_with_argument(self):
        assert tag_nesting_ok("{color=#ff0000}red{/color}")
        assert not tag_nesting_ok("{color=#ff0000}{size=30}x{/color}{/size}")

    def test_escaped_braces_are_not_tags(self):
        assert tag_nesting_ok("use {{i}} for italics")


class TestValidateTranslationNesting:
    P = {"echo_check": True, "script_check": False, "script_ranges": [],
         "min_script_chars": 1, "allow_identical": set(), "keep_untranslated": []}

    def test_regression_flagged(self):
        assert validate_translation("{i}a{/i} {b}b{/b}", "{i}ก {b}ข{/i} {/b}",
                                    self.P) == (False, "TAGNEST")

    def test_faithfully_copied_broken_source_not_flagged(self):
        # Source itself is mis-nested; a copy of it is not the translator's bug.
        ok, code = validate_translation("{i}a {b}b{/i} {/b}",
                                        "{i}ก {b}ข{/i} {/b}", self.P)
        assert code != "TAGNEST"

    def test_checked_even_when_residue_empty(self):
        p = dict(self.P, keep_untranslated=["Maya"])
        assert validate_translation("{i}Maya{/i}", "{i}เมยา{/b}", p) == (False, "TAGNEST")


class TestMultisetDiff:
    def test_missing(self):
        assert multiset_diff(["{b}", "{/b}"], ["{b}"]) == (["{/b}"], [])

    def test_extra_duplicate_is_caught(self):
        """Set difference would call this clean; it is not."""
        assert multiset_diff(["{b}"], ["{b}", "{b}"]) == ([], ["{b}"])

    def test_reorder_is_clean(self):
        assert multiset_diff(["{b}", "{i}"], ["{i}", "{b}"]) == ([], [])

    def test_swap_reports_both_sides(self):
        assert multiset_diff(["{b}"], ["{i}"]) == (["{b}"], ["{i}"])


class TestWriteTextAtomic:
    def test_writes_content(self, tmp_path):
        target = tmp_path / "out.json"
        write_text_atomic(target, '{"a": "ก"}')
        assert target.read_text(encoding="utf-8") == '{"a": "ก"}'

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "out.txt"
        write_text_atomic(target, "hi")
        assert target.read_text(encoding="utf-8") == "hi"

    def test_leaves_no_temp_files(self, tmp_path):
        write_text_atomic(tmp_path / "out.txt", "hi")
        assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]

    def test_writes_lf_on_every_platform(self, tmp_path):
        """Deliberate: patches built on Windows and Linux must be identical
        byte-for-byte, since they ship to players and get diffed."""
        target = tmp_path / "out.rpy"
        write_text_atomic(target, "line1\nline2\n")
        assert target.read_bytes() == b"line1\nline2\n"

    def test_failure_leaves_original_intact_and_no_temp(self, tmp_path, monkeypatch):
        target = tmp_path / "out.txt"
        target.write_text("ORIGINAL", encoding="utf-8")

        def boom(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr(validation.os, "replace", boom)
        with pytest.raises(OSError):
            write_text_atomic(target, "REPLACEMENT")

        assert target.read_text(encoding="utf-8") == "ORIGINAL"
        assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]
