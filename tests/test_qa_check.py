import json
import subprocess
import sys

from conftest import SCRIPTS_DIR


def run_qa(tmp_path, strings, translations, qa_rules=None, profile_extra=None, *args):
    profile = {
        "game_name": "Pocket Cafe", "language_id": "greek", "language_name": "Greek",
        "strings_file": "strings.json", "progress_file": "tr.json",
    }
    if qa_rules is not None:
        profile["qa_rules_file"] = "qa_rules.json"
        (tmp_path / "qa_rules.json").write_text(
            json.dumps(qa_rules, ensure_ascii=False), encoding="utf-8")
    if profile_extra:
        profile.update(profile_extra)
    (tmp_path / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
    (tmp_path / "strings.json").write_text(
        json.dumps(strings, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "tr.json").write_text(
        json.dumps(translations, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "qa_check.py"),
         "--profile", str(tmp_path / "profile.json"), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc


def say(text, speaker, line, file="a.rpy"):
    return {"text": text, "speaker": speaker, "file": file, "line": line, "kind": "say"}


STRINGS = [
    say("Good morning, class.", "prof", 10),
    say("Hello teach!", "mc", 12),
    say("(Ugh, morning.)", "mc", 14),
    say("Where is the {b}library{/b}, [name]?", "mc", 16),
    say("Long line that is quite verbose and contains many words indeed.", "mc", 18),
    say("No translation here.", "mc", 20),
    say("My friend Robert is here.", "amy", 5, file="b.rpy"),
]

TRANSLATIONS = {
    "Good morning, class.": "α β γ",
    "Hello teach!": "GRR οι",
    "(Ugh, morning.)": "(GRR)",
    "Where is the {b}library{/b}, [name]?": "πού;",
    "Long line that is quite verbose and contains many words indeed.": "α",
    "My friend Robert is here.": "ο φίλος μου Robert εδώ GRR",
}

RULES = {
    "window": 5,
    "groups": {"teachers": ["prof"], "girls": ["amy"]},
    "rules": [
        {"name": "crude near teacher", "category": 2, "speakers": ["mc"],
         "skip_monologue": True, "pattern": "GRR",
         "near": {"group": "teachers", "min": 1}},
        {"name": "crude girl", "category": 3, "speakers_group": "girls",
         "pattern": "GRR"},
    ],
}


class TestFullRun:
    def test_all_categories(self, tmp_path):
        proc = run_qa(tmp_path, STRINGS, TRANSLATIONS, RULES)
        assert proc.returncode == 1  # hard issues present
        out = proc.stdout
        assert "[MISSING]" in out and "No translation here." in out
        assert "[TAG:{/b},{b}]" in out
        assert "[VAR:[name]]" in out
        assert "[crude near teacher]" in out and "Hello teach!" in out
        assert "[crude girl]" in out
        assert "[roman:Robert]" in out
        assert "[short?]" in out

    def test_monologue_exempt(self, tmp_path):
        proc = run_qa(tmp_path, STRINGS, TRANSLATIONS, RULES)
        assert "(Ugh, morning.)" not in proc.stdout

    def test_technical_only(self, tmp_path):
        proc = run_qa(tmp_path, STRINGS, TRANSLATIONS, RULES, None, "--technical-only")
        out = proc.stdout
        assert "[MISSING]" in out
        assert "[crude near teacher]" not in out
        assert "[roman:Robert]" not in out
        assert proc.returncode == 1  # cat-1 issues are hard

    def test_keep_untranslated_whitelists_roman(self, tmp_path):
        proc = run_qa(tmp_path, STRINGS, TRANSLATIONS, RULES,
                      {"keep_untranslated": ["Robert"]})
        assert "[roman:Robert]" not in proc.stdout

    def test_clean_run_exits_zero(self, tmp_path):
        strings = [say("Hi.", "mc", 1)]
        proc = run_qa(tmp_path, strings, {"Hi.": "γεια"})
        assert proc.returncode == 0
        assert "CLEAN" in proc.stdout

    def test_report_file(self, tmp_path):
        proc = run_qa(tmp_path, STRINGS, TRANSLATIONS, RULES, None,
                      "--report", str(tmp_path / "report.txt"))
        report = (tmp_path / "report.txt").read_text(encoding="utf-8")
        assert "[MISSING]" in report


class TestNearDominance:
    def make(self, speakers_before, speakers_after):
        strings, line = [], 1
        for sp in speakers_before:
            strings.append(say(f"l{line}", sp, line))
            line += 1
        strings.append(say("Target line.", "mc", line))
        line += 1
        for sp in speakers_after:
            strings.append(say(f"l{line}", sp, line))
            line += 1
        translations = {s["text"]: "x" for s in strings}
        translations["Target line."] = "GRR"
        return strings, translations

    RULES = {
        "window": 10,
        "groups": {"ga": ["aa"], "gb": ["bb"]},
        "rules": [{"name": "dominant rule", "category": 2, "speakers": ["mc"],
                   "pattern": "GRR",
                   "near": {"group": "ga", "min": 2, "dominant_over": ["gb"]}}],
    }

    def test_fires_when_dominant(self, tmp_path):
        strings, tr = self.make(["aa", "aa"], ["bb"])
        proc = run_qa(tmp_path, strings, tr, self.RULES)
        assert "[dominant rule]" in proc.stdout

    def test_silent_when_outnumbered(self, tmp_path):
        strings, tr = self.make(["aa", "aa"], ["bb", "bb", "bb"])
        proc = run_qa(tmp_path, strings, tr, self.RULES)
        assert "[dominant rule]" not in proc.stdout

    def test_silent_below_min(self, tmp_path):
        strings, tr = self.make(["aa"], [])
        proc = run_qa(tmp_path, strings, tr, self.RULES)
        assert "[dominant rule]" not in proc.stdout
