"""Character records: the machine-readable answer to "who is speaking".

Character knowledge lives in `profile.json` -> `speakers`, one record per
speaker code. Every field beyond `name` is optional, so a v1.3 profile with
only `{name, gender, role}` keeps working unchanged.

Why one file and not a separate `characters.json`: a second store keyed by the
same speaker code would need a merge-and-fallback rule in every consumer
(translation prompt, QA, TM context), and those rules drift. Characters who
speak under more than one code — common in visual novels, where someone is
"???" until introduced — are handled by `alias_of` instead (ADR-018).

The two consumers must agree. `translate_api.py` turns a record into a persona
card for the prompt; `qa_check.py` turns the *same* record into register
rules. A voice the prompt asks for and the gate doesn't check (or vice versa)
is worse than either alone — the same principle as `validation.py`.

Record shape (all optional except `name`):

    "my": {
      "name": "Maya", "gender": "female", "role": "childhood best friend",
      "register": "casual, warm, teasing",
      "self_pronoun": "ฉัน", "address_pronoun": "เธอ",
      "forbidden": ["กู", "มึง"],          # never, in any context
      "must_use": [],
      "speech_notes": "never crude, however close she is",
      "examples": [{"en": "...", "tr": "...", "note": "..."}],
      "monologue": {"self_pronoun": "..."},   # inner-thought override
      "to": {                                  # per-relationship overrides
        "mc": {"self_pronoun": "ฉัน", "address_pronoun": "นาย",
               "note": "close but never crude"}
      }
    }

`to` exists because in register-rich languages pronouns are a property of the
*pair*, not the person: in the shipped worked example the protagonist uses
เรา/แก with one friend and ผม with a formal acquaintance. Relationships are
declared and shown to the translator alongside the scene, rather than resolved
automatically — an addressee resolver that guesses wrong is worse than one
that doesn't exist, because it is wrong silently and everywhere.
"""

# Pseudo-speakers the extractor emits for non-character text.
PSEUDO_SPEAKERS = {"_text", "_menu", "_screen", "_ui", "narrator"}

MAX_ALIAS_DEPTH = 10


def resolve_alias(speakers, code, _depth=0):
    """Follow `alias_of` to the canonical speaker code.

    Returns the code unchanged if it has no alias, is unknown, or the chain
    is circular — resolution must never raise or loop on bad profile data.
    """
    seen = {code}
    while _depth < MAX_ALIAS_DEPTH:
        record = speakers.get(code)
        if not isinstance(record, dict):
            return code
        target = record.get("alias_of")
        if not target or target in seen:
            return code
        seen.add(target)
        code = target
        _depth += 1
    return code


def get_record(speakers, code):
    """The character record for a speaker code, following aliases."""
    return speakers.get(resolve_alias(speakers, code)) or {}


def is_character(speakers, code):
    """False for narration, menus, and screen/UI text — they have no voice."""
    return resolve_alias(speakers, code) not in PSEUDO_SPEAKERS


def display_name(speakers, code):
    return get_record(speakers, code).get("name", code)


def relationship(speakers, speaker_code, target_code):
    """Declared overrides for how `speaker` speaks *to* `target`."""
    to = get_record(speakers, speaker_code).get("to") or {}
    return to.get(resolve_alias(speakers, target_code)) or {}


def has_detail(record):
    """True when a record carries more than the v1.3 name/gender/role."""
    return any(record.get(k) for k in
               ("register", "self_pronoun", "address_pronoun", "forbidden",
                "must_use", "speech_notes", "examples", "to", "monologue"))


def character_line(speakers, code):
    """The v1.3 blurb: `Maya (female) — childhood best friend`."""
    record = get_record(speakers, code)
    if not record:
        return f"unknown speaker '{code}'"
    name = record.get("name", code)
    gender = f" ({record['gender']})" if record.get("gender") else ""
    role = f" — {record['role']}" if record.get("role") else ""
    return f"{name}{gender}{role}"


