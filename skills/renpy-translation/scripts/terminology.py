"""Terminology Dictionary (v1.6): canonical renderings with a lifecycle.

Library (imported by validation.py, translate_api.py, qa_check.py) and CLI:

  python terminology.py preflight --profile profile.json
  python terminology.py sweep     --profile profile.json [--min-count N]
  python terminology.py add       --profile profile.json "Rush" --target "..." --priority 10
  python terminology.py promote   --profile profile.json "Rush" [--target T] [--priority N]
  python terminology.py import    --profile profile.json other_glossary.json

The dictionary is `terminology.json` beside the profile (`terminology_file`).
`profile.keep_untranslated` migrates in transparently as APPROVED `keep` terms.

Design rules, all from the spec in ROADMAP.md / ADR-023:
- A term enforces nothing until ENFORCED; promotion is one step at a time.
- ONE matcher serves the prompt, the QA gate and preflight, and it can refuse:
  an equal-priority identical-trigger tie is *unresolved* — neither term
  guides or enforces, and preflight names the pair. Never an insertion-order pick.
- Matching is exact surface form: word-bounded, case-sensitive, blind to
  `[vars]` and `{tags}`. No fuzzy or semantic matching (that is v3.0's problem).
"""
import argparse
import json
import re
import sys
from pathlib import Path

STAGES = ("DISCOVERED", "CANDIDATE", "REVIEWED", "APPROVED", "ENFORCED")
SCOPES = ("translate", "transliterate", "keep")
PROVENANCES = ("corpus_sweep", "human", "imported")
GUIDE_FROM = "REVIEWED"      # first stage that feeds the prompt
CHECK_FROM = "APPROVED"      # first stage that takes part in conflict detection

_TOKEN_RE = re.compile(r"\[[^\]]+\]|\{[^}]+\}")


def rank(stage):
    return STAGES.index(stage)


# ---- loading -------------------------------------------------------------

def terminology_path(profile, base):
    return Path(base) / profile.get("terminology_file", "terminology.json")


def problems(term):
    """Reasons a term is unusable (empty list = fine). An unusable term is
    excluded from every active set and listed by preflight."""
    out = []
    if not isinstance(term.get("source"), str) or not term["source"].strip():
        out.append("no source text")
    if term.get("stage") not in STAGES:
        out.append(f"stage must be one of {', '.join(STAGES)}")
    if term.get("scope", "translate") not in SCOPES:
        out.append(f"scope must be one of {', '.join(SCOPES)}")
    if term.get("stage") in STAGES and rank(term["stage"]) >= rank("REVIEWED") \
            and not isinstance(term.get("priority"), int):
        out.append("priority (integer) is required from REVIEWED up")
    if term.get("stage") in STAGES and rank(term["stage"]) >= rank("CANDIDATE") \
            and term.get("scope", "translate") != "keep" and not term.get("target"):
        out.append("target rendering is required from CANDIDATE up")
    return out


def load_terms(profile, base):
    """-> (terms, authored_count). Authored terms from terminology.json plus
    migrated `keep_untranslated` entries, deduplicated BEFORE any conflict check
    (an authored term wins its source text; a migrated duplicate disappears)."""
    path = terminology_path(profile, base)
    authored = []
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        for t in data.get("terms", []):
            term = dict(t)
            term.setdefault("scope", "translate")
            if term["scope"] == "keep" and term.get("source"):
                term.setdefault("target", term["source"])
            authored.append(term)
    seen = {t.get("source") for t in authored}
    migrated = [{"source": k, "scope": "keep", "target": k, "stage": "APPROVED",
                 "priority": 0, "provenance": "human", "forbidden": [],
                 "_migrated": True}
                for k in dict.fromkeys(profile.get("keep_untranslated", []))
                if k and k not in seen]
    return authored + migrated, len(authored)


