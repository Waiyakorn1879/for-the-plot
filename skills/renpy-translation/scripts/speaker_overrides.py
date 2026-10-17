"""Per-speaker translations for texts that several characters say.

The Translation dictionary maps ONE English text to ONE translation. When
characters of different genders say the same line ("Hi!", "Thank you!"), that
one translation can only be unisex. This tool finds those texts and manages
`speaker_translations.json` — `{"<speaker code>::<text>": "<translation>"}` —
which build_patch.py turns into overrides the runtime filter prefers over the
dictionary (it knows who is speaking: the filter runs inside the `Say`
statement). Speakers of unknown gender, and minor extras, are NOT given an
override: they keep the dictionary's unisex translation.

  python speaker_overrides.py todo  --profile profile.json   # write the work list
  python speaker_overrides.py merge --profile profile.json --file filled.json
  python speaker_overrides.py status --profile profile.json

`todo` writes `speaker_translations_todo.json`: one item per (speaker, text)
still missing, with the unisex translation for reference. Fill `tr` however
you translate (in-session, API, a person), then `merge` the result. `merge`
holds every translation to the same gate as the bulk translator plus the
speaker's own gender rule, and saves only what passes.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from characters import avoid_pattern, gender_grammar, speech_gender
from validation import (ESC_RE, TAG_RE, VAR_RE, configure_console, multiset_diff,
                        validate_translation, validation_policy, write_text_atomic)

configure_console()

SEP = "::"


def speakers_of(entry):
    """Every speaker code that says this entry's text (first + also_spoken_by)."""
    codes = [entry["speaker"]] if entry.get("kind") == "say" else []
    return codes + list(entry.get("also_spoken_by") or [])


def needed(strings, speakers):
    """-> {text: {speaker code: 'male'|'female'}} for texts said by BOTH genders.

    Works on deduplicated strings (`also_spoken_by`) and on --no-dedupe ones
    (the same text appearing under several speakers).
    """
    by_text = {}
    for e in strings:
        for code in speakers_of(e):
            by_text.setdefault(e["text"], set()).add(code)
    out = {}
    for text, codes in by_text.items():
        genders = {c: speech_gender(speakers, c) for c in codes}
        known = {c: g for c, g in genders.items() if g in ("male", "female")}
        if set(known.values()) == {"male", "female"}:
            out[text] = dict(sorted(known.items()))
    return out


def _paths(profile, base):
    return (base / profile.get("speaker_translations_file", "speaker_translations.json"),
            base / "speaker_translations_todo.json",
            base / profile.get("progress_file", "translations.json"),
            base / profile.get("strings_file", "strings.json"))


def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _load(args):
    prof = Path(args.profile)
    profile = json.loads(prof.read_text(encoding="utf-8"))
    base = prof.parent
    out_path, todo_path, progress_path, strings_path = _paths(profile, base)
    strings = _read(strings_path, None)
    if strings is None:
        sys.exit(f"strings file not found: {strings_path}")
    speakers = profile.get("speakers", {})
    return (profile, speakers, needed(strings, speakers), _read(out_path, {}),
            _read(progress_path, {}), out_path, todo_path)


def cmd_todo(args):
    profile, speakers, need, have, progress, _, todo_path = _load(args)
    items = [{"key": f"{code}{SEP}{text}", "speaker": code, "gender": gender,
              "text": text, "unisex": progress.get(text), "tr": ""}
             for text, by_code in need.items()
             for code, gender in by_code.items()
             if f"{code}{SEP}{text}" not in have]
    write_text_atomic(todo_path, json.dumps(items, ensure_ascii=False, indent=2))
    print(f"{len(need)} text(s) said by both genders; {len(items)} (speaker, text) "
          f"override(s) still to write -> {todo_path.name}")
    if not gender_grammar(profile.get("language_id")):
        print("note: no gender grammar is built in for this language, so merge can "
              "only check tokens and validity, not the speaker's gender form")


def check(source, tr, gender, profile, grammar):
    """-> None if `tr` is acceptable for a speaker of `gender`, else a reason."""
    ok, code = validate_translation(source, tr, validation_policy(profile))
    if not ok:
        return code
    for label, rx in (("TAG", TAG_RE), ("VAR", VAR_RE), ("ESC", ESC_RE)):
        missing, extra = multiset_diff(rx.findall(source), rx.findall(tr))
        if missing or extra:
            return f"{label}:{','.join(missing + extra)}"
    if grammar:
        import re
        if re.search(avoid_pattern(grammar, gender), tr):
            return f"WRONG-GENDER({gender})"
    return None


def cmd_merge(args):
    profile, speakers, need, have, _, out_path, _ = _load(args)
    grammar = gender_grammar(profile.get("language_id"))
    filled = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if isinstance(filled, list):                       # the todo file, filled in
        filled = {i["key"]: i["tr"] for i in filled if i.get("tr", "").strip()}
    wanted = {f"{c}{SEP}{t}": (t, g) for t, by in need.items() for c, g in by.items()}
    saved, rejected = 0, Counter()
    for key, tr in filled.items():
        if key not in wanted:
            rejected["not a needed (speaker, text)"] += 1
            continue
        text, gender = wanted[key]
        reason = check(text, tr, gender, profile, grammar)
        if reason:
            rejected[reason] += 1
            print(f"  rejected {key[:60]!r}: {reason}")
            continue
        have[key] = tr
        saved += 1
    write_text_atomic(out_path, json.dumps(have, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"saved {saved}, rejected {sum(rejected.values())} -> {out_path.name}")
    sys.exit(1 if rejected else 0)


def cmd_status(args):
    _, _, need, have, _, out_path, _ = _load(args)
    total = sum(len(v) for v in need.values())
    done = sum(1 for t, by in need.items() for c in by if f"{c}{SEP}{t}" in have)
    print(f"{len(need)} mixed-gender shared text(s); {done}/{total} per-speaker "
          f"override(s) in {out_path.name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("todo", cmd_todo), ("merge", cmd_merge), ("status", cmd_status)):
        p = sub.add_parser(name)
        p.add_argument("--profile", required=True)
        if name == "merge":
            p.add_argument("--file", required=True,
                           help="{key: translation} JSON, or the filled-in todo list")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
