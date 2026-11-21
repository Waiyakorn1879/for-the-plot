"""Style Rules Engine (v1.7.0): one rule definition, two enforcement points.

A rule in the profile's `style_rules` list is compiled twice from the same
record: into an instruction the translator reads (`prompt_block`) and into a
qa_check rule that verifies the output (`qa_rules`). The prompt can never ask
for something QA does not check, and QA never judges something the prompt did
not say. Library, not a CLI; `qa_check.py` and `translate_api.py` import it.

A rule:

    {"name": "no synonym stacking",
     "say": "Use one word, never two near-synonyms in a row.",   # prompt text
     "forbid": ["ที่แท้จริงแล้ว"],       # literal terms QA looks for (optional)
     "mode": "strict",                    # "strict" (default) | "standalone"
     "except_in": ["กูเกิล"],             # standalone only: compounds where the term is valid
     "use": "ตัวจริง",                    # preferred form, shown after the ban (optional)
     "category": 4,                       # 2 | 3 | 4 (default 4: review, never blocks)
     "speakers": ["mc"],                  # scope: codes ...
     "speakers_where": {"gender": "female"},   # ... or any character-record attribute
     "to": ["prof"]}                      # scope: resolved addressee (category 3 only)

`say` alone is a prompt-only rule (emphasis markup, tone): nothing mechanical
to check, so it never reaches QA. `forbid` without `say` still gets a prompt
line, so the translator is told what QA will reject.

`strict`: the term is never acceptable. `standalone`: forbidden as a word of
its own but valid inside the compounds listed in `except_in`; QA removes those
exact compounds before matching. Unspaced scripts have no word boundary, so the
exclusions are explicit literals, never a lookaround that could hide a real
violation (references/qa.md).

Rules are matched literally and reported, never suppressed, and nothing here
edits text.
"""
import re

MODES = ("strict", "standalone")
CATEGORIES = (2, 3, 4)


def problems(rules):
    """-> [str] malformed-rule messages. Called at load so a typo is loud."""
    out = []
    seen = set()
    if not isinstance(rules, list):
        return ["style_rules must be a list"]
    for i, r in enumerate(rules):
        tag = f"style_rules[{i}]"
        if not isinstance(r, dict):
            out.append(f"{tag}: not an object")
            continue
        name = r.get("name")
        if not name:
            out.append(f"{tag}: missing name")
        elif name in seen:
            out.append(f"{tag}: duplicate name {name!r}")
        seen.add(name)
        if not r.get("say") and not r.get("forbid"):
            out.append(f"{tag} ({name}): needs `say` or `forbid`")
        if r.get("mode", "strict") not in MODES:
            out.append(f"{tag} ({name}): mode must be one of {MODES}")
        if r.get("except_in") and r.get("mode") != "standalone":
            out.append(f"{tag} ({name}): `except_in` only applies to mode standalone")
        if r.get("category", 4) not in CATEGORIES:
            out.append(f"{tag} ({name}): category must be one of {CATEGORIES}")
        if r.get("to") and r.get("category") != 3:
            out.append(f"{tag} ({name}): `to` needs category 3")
        if r.get("speakers") and r.get("speakers_where"):
            out.append(f"{tag} ({name}): use `speakers` or `speakers_where`, not both")
    return out


def _scope(rule, speakers):
    """Speaker codes a rule applies to, or None for everyone."""
    if rule.get("speakers"):
        return sorted(rule["speakers"])
    where = rule.get("speakers_where")
    if where:
        return sorted(
            code for code, rec in speakers.items()
            if isinstance(rec, dict) and not rec.get("alias_of")
            and all(str(rec.get(k, "")).strip().lower() == str(v).strip().lower()
                    for k, v in where.items()))
    return None


def _aliases(speakers, codes):
    """Codes plus every alias that speaks as one of them."""
    out = set(codes)
    for code, rec in speakers.items():
        if isinstance(rec, dict) and rec.get("alias_of") in out:
            out.add(code)
    return sorted(out)


def qa_rules(rules, speakers):
    """Style rules -> qa_check rule dicts (only those with something to check)."""
    out = []
    for r in rules or []:
        terms = [t for t in (r.get("forbid") or []) if t]
        if not terms:
            continue
        q = {
            "name": f"style: {r['name']}",
            "category": r.get("category", 4),
            "pattern": "|".join(re.escape(t) for t in terms),
            "_from_style": True,
        }
        if r.get("mode") == "standalone" and r.get("except_in"):
            q["except"] = sorted((t for t in r["except_in"] if t), key=len, reverse=True)
        scope = _scope(r, speakers)
        if scope is not None:
            q["speakers"] = _aliases(speakers, scope)
        if r.get("to"):
            q["to"] = list(r["to"])
        out.append(q)
    return out


def strip_exceptions(text, rule):
    """Remove the rule's allowed compounds (longest first) before matching."""
    for ex in rule.get("except") or ():
        text = text.replace(ex, "\0")
    return text


def prompt_block(rules, speakers, batch_codes):
    """The STYLE RULES block for one batch, or "". Rules scoped to speakers
    absent from the batch are left out, so a long list costs nothing on batches
    it does not concern."""
    batch = set(batch_codes)
    lines = []
    for r in rules or []:
        scope = _scope(r, speakers)
        if scope is not None and not batch & set(_aliases(speakers, scope)):
            continue
        parts = []
        if r.get("say"):
            parts.append(r["say"].strip())
        terms = [t for t in (r.get("forbid") or []) if t]
        if terms:
            ban = "Never write: " + ", ".join(terms)
            if r.get("mode") == "standalone":
                ex = [t for t in (r.get("except_in") or []) if t]
                ban = ("Never use as a word of its own: " + ", ".join(terms)
                       + (f" (fine inside: {', '.join(ex)})" if ex else ""))
            if r.get("use"):
                ban += f". Use: {r['use']}"
            parts.append(ban)
        who = ""
        if scope is not None:
            who = f" [{', '.join(scope)}]"
        lines.append(f"- {r['name']}{who}: " + " ".join(p.rstrip('.') + "." for p in parts))
    if not lines:
        return ""
    return "STYLE RULES (checked after you answer):\n" + "\n".join(lines)
