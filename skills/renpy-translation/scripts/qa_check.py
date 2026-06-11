"""Translation quality check for Ren'Py translation projects.

Built-in technical checks (category 1 — always run, language-agnostic):
  - MISSING: source string has no translation
  - TAG: {tags} present in source but absent in translation
  - VAR: [variables] present in source but absent in translation

Built-in review checks (category 4 — language-agnostic, skipped by --technical-only):
  - roman: untranslated Latin-script words in the translation
    (skipped for words in the profile's keep_untranslated; disable entirely
    with "roman_check": false in the QA rules file — e.g. when the target
    language itself uses Latin script)
  - short?: translation suspiciously shorter than the source (possible truncation)

Declarative register rules (categories 2/3/4 — from the profile's qa_rules_file):
  See references/qa.md and examples/badik-thai/qa_rules.json. Each rule is a
  regex over the translation, optionally restricted to certain speakers and/or
  conditioned on which characters appear nearby in the script (context window),
  which is how relationship-dependent registers (pronouns, formality) are checked.

Usage:
  python qa_check.py --profile profile.json
  python qa_check.py --profile profile.json --technical-only
  python qa_check.py --profile profile.json --report qa_report.txt
"""
import argparse
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TAG_RE = re.compile(r"\{[^}]+\}")
VAR_RE = re.compile(r"\[[^\]]+\]")
ROMAN_RE = re.compile(r"[a-zA-Z]{4,}")

DEFAULT_WINDOW = 12
DEFAULT_TRUNCATION_RATIO = 0.28
DEFAULT_TRUNCATION_MIN_LEN = 20