def save_terms(profile, base, terms):
    from validation import write_text_atomic
    kept = [{k: v for k, v in t.items() if not k.startswith("_")}
            for t in terms if not t.get("_migrated")]
    write_text_atomic(terminology_path(profile, base),
                      json.dumps({"terms": kept}, ensure_ascii=False, indent=2))


def active(terms, min_stage, only_stage=None):
    """Usable terms at or above `min_stage`. Migrated ones are included —
    they are real members of the dictionary for matching and conflicts."""
    return [t for t in terms if not problems(t)
            and (t["stage"] == only_stage if only_stage else rank(t["stage"]) >= rank(min_stage))]


# ---- the matcher ---------------------------------------------------------

def _mask(text):
    """Blank out [vars] and {tags} (same length) so no trigger matches inside one."""
    return _TOKEN_RE.sub(lambda m: " " * len(m.group(0)), text)


def _find(masked, trigger):
    return [m.span() for m in
            re.finditer(r"(?<!\w)" + re.escape(trigger) + r"(?!\w)", masked)]


def match(text, terms):
    """-> (winners, unresolved). `winners` = [(term, start, end)] left to right.

    Longest match wins; at the same span the higher `priority` wins; an equal
    priority tie with a different rendering is UNRESOLVED: the span is skipped
    (nobody guides or enforces there) and the pair is returned for reporting.
    """
    masked = _mask(text)
    spans = []
    for t in terms:
        for s, e in _find(masked, t["source"]):
            spans.append((s, e, t))
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    winners, unresolved, pos, i = [], [], 0, 0
    while i < len(spans):
        s, e, t = spans[i]
        if s < pos:
            i += 1
            continue
        group = [x for x in spans if x[0] == s and x[1] == e]
        i += len(group) if group else 1
        top = max(g[2].get("priority", 0) for g in group)
        best = [g[2] for g in group if g[2].get("priority", 0) == top]
        if len({(b.get("target"), b.get("scope")) for b in best}) > 1:
            unresolved.append(tuple(best))
            pos = e
            continue
        winners.append((best[0], s, e))
        pos = e
    return winners, unresolved


# ---- the gate ------------------------------------------------------------

def violations(source, translation, terms):
    """-> [(kind, term)] — ENFORCED terms the source triggers and the
    translation breaks. kind is 'missing' (canonical rendering absent) or
    'forbidden' (a forbidden variant present). Empty for a profile with no
    ENFORCED terms, so existing projects are untouched."""
    enforced = active(terms, "ENFORCED", only_stage="ENFORCED")
    if not enforced:
        return []
    out = []
    winners, _ = match(source, enforced)
    for term, _s, _e in winners:
        want = term["source"] if term["scope"] == "keep" else term["target"]
        if want and want not in translation:
            out.append(("missing", term))
        for bad in term.get("forbidden") or []:
            if bad and bad in translation:
                out.append(("forbidden", term))
                break
    return out


def feedback(source, translation, terms):
    """-> [str]: one plain instruction per ENFORCED violation, for a retry
    prompt. Names the term and the exact form wanted or forbidden, so the
    model need not rediscover its own mistake."""
    out = []
    for kind, term in violations(source, translation, terms):
        if kind == "missing":
            want = term["source"] if term["scope"] == "keep" else term["target"]
            how = "exactly as written" if term["scope"] == "keep" else "as"
            out.append(f'"{term["source"]}" must appear {how} "{want}"')
        else:
            bad = [b for b in term.get("forbidden") or [] if b and b in translation]
            out.append(f'"{term["source"]}": do not use ' + ", ".join(f'"{b}"' for b in bad))
    return out


def explain(source, translation, terms):
    return ",".join(f"{k}:{t['source']}" for k, t in violations(source, translation, terms))


def keep_sources(terms):
    """Sources the validity gate should treat as 'kept as written' — keep-scope
    terms from APPROVED up (migrated ones are already in keep_untranslated)."""
    return [t["source"] for t in active(terms, CHECK_FROM)
            if t["scope"] == "keep" and not t.get("_migrated")]


