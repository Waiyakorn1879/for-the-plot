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


GREEK = {"validation": {"target_script": "greek"}}


class TestOutputValidity:
    """The gate that used to not exist: an echoed source has an identical
    token signature, so token parity alone let it through."""

    def test_echo_is_a_hard_cat1_failure(self, tmp_path):
        strings = [say("Hello there.", "mc", 1)]
        proc = run_qa(tmp_path, strings, {"Hello there.": "Hello there."},
                      None, GREEK, "--technical-only")
        assert "[UNTRANSLATED]" in proc.stdout
        assert proc.returncode == 1

    def test_echo_does_not_also_report_as_a_roman_phrasing_flag(self, tmp_path):
        strings = [say("Hello there.", "mc", 1)]
        proc = run_qa(tmp_path, strings, {"Hello there.": "Hello there."}, None, GREEK)
        assert "[UNTRANSLATED]" in proc.stdout
        assert "[roman:" not in proc.stdout

    def test_wrong_script_flagged_when_target_script_is_explicit(self, tmp_path):
        strings = [say("Hello there.", "mc", 1)]
        proc = run_qa(tmp_path, strings, {"Hello there.": "Bonjour."},
                      None, GREEK, "--technical-only")
        assert "[SCRIPT]" in proc.stdout
        assert proc.returncode == 1

    def test_no_script_check_without_explicit_target_script(self, tmp_path):
        """Backward compatibility: upgrading must not fail existing profiles."""
        strings = [say("Hello there.", "mc", 1)]
        proc = run_qa(tmp_path, strings, {"Hello there.": "Bonjour."},
                      None, None, "--technical-only")
        assert "[SCRIPT]" not in proc.stdout
        assert proc.returncode == 0
        assert "set validation.target_script" in proc.stdout  # the hint

    def test_kept_name_translating_to_itself_is_clean(self, tmp_path):
        strings = [say("Maya", "mc", 1), say("Maya!", "mc", 2)]
        proc = run_qa(tmp_path, strings, {"Maya": "Maya", "Maya!": "Maya!"},
                      None, dict(GREEK, keep_untranslated=["Maya"]), "--technical-only")
        assert "[UNTRANSLATED]" not in proc.stdout
        assert proc.returncode == 0

    def test_allow_identical_permits_a_specific_line(self, tmp_path):
        strings = [say("OK, Maya.", "mc", 1)]
        trans = {"OK, Maya.": "OK, Maya."}
        flagged = run_qa(tmp_path, strings, trans, None, GREEK, "--technical-only")
        assert "[UNTRANSLATED]" in flagged.stdout
        allowed = run_qa(tmp_path, strings, trans, None,
                         {"validation": {"target_script": "greek",
                                         "allow_identical": ["OK, Maya."]}},
                         "--technical-only")
        assert "[UNTRANSLATED]" not in allowed.stdout
        assert allowed.returncode == 0


class TestTokenParity:
    """SKILL.md promised escape and %% checking here long before it existed."""

    def test_missing_escape_flagged(self, tmp_path):
        src = "Line one" + chr(92) + "nLine two"
        strings = [say(src, "mc", 1)]
        proc = run_qa(tmp_path, strings, {src: "μία γραμμή"}, None, GREEK,
                      "--technical-only")
        assert "[ESC:" in proc.stdout
        assert proc.returncode == 1

    def test_lost_percent_flagged(self, tmp_path):
        strings = [say("50%% done", "mc", 1)]
        proc = run_qa(tmp_path, strings, {"50%% done": "50% έτοιμο"}, None, GREEK,
                      "--technical-only")
        assert "[PCT:1->0]" in proc.stdout
        assert proc.returncode == 1

    def test_duplicated_tag_flagged(self, tmp_path):
        src = "A {b}word{/b} here."
        strings = [say(src, "mc", 1)]
        proc = run_qa(tmp_path, strings, {src: "μία {b}{b}λέξη{/b} εδώ."},
                      None, GREEK, "--technical-only")
        assert "[TAG+:{b}]" in proc.stdout
        assert proc.returncode == 1

    def test_duplicated_variable_flagged(self, tmp_path):
        src = "Hi [name]."
        strings = [say(src, "mc", 1)]
        proc = run_qa(tmp_path, strings, {src: "γεια [name] [name]."},
                      None, GREEK, "--technical-only")
        assert "[VAR+:[name]]" in proc.stdout

    def test_reordered_tags_are_clean(self, tmp_path):
        src = "{b}A{/b} {i}B{/i}"
        strings = [say(src, "mc", 1)]
        proc = run_qa(tmp_path, strings, {src: "{i}Β{/i} {b}Α{/b}"},
                      None, GREEK, "--technical-only")
        assert proc.returncode == 0


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


