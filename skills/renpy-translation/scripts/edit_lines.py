"""Targeted edits to existing translations, addressed by source `file:line`.

For fixing a register or pronoun leak in a handful of lines you found by audit,
without touching the others. Dry-run by default: prints `old -> new` for every
change and writes nothing. With --write, backs up both stores first.

  python edit_lines.py --profile profile.json --jobs jobs.json [--write]

jobs.json is a list of regex substitutions per line:
  [{"file": "script4.rpy", "line": 2297, "sub": [["ฉัน", "ข้า"], ["แก(?=ใส่)", "เอ็ง"]]}]

Lines are found in strings.json by (file, line), so extract with --no-dedupe if
a line is missing ("norow"). The edit lands on the speaker override
(`speaker::text`) when one exists, else on the dictionary entry. Several jobs
that hit the same entry are applied in order. Every result is held to the same
gate as merge (tokens, tag nesting, echo, script, terms).

A dictionary entry serves EVERY line with that text. If other rows share it and
are not in the jobs, they change too: reported as SHARED. Resolve it with a
speaker override instead of editing the shared entry.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from validation import (ESC_RE, TAG_RE, VAR_RE, backup_file, configure_console,
                        multiset_diff, norm_key, validate_translation,
                        validation_policy, write_text_atomic)


def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _paths(profile, base):
    """-> (speaker overrides, translations, strings) file paths."""
    return (base / profile.get("speaker_translations_file", "speaker_translations.json"),
            base / profile.get("progress_file", "translations.json"),
            base / profile.get("strings_file", "strings.json"))


def gate(source, new, profile, base):
    """-> None if `new` is acceptable, else a reason (same gate as merge)."""
    ok, code = validate_translation(source, new, validation_policy(profile, base))
    if not ok:
        return code
    for label, rx in (("TAG", TAG_RE), ("VAR", VAR_RE), ("ESC", ESC_RE)):
        missing, extra = multiset_diff(rx.findall(source), rx.findall(new))
        if missing or extra:
            return f"{label}:{','.join(missing + extra)}"


def check_jobs(jobs):
    """Fail with a message, not a traceback, on a malformed jobs file."""
    if not isinstance(jobs, list):
        sys.exit("jobs file must be a list of {file, line, sub} objects")
    for i, j in enumerate(jobs):
        if not (isinstance(j, dict) and isinstance(j.get("file"), str)
                and isinstance(j.get("line"), int) and isinstance(j.get("sub"), list)
                and all(isinstance(s, list) and len(s) == 2 and all(isinstance(x, str) for x in s)
                        for s in j["sub"])):
            sys.exit(f'job #{i + 1} needs "file" (str), "line" (int) and "sub" '
                     f'(a list of [pattern, replacement] pairs): {json.dumps(j, ensure_ascii=False)[:100]}')
        for pat, _ in j["sub"]:
            try:
                re.compile(pat)
            except re.error as e:
                sys.exit(f"job #{i + 1} ({j['file']}:{j['line']}): bad pattern {pat!r}: {e}")


def _finder(d):
    """key -> the stored spelling of it (exact, else equal after norm_key)."""
    alt = {norm_key(k): k for k in d}
    return lambda key: key if key in d else alt.get(norm_key(key))


def plan(jobs, rows, tr, sp, profile, base):
    """-> (changes {(store, key): (old, new, where)}, problems [str])."""
    by_pos = {(r["file"], r["line"]): r for r in rows if r.get("kind") == "say"}
    wanted = {(j["file"], j["line"]) for j in jobs}
    find = {"sp": _finder(sp), "tr": _finder(tr)}
    changes, problems = {}, []
    for j in jobs:
        where = f"{j['file']}:{j['line']}"
        r = by_pos.get((j["file"], j["line"]))
        if not r:
            problems.append(f"norow    {where} (not in strings.json; extract with --no-dedupe?)")
            continue
        text, spk = r["text"], r["speaker"]
        key = find["sp"](f"{spk}::{text}")
        store = "sp" if key else "tr"
        key = key or find["tr"](text)
        d = sp if store == "sp" else tr
        if key is None:
            problems.append(f"nokey    {where} {text[:40]!r}")
            continue
        # Jobs on one entry compose in order; the first one's edit must survive.
        orig, current, wheres = changes.get((store, key), (d[key], d[key], ""))
        new = current
        for pat, repl in j["sub"]:
            new = re.sub(pat, repl, new)
        if new == current:
            problems.append(f"nochange {where} {current[:40]!r}")
            continue
        why = gate(text, new, profile, base)
        if why:
            problems.append(f"REJECTED {where} {why}: {new[:60]!r}")
            continue
        if store == "tr":
            others = [f"{x['file']}:{x['line']}" for x in rows
                      if x.get("kind") == "say" and x["text"] == text
                      and (x["file"], x["line"]) not in wanted]
            if others or r.get("also_spoken_by"):
                problems.append(f"SHARED   {where} also: {others[:3] or r['also_spoken_by']}")
        changes[(store, key)] = (orig, new, f"{wheres}, {where}" if wheres else where)
    return changes, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--jobs", required=True)
    ap.add_argument("--write", action="store_true", help="apply (default: dry-run)")
    args = ap.parse_args()
    configure_console()

    pp = Path(args.profile)
    profile, base = json.loads(pp.read_text(encoding="utf-8")), pp.parent
    sp_path, tr_path, strings_path = _paths(profile, base)
    tr, sp = _read(tr_path, {}), _read(sp_path, {})
    jobs_path = Path(args.jobs)
    if not jobs_path.is_file():
        sys.exit(f"jobs file not found: {jobs_path}")
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    check_jobs(jobs)
    changes, problems = plan(jobs, _read(strings_path, []), tr, sp, profile, base)

    for p in problems:
        print(p)
    for old, new, where in changes.values():
        print(f"{where}  {old[:60]} -> {new[:60]}")
    print(f"{len(changes)} change(s), {len(problems)} problem(s)")
    if not args.write:
        print("dry-run: nothing written (use --write)")
        return
    for path, d, tag in ((tr_path, tr, "tr"), (sp_path, sp, "sp")):
        if not any(s == tag for s, _ in changes) or not path.is_file():
            continue
        bak = backup_file(path)
        for (s, k), (_, new, _) in changes.items():
            if s == tag:
                d[k] = new
        write_text_atomic(path, json.dumps(d, ensure_ascii=False, indent=2))
        print(f"wrote {path.name} (backup {bak.name})")


if __name__ == "__main__":
    main()