# ---- prompt guidance -----------------------------------------------------

def guidance_block(texts, terms):
    """Per-batch terminology for the USER message (the system prompt stays
    static for provider caching). '' when nothing applies, so a project with
    no dictionary produces exactly the v1.5 prompt."""
    eligible = [t for t in active(terms, GUIDE_FROM) if not t.get("_migrated")]
    if not eligible:
        return ""
    seen, lines = set(), []
    for text in texts:
        for term, _s, _e in match(text, eligible)[0]:
            if term["source"] in seen:
                continue
            seen.add(term["source"])
            if term["scope"] == "keep":
                line = f"- {term['source']}: keep EXACTLY as written"
            else:
                line = f"- {term['source']} -> {term['target']}  [{term['scope']}]"
            if term.get("forbidden"):
                line += "  NEVER: " + ", ".join(term["forbidden"])
            if term.get("note"):
                line += f"  ({term['note']})"
            if term["stage"] == "ENFORCED":
                line += "  MANDATORY"
            lines.append(line)
    return "TERMINOLOGY IN THIS BATCH:\n" + "\n".join(lines) if lines else ""


# ---- preflight -----------------------------------------------------------

def preflight(terms):
    """-> report dict. Only ENFORCED-term trouble blocks (spec: the same
    'hard issues block, everything else is reviewed' split as qa_check.py)."""
    usable = [t for t in terms if not problems(t)]
    stages = {s: sum(1 for t in terms if t.get("stage") == s) for s in STAGES}
    pool = [t for t in usable if rank(t["stage"]) >= rank(CHECK_FROM)]
    conflicts, shadows, duplicates = [], [], []
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            if a["source"] == b["source"]:
                same = (a.get("target"), a["scope"]) == (b.get("target"), b["scope"])
                if same:
                    duplicates.append((a, b))
                elif a.get("priority") == b.get("priority"):
                    conflicts.append((a, b))
            elif a["source"] in b["source"] or b["source"] in a["source"]:
                shadows.append((a, b))
    blocking = [p for p in conflicts if "ENFORCED" in (p[0]["stage"], p[1]["stage"])]
    invalid = [(t, problems(t)) for t in terms if problems(t)]
    blocking_invalid = [x for x in invalid if x[0].get("stage") == "ENFORCED"]
    prov = {}
    for t in terms:
        prov[t.get("provenance") or "unrecorded"] = prov.get(t.get("provenance") or "unrecorded", 0) + 1
    return {"stages": stages, "conflicts": conflicts, "blocking": blocking,
            "shadows": shadows, "duplicates": duplicates, "invalid": invalid,
            "blocking_invalid": blocking_invalid, "provenance": prov,
            "unenforced": [t for t in pool if t["stage"] != "ENFORCED"]}


def conflicts_for(term, terms):
    """Unresolved identical-trigger ties between `term` and any other
    APPROVED-or-higher usable term (what blocks promotion to ENFORCED)."""
    return [o for o in terms if o is not term and not problems(o)
            and rank(o["stage"]) >= rank(CHECK_FROM) and o["source"] == term["source"]
            and (o.get("target"), o["scope"]) != (term.get("target"), term["scope"])
            and o.get("priority") == term.get("priority")]


# ---- sweep ---------------------------------------------------------------

_CAP_PHRASE = re.compile(r"(?<![\w'])[A-Z][\w'-]*"
                         r"(?:\s+(?:(?:of|the|de|la|von|van)\s+)?[A-Z][\w'-]*)+")
_CAP_WORD = re.compile(r"(?<=[a-z,;]\s)[A-Z][\w'-]{2,}")


# Function words that capitalize only because they open a sentence. Stripped from
# the FRONT of a swept phrase: "To Dark Harbor" is the term "Dark Harbor".
_LEADING_STOPWORDS = (
    "a", "an", "the", "and", "but", "or", "if", "when", "to", "in", "on", "at",
    "from", "with", "by", "of", "for", "into", "about", "after", "before")
