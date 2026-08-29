# Phase 5: QA

```
python qa_check.py --profile profile.json [--technical-only] [--report qa_report.txt]
```

Exit code is 1 while "hard" (non-review) issues remain — usable as a gate before building the patch.

## Category-1 codes

| Code | Meaning |
|---|---|
| `MISSING` | no translation, or an empty one |
| `UNTRANSLATED` | the translation is the source text back again |
| `SCRIPT` | the translation contains no target-script characters |
| `TAG:` / `VAR:` / `ESC:` | a `{tag}`, `[variable]`, or `\escape` the source has and the translation lost |
| `TAG+:` / `VAR+:` / `ESC+:` | a token the translation **added or duplicated** — counts are compared, not sets |
| `PCT:n->m` | the number of literal `%%` changed |

`UNTRANSLATED` and `SCRIPT` come from the shared `validation.py` gate that `translate_api.py` also refuses to save on, so bulk output and hand-written translations are held to one standard. Sources whose only translatable content is a `keep_untranslated` term, a variable, a tag, or punctuation are exempt automatically — `"Maya!" → "Maya!"` is fine. For the residue that exemption doesn't cover (a line genuinely identical in both languages), list the exact source in `profile.json` → `validation.allow_identical`.

**`SCRIPT` is opt-in.** It only runs when `validation.target_script` is set explicitly (`"thai"`, `"greek"`, … or `{"ranges": ["0E00-0E7F"]}`). Without it, `qa_check.py` prints the script it *inferred* from `language_id` and leaves the check off, so upgrading the tooling can never turn on a new hard failure for an existing project. Latin-script targets can't use this check at all — they share codepoints with the source.

## The 4-category model

1. **Technical (built-in, must fix):** missing translations, untranslated output, `{tag}` / `[variable]` / `\escape` / `%%` mismatches. These break rendering, crash the game, or ship English to the player. Always zero before a patch build.
2. **Register violations — speaker identity:** a character using language their persona forbids (e.g. a refined character using gutter pronouns). Declarative rules.
3. **Register violations — relationship/context:** correct words in the wrong company (e.g. crude pronouns while talking to a teacher or love interest). Declarative rules restricted by resolved addressee (`to` / `to_group`), or by `near` context conditions where no addressee could be resolved.
4. **Phrasing flags (review, not auto-fix):** built-in untranslated-Latin-word and truncation checks, plus any declarative rules marked category 4 (awkward loanwords etc.).

## Rules from character records (no authoring needed)

A `forbidden` list on a character in `profile.json` → `speakers` becomes a **category-2 rule automatically** — the same list the translation prompt shows as `NEVER use`. Declare it once on the character; both ends read it:

```json
"my": { "name": "Maya", "forbidden": ["กู", "มึง"], "must_use": ["นะ"] }
```

- Codes with `alias_of` pointing at that character are covered by the same rule, so a character who is `"???"` before introduction can't slip through.
- `must_use` is **advisory only** — a category-4 flag on longer lines. A short reply legitimately carries none of a character's signature vocabulary, so it must never block a build.
- Terms are regex-escaped and matched literally. A hand-written rule in `qa_rules.json` with the same `name` shadows the generated one, so you can override the category or add a `near` condition without double-reporting.

A `forbidden` list inside a **relationship** becomes a **category-3 rule** the same way — terms this character must never use *to this particular person*:

```json
"mc": { "name": "MC",
        "to": { "prof": { "address_pronoun": "…", "forbidden": ["กู", "มึง"] } } }
```

That rule only fires on lines whose addressee `relationships.py` resolved at or above the profile's `min_confidence`. An unresolved line is **not** judged against a relationship — there is no pairing to judge it against, and inventing one would flag correct text. Run `relationships.py --profile profile.json` to see how much of the script actually resolves before relying on these.

Only `to[…].forbidden` generates a rule. Pronoun fields do not: they describe what to write, and a pronoun's absence from a line is not evidence of anything.

