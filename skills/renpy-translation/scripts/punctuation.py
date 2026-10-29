"""Exclamation-mark policy: many source games over-use `!`, and a translation
that copies every one reads as shouting. Opt in with a profile block:

  "punctuation": {"exclamation": {"short_words": 2}}

A `!` is KEPT only when the source line is ALL CAPS, contains `!!`, carries a
shout tag (`*Shouts*`, `*Yelling*` ...), or is a short interjection (at most
`short_words` words, default 2). Anywhere else the translation drops it:
sentence-final `!` goes, `?!` becomes `?`, an inner `!` becomes a space.
The rule is purely form-based, so a shouted lower-case line longer than
`short_words` loses its `!`: review the dry-run.

  python punctuation.py --profile profile.json           # dry-run, prints counts
  python punctuation.py --profile profile.json --write   # backs up, then applies

qa_check.py reports how many lines are over policy (informational, never a hard
failure). Tokens ([x!u], {tags}, escapes) are masked while editing, so they
cannot change.
"""
import argparse
import json
import re
import shutil
import time
from pathlib import Path

from validation import (configure_console, is_echo, mask_tokens, unmask_tokens,
                        write_text_atomic)

def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _paths(profile, base):
    """-> (speaker overrides, translations, strings) file paths."""
    return (base / profile.get("speaker_translations_file", "speaker_translations.json"),
            base / profile.get("progress_file", "translations.json"),
            base / profile.get("strings_file", "strings.json"))


DEFAULT_SHOUT = r"\*(?:shouts?|yells?|screams?|screaming|yelling|shouting)"


def policy(profile):
    """-> the exclamation config dict, or None when the profile doesn't opt in."""
    cfg = (profile.get("punctuation") or {}).get("exclamation")
    return None if cfg is None else {"short_words": 2, **cfg}


def keep(source, cfg):
    """True if `source` earns its `!` under the policy."""
    plain = re.sub(r"\x00\d+\x00", "", mask_tokens(source)[0]).replace("*", "")
    letters = re.sub(r"[^A-Za-z]", "", plain)
    if len(letters) >= 3 and letters.isupper():
        return True
    if "!!" in source:
        return True
    if re.search(cfg.get("shout_pattern", DEFAULT_SHOUT), source, re.I):
        return True
    words = re.findall(r"[A-Za-z0-9'’]+", plain)
    return plain.strip().endswith("!") and len(words) <= cfg.get("short_words", 2)


def soften(translation):
    masked, toks = mask_tokens(translation)
    s = re.sub(r"\?!+", "?", masked)
    s = re.sub(r"!+(?=\s*(?:\*|\x00\d+\x00|\"|”|\)|$))", "", s)
    s = re.sub(r"!+\s+", " ", s)
    s = re.sub(r"!+(?=\w)", " ", s)
    return unmask_tokens(s.replace("!", ""), toks).rstrip()


def over_policy(source, translation, cfg):
    """True if `translation` carries a `!` the policy would drop."""
    return ("!" in mask_tokens(translation)[0] and not is_echo(source, translation)
            and not keep(source, cfg))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--write", action="store_true", help="apply (default: dry-run)")
    args = ap.parse_args()
    configure_console()

    pp = Path(args.profile)
    profile, base = json.loads(pp.read_text(encoding="utf-8")), pp.parent
    cfg = policy(profile)
    if cfg is None:
        raise SystemExit('profile has no punctuation.exclamation block; nothing to do')
    sp_path, tr_path, _ = _paths(profile, base)
    stores = [(tr_path, _read(tr_path, {}), lambda k: k),
              (sp_path, _read(sp_path, {}), lambda k: k.split("::", 1)[-1])]

    changed = marks = 0
    for path, d, source_of in stores:
        for k, v in d.items():
            src = source_of(k)
            if over_policy(src, v, cfg):
                new = soften(v)
                changed += new != v
                marks += v.count("!") - new.count("!")
                d[k] = new
    left = sum(v.count("!") for _, d, _ in stores for v in d.values())
    print(f"{changed} entr(ies) to change, {marks} mark(s) removed, {left} remain")
    if not args.write:
        print("dry-run: nothing written (use --write)")
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for path, d, _ in stores:
        if path.is_file():
            shutil.copy2(path, path.with_name(f"{path.name}.bak-{stamp}"))
            write_text_atomic(path, json.dumps(d, ensure_ascii=False, indent=2))
            print(f"wrote {path.name} (backup .bak-{stamp})")


if __name__ == "__main__":
    main()
