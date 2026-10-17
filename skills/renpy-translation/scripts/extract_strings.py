"""Extract translatable strings from Ren'Py .rpy files.

Outputs a JSON list of {text, speaker, file, line, kind, label}
- kind = "say" | "menu" | "text" | "narrator"
- with --screens additionally: "screen" (literal text/textbutton/label/tooltip
  inside screen blocks) and "ui" (_()-wrapped strings anywhere, and literal
  renpy.input() prompts).
- label = the enclosing Ren'Py label, or null outside any. It is the script's
  own scene boundary, and relationships.py scopes addressee resolution to it;
  strings.json files extracted before v1.5 simply lack the field.
- label_cast (say lines only) = every speaker code that speaks anywhere in that
  label. Recorded BEFORE deduplication, because dedupe is what makes the
  question unanswerable downstream: a minor character whose only line in a
  scene is "Yeah." loses it to an earlier duplicate, and a three-person scene
  then looks like a two-person one to anything counting surviving speakers.
Duplicates are skipped by exact text match unless --no-dedupe is given
(keep duplicates when targeting native `translate` blocks, where each
occurrence can translate differently).

Note: "screen"/"ui" strings are NOT reachable by the runtime say filter —
build_patch.py routes them into a `translate <lang> strings:` file instead.

Usage:
  python extract_strings.py --src decompiled/ --out strings.json
  python extract_strings.py --profile profile.json --screens
"""
import argparse
import json
import re
import sys
from pathlib import Path

from validation import configure_console, write_text_atomic

configure_console()

# Ren'Py say statement: `who [attrs] "text" [(args)] [nointeract] [id x] [with trans]`.
# Every trailer is optional and may repeat in any order; a line that silently
# fails to match here is never extracted, so QA never sees its speaker (the
# "a \"Hi!\" with dissolve" bug). Allows escaped quotes inside the text.
_SAY_TRAILER = r'(?:\s*\([^)]*\)|\s+nointeract|\s+id\s+\w+|\s+with\s+[^:"\n]+?)*'
SAY_RE = re.compile(
    r'^(\s*)([a-zA-Z_]\w*)((?:\s+[\w@.]+)*)\s+"((?:[^"\\]|\\.)*)"' + _SAY_TRAILER + r'\s*$'
)
# Narrator-only say: just `"text"` (optionally with a transition)
NARRATOR_RE = re.compile(
    r'^(\s*)"((?:[^"\\]|\\.)*)"' + _SAY_TRAILER + r'\s*$'
)
# Menu choice: `    "Choice text" if cond:` or `    "Choice text":`
MENU_RE = re.compile(
    r'^(\s+)"((?:[^"\\]|\\.)*)"(?:\s+if\s+[^:]+)?:\s*$'
)
# show text "..."
SHOWTEXT_RE = re.compile(
    r'^(\s*)show\s+text\s+"((?:[^"\\]|\\.)*)"'
)
# label statement: `label chapter1:` / `label ch1(x=1):` / `label .retry:`
# The label is the only scene boundary a Ren'Py script states outright, so it
# is what addressee resolution scopes its dyad test to (see relationships.py).
LABEL_RE = re.compile(r'^label\s+(\.?\w+)\s*(?:\([^)]*\))?\s*:\s*$')
# screen definition header: `screen name(...):`
SCREEN_START_RE = re.compile(r'^screen\s+\w+.*:\s*$')
# literal-string screen statements: text/textbutton/label/tooltip "..."
SCREEN_TEXT_RE = re.compile(
    r'^\s*(?:text|textbutton|label|tooltip)\s+"((?:[^"\\]|\\.)*)"'
)
# _("...") / _('...') translatable-marked strings (several can share a line);
# the trailing _( of __("...") matches too, covering the immediate form.
UNDERSCORE_RE = re.compile(r'_\(\s*(["\'])((?:(?!\1)[^\\]|\\.)*)\1\s*\)')

# renpy.input("prompt", ...) — a literal prompt is shown to the player but is
# not `_()`-marked, so it is invisible to every other pattern. (An already
# `_()`-wrapped prompt starts with `_(`, not a quote, and is not matched twice.)
INPUT_RE = re.compile(r'renpy\.input\(\s*(["\'])((?:(?!\1)[^\\]|\\.)*)\1')

# tokens with no translatable content once vars/tags are stripped
_VAR_TAG_RE = re.compile(r'\[[^\]]+\]|\{[^}]+\}')


