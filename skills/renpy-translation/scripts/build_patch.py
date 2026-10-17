"""Build runtime-filter Ren'Py patch files from a translations JSON.

Output (into <out>/tl/<language_id>/):
  00_<lang>_filter.rpy   — text filter + toggle key + optional font swap
  01_<lang>_dict.rpy     — generated translation dictionary (optionally split)
  02_<lang>_strings.rpy  — `translate <lang> strings:` blocks for screen/ui
                           kinds (only when a strings file with such kinds
                           is available; see extract_strings.py --screens)

Approach: config.say_menu_text_filter as a runtime translator.
No hash/ID generation needed; no game source modification. The filter
chains with any pre-existing filter (e.g. SanchoMod) instead of stomping it.

Usage:
  python build_patch.py --profile profile.json
  python build_patch.py --profile profile.json --translations my.json --out dist/ --split-size 5000
"""
import argparse
import json
import re
import sys
from pathlib import Path

from validation import configure_console, write_text_atomic

configure_console()


def load_profile(path):
    profile_path = Path(path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return profile, profile_path.parent


def py2_unicode_repr(s):
    """Emit u'...' literal that is valid in both py2 and py3 Ren'Py.
    Escape backslashes and single quotes; leave non-ASCII chars raw (file is UTF-8).

    Known limitation (accepted): a literal double-backslash in the SOURCE
    text (e.g. a Windows path in dialog) is emitted double-escaped and the
    dict key won't match at runtime. Never observed in real VN dialog
    (0 of 36k strings in the reference project); this function is
    parity-locked against that proven output — do not "fix" without
    re-running the full parity regression."""
    s = s.replace("\\", "\\\\").replace("'", "\\'")
    # Source data carries literal \n etc. as the 2-char sequence "\\n" from the
    # rpy file; the escaping above turned that into "\\\\n". Reverse it so the
    # emitted literal keeps the original escape.
    s = s.replace("\\\\n", "\\n").replace("\\\\t", "\\t").replace('\\\\"', '\\"')
    # Escape any REAL control chars (actual newline/tab/CR) that slipped into
    # the data so they don't break the single-line string literal.
    s = s.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n").replace("\t", "\\t")
    return "u'" + s + "'"


def renpy_string_literal(s):
    """Emit a double-quoted Ren'Py string literal for the `new` side of
    translate-strings blocks. Input is translator/runtime text where typed
    escape sequences (\\n etc.) are intended as escapes and a lone backslash
    must survive — same contract as py2_unicode_repr."""
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    # Escapes that were already escapes in the extracted source stay escapes.
    s = s.replace("\\\\n", "\\n").replace("\\\\t", "\\t").replace('\\\\\\"', '\\"')
    # Real control chars must not break the literal.
    s = s.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n").replace("\t", "\\t")
    return '"' + s + '"'


_SOURCE_ESCAPE_RE = re.compile(r'\\(.)')


def _decode_source_escapes(s):
    """Raw text between quotes in .rpy source -> the engine-decoded string."""
    return _SOURCE_ESCAPE_RE.sub(
        lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def renpy_source_literal(s):
    """Literal for the `old` side of translate-strings blocks. Input is the
    extractor's RAW source text (escapes undecoded); `old` must match the
    engine-decoded string exactly, so decode once and re-encode cleanly —
    deterministic for any nesting depth, including literal backslashes."""
    s = _decode_source_escapes(s)
    s = (s.replace("\\", "\\\\").replace('"', '\\"')
          .replace("\r\n", "\\n").replace("\r", "\\n")
          .replace("\n", "\\n").replace("\t", "\\t"))
    return '"' + s + '"'


def py_literal(v):
    """Python-2-safe literal for a JSON scalar from the profile (str/bool/num/None)."""
    return py2_unicode_repr(v) if isinstance(v, str) else repr(v)


def build_store_block(profile):
    """Replay/gallery safety net, entirely profile-driven.

    `store_defaults` {name: value}: seeded into the store when the game has not
    defined the name — scene replays run outside the story flow, so variables
    assigned only during play are undefined there and raise NameError. List
    only names the game never `default`s: a seeded value makes Ren'Py's own
    `default` skip that name.
    `safe_store_files` [substrings]: a missing store attribute read from a
    frame whose file name contains one of these returns "" instead of raising.
    Neither key set -> no output, and the store is never touched.
    """
    defaults = profile.get("store_defaults") or {}
    files = profile.get("safe_store_files") or []
    if not (defaults or files):
        return ""
    entries = "".join(f"        {py2_unicode_repr(k)}: {py_literal(v)},\n"
                      for k, v in sorted(defaults.items()))
    out = f"""    # Replay safety net (profile: store_defaults / safe_store_files)
    _store_defaults = {{
{entries}    }}
    for _k, _v in _store_defaults.items():
        if not hasattr(renpy.store, _k):
            setattr(renpy.store, _k, _v)
"""
    if files:
        out += f"""
    _safe_store_files = ({", ".join(py2_unicode_repr(f.lower()) for f in files)},)
    _orig_store_getattr = getattr(renpy.python.StoreModule, "__getattr__", None)
    def _safe_store_getattr(self, key):
        if key in _store_defaults:
            return _store_defaults[key]
        try:
            f = sys._getframe(1)
            for _ in range(5):
                if f:
                    fn = getattr(f.f_code, "co_filename", "").lower()
                    if any(x in fn for x in _safe_store_files):
                        return ""
                    f = f.f_back
        except Exception:
            pass
        if _orig_store_getattr:
            return _orig_store_getattr(self, key)
        raise AttributeError("'StoreModule' object has no attribute '%s'" % key)
    renpy.python.StoreModule.__getattr__ = _safe_store_getattr
"""
    return out + "\n"


def build_filter_rpy(profile, nameplates=None, input_prompts=None):
    lang = profile["language_id"]
    ident = re.sub(r"\W", "_", lang)  # safe python identifier fragment
    lang_name = profile.get("language_name", lang)
    game = profile.get("game_name", "a Ren'Py game")
    toggle_key = profile.get("toggle_key", "K_F11")
    auto_set = profile.get("auto_set_language", False)
    font = profile.get("font")
    store_block = build_store_block(profile)

    parts = []
    parts.append(f'''# {lang_name} translation runtime loader for {game}
# Generated by build_patch.py (For the Plot) - DO NOT EDIT BY HAND
#   - Press {toggle_key.replace("K_", "")} anytime to toggle {lang_name} <-> original language

init -1 python:
    import sys
    _{ident}_translations = {{}}
    _{ident}_speaker_translations = {{}}
    _{ident}_filter_calls = [0]
    _{ident}_filter_hits = [0]
    _{ident}_last_miss = [""]

{store_block}    def _{ident}_get_speaker():
        try:
            f = sys._getframe(1)
            for _ in range(5):
                if f is None:
                    break
                loc = f.f_locals
                if 'self' in loc:
                    s = loc['self']
                    if hasattr(s, 'who'):
                        return getattr(s, 'who', None)
                f = f.f_back
        except Exception:
            pass
        return None

    def _{ident}_say_filter(text):
        _{ident}_filter_calls[0] += 1
        try:
            if renpy.game.preferences.language == "{lang}":
                spk = _{ident}_get_speaker()
                if spk and (spk, text) in _{ident}_speaker_translations:
                    _{ident}_filter_hits[0] += 1
                    return _{ident}_speaker_translations[(spk, text)]
                if text in _{ident}_translations:
                    _{ident}_filter_hits[0] += 1
                    return _{ident}_translations[text]
                else:
                    _{ident}_last_miss[0] = text
        except Exception:
            pass
        return text

    def _{ident}_toggle():
        cur = renpy.game.preferences.language
        new = None if cur == "{lang}" else "{lang}"
        renpy.change_language(new)
        renpy.notify(
            "Lang=%s | dict=%d | calls=%d hits=%d | filter=%s" % (
                "{lang}" if new == "{lang}" else "default",
                len(_{ident}_translations),
                _{ident}_filter_calls[0],
                _{ident}_filter_hits[0],
                "ours" if (config.say_menu_text_filter is _{ident}_say_filter
                          or getattr(config.say_menu_text_filter, "_{ident}_owned", False))
                       else "OVERRIDDEN",
            )
        )

    config.keymap["{ident}_toggle"] = ["{toggle_key}"]
    config.underlay.append(renpy.Keymap({ident}_toggle=_{ident}_toggle))

# Wrap whatever filter exists so we cooperate with mods (e.g. SanchoMod)
# instead of stomping their filter.
init 1999 python:
    def _{ident}_install_filter():
        prev = config.say_menu_text_filter
        if prev is _{ident}_say_filter:
            return
        if prev is None:
            inner = lambda t: t
        else:
            inner = prev

        # Translate FIRST (original -> {lang_name}), THEN let the mod style the
        # output. This way dict keys match the raw text the engine emits.
        def _chained(text):
            if text is None:
                return text
            t = _{ident}_say_filter(text)
            if t is None:
                t = text
            try:
                t2 = inner(t)
                return t if t2 is None else t2
            except Exception:
                return t

        # Mark our chained filter so we don't re-wrap on every callback
        _chained._{ident}_owned = True
        if getattr(prev, "_{ident}_owned", False):
            return  # already chained
        config.say_menu_text_filter = _chained

    _{ident}_install_filter()
    config.start_callbacks.append(_{ident}_install_filter)
    config.after_load_callbacks.append(_{ident}_install_filter)
''')

    if auto_set:
        parts.append(f'''
# Auto-switch to {lang_name} on first ever launch
init 2000 python:
    def _{ident}_autostart():
        if not persistent._{ident}_auto_set:
            renpy.change_language("{lang}")
            persistent._{ident}_auto_set = True
    config.start_callbacks.append(_{ident}_autostart)
''')

    parts.append(f'''
# Empty translate block registers "{lang}" as a language.
translate {lang} python:
    pass
''')

    if font:
        regular = font["regular"]
        italic = font.get("italic", regular)
        replace_fonts = font.get("replace_fonts", [])
        size_scale = font.get("size_scale", 1.0)
        base_sizes = font.get("base_sizes", {})
        # Optional dialogue size cap (font.text_size): only when the profile asks,
        # since forcing a size on a game that doesn't need it shrinks its text.
        cap = font.get("text_size")
        text_size_block = (
            f"        if getattr(persistent, \"text_size\", {cap + 1}) > {cap}:\n"
            f"            persistent.text_size = {cap}\n"
            f"        gui.text_size = {cap}\n" if cap else "")
        default_styles = ["default", "say_dialogue", "say_thought", "say_label",
                          "namebox", "namebox_label", "button", "button_text",
                          "choice_button", "choice_button_text", "notify",
                          "notify_text", "input", "menu_choice", "menu_choice_button"]
        styles = font.get("styles", default_styles)

        replace_list = ",\n                    ".join(
            json.dumps(replace_fonts[i:i + 3])[1:-1]
            for i in range(0, len(replace_fonts), 3)
        )
        sizes_body = ", ".join(f'"{k}": {v}' for k, v in base_sizes.items())
        styles_tuple = ",\n                      ".join(
            ", ".join(f'"{s}"' for s in styles[i:i + 4])
            for i in range(0, len(styles), 4)
        )

        parts.append(f'''
# Swap the game's original fonts for {regular} whenever {lang_name} is the
# active language. Two mechanisms:
#   1. style overrides for every style that displays text
#   2. config.font_replacement_map so any missed style still falls back
init 2001 python:
    _{ident.upper()}_FONT = "{regular}"
    _{ident.upper()}_FONT_ITALIC = "{italic}"
    _{ident.upper()}_REPLACE_FONTS = [{replace_list}]

    # Per-style size scaling: adjust if the target font renders smaller or
    # larger than the originals at the same point size.
    _{ident.upper()}_SIZE_SCALE = {size_scale}
    _{ident.upper()}_BASE_SIZES = {{ {sizes_body} }}

    def _{ident}_apply_font():
        if renpy.game.preferences.language != "{lang}":
            return
{text_size_block}        for sname in ({styles_tuple},):
            try:
                getattr(style, sname).font = _{ident.upper()}_FONT
            except Exception:
                pass
            if sname in _{ident.upper()}_BASE_SIZES:
                try:
                    getattr(style, sname).size = int(_{ident.upper()}_BASE_SIZES[sname] * _{ident.upper()}_SIZE_SCALE)
                except Exception:
                    pass

    def _{ident}_apply_font_map():
        # font_replacement_map: when these fonts would render target-language
        # chars, substitute the target font instead.
        for f in _{ident.upper()}_REPLACE_FONTS:
            for bold in (True, False):
                for italic in (True, False):
                    # Map to the real Bold (or Bold Italic) file; clear the synthetic
                    # bold/italic flags so we don't double-bold an already-bold font.
                    tgt = _{ident.upper()}_FONT_ITALIC if italic else _{ident.upper()}_FONT
                    config.font_replacement_map[(f, bold, italic)] = (tgt, False, False)

    _{ident}_apply_font_map()
    _{ident}_apply_font()
    config.start_callbacks.append(_{ident}_apply_font)
    config.after_load_callbacks.append(_{ident}_apply_font)
    # Hook language change to re-apply
    _prev_change_language = renpy.change_language
    def _{ident}_change_language(lang, force=False):
        result = _prev_change_language(lang, force) if force else _prev_change_language(lang)
        _{ident}_apply_font()
        if '_{ident}_apply_nameplates' in globals():
            _{ident}_apply_nameplates()
        return result
    renpy.change_language = _{ident}_change_language
''')

    if nameplates:
        nameplate_entries = ",\n        ".join(
            f"{py2_unicode_repr(k)}: {py2_unicode_repr(v)}"
            for k, v in sorted(nameplates.items())
        )
        # Possessive/derived speaker names ("X's Echo"), declared per game in
        # profile.nameplate_patterns: [{"suffix": "'s Echo", "format": "... {base}"}].
        # `base` is the name with the suffix removed, looked up in nameplates.
        pattern_entries = ",\n        ".join(
            f"({py2_unicode_repr(p['suffix'])}, {py2_unicode_repr(p['format'])})"
            for p in profile.get("nameplate_patterns") or []
        )
        parts.append(f'''
# Character nameplates in {lang_name}
init 2002 python:
    _{ident}_nameplates = {{
        {nameplate_entries}
    }}

    _{ident}_nameplate_patterns = [
        {pattern_entries}
    ]

    def _{ident}_translate_who(who):
        if not who:
            return who
        if who in _{ident}_nameplates:
            return _{ident}_nameplates[who]
        for suffix, fmt in _{ident}_nameplate_patterns:
            if who.endswith(suffix):
                base = who[:-len(suffix)]
                return fmt.replace(u"{{base}}", _{ident}_nameplates.get(base, base))
        return who

    def _{ident}_apply_nameplates():
        is_active = (renpy.game.preferences.language == "{lang}")
        for k, v in list(renpy.store.__dict__.items()):
            if isinstance(v, renpy.character.ADVCharacter):
                if not hasattr(v, "_{ident}_orig_name"):
                    v._{ident}_orig_name = v.name
                if is_active:
                    orig = v._{ident}_orig_name
                    if orig is not None:
                        v.name = _{ident}_translate_who(orig)
                else:
                    if hasattr(v, "_{ident}_orig_name"):
                        v.name = v._{ident}_orig_name

    _orig_show_display_say = renpy.character.show_display_say
    def _{ident}_show_display_say(who, what, *args, **kwargs):
        if renpy.game.preferences.language == "{lang}" and who:
            who = _{ident}_translate_who(who)
        return _orig_show_display_say(who, what, *args, **kwargs)
    renpy.character.show_display_say = _{ident}_show_display_say

    _{ident}_apply_nameplates()
    config.start_callbacks.append(_{ident}_apply_nameplates)
    config.after_load_callbacks.append(_{ident}_apply_nameplates)
''')

    # renpy.input hook: translated prompts, and variables derived from what the
    # player typed (profile.input_sync) — a game that precomputes forms of the
    # protagonist's name ("Or", "O-Orion") must recompute them for a Thai name,
    # or replays and later scenes keep the English-derived forms.
    sync = profile.get("input_sync") or []
    if input_prompts or sync:
        prompt_entries = ",\n        ".join(
            f"{py2_unicode_repr(k)}: {py2_unicode_repr(v)}"
            for k, v in sorted((input_prompts or {}).items())
        )
        sync_entries = ",\n        ".join(
            "(" + py2_unicode_repr(rule["prompt"]) + ", [" + ", ".join(
                f"({py2_unicode_repr(var)}, compile({py2_unicode_repr(expr)}, '<input_sync>', 'eval'))"
                for var, expr in sorted(rule["vars"].items())) + "])"
            for rule in sync
        )
        parts.append(f'''
# Input prompts and input-derived variables in {lang_name}
init 2002 python:
    _{ident}_input_prompts = {{
        {prompt_entries}
    }}

    # (substring of the original prompt, [(variable, compiled expression of `name`)])
    _{ident}_input_sync = [
        {sync_entries}
    ]

    _orig_input = renpy.exports.input
    def _{ident}_input(prompt, *args, **kwargs):
        p = prompt
        if renpy.game.preferences.language == "{lang}" and prompt:
            p = _{ident}_input_prompts.get(prompt, _{ident}_translations.get(prompt, prompt))
        result = _orig_input(p, *args, **kwargs)
        name = (result or "").strip()
        if name:
            for needle, assigns in _{ident}_input_sync:
                if needle in (prompt or ""):
                    for var, code in assigns:
                        setattr(renpy.store, var, eval(code, {{}}, {{"name": name}}))
        return result
    renpy.exports.input = _{ident}_input
''')

    return "".join(parts)


def build_dict_rpy(translations, ident, lang_name, chunk=None, speaker_translations=None):
    """Yield (filename_suffix, content) for one or more dict files."""
    items = list(translations.items())
    if not chunk or chunk <= 0:
        chunk = len(items) or 1
    n_files = (len(items) + chunk - 1) // chunk if items else 1
    for fi in range(max(n_files, 1)):
        part = items[fi * chunk:(fi + 1) * chunk]
        lines = [
            f"# {lang_name} translation dictionary — auto-generated"
            + (f" (part {fi + 1}/{n_files})" if n_files > 1 else "") + "\n",
            "# DO NOT EDIT BY HAND\n\n",
            "init 0 python:\n",
            f"    _{ident}_translations.update({{\n",
        ]
        for eng, tr in part:
            lines.append(f"        {py2_unicode_repr(eng)}: {py2_unicode_repr(tr)},\n")
        lines.append("    })\n")

        # In the first dict file, append character-specific translation overrides if present
        if fi == 0 and speaker_translations:
            lines.append(f"\n    _{ident}_speaker_translations.update({{\n")
            for (spk, eng), tr in speaker_translations.items():
                lines.append(f"        ({py2_unicode_repr(spk)}, {py2_unicode_repr(eng)}): {py2_unicode_repr(tr)},\n")
            lines.append("    })\n")

        yield fi, "".join(lines)


def build_strings_rpy(strings_translations, lang, lang_name):
    lines = [
        f"# {lang_name} screen/UI string translations — auto-generated\n",
        "# DO NOT EDIT BY HAND\n\n",
        f"translate {lang} strings:\n",
    ]
    for eng, tr in strings_translations.items():
        lines.append(f"\n    old {renpy_source_literal(eng)}\n")
        lines.append(f"    new {renpy_string_literal(tr)}\n")
    return "".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Build a runtime-filter Ren'Py translation patch")
    ap.add_argument("--profile", required=True, help="profile.json")
    ap.add_argument("--translations", help="translations JSON (overrides profile progress_file)")
    ap.add_argument("--strings", help="strings JSON from extract_strings.py; screen/ui kinds "
                                      "are routed into a translate-strings file "
                                      "(defaults to profile strings_file when it exists)")
    ap.add_argument("--out", help="output dir (overrides profile output_dir); patch goes to <out>/tl/<lang>/")
    ap.add_argument("--split-size", type=int, default=0,
                    help="max entries per dict file (0 = single file)")
    args = ap.parse_args()

    profile, base = load_profile(args.profile)
    lang = profile["language_id"]
    ident = re.sub(r"\W", "_", lang)
    lang_name = profile.get("language_name", lang)

    trans_path = Path(args.translations) if args.translations else base / profile.get("progress_file", "translations.json")
    out_root = Path(args.out) if args.out else base / profile.get("output_dir", "output")
    out_dir = out_root / "tl" / lang
    out_dir.mkdir(parents=True, exist_ok=True)

    translations = json.loads(trans_path.read_text(encoding="utf-8"))
    print(f"Building patch with {len(translations)} translations...")

    # Route screen/ui kinds (which the say filter can't reach) into a
    # translate-strings file, when kind metadata is available.
    strings_path = Path(args.strings) if args.strings else base / profile.get("strings_file", "strings.json")
    strings_translations = {}
    if strings_path.is_file():
        entries = json.loads(strings_path.read_text(encoding="utf-8"))
        for e in entries:
            if e.get("kind") in ("screen", "ui") and e["text"] in translations:
                strings_translations[e["text"]] = translations[e["text"]]
    dict_translations = {k: v for k, v in translations.items()
                         if k not in strings_translations}

    # Load character nameplates if configured
    nameplates_path = base / profile.get("nameplates_file", "nameplates.json")
    nameplates = {}
    if nameplates_path.is_file():
        nameplates = json.loads(nameplates_path.read_text(encoding="utf-8"))
        print(f"Loaded {len(nameplates)} character nameplates from {nameplates_path.name}")

    # Load input prompts if configured
    input_prompts_path = base / profile.get("input_prompts_file", "input_prompts.json")
    input_prompts = {}
    if input_prompts_path.is_file():
        input_prompts = json.loads(input_prompts_path.read_text(encoding="utf-8"))
        print(f"Loaded {len(input_prompts)} input prompt translations from {input_prompts_path.name}")

    # Atomic: an interrupted build must not leave a truncated .rpy, which
    # would be a syntax error inside the player's game folder.
    filter_path = out_dir / f"00_{ident}_filter.rpy"
    write_text_atomic(filter_path, build_filter_rpy(profile, nameplates=nameplates, input_prompts=input_prompts))
    print(f"Wrote {filter_path}")

    # Load character-specific translation overrides if speaker_translations.json exists
    speaker_path = base / profile.get("speaker_translations_file", "speaker_translations.json")
    speaker_translations = {}
    if speaker_path.is_file():
        spk_raw = json.loads(speaker_path.read_text(encoding="utf-8"))
        for k, v in spk_raw.items():
            if "::" in k:
                spk, eng = k.split("::", 1)
                speaker_translations[(spk, eng)] = v
        print(f"Loaded {len(speaker_translations)} character-specific overrides from {speaker_path.name}")

    for fi, content in build_dict_rpy(dict_translations, ident, lang_name, args.split_size, speaker_translations):
        dict_path = out_dir / f"{fi + 1:02d}_{ident}_dict.rpy"
        write_text_atomic(dict_path, content)
        print(f"Wrote {dict_path}")

    if strings_translations:
        strings_out = out_dir / f"02_{ident}_strings.rpy"
        write_text_atomic(strings_out,
                          build_strings_rpy(strings_translations, lang, lang_name))
        print(f"Wrote {strings_out} ({len(strings_translations)} screen/UI strings)")

    print(f"\nDeploy: copy {out_dir} into the game's game/tl/ folder "
          f"(and the target font files into game/).")


if __name__ == "__main__":
    main()
