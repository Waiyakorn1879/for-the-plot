# Phase 3: The game profile

A profile is the per-game/per-language knowledge base. Everything game- or language-specific lives here; the scripts and skill stay generic. It consists of:

| File | Consumed by | Contains |
|---|---|---|
| `profile.json` | all scripts | machine config (schema: `scripts/profile_schema.json`) |
| `translation-guide.md` | translator (Claude or API prompt) | registers, formality, slang policy, few-shot examples |
| `qa_rules.json` | `qa_check.py` | declarative register checks (see `qa.md`) |

Worked example: `examples/badik-thai/` — copy its **structure** for a new game, never its content.

## Building a profile: the interview

Work through these with the user; they know the game and the target-language culture.

**1. Identify the speakers.** From the extracted strings: `sorted({s["speaker"] for s in strings})`. For each code, fill in `name`, `gender`, and a one-line `role` covering relationship to the protagonist and personality ("strict literature professor", "frat brother, crude"). Unknown minor codes can stay rough; the major cast must be precise — register accuracy depends on it.

**2. Map the register system.** This is the highest-value step for languages with pronoun/formality systems (Thai, Japanese, Korean, Vietnamese...). For each major relationship, decide pronouns/speech level both directions: protagonist↔friends, protagonist↔love interests (and how it shifts as routes progress), protagonist↔authority figures, rivals→protagonist. Capture it in `translation-guide.md` with a few-shot example per archetype, not per character. If a game has tone-shifting mechanics (e.g. a crude-vs-polite stat), document how each path maps to registers.

**3. Build the keep-untranslated list.** Character names, place names, faction/club names, branded mechanics. These go in `profile.json` `keep_untranslated` (which also whitelists them for QA's untranslated-word check).

**4. Set the slang/profanity policy.** Translate intent, not words: list the source game's recurring profanity and idioms with target-language equivalents by context. State explicitly that NSFW register must not be sanitized (or whatever the user wants).

**5. Pick fonts (non-Latin targets).** Find a font covering the target script with a license that allows redistribution (e.g. SIPA/national fonts for Thai, Noto for almost everything). Test it at the game's dialog size; if it renders smaller than the original font, set `font.size_scale` (Thai TH Krub needed 1.3). List the game's original font files (from `gui.rpy`/`gui.rpa`) in `font.replace_fonts`. **Don't commit font files to a repo — link to their source.**

**6. Decide toggle/auto-set.** If the game's Preferences has no language picker, set `auto_set_language: true` and a `toggle_key` so players can flip languages in-game.

## Maintaining the profile

The profile is living documentation. When the user corrects a translation pattern ("X should never use pronoun Y"), update `translation-guide.md` AND add a `qa_rules.json` rule enforcing it — corrections that only live in chat history get lost.