def has_translatable_content(txt):
    """False for pure-interpolation/markup strings like "[points]"."""
    return any(c.isalnum() for c in _VAR_TAG_RE.sub("", txt))

# Ren'Py keywords/commands that look like "speaker" but aren't
NON_SPEAKERS = {
    "scene", "show", "hide", "play", "stop", "queue", "pause",
    "call", "jump", "return", "menu", "label", "if", "elif",
    "else", "while", "for", "with", "window", "image", "screen",
    "init", "define", "default", "transform", "python", "translate",
    "voice", "nvl", "centered", "extend", "style", "$",
    "camera", "use", "add",
}

# Text before the first quote of a say-shaped line: `who [attrs]` or nothing.
_SAY_PREFIX_RE = re.compile(r'^\s*(?:[\w@.]+(?:\s+[\w@.]+)*)?\s*$')


def extract(rpy_path: Path, screens=False, suspects=None):
    """`suspects`, if a list, collects (file, line, text) for lines shaped like
    dialogue that no pattern accepted — the extractor's blind spots."""
    out = []
    in_python_block = False
    python_indent = None
    in_screen_block = False
    screen_indent = None
    label = None
    with rpy_path.open(encoding="utf-8", errors="replace") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # _( "..." ) strings are translatable wherever they appear,
            # including python blocks and $ lines — scan before any skips.
            if screens and not stripped.startswith("#"):
                for m in (*UNDERSCORE_RE.finditer(line), *INPUT_RE.finditer(line)):
                    txt = m.group(2)
                    if txt.strip() and has_translatable_content(txt):
                        out.append({"text": txt, "speaker": "_ui",
                                    "file": rpy_path.name, "line": lineno, "kind": "ui",
                                    "label": label})

            # Track python blocks (skip them)
            if in_python_block:
                if stripped == "" or indent > python_indent:
                    continue
                in_python_block = False
            if re.match(r'^(init\s+(-?\d+\s+)?)?python(\s+\w+)?\s*:\s*$', stripped):
                in_python_block = True
                python_indent = indent
                continue
            if re.match(r'^\$\s', stripped):
                continue  # python one-liner
            if stripped.startswith("#"):
                continue  # comment

            # Track screen blocks: inside them, only literal screen-language
            # statements are translatable — say/menu/narrator regexes would
            # misread them, so never fall through.
            if screens:
                if in_screen_block:
                    if stripped == "" or indent > screen_indent:
                        m = SCREEN_TEXT_RE.match(line)
                        if m:
                            txt = m.group(1)
                            if txt.strip() and has_translatable_content(txt):
                                out.append({"text": txt, "speaker": "_screen",
                                            "file": rpy_path.name, "line": lineno,
                                            "kind": "screen", "label": label})
                        continue
                    in_screen_block = False
                if SCREEN_START_RE.match(stripped):
                    in_screen_block = True
                    screen_indent = indent
                    continue

            # label statement — records the scene a line belongs to. A label
            # runs until the next one (Ren'Py falls through), which is exactly
            # the span addressee resolution treats as one scene.
            m = LABEL_RE.match(stripped)
            if m:
                name = m.group(1)
                if name.startswith("."):
                    # A local label belongs to its enclosing global one; on its
                    # own `.retry` is not unique across the file.
                    label = (label.split(".", 1)[0] + name) if label else name
                else:
                    label = name
                continue

            # show text "..."
            m = SHOWTEXT_RE.match(line)
            if m:
                txt = m.group(2)
                if txt.strip():
                    out.append({"text": txt, "speaker": "_text",
                                "file": rpy_path.name, "line": lineno, "kind": "text",
                                "label": label})
                continue

            # speaker "text"
            m = SAY_RE.match(line)
            if m:
                speaker = m.group(2)
                txt = m.group(4)
                if speaker in NON_SPEAKERS:
                    pass  # fall through to narrator/menu checks
                else:
                    if txt.strip():
                        out.append({"text": txt, "speaker": speaker,
                                    "file": rpy_path.name, "line": lineno, "kind": "say",
                                    "label": label})
                    continue

            # menu choice
            m = MENU_RE.match(line)
            if m:
                txt = m.group(2)
                if txt.strip():
                    out.append({"text": txt, "speaker": "_menu",
                                "file": rpy_path.name, "line": lineno, "kind": "menu",
                                "label": label})
                continue

            # narrator (bare string on its own line, indented)
            m = NARRATOR_RE.match(line)
            if m and indent > 0:
                txt = m.group(2)
                if txt.strip():
                    out.append({"text": txt, "speaker": "narrator",
                                "file": rpy_path.name, "line": lineno, "kind": "narrator",
                                "label": label})
                continue

            if suspects is not None and '"' in stripped:
                first = stripped.split()[0]
                if first not in NON_SPEAKERS and _SAY_PREFIX_RE.match(line.split('"', 1)[0]):
                    suspects.append((rpy_path.name, lineno, stripped))
    return stamp_label_cast(out)


