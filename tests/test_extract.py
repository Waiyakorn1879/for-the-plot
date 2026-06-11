import json
import subprocess
import sys

from conftest import FIXTURES, SCRIPTS_DIR

import extract_strings


def texts(entries, kind=None):
    return [e["text"] for e in entries if kind is None or e["kind"] == kind]


def run_cli(tmp_path, *args):
    out = tmp_path / "strings.json"
    subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "extract_strings.py"),
         "--src", str(FIXTURES), "--out", str(out), *args],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.read_text(encoding="utf-8"))


class TestMiniGameDefaults:
    """v1.0 behavior on dialog scripts — must never change."""

    def setup_method(self):
        self.entries = extract_strings.extract(FIXTURES / "mini_game.rpy")

    def test_total_occurrences(self):
        assert len(self.entries) == 11

    def test_kinds(self):
        kinds = [e["kind"] for e in self.entries]
        assert kinds.count("say") == 7
        assert kinds.count("narrator") == 1
        assert kinds.count("text") == 1
        assert kinds.count("menu") == 2

    def test_say_speakers(self):
        speakers = {e["speaker"] for e in self.entries if e["kind"] == "say"}
        assert speakers == {"hero", "partner"}

    def test_escaped_quotes_preserved(self):
        assert 'She said \\"hold the door\\" and left.' in texts(self.entries)

    def test_backslash_n_preserved_as_two_chars(self):
        assert "Maybe another day.\\nI should go." in texts(self.entries)
        assert "Maybe another day.\nI should go." not in texts(self.entries)

    def test_vars_and_tags_survive(self):
        assert "Hello there, [partner_name]!" in texts(self.entries, "say")
        assert "I'm {b}really{/b} glad you came." in texts(self.entries, "say")

    def test_menu_choices(self):
        assert texts(self.entries, "menu") == ["Order a coffee", "Leave the cafe"]

    def test_show_text(self):
        assert texts(self.entries, "text") == ["CHAPTER ONE"]

    def test_python_block_and_dollar_skipped(self):
        all_texts = texts(self.entries)
        assert not any("must not be extracted" in t for t in all_texts)

    def test_monologue_kept(self):
        assert "(She seems happier today.)" in texts(self.entries, "say")


class TestDedupe:
    def test_dedupe_default(self, tmp_path):
        entries = run_cli(tmp_path)
        all_texts = texts(entries)
        assert len(all_texts) == len(set(all_texts))
        assert all_texts.count("I'm {b}really{/b} glad you came.") == 1

    def test_no_dedupe(self, tmp_path):
        entries = run_cli(tmp_path, "--no-dedupe")
        assert texts(entries).count("I'm {b}really{/b} glad you came.") == 2


class TestScreensFixtureDefaults:
    """v1.0 quirk on screen files without --screens: bare text/tooltip lines
    look like say lines. Locked in so the default path never changes."""

    def setup_method(self):
        self.entries = extract_strings.extract(FIXTURES / "screens.rpy")

    def test_no_screen_or_ui_kinds(self):
        assert all(e["kind"] in ("say", "menu", "text", "narrator") for e in self.entries)

    def test_quirky_say_speakers(self):
        by_speaker = {}
        for e in self.entries:
            by_speaker.setdefault(e["speaker"], []).append(e["text"])
        assert by_speaker.get("text") == ["Affection level", "[affection_points]"]
        assert by_speaker.get("tooltip") == ["Go to the next scene"]
        assert by_speaker.get("hero") == ["Back to dialog."]

    def test_underscore_strings_not_extracted(self):
        assert "Pocket Cafe" not in texts(self.entries)
        assert "Saved to slot one" not in texts(self.entries)


class TestScreensMode:
    """--screens: screen-language and _() extraction (v1.1)."""

    def setup_method(self):
        self.entries = extract_strings.extract(FIXTURES / "screens.rpy", screens=True)

    def test_screen_kind_entries(self):
        screen_texts = texts(self.entries, "screen")
        assert screen_texts == ["Status", "Affection level", "Continue",
                                "Go to the next scene"]
        assert all(e["speaker"] == "_screen" for e in self.entries
                   if e["kind"] == "screen")

    def test_pure_interpolation_skipped(self):
        assert "[affection_points]" not in texts(self.entries, "screen")

    def test_empty_string_skipped(self):
        assert "" not in texts(self.entries)

    def test_ui_strings(self):
        ui_texts = texts(self.entries, "ui")
        assert sorted(ui_texts) == [
            "Overwrite?", "Pocket Cafe", "Saved to slot one",
            'She yelled, \\"Watch out for [enemy_name]!\\"',
            'Single quoted with "inner" quotes',
        ]
        assert all(e["speaker"] == "_ui" for e in self.entries if e["kind"] == "ui")

    def test_nested_escaped_quotes_in_underscore(self):
        # The audit example: tokens and escapes must survive extraction raw.
        nested = [t for t in texts(self.entries, "ui") if t.startswith("She yelled")]
        assert nested == ['She yelled, \\"Watch out for [enemy_name]!\\"']
        assert "[enemy_name]" in nested[0]

    def test_single_quoted_underscore_extracted(self):
        assert 'Single quoted with "inner" quotes' in texts(self.entries, "ui")

    def test_underscore_text_lines_not_double_counted_as_screen(self):
        screen_texts = texts(self.entries, "screen")
        assert not any("She yelled" in t for t in screen_texts)

    def test_say_outside_screen_still_extracted(self):
        assert texts(self.entries, "say") == ["Back to dialog."]

    def test_quirky_says_replaced_inside_screens(self):
        speakers = {e["speaker"] for e in self.entries}
        assert "text" not in speakers
        assert "tooltip" not in speakers

    def test_mini_game_unaffected_by_screens_flag(self):
        plain = extract_strings.extract(FIXTURES / "mini_game.rpy")
        flagged = extract_strings.extract(FIXTURES / "mini_game.rpy", screens=True)
        assert plain == flagged