Use `qa_rules.json` below for rules that depend on **context** rather than speaker identity.

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
- `to` / `to_group` (optional): the line's **resolved addressee** is that code (or in that named group). Lines whose addressee is unresolved never match. This is the exact answer; prefer it over `near`.
- `near` (optional): within ±`window` strings in the same file, characters from `group` appear at least `min` times, and at least as often as every group in `dominant_over`. This *approximates* "who is the speaker talking to" by proximity — use it for the lines `to` cannot cover (crowded scenes, a register that depends on who is merely present rather than addressed). Tune `window` (default 12) if scenes are long.
- `dedupe` (default true): report each (rule, text) pair once.

Findings name the pairing they were judged against: `spk=mc→prof` means the addressee resolved to `prof`, while a bare `spk=mc` means it did not resolve and only speaker-level rules applied.

Regex notes: patterns run on raw translation text. For languages without word boundaries (Thai), a lookaround can exclude a known compound — e.g. `กู(?![้ล])` avoids matching กู้ (to borrow) and กูล. **But read the next section before reaching for one.**

## Tuning scanners: bias toward noise, never toward silence

In an **unspaced script** (Thai, Japanese, Chinese, Lao, Khmer) the obvious way to reduce false positives — strip the compounds that legitimately contain your target, then flag what remains — *silently hides real violations*.

The worked example that cost a real project a backward fix: the kinship compound `คุณอา` ("uncle") false-matches inside the ordinary sentence fragment `คุณอายุ` ("you, age…"). Allowlisting `คุณอา` strips it out of that fragment and **erases the very `คุณ` violation you were hunting for**. The line reads clean and ships wrong.

The rule:

> **A false positive costs a glance. A false negative ships.**

So:

- Keep **long, unambiguous** compounds in the allowlist (`คุณภาพ`, `ขอบคุณ` — nothing else looks like them).
- **Exclude short, ambiguous** compounds and eat the extra reports, checking them by hand.
- Whenever you tune a rule to fire *less*, **re-run it against lines you already know violate it** before accepting the new pattern. If the known-bad lines stop being reported, the tuning was wrong.
- If you ever write a *mutating* fix script (the shipped tools only report), protect compounds by masking them to placeholders before replacing and unmasking afterwards — never replace directly in unspaced text.

## The backward-audit rule

Every newly-discovered convention triggers an audit of everything already translated. When you learn a rule at string 1,400, the 1,399 before it were translated without it.

1. **Discover** — from user feedback, a QA sample, or your own review.
2. **Write it down in the same turn**, into `translation-guide.md` *and* as a `qa_rules.json` rule. An unwritten rule gets re-broken within ten batches.
3. **Scan** for what's already committed. `qa_check.py` re-reads the whole corpus on every run, so adding a rule retro-scans automatically — you get the back catalogue for free.
4. **Fix** the flagged lines through the progress file.
5. **Re-verify** and note the count. If the rule's own allowlist later turns out to be wrong, re-run over rows you already marked done — the earlier pass may have missed real violations behind a bad compound match.

Budget for 5–15 of these over a full game. Their cost is proportional to how late you find them, which is the argument for front-loading the profile and glossary.

## Fix loop

Category 1 → fix immediately in the progress file (usually re-translate preserving tokens). Categories 2–3 → re-translate the flagged lines with the correct register; if a rule keeps firing on legitimate lines (e.g. quoting someone), refine the rule rather than ignoring the report — subject to the tuning rule above. Category 4 → human or assistant judgment, one pass near the end.

**Forcing a re-translation:** deleting a key from `translations.json` is *not* enough. The Translation Memory resolves hits before batching and will silently restore the old translation with no model call. Run with `tm.enabled: false` in the profile to force real re-translation. (`translation_memory.py clean` does **not** help — it only drops empty and duplicate entries.) One exception: since v1.3.1 the TM validates entries on lookup too, so a cached translation that echoes its source or misses the target script is rejected and re-translated automatically.
