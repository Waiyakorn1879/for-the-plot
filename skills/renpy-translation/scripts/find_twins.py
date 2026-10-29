"""Find "twin" dictionary keys: the same source text spelled two ways that carry
different translations.

Ren'Py scripts write a quote as `\\"`; the text the engine hands the runtime filter
may have it unescaped, and a curly apostrophe may stand for a straight one. If both
spellings are keys with different translations, the player sees whichever form the
engine happens to produce. Unify them.

  python find_twins.py --profile profile.json     # exit 1 while differing twins exist
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from validation import configure_console


def norm(s):
    return s.replace('\\"', '"').replace("’", "'")


def find_twins(tr):
    """-> [(norm_text, {key: translation})] for groups whose translations differ
    beyond the same escaping (a value mirrors its key's `\\"` style, legitimately)."""
    groups = defaultdict(dict)
    for k, v in tr.items():
        groups[norm(k)][k] = v
    return [(n, g) for n, g in groups.items() if len({norm(v) for v in g.values()}) > 1]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--translations", help="overrides profile progress_file")
    args = ap.parse_args()
    configure_console()
    pp = Path(args.profile)
    profile, base = json.loads(pp.read_text(encoding="utf-8")), pp.parent
    path = Path(args.translations) if args.translations else base / profile.get("progress_file", "translations.json")
    twins = find_twins(json.loads(path.read_text(encoding="utf-8")))
    for _, g in twins:
        for k, v in g.items():
            print(f"  {k!r} -> {v!r}")
        print()
    print(f"Differing twins: {len(twins)}")
    sys.exit(1 if twins else 0)


if __name__ == "__main__":
    main()