def stamp_label_cast(entries):
    """Record each label's full speaking cast on its `say` lines.

    Computed here, over one file's complete output, because this is the last
    point at which the answer is knowable: `main()` deduplicates by text
    afterwards, and dedupe can only ever *remove* a speaker from a label — so a
    cast counted downstream can turn a three-party scene into an apparent
    two-party one, never the reverse. That is the dangerous direction, and it
    would resolve confidently to the wrong addressee.
    """
    # Keyed by label name within one file. Two scenes can only ever share a key
    # through a malformed script (a local `.retry` before any global label, so
    # its qualified name is bare), and the effect of a shared key is a UNION of
    # casts — which can turn a dyad into a multi-party refusal but never the
    # reverse. The collision over-refuses; it cannot mis-resolve.
    cast = {}
    for entry in entries:
        if entry["kind"] == "say" and entry["label"]:
            cast.setdefault(entry["label"], set()).add(entry["speaker"])
    for entry in entries:
        if entry["kind"] == "say" and entry["label"]:
            entry["label_cast"] = sorted(cast[entry["label"]])
    return entries


def load_profile(path):
    profile_path = Path(path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return profile, profile_path.parent


def main():
    ap = argparse.ArgumentParser(description="Extract translatable strings from Ren'Py sources")
    ap.add_argument("--profile", help="profile.json (provides source_dir/strings_file defaults)")
    ap.add_argument("--src", help="directory containing .rpy files (overrides profile source_dir)")
    ap.add_argument("--out", help="output JSON path (overrides profile strings_file)")
    ap.add_argument("--no-dedupe", action="store_true",
                    help="keep every occurrence instead of deduplicating by text")
    ap.add_argument("--screens", action="store_true",
                    help="also extract screen-language strings (text/textbutton/"
                         "label/tooltip) and _()-wrapped strings")
    args = ap.parse_args()

    src = out = None
    if args.profile:
        profile, base = load_profile(args.profile)
        if profile.get("source_dir"):
            src = base / profile["source_dir"]
        if profile.get("strings_file"):
            out = base / profile["strings_file"]
    if args.src:
        src = Path(args.src)
    if args.out:
        out = Path(args.out)
    if src is None or out is None:
        ap.error("need --src and --out, or a --profile providing source_dir and strings_file")
    if not src.is_dir():
        sys.exit(f"source dir not found: {src}")

    all_entries = []
    suspects = []
    for rpy in sorted(src.glob("*.rpy")):
        entries = extract(rpy, screens=args.screens, suspects=suspects)
        print(f"{rpy.name}: {len(entries)} strings")
        all_entries.extend(entries)

    if args.no_dedupe:
        result = all_entries
        print(f"\nTotal: {len(all_entries)} occurrences (dedupe disabled)")
    else:
        # Deduplicate by text but keep first occurrence for context
        seen = {}
        for e in all_entries:
            first = seen.setdefault(e["text"], e)
            # One shared translation serves every speaker of this text, so QA
            # must judge it against all of them, not just the first.
            if e["kind"] == "say" and e["speaker"] != first["speaker"]:
                also = first.setdefault("also_spoken_by", [])
                if e["speaker"] not in also:
                    also.append(e["speaker"])
        result = list(seen.values())
        shared = sum(1 for e in result if e.get("also_spoken_by"))
        if shared:
            print(f"note: {shared} text(s) are spoken by more than one character "
                  "(see also_spoken_by); one translation must fit all of them")
        print(f"\nTotal: {len(all_entries)} occurrences, {len(result)} unique strings")

    if suspects:
        print(f"\nWARNING: {len(suspects)} dialogue-shaped line(s) matched no pattern "
              "and were NOT extracted:")
        for f, ln, t in suspects[:10]:
            print(f"  {f}:{ln}: {t[:100]}")

    write_text_atomic(out, json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
