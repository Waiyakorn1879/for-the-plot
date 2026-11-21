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


class TestRenpySourceLiteral:
    """`old`-side literal: decode raw source escapes, re-encode cleanly."""

    def test_plain(self):
        assert build_patch.renpy_source_literal("hello") == '"hello"'

    def test_audit_nested_quotes_example(self):
        raw = 'She yelled, \\"Watch out for [enemy_name]!\\"'
        assert build_patch.renpy_source_literal(raw) == \
            '"She yelled, \\"Watch out for [enemy_name]!\\""'

    def test_unescaped_quotes_from_single_quoted_source(self):
        assert build_patch.renpy_source_literal('with "inner" quotes') == \
            '"with \\"inner\\" quotes"'

    def test_source_newline_escape(self):
        assert build_patch.renpy_source_literal("a\\nb") == '"a\\nb"'

    def test_literal_double_backslash(self):
        # Source raw `path\\end` decodes to a single backslash in the engine;
        # the emitted literal must round-trip to exactly that.
        assert build_patch.renpy_source_literal("path\\\\end") == '"path\\\\end"'

    def test_real_newline(self):
        assert build_patch.renpy_source_literal("a\nb") == '"a\\nb"'

    def test_tokens_untouched(self):
        out = build_patch.renpy_source_literal("Use [item] {b}now{/b}")
        assert out == '"Use [item] {b}now{/b}"'


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
        return tmp_path / "out" / "french_patch"

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

    def test_atomic_write_leaves_no_temp_files(self, tmp_path):
        """A half-written .rpy would be a syntax error in the player's game."""
        out = self.run_build(tmp_path, with_strings=True)
        leftovers = [p.name for p in out.iterdir() if p.suffix == ".tmp"]
        assert leftovers == []
        assert all(p.suffix == ".rpy" for p in out.iterdir())

    def test_nested_quote_string_end_to_end(self, tmp_path):
        profile = {"game_name": "Pocket Cafe", "language_id": "french",
                   "language_name": "French", "progress_file": "tr.json",
                   "strings_file": "strings.json", "output_dir": "out"}
        raw = 'She yelled, \\"Watch out for [enemy_name]!\\"'
        tr = 'Elle a crié : \\"Attention à [enemy_name] !\\"'
        (tmp_path / "profile.json").write_text(json.dumps(profile), encoding="utf-8")
        (tmp_path / "tr.json").write_text(
            json.dumps({raw: tr}, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "strings.json").write_text(json.dumps([
            {"text": raw, "speaker": "_ui", "file": "s.rpy", "line": 1, "kind": "ui"},
        ], ensure_ascii=False), encoding="utf-8")
        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "build_patch.py"),
             "--profile", str(tmp_path / "profile.json")],
            check=True, capture_output=True, text=True, encoding="utf-8",
        )
        content = (tmp_path / "out" / "french_patch" / "02_french_strings.rpy"
                   ).read_text(encoding="utf-8")
        assert '    old "She yelled, \\"Watch out for [enemy_name]!\\""' in content
        assert '    new "Elle a crié : \\"Attention à [enemy_name] !\\""' in content

    def test_no_strings_file_keeps_v10_behavior(self, tmp_path):
        out = self.run_build(tmp_path, with_strings=False)
        dict_content = (out / "01_french_dict.rpy").read_text(encoding="utf-8")
        assert "u'Hello!': u'Salut !'," in dict_content
        assert "u'Continue': u'Continuer'," in dict_content
        assert not (out / "02_french_strings.rpy").exists()