_LEADING_STOP_RE = re.compile(r"^(?:(?:%s)\s+)+" % "|".join(_LEADING_STOPWORDS), re.I)


def sweep(strings, known_sources, ignore=(), min_count=3):
    """-> {phrase: count}: capitalized multi-word phrases (>= 2 occurrences) and
    capitalized words that appear mid-sentence (>= min_count). Heuristic and
    deliberately plain — it seeds DISCOVERED entries for a human to review.
    High-frequency common nouns need a part-of-speech tagger; not attempted."""
    counts, singles = {}, {}
    ignore = {i.lower() for i in ignore}
    for entry in strings:
        text = _mask(entry["text"])
        for m in _CAP_PHRASE.finditer(text):
            phrase = _LEADING_STOP_RE.sub("", m.group(0))
            if not phrase:
                continue
            # What is left may be one word ("The Harbor"): that is an ordinary
            # capitalized-word sighting, held to the same min_count as any.
            bucket = counts if re.search(r"\s", phrase) else singles
            bucket[phrase] = bucket.get(phrase, 0) + 1
        # A phrase's own words are not separate terms.
        text = _CAP_PHRASE.sub(lambda m: " " * len(m.group(0)), text)
        for m in _CAP_WORD.finditer(text):
            singles[m.group(0)] = singles.get(m.group(0), 0) + 1
    out = {k: v for k, v in counts.items() if v >= 2}
    out.update({k: v for k, v in singles.items() if v >= min_count})
    return {k: v for k, v in sorted(out.items(), key=lambda kv: (-kv[1], kv[0]))
            if k not in known_sources and k.lower() not in ignore}


# ---- CLI -----------------------------------------------------------------

def _load(args):
    prof = Path(args.profile)
    profile = json.loads(prof.read_text(encoding="utf-8"))
    base = prof.parent
    terms, _ = load_terms(profile, base)
    return profile, base, terms


def _find_term(terms, source):
    for t in terms:
        if t.get("source") == source:
            return t
    sys.exit(f"no term {source!r} in the dictionary (or keep_untranslated)")


def cmd_preflight(args):
    profile, base, terms = _load(args)
    r = preflight(terms)
    print("Terminology preflight")
    print("  stages:     " + "  ".join(f"{s}={n}" for s, n in r["stages"].items()))
    print("  provenance: " + "  ".join(f"{k}={n}" for k, n in sorted(r["provenance"].items())))
    for a, b in r["conflicts"]:
        tag = "BLOCKING" if (a, b) in r["blocking"] else "unresolved"
        print(f"  CONFLICT [{tag}] {a['source']!r}: {a['stage']}->{a.get('target')!r} vs "
              f"{b['stage']}->{b.get('target')!r}, equal priority {a.get('priority')}")
    for t, why in r["invalid"]:
        print(f"  INVALID  {t.get('source')!r} ({t.get('stage')}): {'; '.join(why)}")
    for a, b in r["shadows"]:
        print(f"  shadow   {a['source']!r} / {b['source']!r}: longest match wins")
    for a, b in r["duplicates"]:
        print(f"  duplicate {a['source']!r}: same rendering twice")
    if r["unenforced"]:
        print(f"  {len(r['unenforced'])} APPROVED term(s) guide the prompt but the gate cannot check them yet")
    bad = r["blocking"] or r["blocking_invalid"]
    print("FAIL: ENFORCED terms are in conflict or invalid" if bad else "OK")
    sys.exit(1 if bad else 0)


def cmd_sweep(args):
    from validation import configure_console
    configure_console()
    profile, base, terms = _load(args)
    strings = json.loads((base / profile.get("strings_file", "strings.json"))
                         .read_text(encoding="utf-8"))
    names = [n for r in (profile.get("speakers") or {}).values() if isinstance(r, dict)
             for n in [r.get("name"), *(r.get("called") or [])] if n]
    found = sweep(strings, {t["source"] for t in terms}, ignore=names, min_count=args.min_count)
    for phrase, n in found.items():
        terms.append({"source": phrase, "scope": "translate", "stage": "DISCOVERED",
                      "priority": None, "provenance": "corpus_sweep", "count": n})
    save_terms(profile, base, terms)
    print(f"{len(found)} new DISCOVERED term(s) -> {terminology_path(profile, base).name}")


