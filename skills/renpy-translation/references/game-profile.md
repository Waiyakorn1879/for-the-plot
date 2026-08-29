# Phase 3: The game profile

Scaffold the project first if you haven't:

```
python init_project.py --game "D:/Games/SomeGame-1.0-pc" --language thai
```

That writes a wired-up `profile.json`, a style-guide skeleton, `qa_rules.json`, a `.gitignore` that keeps game text out of version control, and `TRANSLATION.md` — the project's always-loaded instruction file — with `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` stubs pointing at it. It refuses to overwrite an existing profile, and refuses to write inside the game install.

A profile is the per-game/per-language knowledge base. Everything game- or language-specific lives here; the scripts and skill stay generic. It consists of:

| File | Consumed by | Contains |
|---|---|---|
| `profile.json` | all scripts | machine config (schema: `scripts/profile_schema.json`) |
| `translation-guide.md` | translator (in-session assistant or API prompt) | registers, formality, slang policy, few-shot examples |
| `qa_rules.json` | `qa_check.py` | declarative register checks (see `qa.md`) |

Worked example: `examples/badik-thai/` — copy its **structure** for a new game, never its content.

## Building a profile: the interview

Work through these with the user; they know the game and the target-language culture.

**1. Identify the speakers.** From the extracted strings: `sorted({s["speaker"] for s in strings})`. For each code, fill in `name`, `gender`, and a one-line `role` covering relationship to the protagonist and personality ("strict literature professor", "frat brother, crude"). Unknown minor codes can stay rough; the major cast must be precise — register accuracy depends on it.

Watch for **one character under several codes** — a love interest who is `"???"` until introduced, a `_thinking` variant. Give the extra code `{"alias_of": "<main code>"}` so the two share one record and one set of QA rules instead of drifting apart.

**2. Map the register system.** This is the highest-value step for languages with pronoun/formality systems (Thai, Japanese, Korean, Vietnamese...). For each major relationship, decide pronouns/speech level both directions: protagonist↔friends, protagonist↔love interests (and how it shifts as routes progress), protagonist↔authority figures, rivals→protagonist. If a game has tone-shifting mechanics (e.g. a crude-vs-polite stat), document how each path maps to registers.

**Put the machine-readable part in `profile.json` → `speakers`, not in prose.** Prose can't be queried, validated, or injected into a prompt:

```json
"mc": {
  "name": "MC", "gender": "male", "role": "protagonist",
  "register": "18-year-old male, casual contemporary",
  "self_pronoun": "<default>", "address_pronoun": "<default>",
  "monologue": { "self_pronoun": "<inner-thought form>" },
  "called": ["<nicknames the script uses to address them>"],
  "to": {
    "sage": { "self_pronoun": "…", "address_pronoun": "…", "note": "closest friend" },
    "prof": { "self_pronoun": "…", "address_pronoun": "…",
              "forbidden": ["<terms never used TO this person>"] }
  },
  "forbidden": ["<terms this character never uses>"],
  "examples": [{ "en": "…", "tr": "…", "note": "why this rendering is right" }]
}
```

The `to` map is the important part: a pronoun is a property of the **pair**. Declaring it once here beats repeating it in prose, because `translate_api.py` puts the table in the prompt and `qa_check.py` enforces `forbidden` automatically — no `qa_rules.json` entry needed.

**Which pair applies to a line is worked out for you, where it can be.** `relationships.py` resolves the addressee from three kinds of evidence — a scope you declared, a name addressed in vocative position in the English line, or a Ren'Py label containing exactly two character speakers — and leaves every other line unresolved rather than guessing. Resolved lines get `"to": "<name>"` in the translation prompt and can be checked by category-3 QA rules; unresolved lines behave exactly as they did before, with the whole `to` table shown to the translator.

Two limits worth knowing before you read the numbers. The vocative tier essentially never resolves *to the protagonist*, because most games render the player's name as a `[variable]` and a player-chosen name cannot be listed in `called` — lines addressed to the MC lean entirely on the dyad and declared tiers. And the dyad tier sees who *speaks* in a scene, not who is *present*: a third character standing there silently is invisible to it. Both are what `declared` scopes are for.

Run the report early — before batch 1, right after the speakers are filled in:

```
python relationships.py --profile profile.json
```

It tells you the resolution rate per tier, why the rest did not resolve, which labels are two-person scenes, **which resolved pairs have no declared register yet** (the most useful column — it is a to-do list for step 2), and which speaker codes have no character record at all. Two knobs, both under `profile.json` → `relationships`:

- `min_confidence` (`dyad` | `vocative` | `declared`, default `dyad`) — the weakest evidence allowed to act. Raise it if you check the report and disagree with a tier.
- `declared` — hand-authored scopes for passages resolution gets wrong or cannot see (a crowded scene, a phone call, a letter read aloud). They outrank every other tier:

```json
"relationships": {
  "declared": [
    { "label": "ep1_dorm_argument", "cast": ["mc", "sage"] },
    { "file": "script.rpy", "lines": [1200, 1310], "pairs": { "mc": "prof" } }
  ]
}
```

One source word can need three different renderings depending on who says it to whom — a term of address from the protagonist to a stranger, from an inner voice to the protagonist, and describing an absent third party are three different words. Encode the mechanical part in `to`; write the reasoning in `translation-guide.md`.

Keep `translation-guide.md` for the *reasoning* and anything prose-shaped. Two `examples` per character reach the prompt; a `note` explaining **why** a rendering is right is worth more than a third example.

**3. Build the keep-untranslated list.** Character names, place names, faction/club names, branded mechanics. These go in `profile.json` `keep_untranslated` (which also whitelists them for QA's untranslated-word check).

**4. Set the slang/profanity policy.** Translate intent, not words: list the source game's recurring profanity and idioms with target-language equivalents by context. State explicitly that NSFW register must not be sanitized (or whatever the user wants).

**5. Pick fonts (non-Latin targets).** Find a font covering the target script with a license that allows redistribution (e.g. SIPA/national fonts for Thai, Noto for almost everything). Test it at the game's dialog size; if it renders smaller than the original font, set `font.size_scale` (Thai TH Krub needed 1.3). List the game's original font files (from `gui.rpy`/`gui.rpa`) in `font.replace_fonts`. **Don't commit font files to a repo — link to their source.**

**6. Decide toggle/auto-set.** If the game's Preferences has no language picker, set `auto_set_language: true` and a `toggle_key` so players can flip languages in-game.

**7. Set the validation gate.** For a non-Latin target, set `validation.target_script` (`"thai"`, `"japanese"`, `"cyrillic"`, … or explicit `{"ranges": ["0E00-0E7F"]}`). This turns on the check that a translation actually contains target-script characters — off by default so that upgrading the tooling can't break an existing project, but you want it on from day one on a new one. The echo check (translation == source) is always on and needs no configuration. See `qa.md` for the category-1 codes.

## Maintaining the profile

The profile is living documentation. When the user corrects a translation pattern ("X should never use pronoun Y"), update `translation-guide.md` AND add a `qa_rules.json` rule enforcing it — corrections that only live in chat history get lost. Then run the **backward audit** (`qa.md`): the rule you just learned was broken in everything translated before you learned it, and `qa_check.py` re-scans the whole corpus every run, so the back catalogue comes free.