class TestProfileDrivenRuntime:
    """Game-specific runtime behaviour comes from the profile, never the template."""

    BASE = {"language_id": "thai", "language_name": "Thai", "game_name": "G",
            "font": {"regular": "a.ttf"}}

    @staticmethod
    def python_of(rpy):
        """The code of every `init N python:` block, dedented."""
        out, grab = [], False
        for line in rpy.split("\n"):
            if line.startswith("init"):
                grab = line.rstrip().endswith("python:")
            elif grab and (line.startswith("    ") or not line.strip()):
                out.append(line[4:])
            elif line.strip():
                grab = False
        return "\n".join(out)

    def test_unconfigured_profile_emits_no_game_specifics(self):
        rpy = build_patch.build_filter_rpy(self.BASE)
        for needle in ("_store_defaults", "StoreModule", "input_sync", "text_size"):
            assert needle not in rpy
        compile(self.python_of(rpy), "<filter>", "exec")

    def test_configured_runtime_compiles_and_behaves(self):
        profile = dict(self.BASE, store_defaults={"mc": "Neo", "flag": False},
                       safe_store_files=["gallery"],
                       font={"regular": "a.ttf", "text_size": 28},
                       input_sync=[{"prompt": "name?", "vars": {"short": "name[:2]"}}],
                       nameplate_patterns=[{"suffix": "'s Echo", "format": "echo {base}"}])
        rpy = build_patch.build_filter_rpy(
            profile, nameplates={"Ann": "แอน"}, input_prompts={"name?": "ชื่อ?"})
        code = self.python_of(rpy)
        compile(code, "<filter>", "exec")
        assert "gui.text_size = getattr(persistent, \"text_size\", 28)" in code
        # one-time default: guarded by a flag so the player's own size survives
        assert "_size_set" in code and "_ORIG_TEXT_SIZE = gui.text_size" in code

        # run just the store block against stand-ins for the engine
        import types
        block = rpy.split("init -1 python:")[1].split("def _thai_get_speaker")[0]
        block = "\n".join(l[4:] for l in block.split("\n"))
        store = types.SimpleNamespace()
        class StoreModule: pass
        renpy = types.SimpleNamespace(store=store, python=types.SimpleNamespace(StoreModule=StoreModule))
        env = {"renpy": renpy, "sys": sys}
        exec(block.replace("_thai_translations = {}", ""), env)
        assert store.mc == "Neo" and store.flag is False
        assert StoreModule.__getattr__(StoreModule(), "mc") == "Neo"
        import pytest
        with pytest.raises(AttributeError):
            StoreModule.__getattr__(StoreModule(), "nope")

    def test_nameplate_patterns_use_base_lookup(self):
        profile = dict(self.BASE, nameplate_patterns=[{"suffix": "'s Echo", "format": "echo {base}"}])
        rpy = build_patch.build_filter_rpy(profile, nameplates={"Ann": "แอน"})
        ns = {}
        code = self.python_of(rpy).split("def _thai_apply_nameplates")[0]
        exec(code.split("# Character nameplates")[-1].split("_thai_nameplates = ", 1)[0] and
             "_thai_nameplates = " + code.split("_thai_nameplates = ", 1)[1], ns)
        assert ns["_thai_translate_who"]("Ann's Echo") == "echo แอน"
        assert ns["_thai_translate_who"]("Bob") == "Bob"


class TestHandEditWarning:
    def test_unedited_and_edited(self, tmp_path):
        f = tmp_path / "00_x_filter.rpy"
        assert build_patch.hand_edit_warning(f) is None            # missing
        f.write_text(build_patch.stamp_generated("init python:\n    pass\n"), encoding="utf-8")
        assert build_patch.hand_edit_warning(f) is None            # untouched
        f.write_text(f.read_text(encoding="utf-8") + "    hack = 1\n", encoding="utf-8")
        assert "edited by hand" in build_patch.hand_edit_warning(f)

    def test_unstamped_file_not_judged(self, tmp_path):
        f = tmp_path / "old.rpy"
        f.write_text("init python:\n    pass\n", encoding="utf-8")
        assert build_patch.hand_edit_warning(f) is None


def test_speaker_overrides_reach_the_dictionary_file():
    (_, content), = build_patch.build_dict_rpy(
        {"Hi!": "สวัสดี"}, "thai", "Thai",
        speaker_translations={("an", "Hi!"): "สวัสดีค่ะ", ("mc", "Hi!"): "สวัสดีครับ"})
    assert "_thai_speaker_translations.update" in content
    assert "(u'an', u'Hi!')" in content and "(u'mc', u'Hi!')" in content


