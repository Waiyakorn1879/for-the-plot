import json
import subprocess
import sys

from conftest import SCRIPTS_DIR

import speaker_overrides

SPEAKERS = {"mc": {"name": "Max", "gender": "male"}, "an": {"name": "Annie", "gender": "female"},
            "bg": {"name": "Guy", "gender": "male", "role": "background extra"}}


def say(text, spk, also=None):
    e = {"text": text, "speaker": spk, "kind": "say", "file": "a.rpy", "line": 1}
    if also:
        e["also_spoken_by"] = also
    return e


def project(tmp_path, strings):
    (tmp_path / "profile.json").write_text(json.dumps({
        "language_id": "thai", "language_name": "Thai", "speakers": SPEAKERS,
        "strings_file": "strings.json", "progress_file": "tr.json"}), encoding="utf-8")
    (tmp_path / "strings.json").write_text(json.dumps(strings), encoding="utf-8")
    (tmp_path / "tr.json").write_text(json.dumps({"Hi!": "สวัสดี!"}), encoding="utf-8")


def run(tmp_path, *args):
    return subprocess.run([sys.executable, str(SCRIPTS_DIR / "speaker_overrides.py"), *args,
                           "--profile", str(tmp_path / "profile.json")],
                          capture_output=True, text=True, encoding="utf-8")


def test_needed_only_for_both_genders():
    strings = [say("Hi!", "an", ["mc"]), say("Yes.", "mc", ["bg"]), say("Hm.", "an", ["zz"]),
               say("Solo.", "mc")]
    assert speaker_overrides.needed(strings, SPEAKERS) == {"Hi!": {"an": "female", "mc": "male"}}


def test_needed_works_without_dedupe():
    strings = [say("Hi!", "an"), say("Hi!", "mc")]
    assert set(speaker_overrides.needed(strings, SPEAKERS)) == {"Hi!"}


def test_todo_then_merge_gates_gender_and_tokens(tmp_path):
    project(tmp_path, [say("Hi, [n]!", "an", ["mc"])])
    assert "2 (speaker, text)" in run(tmp_path, "todo").stdout
    todo = json.loads((tmp_path / "speaker_translations_todo.json").read_text(encoding="utf-8"))
    assert {i["key"] for i in todo} == {"an::Hi, [n]!", "mc::Hi, [n]!"}

    filled = {"an::Hi, [n]!": "สวัสดีค่ะ [n]!",
              "mc::Hi, [n]!": "สวัสดีค่ะ [n]!",        # female form for a male speaker
              "mc::Nope": "x"}                          # not a needed pair
    (tmp_path / "filled.json").write_text(json.dumps(filled), encoding="utf-8")
    proc = run(tmp_path, "merge", "--file", str(tmp_path / "filled.json"))
    assert proc.returncode == 1 and "WRONG-GENDER(male)" in proc.stdout
    saved = json.loads((tmp_path / "speaker_translations.json").read_text(encoding="utf-8"))
    assert saved == {"an::Hi, [n]!": "สวัสดีค่ะ [n]!"}

    filled = {"mc::Hi, [n]!": "สวัสดีครับ"}            # drops [n]
    (tmp_path / "filled.json").write_text(json.dumps(filled), encoding="utf-8")
    assert "VAR:" in run(tmp_path, "merge", "--file", str(tmp_path / "filled.json")).stdout

    filled = {"mc::Hi, [n]!": "สวัสดีครับ [n]!"}
    (tmp_path / "filled.json").write_text(json.dumps(filled), encoding="utf-8")
    assert run(tmp_path, "merge", "--file", str(tmp_path / "filled.json")).returncode == 0
    assert "2/2" in run(tmp_path, "status").stdout
    # nothing left to do once both are saved
    run(tmp_path, "todo")
    assert json.loads((tmp_path / "speaker_translations_todo.json").read_text(encoding="utf-8")) == []
