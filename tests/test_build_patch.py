import json
import subprocess
import sys

from conftest import SCRIPTS_DIR

import build_patch


class TestPy2UnicodeRepr:
    def test_plain(self):
        assert build_patch.py2_unicode_repr("hello") == "u'hello'"

    def test_single_quote_escaped(self):
        assert build_patch.py2_unicode_repr("it's") == "u'it\\'s'"

    def test_literal_backslash_n_preserved(self):
        # two-char sequence backslash+n from the rpy source stays an escape
        assert build_patch.py2_unicode_repr("a\\nb") == "u'a\\nb'"

    def test_real_newline_becomes_escape(self):
        assert build_patch.py2_unicode_repr("a\nb") == "u'a\\nb'"

    def test_real_tab_and_cr(self):
        assert build_patch.py2_unicode_repr("a\tb\rc") == "u'a\\tb\\nc'"

    def test_escaped_double_quote_preserved(self):
        assert build_patch.py2_unicode_repr('say \\"hi\\"') == "u'say \\\"hi\\\"'"

    def test_literal_evaluates_to_runtime_form(self):
        # The emitted literal must evaluate to what the engine emits at runtime
        # (escape sequences interpreted), since that's what the filter matches on.
        cases = {
            "plain": "plain",
            "it's": "it's",
            "tag {b}x{/b} [v]": "tag {b}x{/b} [v]",
            "a\\nb": "a\nb",        # source escape -> real newline at runtime
            'q\\"q': 'q"q',          # source escape -> real quote at runtime
        }
        for src, runtime in cases.items():
            assert eval(build_patch.py2_unicode_repr(src)) == runtime


class TestRenpyStringLiteral:
    def test_plain(self):
        assert build_patch.renpy_string_literal("hello") == '"hello"'

    def test_double_quote(self):
        assert build_patch.renpy_string_literal('a "b" c') == '"a \\"b\\" c"'

    def test_already_escaped_quote_not_doubled(self):
        assert build_patch.renpy_string_literal('a \\"b\\"') == '"a \\"b\\""'

    def test_real_newline(self):
        assert build_patch.renpy_string_literal("a\nb") == '"a\\nb"'


class TestFilterGeneration:
    BASE = {"game_name": "Pocket Cafe", "language_id": "french",
            "language_name": "French"}

    def test_identifiers_and_language(self):
        out = build_patch.build_filter_rpy(self.BASE)
        assert "_french_translations = {}" in out
        assert 'preferences.language == "french"' in out
        assert "translate french python:" in out
        assert "K_F11" in out  # default toggle key

    def test_autostart_conditional(self):
        out = build_patch.build_filter_rpy(self.BASE)
        assert "_autostart" not in out
        out2 = build_patch.build_filter_rpy({**self.BASE, "auto_set_language": True})
        assert "_french_autostart" in out2

    def test_font_section_conditional(self):
        out = build_patch.build_filter_rpy(self.BASE)
        assert "font_replacement_map" not in out
        out2 = build_patch.build_filter_rpy({
            **self.BASE,
            "font": {"regular": "MyFont.ttf", "replace_fonts": ["Old.ttf"],
                     "size_scale": 1.2, "base_sizes": {"say_dialogue": 30}},
        })
        assert "font_replacement_map" in out2
        assert "MyFont.ttf" in out2
        assert "1.2" in out2

    def test_custom_toggle_key(self):
        out = build_patch.build_filter_rpy({**self.BASE, "toggle_key": "K_F10"})
        assert "K_F10" in out


class TestDictGeneration:
    TRANSLATIONS = {"one": "un", "two": "deux", "three": "trois"}

    def test_single_file(self):
        files = list(build_patch.build_dict_rpy(self.TRANSLATIONS, "french", "French"))
        assert len(files) == 1
        _, content = files[0]
        assert "_french_translations.update({" in content
        assert "u'one': u'un'," in content
        assert content.startswith("# French translation dictionary")

    def test_split_size(self):
        files = list(build_patch.build_dict_rpy(self.TRANSLATIONS, "french", "French", chunk=2))
        assert len(files) == 2
        assert "part 1/2" in files[0][1]
        joined = files[0][1] + files[1][1]
        for en, fr in self.TRANSLATIONS.items():
            assert f"u'{en}': u'{fr}'," in joined


class TestKindRouting:
    """screen/ui kinds route into 02_<lang>_strings.rpy translate-strings blocks."""

    def run_build(self, tmp_path, with_strings):
        profile = {"game_name": "Pocket Cafe", "language_id": "french",
                   "language_name": "French", "progress_file": "tr.json",
                   "strings_file": "strings.json", "output_dir": "out"}
        (tmp_path / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
        (tmp_path / "tr.json").write_text(json.dumps({
            "Hello!": "Salut !",
            "Continue": "Continuer",
            "Pocket Cafe": "Cafe de Poche",
        }), encoding="utf-8")
        if with_strings:
            (tmp_path / "strings.json").write_text(json.dumps([
                {"text": "Hello!", "speaker": "hero", "file": "a.rpy", "line": 1, "kind": "say"},
                {"text": "Continue", "speaker": "_screen", "file": "s.rpy", "line": 2, "kind": "screen"},
                {"text": "Pocket Cafe", "speaker": "_ui", "file": "s.rpy", "line": 3, "kind": "ui"},
            ]), encoding="utf-8")
        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "build_patch.py"),
             "--profile", str(tmp_path / "profile.json")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        return tmp_path / "out" / "tl" / "french"

    def test_routing_with_strings_file(self, tmp_path):
        out = self.run_build(tmp_path, with_strings=True)
        dict_content = (out / "01_french_dict.rpy").read_text(encoding="utf-8")
        strings_content = (out / "02_french_strings.rpy").read_text(encoding="utf-8")
        # say stays in the runtime dict
        assert "u'Hello!': u'Salut !'," in dict_content
        # screen/ui move to translate-strings blocks
        assert "u'Continue'" not in dict_content
        assert "u'Pocket Cafe'" not in dict_content
        assert "translate french strings:" in strings_content
        assert '    old "Continue"' in strings_content
        assert '    new "Continuer"' in strings_content
        assert '    old "Pocket Cafe"' in strings_content

    def test_no_strings_file_keeps_v10_behavior(self, tmp_path):
        out = self.run_build(tmp_path, with_strings=False)
        dict_content = (out / "01_french_dict.rpy").read_text(encoding="utf-8")
        assert "u'Hello!': u'Salut !'," in dict_content
        assert "u'Continue': u'Continuer'," in dict_content
        assert not (out / "02_french_strings.rpy").exists()
