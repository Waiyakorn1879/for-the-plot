"""Two-speaker run audit: register leaks inside a conversation between exactly two people.

qa_check judges a line by its speaker, or by an addressee that relationships.py
could PROVE. Neither sees the common failure: two friends who must use one fixed
pronoun pair, where one line slips into another. This audit finds every run of
consecutive say lines spoken only by A and B (no narrator, menu or third voice
between, same label), looks up the live translation of each, and reports the
ones matching a forbidden form for that pair. It reads the script's own order,
so it does not depend on addressee resolution and does not feed it.

Declare pairs in the profile's qa_rules_file:

  "pairs": [{"name": "friends: fixed pronouns", "between": ["mc", "bob"],
             "forbid": "ฉัน|นาย",
             "min_run": 3, "skip_labels": ["role_play"]}]

`forbid` is one regex, or {speaker_code: regex} for a different list per side.
Inner thoughts "(...)" are skipped. Needs a strings.json extracted with
--no-dedupe, or repeated lines are missing from the runs.

  python pair_audit.py --profile profile.json

Findings are for REVIEW: role-play, flashbacks, a quoted third person or a
character playing someone else are legitimate exceptions the pattern cannot
see. Exit status is always 0.
"""
import argparse
import json
import re
from pathlib import Path

from characters import is_monologue, resolve_alias
from validation import configure_console, norm_key as norm

def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _paths(profile, base):
    """-> (speaker overrides, translations, strings) file paths."""
    return (base / profile.get("speaker_translations_file", "speaker_translations.json"),
            base / profile.get("progress_file", "translations.json"),
            base / profile.get("strings_file", "strings.json"))


def runs(strings, speakers, between, min_run=3):
    """Yield lists of say rows: consecutive, one label, speakers exactly `between`."""
    pair = set(between)
    by_file = {}
    for s in strings:
        by_file.setdefault(s["file"], []).append(s)
    for rows in by_file.values():
        rows.sort(key=lambda s: s["line"])
        run = []
        for s in rows + [None]:
            ok = (s is not None and s.get("kind") == "say"
                  and resolve_alias(speakers, s["speaker"]) in pair
                  and (not run or s.get("label") == run[-1].get("label")))
            if ok:
                run.append(s)
                continue
            if len(run) >= min_run and {resolve_alias(speakers, r["speaker"]) for r in run} == pair:
                yield run
            run = [s] if (s is not None and s.get("kind") == "say"
                          and resolve_alias(speakers, s["speaker"]) in pair) else []


def audit(strings, tr, sp, speakers, pair_rules):
    """-> [(rule name, speaker, file, line, source, translation)]"""
    alt = {norm(k): v for k, v in tr.items()}
    found = []
    for rule in pair_rules:
        forbid = rule["forbid"]
        for run in runs(strings, speakers, rule["between"], rule.get("min_run", 3)):
            if run[0].get("label") in rule.get("skip_labels", ()):
                continue
            for s in run:
                code = resolve_alias(speakers, s["speaker"])
                text = s["text"]
                t = sp.get(f"{s['speaker']}::{text}") or sp.get(f"{code}::{text}") \
                    or tr.get(text) or alt.get(norm(text))
                rx = forbid.get(code) if isinstance(forbid, dict) else forbid
                if not t or not rx or is_monologue(text) or is_monologue(t.strip()):
                    continue
                if re.search(rx, t):
                    found.append((rule["name"], s["speaker"], s["file"], s["line"], text, t))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True)
    args = ap.parse_args()
    configure_console()

    pp = Path(args.profile)
    profile, base = json.loads(pp.read_text(encoding="utf-8")), pp.parent
    sp_path, tr_path, strings_path = _paths(profile, base)
    rules_file = profile.get("qa_rules_file")
    rules_path = base / rules_file if rules_file else None
    conf = json.loads(rules_path.read_text(encoding="utf-8")) if rules_path and rules_path.is_file() else {}
    pairs = conf.get("pairs", [])
    if not pairs:
        raise SystemExit('no "pairs" in the qa_rules_file; nothing to audit')
    found = audit(_read(strings_path, []), _read(tr_path, {}), _read(sp_path, {}),
                  profile.get("speakers", {}), pairs)
    for name, spk, f, ln, en, tr in found:
        print(f"[{name}]  spk={spk}  {f}:{ln}\n    EN: {en[:80]}\n    TR: {tr[:90]}")
    print(f"{len(found)} line(s) to review")


if __name__ == "__main__":
    main()
