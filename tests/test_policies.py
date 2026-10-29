import json
import subprocess
import sys

from conftest import SCRIPTS_DIR

import pair_audit
import punctuation
import thai_text
from validation import mask_tokens, unmask_tokens

CFG = {"short_words": 2}


def test_mask_roundtrip_protects_tokens():
    s = r"Hi [x!u] {i}a!{/i} 100%% \n ok!"
    masked, toks = mask_tokens(s)
    assert "[x!u]" not in masked and unmask_tokens(masked, toks) == s


def test_replace_word_thai_boundaries_and_tokens():
    f = lambda t: thai_text.replace_word(t, "แก", "เอ็ง", not_before=("ป้า",),
                                         not_after=("ง", "น", "ล"))
    assert f("แกเอง แกใส่ [แก]") == "เอ็งเอง เอ็งใส่ [แก]"      # leading vowels do not block
    assert f("ป้าแก แกง แกน") == "ป้าแก แกง แกน"                 # compounds left alone


def test_keep_exclamation_rules():
    for src in ("STOP IT!", "No way!!", "*Shouts* Come here now please", "Hey!"):
        assert punctuation.keep(src, CFG), src
    for src in ("That was a great day for all of us!", "Well, I did it!"):
        assert not punctuation.keep(src, CFG), src


def test_soften():
    assert punctuation.soften("ไป! {i}เลย!{/i} ดีนะ?! จริง!ๆ [x!u]!") == "ไป {i}เลย{/i} ดีนะ? จริง ๆ [x!u]"


def test_over_policy_ignores_echo_and_kept():
    assert punctuation.over_policy("It is a long day!", "วันยาวนาน!", CFG)
    assert not punctuation.over_policy("Hey!", "เฮ้!", CFG)
    assert not punctuation.over_policy("It is a long day!", "It is a long day!", CFG)


def row(spk, line, text, label="L", kind="say"):
    return {"speaker": spk, "line": line, "text": text, "label": label,
            "file": "a.rpy", "kind": kind}


def test_pair_audit_runs_break_on_third_voice_and_skip_thoughts():
    strings = [row("a", 1, "one"), row("b", 2, "two"), row("a", 3, "three"),
               row("a", 4, "four"), row("c", 5, "third"), row("b", 6, "five"),
               row("a", 7, "(six)"), row("b", 8, "seven")]
    tr = {"one": "ฉัน", "two": "ok", "three": "นาย", "four": "ok", "third": "ฉัน",
          "five": "ฉัน", "(six)": "(ฉัน)", "seven": "ok"}
    rule = {"name": "fixed", "between": ["a", "b"], "forbid": "ฉัน|นาย"}
    got = [(f[3]) for f in pair_audit.audit(strings, tr, {}, {}, [rule])]
    # run 1-4 flags 1 and 3; the third voice (5) is outside any run; run 6-8 flags 6;
    # the thought on line 7 is skipped
    assert got == [1, 3, 6]


def test_empty_block_enables_policy_and_qa_counts_it(tmp_path):
    assert punctuation.policy({}) is None
    assert punctuation.policy({"punctuation": {"exclamation": {}}}) == {"short_words": 2}
    (tmp_path / "profile.json").write_text(json.dumps({
        "language_id": "greek", "language_name": "Greek", "strings_file": "s.json",
        "progress_file": "t.json", "punctuation": {"exclamation": {}}}), encoding="utf-8")
    (tmp_path / "s.json").write_text(json.dumps([
        {"text": "It is a long day!", "speaker": "a", "file": "a.rpy", "line": 1, "kind": "say"}]))
    (tmp_path / "t.json").write_text(json.dumps({"It is a long day!": "μακριά μέρα!"}))
    out = subprocess.run([sys.executable, str(SCRIPTS_DIR / "qa_check.py"), "--profile",
                          str(tmp_path / "profile.json")], capture_output=True, text=True,
                         encoding="utf-8").stdout
    assert "Exclamation policy: 1 line(s)" in out


def test_replace_word_is_literal_and_ignores_placeholder_digits():
    assert thai_text.replace_word("แกไป", "แก", r"\1\n") == r"\1\nไป"
    assert thai_text.replace_word("[a] 0", "0", "Z") == "[a] Z"


def test_soften_keeps_words_apart_across_a_tag():
    assert punctuation.soften("Go!{w=1}Now") == "Go {w=1}Now"
    assert punctuation.soften("Go!{/i} Now") == "Go{/i} Now"


def test_pair_audit_rejects_malformed_rules():
    import pytest
    for bad in ({"name": "x", "between": ["a", "b"]},
                {"name": "x", "between": ["a", "a"], "forbid": "x"},
                {"name": "x", "between": ["a", "b"], "forbid": "("},
                {"name": "x", "between": ["a", "b"], "forbid": "x", "min_run": 1}):
        with pytest.raises(SystemExit):
            pair_audit.check_rules([bad])
