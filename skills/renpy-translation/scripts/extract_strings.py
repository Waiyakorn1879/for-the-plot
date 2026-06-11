"""Extract translatable strings from Ren'Py .rpy files.

Outputs a JSON list of {text, speaker, file, line, kind}
- kind = "say" | "menu" | "text" | "narrator"
Duplicates are skipped by exact text match unless --no-dedupe is given
(keep duplicates when targeting native `translate` blocks, where each
occurrence can translate differently).

Usage:
  python extract_strings.py --src decompiled/ --out strings.json
  python extract_strings.py --profile profile.json
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

# Ren'Py keywords/commands that look like "speaker" but aren't
NON_SPEAKERS = {
    "scene", "show", "hide", "play", "stop", "queue", "pause",
    "call", "jump", "return", "menu", "label", "if", "elif",
    "else", "while", "for", "with", "window", "image", "screen",
    "init", "define", "default", "transform", "python", "translate",
    "voice", "nvl", "centered", "extend", "style", "$",
}


def extract(rpy_path: Path):
    out = []
    in_python_block = False
    python_indent = None
    with rpy_path.open(encoding="utf-8", errors="replace") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

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
        entries = extract(rpy)
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