class TestCharacterDerivedRules:
    """The prompt and the gate must read one source: a `forbidden` term
    declared on a character is enforced with no qa_rules.json at all."""

    SPEAKERS = {
        "mc": {"name": "MC", "gender": "male", "role": "protagonist"},
        "my": {"name": "Maya", "gender": "female", "role": "friend",
               "forbidden": ["GRR"], "must_use": ["nya"]},
        "my_q": {"name": "???", "alias_of": "my"},
    }

    def test_forbidden_term_flagged_without_any_qa_rules_file(self, tmp_path):
        strings = [say("You idiot.", "my", 1)]
        proc = run_qa(tmp_path, strings, {"You idiot.": "GRR κακό"},
                      None, {"speakers": self.SPEAKERS})
        assert "[Maya: forbidden term]" in proc.stdout
        assert proc.returncode == 1

    def test_alias_code_inherits_the_rule(self, tmp_path):
        strings = [say("Who are you?", "my_q", 1)]
        proc = run_qa(tmp_path, strings, {"Who are you?": "GRR ποιος"},
                      None, {"speakers": self.SPEAKERS})
        assert "[Maya: forbidden term]" in proc.stdout

    def test_other_speakers_are_unaffected(self, tmp_path):
        strings = [say("Whatever.", "mc", 1)]
        proc = run_qa(tmp_path, strings, {"Whatever.": "GRR ό,τι"},
                      None, {"speakers": self.SPEAKERS})
        assert "forbidden term" not in proc.stdout

    def test_must_use_is_advisory_not_a_hard_gate(self, tmp_path):
        strings = [say("A reasonably long line of dialogue here.", "my", 1)]
        proc = run_qa(tmp_path, strings,
                      {"A reasonably long line of dialogue here.": "μια αρκετά μακριά γραμμή"},
                      None, {"speakers": self.SPEAKERS})
        assert "[must_use?:nya]" in proc.stdout
        assert proc.returncode == 0        # category 4 never blocks a build

    def test_short_lines_are_exempt_from_must_use(self, tmp_path):
        strings = [say("Hi.", "my", 1)]
        proc = run_qa(tmp_path, strings, {"Hi.": "γεια"},
                      None, {"speakers": self.SPEAKERS})
        assert "must_use" not in proc.stdout

    def test_authored_rule_shadows_the_generated_one(self, tmp_path):
        """A hand-written rule of the same name wins, rather than double-reporting."""
        rules = {"rules": [{"name": "Maya: forbidden term", "category": 3,
                            "speakers": ["my"], "pattern": "GRR"}]}
        strings = [say("You idiot.", "my", 1)]
        proc = run_qa(tmp_path, strings, {"You idiot.": "GRR κακό"},
                      rules, {"speakers": self.SPEAKERS})
        assert proc.stdout.count("[Maya: forbidden term]") == 1
        assert "Cat 3:    1" in proc.stdout      # the authored category, not 2


class TestAliasReachesAuthoredRules:
    """ADR-018 promises one character under several codes behaves as one
    character EVERYWHERE — including in hand-written rules, which don't
    expand aliases the way generated rules do."""

    SPEAKERS = {
        "my": {"name": "Maya", "gender": "female", "role": "friend"},
        "my_q": {"name": "???", "alias_of": "my"},
        "prof": {"name": "Prof", "gender": "female", "role": "teacher"},
    }

    def test_authored_speaker_rule_covers_the_alias(self, tmp_path):
        rules = {"rules": [{"name": "crude", "category": 2,
                            "speakers": ["my"], "pattern": "GRR"}]}
        strings = [say("Who's there?", "my_q", 1)]
        proc = run_qa(tmp_path, strings, {"Who's there?": "GRR ποιος"},
                      rules, {"speakers": self.SPEAKERS})
        assert "[crude]" in proc.stdout
        assert "spk=my_q" in proc.stdout      # raw code still shown, traceable

    def test_authored_group_rule_covers_the_alias(self, tmp_path):
        rules = {"groups": {"girls": ["my"]},
                 "rules": [{"name": "crude girl", "category": 2,
                            "speakers_group": "girls", "pattern": "GRR"}]}
        strings = [say("Who's there?", "my_q", 1)]
        proc = run_qa(tmp_path, strings, {"Who's there?": "GRR ποιος"},
                      rules, {"speakers": self.SPEAKERS})
        assert "[crude girl]" in proc.stdout

    def test_near_condition_counts_the_alias(self, tmp_path):
        rules = {"window": 5, "groups": {"cast": ["my"]},
                 "rules": [{"name": "near maya", "category": 3,
                            "speakers": ["prof"], "pattern": "GRR",
                            "near": {"group": "cast", "min": 1}}]}
        strings = [say("Hi.", "my_q", 1), say("Quiet!", "prof", 2)]
        proc = run_qa(tmp_path, strings,
                      {"Hi.": "γεια", "Quiet!": "GRR ησυχία"},
                      rules, {"speakers": self.SPEAKERS})
        assert "[near maya]" in proc.stdout

    def test_shadowing_an_authored_rule_keeps_alias_coverage(self, tmp_path):
        """Overriding the generated rule must not silently lose the alias."""
        speakers = dict(self.SPEAKERS)
        speakers["my"] = dict(speakers["my"], forbidden=["GRR"])
        rules = {"rules": [{"name": "Maya: forbidden term", "category": 3,
                            "speakers": ["my"], "pattern": "GRR"}]}
        strings = [say("Who's there?", "my_q", 1)]
        proc = run_qa(tmp_path, strings, {"Who's there?": "GRR ποιος"},
                      rules, {"speakers": speakers})
        assert proc.stdout.count("[Maya: forbidden term]") == 1
        assert "Cat 3:    1" in proc.stdout