def cmd_add(args):
    profile, base, terms = _load(args)
    if any(t.get("source") == args.term for t in terms if not t.get("_migrated")):
        sys.exit(f"{args.term!r} is already in the dictionary")
    term = {"source": args.term, "scope": args.scope, "stage": "CANDIDATE",
            "priority": args.priority, "provenance": "human",
            "forbidden": args.forbidden or [], "note": args.note or ""}
    if args.scope == "keep":
        term["target"] = args.term
    elif args.target:
        term["target"] = args.target
    else:
        sys.exit("--target is required unless --scope keep")
    terms.append(term)
    save_terms(profile, base, terms)
    print(f"added {args.term!r} as CANDIDATE")


def cmd_promote(args):
    profile, base, terms = _load(args)
    term = _find_term(terms, args.term)
    if args.target:
        term["target"] = args.target
    if args.priority is not None:
        term["priority"] = args.priority
    if term["scope"] == "keep":
        term.setdefault("target", term["source"])
    cur = term["stage"]
    if cur == STAGES[-1]:
        sys.exit(f"{args.term!r} is already ENFORCED")
    nxt = STAGES[rank(cur) + 1]
    trial = dict(term, stage=nxt)
    why = problems(trial)
    if why:
        sys.exit(f"cannot promote {args.term!r} {cur} -> {nxt}: {'; '.join(why)}")
    if nxt == "ENFORCED":
        clash = conflicts_for(trial, terms)
        if clash:
            sys.exit(f"cannot enforce {args.term!r}: unresolved conflict with "
                     f"{[(c['stage'], c.get('target')) for c in clash]} at equal priority "
                     f"{term.get('priority')} - give one a higher priority")
    term["stage"] = nxt
    term["provenance"] = term.get("provenance") or "human"
    term.pop("_migrated", None)               # promoting materializes a migrated keep term
    save_terms(profile, base, terms)
    print(f"{args.term!r}: {cur} -> {nxt}")


def cmd_import(args):
    profile, base, terms = _load(args)
    have = {t["source"] for t in terms}
    incoming = json.loads(Path(args.file).read_text(encoding="utf-8"))
    incoming = incoming.get("terms", incoming) if isinstance(incoming, dict) else incoming
    added = 0
    for t in incoming:
        if not isinstance(t, dict) or t.get("source") in have:
            continue
        term = dict(t, provenance="imported", scope=t.get("scope", "translate"))
        # Trust is earned locally: an imported term never arrives above CANDIDATE.
        if term.get("stage") not in STAGES or rank(term["stage"]) > rank("CANDIDATE"):
            term["stage"] = "CANDIDATE" if term.get("target") or term["scope"] == "keep" else "DISCOVERED"
        terms.append(term)
        added += 1
    save_terms(profile, base, terms)
    print(f"imported {added} term(s) (existing sources skipped; none above CANDIDATE)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("preflight", cmd_preflight), ("sweep", cmd_sweep), ("add", cmd_add),
                     ("promote", cmd_promote), ("import", cmd_import)):
        p = sub.add_parser(name)
        p.add_argument("--profile", required=True)
        p.set_defaults(fn=fn)
        if name == "sweep":
            p.add_argument("--min-count", type=int, default=3)
        if name in ("add", "promote"):
            p.add_argument("term")
            p.add_argument("--target")
            p.add_argument("--priority", type=int)
        if name == "add":
            p.add_argument("--scope", choices=SCOPES, default="translate")
            p.add_argument("--forbidden", nargs="*")
            p.add_argument("--note")
        if name == "import":
            p.add_argument("file")
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
