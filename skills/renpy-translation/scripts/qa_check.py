"""Translation quality check for Ren'Py translation projects.

Built-in technical checks (category 1 — always run, language-agnostic):
  - MISSING: source string has no translation
  - TAG: {tags} present in source but absent in translation
  - VAR: [variables] present in source but absent in translation
  - TAGNEST: translation closes a {i}/{b}/{color}... tag that the source did
    not — a mis-nested close renders wrong or raises in Ren'Py even when the
    tag COUNT still matches (checked via validation.tag_nesting_ok)

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

from characters import (
    gender_grammar, avoid_pattern, get_record, is_character,
    is_monologue, missing_must_use, register_rules, resolve_alias,
)
import orthography
import punctuation
import terminology
from relationships import build_resolver
from validation import (
    ESC_RE, PCT_RE, TAG_RE, VAR_RE,
    configure_console, mask_tokens, multiset_diff, norm_key, policy_banner, validate_translation,
    validation_policy, write_text_atomic,
)

configure_console()

ROMAN_RE = re.compile(r"[a-zA-Z]{4,}")

DEFAULT_WINDOW = 12
DEFAULT_TRUNCATION_RATIO = 0.28
DEFAULT_TRUNCATION_MIN_LEN = 20


def load_profile(path):
    profile_path = Path(path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return profile, profile_path.parent


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


def canon(speakers, code):
    """Canonical speaker code, following `alias_of`.

    Rule matching and group membership run on canonical codes so a character
    who speaks under several codes ("???" before introduction) is one
    character everywhere. Without this, a hand-written rule naming the main
    code silently misses the alias while the generated rule catches it —
    the same character behaving two ways depending on where the rule came
    from. Reports still display the RAW code, so a finding stays traceable
    to the line that produced it.
    """
    return resolve_alias(speakers, code)


def rule_targets(rule, groups, speakers=None):
    """Canonical addressee codes a rule is restricted to, or None for any.

    A rule with `to`/`to_group` only fires on lines whose addressee was
    resolved at or above the profile's min_confidence — an unresolved line is
    not evidence that the rule does or does not apply, so it is skipped.
    """
    speakers = speakers or {}
    if "to" in rule:
        codes = rule["to"]
        if isinstance(codes, str):
            codes = [codes]
        return {canon(speakers, c) for c in codes}
    if "to_group" in rule:
        return {canon(speakers, c) for c in groups.get(rule["to_group"], [])}
    return None


def rule_speakers(rule, groups, speakers=None):
    speakers = speakers or {}
    if "speakers" in rule:
        return {canon(speakers, c) for c in rule["speakers"]}
    if "speakers_group" in rule:
        return {canon(speakers, c) for c in groups.get(rule["speakers_group"], [])}
    return None  # applies to all speakers


def near_condition_met(rule, ctx, groups, s, speakers=None):
    near = rule.get("near")
    if not near:
        return True
    speakers = speakers or {}
    window = ctx.get_window(s["file"], s["line"])
    win_codes = [canon(speakers, w["speaker"]) for w in window]
    grp = {canon(speakers, c) for c in groups.get(near["group"], [])}
    count = sum(1 for c in win_codes if c in grp)
    if count < near.get("min", 1):
        return False
    for other in near.get("dominant_over", []):
        ogrp = {canon(speakers, c) for c in groups.get(other, [])}
        ocount = sum(1 for c in win_codes if c in ogrp)
        if count < ocount:
            return False
    return True


def technical_issues(text, tr, policy):
    """-> (labels, untranslated): every category-1 finding for one translation.

    One function for the dictionary and for speaker overrides, so the line a
    player actually sees is held to the same standard whichever store it
    came from.
    """
    labels = []
    # Output validity: the same gate translate_api.py refuses to save on,
    # so a hand-written or pre-1.3.1 translation is held to one standard.
    ok, code = validate_translation(text, tr, policy)
    if not ok:
        labels.append("UNTRANSLATED" if code == "ECHO" else code if code != "TERM"
                      else "TERM:" + terminology.explain(text, tr, policy["terms"]))

    # Multiset, not set difference: a translation that ADDS or DUPLICATES
    # a tag is just as broken as one that drops it.
    for label, rx in (("TAG", TAG_RE), ("VAR", VAR_RE), ("ESC", ESC_RE)):
        missing, extra = multiset_diff(rx.findall(text), rx.findall(tr))
        if missing:
            labels.append(f"{label}:{','.join(sorted(missing))}")
        if extra:
            labels.append(f"{label}+:{','.join(sorted(extra))}")

    en_pct, tr_pct = len(PCT_RE.findall(text)), len(PCT_RE.findall(tr))
    if en_pct != tr_pct:
        labels.append(f"PCT:{en_pct}->{tr_pct}")
    return labels, not ok


def load_overrides(profile, base):
    """-> {(speaker code, text): translation} from the speaker overrides file.

    Keyed exactly as build_patch.py emits them and the runtime filter looks
    them up, so QA judges the same entries the player will see.
    """
    path = base / profile.get("speaker_translations_file", "speaker_translations.json")
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {tuple(k.split("::", 1)): v for k, v in raw.items() if "::" in k}


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

    # A message, not a traceback: this is the first command run in a new project.
    for what, path, hint in (("strings", strings_file, "run extract_strings.py first"),
                             ("translations", trans_file, "nothing has been translated yet")):
        if not path.is_file():
            sys.exit(f"{what} file not found: {path} ({hint})")
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
    # Character-derived rules first, so a hand-written rule of the same name in
    # qa_rules.json shadows the generated one rather than duplicating it.
    speakers = profile.get("speakers", {})
    language = profile.get("language_id")
    generated = register_rules(speakers, language)
    grammar = gender_grammar(language)
    if grammar:
        # Speakers with no record at all are unknown: unisex speech, like extras.
        generated.append({
            "name": "unknown speaker: gendered speech", "category": 2,
            "pattern": avoid_pattern(grammar, None), "unknown_speakers": True})
    authored = qa_conf.get("rules", [])
    authored_names = {r.get("name") for r in authored}
    rules = [r for r in generated if r["name"] not in authored_names] + authored
    window = qa_conf.get("window", DEFAULT_WINDOW)
    roman_check = qa_conf.get("roman_check", True)
    # Writing conventions of the target language (Chinese): the same list the
    # translation prompt states.
    conventions = orthography.config(profile)
    trunc_ratio = qa_conf.get("truncation_ratio", conventions["truncation_ratio"]
                              if conventions else DEFAULT_TRUNCATION_RATIO)

    def convention_issues(tr):
        """-> [(category, label)]. A variant leak is a hard failure only when
        the profile itself names the variant; everything else is for review."""
        return [(2 if label.startswith("variant") and conventions["explicit"] else 4,
                 "zh " + label) for label in orthography.issues(tr, conventions)]
    trunc_min_len = qa_conf.get("truncation_min_len", DEFAULT_TRUNCATION_MIN_LEN)

    for rule in rules:
        rule["_re"] = re.compile(rule["pattern"])
        rule["_speakers"] = rule_speakers(rule, groups, speakers)
        rule["_to"] = rule_targets(rule, groups, speakers)

    # Addressee resolution (v1.5). Built from the same profile block and the
    # same gate the translation prompt uses, so a relationship rule checks the
    # pairing the translator was actually told to write.
    resolver = build_resolver(profile, strings)
    targets = [resolver.target_for(s) for s in strings] if resolver.enabled         else [None] * len(strings)

    ctx = ContextIndex(strings, window)
    keep_lower = {k.lower() for k in profile.get("keep_untranslated", [])}
    policy = validation_policy(profile, base)

    categories = defaultdict(list)  # category label -> issue tuples
    # The dictionary may spell a key the other way round (escaped quote, curly
    # apostrophe); edit_lines and pair_audit already find it, so QA must too.
    trans_alt = {norm_key(k): (k, v) for k, v in trans.items()}
    overrides = load_overrides(profile, base)
    override_at = {}    # (speaker code, text) -> first (file, line) that says it
    bang_policy = punctuation.policy(profile)
    bang_over = 0

    for idx, s in enumerate(strings):
        text, speaker, file, line = s["text"], s["speaker"], s["file"], s["line"]
        # Match rules on the canonical code; report the raw one.
        canon_speaker = canon(speakers, speaker)
        target = targets[idx]
        # Findings name the pair when one was resolved, so a category-3 hit is
        # traceable to the relationship it was judged against.
        speaker = f"{speaker}→{target}" if target else speaker
        # `stored` is the key as the dictionary spells it. Tokens are compared
        # against that spelling: a value mirrors its own key's quote escaping.
        stored, tr = text, trans.get(text)
        if tr is None:
            stored, tr = trans_alt.get(norm_key(text), (text, None))
        if overrides:
            for code in [s["speaker"]] + list(s.get("also_spoken_by") or []):
                override_at.setdefault((code, text), (file, line))

        # ── Category 1: Technical ──────────────────────────────────────────
        if tr is None or tr.strip() == "":
            categories[1].append(("MISSING", speaker, file, line, text, tr or ""))
            continue

        labels, untranslated = technical_issues(stored, tr, policy)
        for label in labels:
            categories[1].append((label, speaker, file, line, text, tr))

        if args.technical_only:
            continue

        if bang_policy and punctuation.over_policy(text, tr, bang_policy):
            bang_over += 1

        # ── Declarative register/phrasing rules ────────────────────────────
        # A deduplicated text shared by several speakers is judged against each.
        # Each is judged on what the player will see from THAT speaker: their
        # override when one exists (the runtime filter prefers it), else the
        # dictionary entry.
        judged = [(canon_speaker, target, overrides.get((s["speaker"], text), tr))] + [
            (canon(speakers, o), None, overrides.get((o, text), tr))
            for o in s.get("also_spoken_by", [])]
        for rule, (rule_spk, rule_tgt, seen_tr) in ((r, j) for r in rules for j in judged):
            if rule["_speakers"] is not None and rule_spk not in rule["_speakers"]:
                continue
            if rule.get("unknown_speakers") and (
                    s["kind"] != "say" or not is_character(speakers, rule_spk)
                    or get_record(speakers, rule_spk)):
                continue
            if rule["_to"] is not None and (rule_tgt is None or rule_tgt not in rule["_to"]):
                continue
            if rule.get("skip_monologue") and is_monologue(text):
                continue
            if not rule["_re"].search(seen_tr):
                continue
            if not near_condition_met(rule, ctx, groups, s, speakers):
                continue
            cat = rule.get("category", 4)
            if rule.get("dedupe", True):
                key = (rule["name"], text, seen_tr)
                if key in rule.setdefault("_seen", set()):
                    continue
                rule["_seen"].add(key)
            categories[cat].append((rule["name"], speaker if rule_spk == canon_speaker else rule_spk, file, line, text, seen_tr))

        # ── Category 4 built-ins: phrasing review flags ────────────────────
        # An echoed line is 100% Latin by definition; reporting it again as a
        # cat-4 phrasing flag is noise on top of a cat-1 failure.
        if roman_check and not untranslated:
            # Tokens are not prose: [partner_name] is not two untranslated words.
            roman_words = ROMAN_RE.findall(mask_tokens(tr)[0])
            non_proper = [w for w in roman_words if w.lower() not in keep_lower]
            if non_proper:
                categories[4].append((f"roman:{','.join(non_proper[:3])}", speaker, file, line, text, tr))

        if conventions:
            for cat, label in convention_issues(tr):
                categories[cat].append((label, speaker, file, line, text, tr))

        if len(text) > trunc_min_len and tr and len(tr) < len(text) * trunc_ratio:
            categories[4].append(("short?", speaker, file, line, text, tr))

        # must_use is advisory (category 4), never a hard gate: a character's
        # signature vocabulary can't be expected on every line, and a short
        # reply legitimately carries none of it. Only longer lines are checked.
        if len(text) > trunc_min_len:
            absent = missing_must_use(speakers, canon_speaker, tr)
            if absent:
                categories[4].append((f"must_use?:{','.join(absent[:3])}",
                                      speaker, file, line, text, tr))

    # ── Speaker overrides: category 1 ───────────────────────────────────────
    # Every override ships and wins over the dictionary at runtime, so each one
    # is checked — including one no extracted line maps to any more.
    for (code, text), otr in overrides.items():
        file, line = override_at.get((code, text), ("(speaker override)", 0))
        labels = technical_issues(text, otr, policy)[0] if otr and otr.strip() else ["EMPTY"]
        for label in labels:
            categories[1].append((f"OVERRIDE {label}", code, file, line, text, otr or ""))
        if conventions and not args.technical_only and otr:
            for cat, label in convention_issues(otr):
                categories[cat].append((f"OVERRIDE {label}", code, file, line, text, otr))

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
    emit(f"  {policy_banner(policy)}")
    # Only when relationships are in use: a profile that declares none gets the
    # v1.4 report unchanged, down to the byte.
    if resolver.enabled:
        emit(f"  Addressee: {sum(1 for t in targets if t)}/{len(strings)} resolved "
             f"(min_confidence={resolver.min_confidence})")
        if resolver.unknown_speakers:
            emit(f"  {len(resolver.unknown_speakers)} speaker code(s) have no "
                 f"character record — run relationships.py to list them.")
    if overrides:
        emit(f"  Speaker overrides: {len(overrides)} checked")
    if conventions and not args.technical_only:
        variant = conventions["variant"] or "not set - set orthography.variant to check it"
        emit(f"  Chinese conventions: variant={variant}"
             + (" (a leak is a hard issue)" if conventions["explicit"] else "")
             + "; orthography.py --write fixes the mechanical ones")
    if bang_policy and not args.technical_only:
        emit(f"  Exclamation policy: {bang_over} line(s) carry a '!' the policy would drop "
             "(run punctuation.py; informational, not a failure)")
    emit("#" * 72)

    section_titles = {
        1: "CAT 1 — Technical (missing / untranslated / tag / variable / escape)",
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
        write_text_atomic(Path(args.report), out.getvalue())
        print(f"Report written to {args.report}")

    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