def load_profile(path):
    profile_path = Path(path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return profile, profile_path.parent


def is_monologue(text):
    return text.startswith("(") and text.endswith(")")


class ContextIndex:
    """Strings grouped by file and sorted by line, for context-window lookups."""

    def __init__(self, strings, window):
        self.window = window
        self.file_strings = defaultdict(list)
        for s in strings:
            self.file_strings[s["file"]].append(s)
        for f in self.file_strings:
            self.file_strings[f].sort(key=lambda x: x["line"])
        self.file_line_idx = {}
        for f, slist in self.file_strings.items():
            for idx, s in enumerate(slist):
                self.file_line_idx[(f, s["line"])] = idx

    def get_window(self, file, line):
        idx = self.file_line_idx.get((file, line))
        if idx is None:
            return []
        sl = self.file_strings[file]
        return sl[max(0, idx - self.window):min(len(sl), idx + self.window + 1)]


def rule_speakers(rule, groups):
    if "speakers" in rule:
        return set(rule["speakers"])
    if "speakers_group" in rule:
        return set(groups.get(rule["speakers_group"], []))
    return None  # applies to all speakers


def near_condition_met(rule, ctx, groups, s):
    near = rule.get("near")
    if not near:
        return True
    window = ctx.get_window(s["file"], s["line"])
    grp = set(groups.get(near["group"], []))
    count = sum(1 for w in window if w["speaker"] in grp)
    if count < near.get("min", 1):
        return False
    for other in near.get("dominant_over", []):
        ogrp = set(groups.get(other, []))
        ocount = sum(1 for w in window if w["speaker"] in ogrp)
        if count < ocount:
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description="QA check a Ren'Py translation project")
    ap.add_argument("--profile", required=True, help="profile.json")
    ap.add_argument("--strings", help="strings file (overrides profile strings_file)")
    ap.add_argument("--translations", help="translations JSON (overrides profile progress_file)")
    ap.add_argument("--technical-only", action="store_true",
                    help="run only category 1 (missing/tag/var) checks")
    ap.add_argument("--report", help="also write the report to this file")
    args = ap.parse_args()

    profile, base = load_profile(args.profile)
    strings_file = Path(args.strings) if args.strings else base / profile.get("strings_file", "strings.json")
    trans_file = Path(args.translations) if args.translations else base / profile.get("progress_file", "translations.json")

    strings = json.loads(strings_file.read_text(encoding="utf-8"))
    trans = json.loads(trans_file.read_text(encoding="utf-8"))

    # Load declarative rules
    qa_conf = {}
    rules_file = profile.get("qa_rules_file")
    if rules_file and not args.technical_only:
        rules_path = base / rules_file
        if rules_path.is_file():
            qa_conf = json.loads(rules_path.read_text(encoding="utf-8"))
        else:
            print(f"warning: qa_rules_file not found: {rules_path}")

    groups = qa_conf.get("groups", {})
    rules = qa_conf.get("rules", [])
    window = qa_conf.get("window", DEFAULT_WINDOW)
    roman_check = qa_conf.get("roman_check", True)
    trunc_ratio = qa_conf.get("truncation_ratio", DEFAULT_TRUNCATION_RATIO)
    trunc_min_len = qa_conf.get("truncation_min_len", DEFAULT_TRUNCATION_MIN_LEN)

    for rule in rules:
        rule["_re"] = re.compile(rule["pattern"])
        rule["_speakers"] = rule_speakers(rule, groups)

    ctx = ContextIndex(strings, window)
    keep_lower = {k.lower() for k in profile.get("keep_untranslated", [])}

    categories = defaultdict(list)  # category label -> issue tuples

    for s in strings:
        text, speaker, file, line = s["text"], s["speaker"], s["file"], s["line"]
        tr = trans.get(text)

        # ── Category 1: Technical ──────────────────────────────────────────
        if tr is None or tr.strip() == "":
            categories[1].append(("MISSING", speaker, file, line, text, tr or ""))
            continue

        en_tags = set(TAG_RE.findall(text))
        tr_tags = set(TAG_RE.findall(tr))
        missing_tags = en_tags - tr_tags
        if missing_tags:
            categories[1].append((f"TAG:{','.join(sorted(missing_tags))}", speaker, file, line, text, tr))

        en_vars = set(VAR_RE.findall(text))
        tr_vars = set(VAR_RE.findall(tr))
        missing_vars = en_vars - tr_vars
        if missing_vars:
            categories[1].append((f"VAR:{','.join(sorted(missing_vars))}", speaker, file, line, text, tr))

        if args.technical_only:
            continue

        # ── Declarative register/phrasing rules ────────────────────────────
        for rule in rules:
            if rule["_speakers"] is not None and speaker not in rule["_speakers"]:
                continue
            if rule.get("skip_monologue") and is_monologue(text):
                continue
            if not rule["_re"].search(tr):
                continue
            if not near_condition_met(rule, ctx, groups, s):
                continue
            cat = rule.get("category", 4)
            if rule.get("dedupe", True):
                key = (rule["name"], text)
                if key in rule.setdefault("_seen", set()):
                    continue
                rule["_seen"].add(key)
            categories[cat].append((rule["name"], speaker, file, line, text, tr))

        # ── Category 4 built-ins: phrasing review flags ────────────────────
        if roman_check:
            roman_words = ROMAN_RE.findall(tr)
            non_proper = [w for w in roman_words if w.lower() not in keep_lower]
            if non_proper:
                categories[4].append((f"roman:{','.join(non_proper[:3])}", speaker, file, line, text, tr))

        if len(text) > trunc_min_len and tr and len(tr) < len(text) * trunc_ratio:
            categories[4].append(("short?", speaker, file, line, text, tr))

    # ── Report ──────────────────────────────────────────────────────────────
    out = io.StringIO()
    SEP = "=" * 72

    def emit(line=""):
        print(line)
        out.write(line + "\n")

    def emit_section(title, items):
        emit()
        emit(SEP)
        emit(f"  {title}  ({len(items)} issues)")
        emit(SEP)
        if not items:
            emit("  CLEAN — no issues found.")
            return
        for kind, spk, file, ln, eng, tr in items:
            emit(f"  [{kind}]  spk={spk}  {file}:{ln}")
            emit(f"    EN: {eng[:80]}")
            emit(f"    TR: {tr[:90]}")

    emit()
    emit("#" * 72)
    emit(f"  TRANSLATION QUALITY REPORT — {profile.get('game_name', '?')} → "
         f"{profile.get('language_name', profile.get('language_id', '?'))}")
    emit(f"  Strings: {len(strings)} | Trans loaded: {len(trans)}")
    emit("#" * 72)

    section_titles = {
        1: "CAT 1 — Technical (missing / tag / variable)",
        2: "CAT 2 — Register Violations (speaker)",
        3: "CAT 3 — Register Violations (relationship)",
        4: "CAT 4 — Phrasing Flags (manual review)",
    }
    cats_present = sorted(set(list(section_titles) + list(categories)))
    if args.technical_only:
        cats_present = [1]
    for c in cats_present:
        emit_section(section_titles.get(c, f"CAT {c}"), categories.get(c, []))

    hard = sum(len(categories.get(c, [])) for c in cats_present if c != 4)
    review = len(categories.get(4, [])) if not args.technical_only else 0
    emit()
    emit(SEP)
    emit("  SUMMARY")
    emit(SEP)
    for c in cats_present:
        flag = "(review manually)" if c == 4 else "(must fix)"
        emit(f"  Cat {c}: {len(categories.get(c, [])):4d}  {flag}")
    emit("  " + "-" * 25)
    emit(f"  Hard issues:   {hard:4d}")
    emit(f"  Total flagged: {hard + review:4d}")
    emit()

    if args.report:
        Path(args.report).write_text(out.getvalue(), encoding="utf-8")
        print(f"Report written to {args.report}")

    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
