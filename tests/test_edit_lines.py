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


def test_two_jobs_on_one_shared_entry_compose(tmp_path):
    jobs = [{"file": "a.rpy", "line": 1, "sub": [["ฉัน", "ข้า"]]},
            {"file": "a.rpy", "line": 2, "sub": [["นาย", "เอ็ง"]]}]
    setup(tmp_path, [say("Go.", "a", 1), say("Go.", "a", 2)], {"Go.": "ฉันและนาย"}, jobs=jobs)
    run(tmp_path, "--write")
    assert json.loads((tmp_path / "tr.json").read_text(encoding="utf-8")) == {"Go.": "ข้าและเอ็ง"}


def test_bad_jobs_exit_with_a_message_not_a_traceback(tmp_path):
    for bad in ([{"file": "a.rpy", "line": 1}], [{"file": "a.rpy", "line": 1, "sub": [["(", "x"]]}]):
        setup(tmp_path, [say("Go.", "a", 1)], {"Go.": "ฉัน"}, jobs=bad)
        p = subprocess.run([sys.executable, str(SCRIPTS_DIR / "edit_lines.py"),
                            "--profile", str(tmp_path / "profile.json"),
                            "--jobs", str(tmp_path / "jobs.json")],
                           capture_output=True, text=True, encoding="utf-8")
        assert p.returncode != 0 and "Traceback" not in p.stderr


def test_backups_never_overwrite_each_other(tmp_path):
    from validation import backup_file
    f = tmp_path / "x.json"
    f.write_text("one")
    a = backup_file(f)
    f.write_text("two")
    b = backup_file(f)
    assert a != b and a.read_text() == "one" and b.read_text() == "two"