def persona_card(speakers, code, max_examples=2):
    """A multi-line voice brief for one character.

    Falls back to the one-line blurb when the record has no detail, so a
    profile that hasn't been enriched produces exactly the v1.3 prompt.
    """
    record = get_record(speakers, code)
    if not has_detail(record):
        return character_line(speakers, code)

    lines = [character_line(speakers, code)]
    add = lines.append

    if record.get("register"):
        add(f"    register: {record['register']}")

    pronouns = []
    if record.get("self_pronoun"):
        pronouns.append(f"refers to self as {record['self_pronoun']}")
    if record.get("address_pronoun"):
        pronouns.append(f"addresses others as {record['address_pronoun']}")
    if pronouns:
        add(f"    pronouns: {'; '.join(pronouns)}")

    monologue = record.get("monologue") or {}
    if monologue.get("self_pronoun"):
        add(f"    inner monologue (...): refers to self as {monologue['self_pronoun']}")

    for target_code, rel in (record.get("to") or {}).items():
        bits = []
        if rel.get("self_pronoun"):
            bits.append(f"self {rel['self_pronoun']}")
        if rel.get("address_pronoun"):
            bits.append(f"calls them {rel['address_pronoun']}")
        if rel.get("note"):
            bits.append(rel["note"])
        if bits:
            add(f"    to {display_name(speakers, target_code)}: {'; '.join(bits)}")

    if record.get("must_use"):
        add(f"    MUST use: {', '.join(record['must_use'])}")
    if record.get("forbidden"):
        add(f"    NEVER use: {', '.join(record['forbidden'])}")
    if record.get("speech_notes"):
        add(f"    note: {record['speech_notes']}")

    for example in (record.get("examples") or [])[:max_examples]:
        en, tr = example.get("en"), example.get("tr")
        if not (en and tr):
            continue
        note = f"   [{example['note']}]" if example.get("note") else ""
        add(f'    e.g. EN "{en}" -> "{tr}"{note}')

    return "\n".join(lines)


def cast_block(speakers, codes, max_examples=2):
    """Persona cards for the distinct speakers in one batch.

    Emitted ONCE per batch rather than repeated per line: a thick card on
    every line would multiply the prompt by the batch size for no gain. The
    system prompt deliberately stays static across batches so providers can
    cache it, and batches stay contiguous by file+line so scene context
    survives — grouping lines by character would trade one context signal
    for another.
    """
    ordered, seen = [], set()
    for code in codes:
        canonical = resolve_alias(speakers, code)
        if canonical in seen or not is_character(speakers, code):
            continue
        seen.add(canonical)
        ordered.append(code)
    if not ordered:
        return ""
    cards = [persona_card(speakers, code, max_examples) for code in ordered]
    return "CAST IN THIS BATCH:\n" + "\n".join(cards)


def register_rules(speakers):
    """Character records -> qa_check rules, so the gate checks what the
    prompt asked for.

    `forbidden` becomes a category-2 rule (speaker identity). Terms are
    matched literally and reported, never suppressed: in an unspaced script
    a clever exclusion pattern hides real violations far more often than it
    removes noise (see references/qa.md).
    """
    import re

    rules = []
    for code, record in sorted(speakers.items()):
        if not isinstance(record, dict) or record.get("alias_of"):
            continue
        forbidden = [t for t in (record.get("forbidden") or []) if t]
        if not forbidden:
            continue
        codes = sorted({code} | {
            other for other, rec in speakers.items()
            if isinstance(rec, dict) and rec.get("alias_of") == code})
        name = record.get("name", code)
        rules.append({
            "name": f"{name}: forbidden term",
            "category": 2,
            "speakers": codes,
            "pattern": "|".join(re.escape(t) for t in forbidden),
            "_from_character": True,
        })
    return rules


def missing_must_use(speakers, code, translation):
    """Terms a character's record requires that the translation lacks.

    Only meaningful on longer lines — a one-word reply cannot be expected to
    carry vocabulary — so callers gate on length.
    """
    must = get_record(speakers, code).get("must_use") or []
    return [term for term in must if term and term not in translation]
