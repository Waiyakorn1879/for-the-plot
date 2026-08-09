import json
import subprocess
import sys

from conftest import SCRIPTS_DIR


def run_init(tmp_path, *args, game="Game-1.0-pc", project="Game-Thai",
             language="thai"):
    (tmp_path / game / "game").mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "init_project.py"),
         "--game", game, "--language", language, "--dir", project, *args],
        cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8",
    )
    return proc, tmp_path / project


class TestScaffold:
    def test_creates_the_expected_files(self, tmp_path):
        proc, project = run_init(tmp_path)
        assert proc.returncode == 0, proc.stderr
        for name in ("profile.json", "TRANSLATION.md", "translation-guide.md",
                     "qa_rules.json", ".gitignore",
                     "CLAUDE.md", "AGENTS.md", "GEMINI.md"):
            assert (project / name).is_file(), f"missing {name}"
        assert (project / "decompiled").is_dir()
        assert (project / "QC").is_dir()

    def test_profile_is_valid_json_and_wired_to_the_other_files(self, tmp_path):
        _, project = run_init(tmp_path)
        profile = json.loads((project / "profile.json").read_text(encoding="utf-8"))
        assert profile["language_id"] == "thai"
        assert profile["style_guide_file"] == "translation-guide.md"
        assert profile["qa_rules_file"] == "qa_rules.json"
        assert profile["source_dir"] == "decompiled"

    def test_non_latin_target_gets_an_enforceable_script(self, tmp_path):
        _, project = run_init(tmp_path)
        profile = json.loads((project / "profile.json").read_text(encoding="utf-8"))
        assert profile["validation"]["target_script"] == "thai"

    def test_latin_target_leaves_script_unset_and_says_why(self, tmp_path):
        """A Latin target shares codepoints with the source; the check can't
        discriminate, so promising it would be false advice."""
        proc, project = run_init(tmp_path, language="french", project="G-Fr")
        profile = json.loads((project / "profile.json").read_text(encoding="utf-8"))
        assert "target_script" not in profile["validation"]
        assert "target_script is unset" in proc.stdout

    def test_gitignore_excludes_game_text(self, tmp_path):
        _, project = run_init(tmp_path)
        ignored = (project / ".gitignore").read_text(encoding="utf-8")
        for path in ("translations.json", "strings.json", "decompiled/", ".ftp/"):
            assert path in ignored

    def test_harness_stubs_point_at_the_single_content_file(self, tmp_path):
        """The content exists once; each harness file only references it."""
        _, project = run_init(tmp_path)
        for stub in ("CLAUDE.md", "AGENTS.md", "GEMINI.md"):
            assert "TRANSLATION.md" in (project / stub).read_text(encoding="utf-8")

    def test_instruction_file_records_an_absolute_game_path(self, tmp_path):
        """Read from another shell, a relative path means nothing."""
        _, project = run_init(tmp_path)
        text = (project / "TRANSLATION.md").read_text(encoding="utf-8")
        assert (tmp_path / "Game-1.0-pc").resolve().as_posix() in text


class TestGuards:
    def test_refuses_to_overwrite_an_existing_profile(self, tmp_path):
        run_init(tmp_path)
        proc, _ = run_init(tmp_path)
        assert proc.returncode != 0
        assert "refusing to overwrite" in proc.stdout + proc.stderr

    def test_force_overwrites(self, tmp_path):
        run_init(tmp_path)
        proc, _ = run_init(tmp_path, "--force")
        assert proc.returncode == 0

    def test_refuses_to_scaffold_inside_the_game_install(self, tmp_path):
        """ADR-014: the game installation is read-only."""
        proc, _ = run_init(tmp_path, project="Game-1.0-pc/tl-work")
        assert proc.returncode != 0
        assert "inside the game install" in proc.stdout + proc.stderr
        assert not (tmp_path / "Game-1.0-pc" / "tl-work").exists()

    def test_refuses_a_missing_game_path(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "init_project.py"),
             "--game", "nope", "--language", "thai", "--dir", "x"],
            cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode != 0
        assert "does not exist" in proc.stdout + proc.stderr

    def test_keeps_a_pre_existing_harness_file(self, tmp_path):
        """CLAUDE.md may already hold unrelated rules — never clobber it."""
        (tmp_path / "Game-Thai").mkdir(parents=True)
        (tmp_path / "Game-Thai" / "CLAUDE.md").write_text("MY OWN RULES",
                                                          encoding="utf-8")
        proc, project = run_init(tmp_path)
        assert proc.returncode == 0
        assert (project / "CLAUDE.md").read_text(encoding="utf-8") == "MY OWN RULES"
        assert "kept existing CLAUDE.md" in proc.stdout


class TestScaffoldFeedsThePipeline:
    def test_generated_profile_runs_qa_end_to_end(self, tmp_path):
        """The scaffold's own output must be immediately usable."""
        _, project = run_init(tmp_path)
        (project / "strings.json").write_text(json.dumps(
            [{"text": "Hello.", "speaker": "hero", "file": "a.rpy",
              "line": 1, "kind": "say"}]), encoding="utf-8")
        (project / "translations.json").write_text(
            json.dumps({"Hello.": "สวัสดี"}, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "qa_check.py"),
             "--profile", str(project / "profile.json"), "--technical-only"],
            capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stdout
        assert "script=on" in proc.stdout
