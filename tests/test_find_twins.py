from find_twins import find_twins


def test_differing_twins_found_identical_ignored():
    tr = {'Say \\"hi\\"': "A", 'Say "hi"': "B",
          "It’s": "X", "It's": "X",
          "Solo": "S"}
    assert [n for n, _ in find_twins(tr)] == ['Say "hi"']


def test_value_escaping_mirroring_key_is_not_a_difference():
    assert find_twins({'a \\"b\\"': 'x \\"y\\"', 'a "b"': 'x "y"'}) == []


def test_cli_also_checks_speaker_overrides(tmp_path):
    import json, subprocess, sys
    from conftest import SCRIPTS_DIR
    (tmp_path / "profile.json").write_text(json.dumps({"progress_file": "t.json"}))
    (tmp_path / "t.json").write_text(json.dumps({"Solo": "S"}))
    run = lambda: subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "find_twins.py"), "--profile",
         str(tmp_path / "profile.json")], capture_output=True, text=True, encoding="utf-8")
    assert run().returncode == 0
    (tmp_path / "speaker_translations.json").write_text(json.dumps(
        {'a::Say \\"hi\\"': "A", 'a::Say "hi"': "B", 'b::Say "hi"': "C"}))
    proc = run()
    assert proc.returncode == 1 and "Differing twins: 1" in proc.stdout