def test_bad_speaker_overrides_are_not_shipped(tmp_path):
    import json, subprocess, sys
    from conftest import SCRIPTS_DIR
    (tmp_path / "profile.json").write_text(json.dumps({
        "language_id": "thai", "language_name": "Thai", "progress_file": "t.json",
        "validation": {"target_script": "thai"}}), encoding="utf-8")
    (tmp_path / "t.json").write_text(json.dumps({"Thanks [n].": "ขอบคุณ [n]"}, ensure_ascii=False),
                                     encoding="utf-8")
    (tmp_path / "speaker_translations.json").write_text(json.dumps({
        "a::Thanks [n].": "Thanks [n].",          # echo
        "b::Thanks [n].": "ขอบคุณ {b}",            # token damage
        "c::Thanks [n].": "ขอบคุณครับ [n]"}, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPTS_DIR / "build_patch.py"), "--profile",
                           str(tmp_path / "profile.json"), "--out", str(tmp_path / "out")],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "2 override(s) NOT shipped" in proc.stdout
    built = (tmp_path / "out" / "thai_patch" / "01_thai_dict.rpy").read_text(encoding="utf-8")
    assert "(u'c', u'Thanks [n].'): u'ขอบคุณครับ [n]'" in built
    assert "(u'a'," not in built and "(u'b'," not in built


def test_alternate_apostrophe_spellings():
    import build_patch as bp
    alts = bp.alternate_spellings(["It’s late.", "Don't go.", 'She said \\"it\'s\\".',
                                   "Plain.", "We're in.", "We’re in."])
    assert alts == {"It's late.": "It’s late.", "Don’t go.": "Don't go.",
                    'She said \\"it’s\\".': 'She said \\"it\'s\\".'}
    # an escaped apostrophe is left alone, and a spelling that only differs by
    # quote escaping from a real key is that key at runtime: not emitted
    assert bp.alternate_spellings(["Rock \\'n roll"]) == {}
    assert bp.alternate_spellings(['It’s \\"x\\"', 'It\'s "x"']) == {}


def test_alternates_are_emitted_and_load_as_the_same_translation():
    import build_patch as bp
    tr = {"It’s late.": "A", "Plain.": "B", "Don't.": "C"}
    sp = {("a", "It’s late."): "A2"}
    files = dict(bp.build_dict_rpy(tr, "x", "X", chunk=2, speaker_translations=sp))
    assert "alternate apostrophe" in files[0] and "alternate apostrophe" not in files[1]
    ns = {"_x_translations": {}, "_x_speaker_translations": {}}
    for content in files.values():
        body = content.split("init 0 python:\n", 1)[1]
        exec("\n".join(l[4:] for l in body.split("\n")), ns)
    assert ns["_x_translations"] == {**tr, "It's late.": "A", "Don’t.": "C"}
    assert ns["_x_speaker_translations"] == {**sp, ("a", "It's late."): "A2"}
    # nothing to add -> output is unchanged from before this feature
    plain = dict(bp.build_dict_rpy({"Plain.": "B"}, "x", "X"))[0]
    assert "alternate" not in plain and plain.count(".update(") == 1


def test_layout_flag(tmp_path):
    (tmp_path / "profile.json").write_text(json.dumps({
        "game_name": "G", "language_id": "french", "language_name": "French",
        "progress_file": "tr.json", "output_dir": "out"}), encoding="utf-8")
    (tmp_path / "tr.json").write_text(json.dumps({"Hi": "Salut"}), encoding="utf-8")
    for extra, where in (([], "french_patch"), (["--layout", "tl"], "tl/french")):
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "build_patch.py"),
                        "--profile", str(tmp_path / "profile.json"), *extra],
                       check=True, capture_output=True, text=True, encoding="utf-8")
        assert (tmp_path / "out" / where / "00_french_filter.rpy").is_file()
