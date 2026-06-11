"""Extract translatable strings from Ren'Py .rpy files.

Outputs a JSON list of {text, speaker, file, line, kind}
- kind = "say" | "menu" | "text" | "narrator"
- with --screens additionally: "screen" (literal text/textbutton/label/tooltip
  inside screen blocks) and "ui" (_()-wrapped strings anywhere).
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

# Match: `speaker "text"` or `speaker "text" (with stuff)` etc.
# Allows escaped quotes inside.
SAY_RE = re.compile(
    r'^(\s*)([a-zA-Z_][\w]*)\s+"((?:[^"\\]|\\.)*)"\s*(?:\([^)]*\))?\s*$'
)
# Narrator-only say: just `"text"`
NARRATOR_RE = re.compile(
    r'^(\s*)"((?:[^"\\]|\\.)*)"\s*$'
)
# Menu choice: `    "Choice text" if cond:` or `    "Choice text":`
MENU_RE = re.compile(
    r'^(\s+)"((?:[^"\\]|\\.)*)"(?:\s+if\s+[^:]+)?:\s*$'
)
# show text "..."
SHOWTEXT_RE = re.compile(
    r'^(\s*)show\s+text\s+"((?:[^"\\]|\\.)*)"'
)
# screen definition header: `screen name(...):`
SCREEN_START_RE = re.compile(r'^screen\s+\w+.*:\s*$')
# literal-string screen statements: text/textbutton/label/tooltip "..."
SCREEN_TEXT_RE = re.compile(
    r'^\s*(?:text|textbutton|label|tooltip)\s+"((?:[^"\\]|\\.)*)"'
)
# _("...") translatable-marked strings (several can share a line)
UNDERSCORE_RE = re.compile(r'_\(\s*"((?:[^"\\]|\\.)*)"\s*\)')

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
}


def extract(rpy_path: Path, screens=False):
    out = []
    in_python_block = False
    python_indent = None
    in_screen_block = False
    screen_indent = None
    with rpy_path.open(encoding="utf-8", errors="replace") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # _( "..." ) strings are translatable wherever they appear,
            # including python blocks and $ lines — scan before any skips.
            if screens and not stripped.startswith("#"):
                for m in UNDERSCORE_RE.finditer(line):
                    txt = m.group(1)
                    if txt.strip() and has_translatable_content(txt):
                        out.append({"text": txt, "speaker": "_ui",
                                    "file": rpy_path.name, "line": lineno, "kind": "ui"})

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
                                            "kind": "screen"})
                        continue
                    in_screen_block = False
                if SCREEN_START_RE.match(stripped):
                    in_screen_block = True
                    screen_indent = indent
                    continue

            # show text "..."
            m = SHOWTEXT_RE.match(line)
            if m:
                txt = m.group(2)
                if txt.strip():
                    out.append({"text": txt, "speaker": "_text",
                                "file": rpy_path.name, "line": lineno, "kind": "text"})
                continue

            # speaker "text"
            m = SAY_RE.match(line)
            if m:
                speaker = m.group(2)
                txt = m.group(3)
                if speaker in NON_SPEAKERS:
                    pass  # fall through to narrator/menu checks
                else:
                    if txt.strip():
                        out.append({"text": txt, "speaker": speaker,
                                    "file": rpy_path.name, "line": lineno, "kind": "say"})
                    continue

            # menu choice
            m = MENU_RE.match(line)
            if m:
                txt = m.group(2)
                if txt.strip():
                    out.append({"text": txt, "speaker": "_menu",
                                "file": rpy_path.name, "line": lineno, "kind": "menu"})
                continue

            # narrator (bare string on its own line, indented)
            m = NARRATOR_RE.match(line)
            if m and indent > 0:
                txt = m.group(2)
                if txt.strip():
                    out.append({"text": txt, "speaker": "narrator",
                                "file": rpy_path.name, "line": lineno, "kind": "narrator"})
                continue
    return out


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
    for rpy in sorted(src.glob("*.rpy")):
        entries = extract(rpy, screens=args.screens)
        print(f"{rpy.name}: {len(entries)} strings")
        all_entries.extend(entries)

    if args.no_dedupe:
        result = all_entries
        print(f"\nTotal: {len(all_entries)} occurrences (dedupe disabled)")
    else:
        # Deduplicate by text but keep first occurrence for context
        seen = {}
        for e in all_entries:
            if e["text"] not in seen:
                seen[e["text"]] = e
        result = list(seen.values())
        print(f"\nTotal: {len(all_entries)} occurrences, {len(result)} unique strings")

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
