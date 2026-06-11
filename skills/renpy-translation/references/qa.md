# Phase 5: QA

```
python qa_check.py --profile profile.json [--technical-only] [--report qa_report.txt]
```

Exit code is 1 while "hard" (non-review) issues remain — usable as a gate before building the patch.

## The 4-category model

1. **Technical (built-in, must fix):** missing translations, `{tag}` mismatches, `[variable]` mismatches. These break rendering or crash the game. Always zero before a patch build.
2. **Register violations — speaker identity:** a character using language their persona forbids (e.g. a refined character using gutter pronouns). Declarative rules.
3. **Register violations — relationship/context:** correct words in the wrong company (e.g. crude pronouns while talking to a teacher or love interest). Declarative rules with `near` context conditions.
4. **Phrasing flags (review, not auto-fix):** built-in untranslated-Latin-word and truncation checks, plus any declarative rules marked category 4 (awkward loanwords etc.).

## Authoring qa_rules.json

```json
{
  "window": 12,
  "roman_check": true,
  "groups": {
    "formal_targets": ["isa", "ca", "ji"],
    "casual_targets": ["my", "js"],
    "refined_females": ["my", "js", "ji", "isa"]
  },
  "rules": [
    {
      "name": "crude pronoun near formal company",
      "category": 3,
      "speakers": ["mc"],
      "skip_monologue": true,
      "pattern": "กู(?![้ล])|มึง",
      "near": { "group": "formal_targets", "min": 2, "dominant_over": ["casual_targets"] }
    },
    {
      "name": "refined female using crude pronouns",
      "category": 2,
      "speakers_group": "refined_females",
      "skip_monologue": true,
      "pattern": "กู(?![้ล])|มึง"
    },
    {
      "name": "awkward loanword",
      "category": 4,
      "pattern": "เลเวล|สกอร์"
    }
  ]
}
```

Screen/UI strings (kinds `screen`/`ui`, speakers `_screen`/`_ui` from `--screens` extraction) are covered by the technical, roman, and truncation checks like everything else. Register rules with a `speakers`/`speakers_group` restriction never match them; rules **without** a speaker restriction do — scope phrasing rules accordingly.

Rule semantics — a rule fires when ALL of these hold:

- `speakers` / `speakers_group`: the line's speaker is in the list/named group (omit → any speaker)
- `skip_monologue`: if true, lines wrapped in `(...)` are exempt (inner thoughts often allow cruder register)
- `pattern`: regex found in the **translation**
- `near` (optional): within ±`window` strings in the same file, characters from `group` appear at least `min` times, and at least as often as every group in `dominant_over`. This approximates "who is the speaker talking to" without parsing scene structure — tune `window` (default 12) if scenes are long.
- `dedupe` (default true): report each (rule, text) pair once.

Regex notes: patterns run on raw translation text; for languages without word boundaries (Thai), guard against false substring hits with lookarounds — e.g. `กู(?![้ล])` avoids matching กู้ (to borrow) and กูล.

## Fix loop

Category 1 → fix immediately in the progress file (usually re-translate preserving tokens). Categories 2–3 → re-translate the flagged lines with the correct register; if a rule keeps firing on legitimate lines (e.g. quoting someone), refine the rule rather than ignoring the report. Category 4 → human/Claude judgment, one pass near the end.
