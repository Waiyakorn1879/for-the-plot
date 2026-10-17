"""Find variables a scene replay (gallery) is likely to crash on.

A Ren'Py replay runs a scene outside the story flow, so a variable that is
only ever assigned DURING play (`$ anniepath = 1`) and never `default`ed or
`define`d does not exist there, and dialogue or conditions that read it raise
NameError. This lists exactly those names, with a neutral starting value
guessed from the first literal assigned, as a `store_defaults` skeleton for
profile.json (see references/patching.md).

Static and conservative: it reports names, never decides values. A seeded
value makes Ren'Py's own `default` skip that name, so only names that are
never `default`ed appear here, and the values are for the author to confirm.

Usage:
  python replay_vars.py --src decompiled/            # report
  python replay_vars.py --src decompiled/ --json     # store_defaults skeleton
  python replay_vars.py --profile profile.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

from validation import configure_console

configure_console()

ASSIGN_RE = re.compile(r"^\$\s*([A-Za-z_]\w*)\s*(?:\+|-|\*|/)?=\s*(.+?)\s*$")
DEFINED_RE = re.compile(r"^(?:default|define)\s+(?:-?\d+\s+)?([A-Za-z_]\w*)\s*=")
PYBLOCK_RE = re.compile(r"^(init\s+(?:-?\d+\s+)?)?python(\s+\w+)?\s*:\s*$")
PYBLOCK_ASSIGN_RE = re.compile(r"^([A-Za-z_]\w*)\s*=[^=]")
INIT_ONE_RE = re.compile(r"^init\s+(?:-?\d+\s+)?\$\s*([A-Za-z_]\w*)\s*=")


def neutral(expr):
    """A falsy starting value of the same type as the first literal assigned,
    or None when the right-hand side is not a plain literal."""
    expr = expr.strip()
    if expr in ("True", "False"):
        return False
    if re.fullmatch(r"-?\d+", expr):
        return 0
    if re.fullmatch(r"-?\d+\.\d*", expr):
        return 0.0
    if re.fullmatch(r"""(["']).*\1""", expr):
        return ""
    return None


def scan(src):
    """-> (assigned_in_play {name: {"file", "line", "rhs"}}, defined {names})"""
    assigned, defined = {}, set()
    for path in sorted(Path(src).rglob("*.rpy")):
        in_py, py_indent = False, 0
        for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").split("\n"), 1):
            stripped = raw.strip()
            indent = len(raw) - len(raw.lstrip())
            if not stripped or stripped.startswith("#"):
                continue
            if in_py:
                if indent > py_indent:
                    m = PYBLOCK_ASSIGN_RE.match(stripped)
                    if m and indent <= py_indent + 4:
                        defined.add(m.group(1))
                    continue
                in_py = False
            if PYBLOCK_RE.match(stripped):
                in_py, py_indent = True, indent
                continue
            m = DEFINED_RE.match(stripped) or INIT_ONE_RE.match(stripped)
            if m:
                defined.add(m.group(1))
                continue
            m = ASSIGN_RE.match(stripped)
            if m and m.group(1) not in assigned:
                assigned[m.group(1)] = {"file": path.name, "line": lineno, "rhs": m.group(2)}
    return assigned, defined


def candidates(src):
    assigned, defined = scan(src)
    return {n: info for n, info in sorted(assigned.items()) if n not in defined}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile")
    ap.add_argument("--src")
    ap.add_argument("--json", action="store_true",
                    help="print a store_defaults skeleton (null = fill in by hand)")
    args = ap.parse_args()
    src = args.src
    if args.profile and not src:
        prof = Path(args.profile)
        conf = json.loads(prof.read_text(encoding="utf-8"))
        if conf.get("source_dir"):
            src = prof.parent / conf["source_dir"]
    if not src or not Path(src).is_dir():
        sys.exit("need --src DIR, or --profile with source_dir")

    found = candidates(src)
    if args.json:
        print(json.dumps({n: neutral(i["rhs"]) for n, i in found.items()},
                         ensure_ascii=False, indent=2))
        return
    print(f"{len(found)} variable(s) assigned during play but never default/define'd:")
    for n, i in found.items():
        print(f"  {n:<24} first set {i['file']}:{i['line']}  ({i['rhs'][:40]})"
              f"  -> start with {neutral(i['rhs'])!r}")
    if found:
        print("\nA replay that reads one of these raises NameError. Put the ones your gallery "
              "touches in profile.json `store_defaults` (--json for a skeleton).")


if __name__ == "__main__":
    main()
