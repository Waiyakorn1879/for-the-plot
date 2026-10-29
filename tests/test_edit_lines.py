import json
import subprocess
import sys

from conftest import SCRIPTS_DIR


def say(text, spk, line):
    return {"text": text, "speaker": spk, "kind": "say", "file": "a.rpy", "line": line}


def setup(tmp_path, strings, tr, sp=None, jobs=None):
    (tmp_path / "profile.json").write_text(json.dumps({
        "language_id": "thai", "language_name": "Thai", "target_script": "thai",
        "progress_file": "tr.json"}), encoding="utf-8")
    for name, data in (("strings", strings), ("tr", tr), ("speaker_translations", sp or {}),
                       ("jobs", jobs)):
        (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def run(tmp_path, *extra):
    return subprocess.run([sys.executable, str(SCRIPTS_DIR / "edit_lines.py"),
                           "--profile", str(tmp_path / "profile.json"),
                           "--jobs", str(tmp_path / "jobs.json"), *extra],
                          capture_output=True, text=True, encoding="utf-8").stdout


JOB = [{"file": "a.rpy", "line": 1, "sub": [["ฉัน", "ข้า"]]}]


def test_dry_run_then_write_with_backup(tmp_path):
    setup(tmp_path, [say("I [x] go.", "a", 1)], {"I [x] go.": "ฉัน [x] ไป"}, jobs=JOB)
    out = run(tmp_path)
    assert "ข้า [x] ไป" in out and "dry-run" in out
    assert json.loads((tmp_path / "tr.json").read_text(encoding="utf-8")) == {"I [x] go.": "ฉัน [x] ไป"}
    run(tmp_path, "--write")
    assert json.loads((tmp_path / "tr.json").read_text(encoding="utf-8")) == {"I [x] go.": "ข้า [x] ไป"}
    assert list(tmp_path.glob("tr.json.bak-*"))


def test_shared_key_warned_and_token_loss_rejected(tmp_path):
    setup(tmp_path, [say("Go.", "a", 1), say("Go.", "b", 2)], {"Go.": "ฉันไป"}, jobs=JOB)
    assert "SHARED" in run(tmp_path)
    job = [{"file": "a.rpy", "line": 1, "sub": [["ฉัน", ""]]}]
    setup(tmp_path, [say("Hi [x].", "a", 1)], {"Hi [x].": "ฉัน [x]"}, jobs=job)
    assert "REJECTED" not in run(tmp_path)   # removing text keeps tokens: allowed
    job = [{"file": "a.rpy", "line": 1, "sub": [[r"\[x\]", ""]]}]
    setup(tmp_path, [say("Hi [x].", "a", 1)], {"Hi [x].": "ฉัน [x]"}, jobs=job)
    assert "REJECTED" in run(tmp_path)
