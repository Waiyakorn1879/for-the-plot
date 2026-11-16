# Thai

Thai has no spaces between words, gendered speech particles, and a pronoun system that depends on the relationship between speaker and listener. Read this at the Profile phase. The reference implementation is `examples/badik-thai/` (Being a DIK, about 36,000 strings): copy its structure, never its content.

**Language id:** `thai`. Set `validation.target_script` to `"thai"` (the scaffold does this). The Thai-specific code is `GENDER_GRAMMAR` in `scripts/characters.py` and the library `scripts/thai_text.py`; there is no `langs/` module because there are no mechanical writing conventions to fix.

## Register

The pronoun belongs to the pair, not the person: the same protagonist uses one form with a close friend and another with a professor. Declare it per character and per relationship in `speakers` (`to`), as [game-profile.md](../game-profile.md) describes. `examples/badik-thai/pronoun-reference.md` and `character-profiles.md` show a full matrix.

## Gender-marked speech

When `language_id` is `thai`, the prompt and QA both know the gender grammar:

- **male** speakers must not use `ค่ะ` / `คะ` / `นะคะ` / `ดิฉัน`; **female** speakers must not use `ครับ`. (`คะ` only matches as a particle, so `คะแนน` is safe.)
- **unknown gender, minor extras** (role contains `extra`/`background`/`minor`/`crowd`) **and speakers with no record** stay unisex: none of the above. These are category-2 findings (`Name: unisex speech`, `unknown speaker: gendered speech`).
- A text spoken by several characters (`also_spoken_by` in `strings.json`) is translated once, so the prompt marks it `shared_by` and asks for a unisex rendering when their genders differ; QA checks it against every speaker. Give each gender its own line with `speaker_overrides.py`.
- Opt a character out (a woman who speaks with `ครับ` on purpose) with `"gender_grammar": false` on the record.

## Editing and scanning

- Use `thai_text.replace_word` in edit scripts, never `\b` or `[ะ-์]` lookarounds: Thai has no spaces, and that range contains the leading vowels เ แ โ ใ ไ, so it blocks a valid pronoun stuck to the next word (`แกเอง`).
- Pronouns are often the first letters of unrelated words (`แก` in `แกง`, `กู` in `กูเกิล`). List exclusions explicitly (`not_before`, `not_after`), never as a character class.
- When tuning a QA scanner, bias toward noise, never toward silence: [qa.md](../qa.md) has the `คุณอา` / `คุณอายุ` example that cost a real project a backward fix.

## Fonts and layout

Values from the Being a DIK project; treat them as a starting point and measure in the engine:

- The original game fonts have no Thai glyphs. Set `font.regular` (the project used TH Krub Bold) and list the game's font files in `font.replace_fonts`.
- TH Krub rendered smaller than the original font, so `font.size_scale` was 1.3. Dialogue often needs `font.text_size` around 28 ([patching.md](../patching.md)).
- Stacked vowels and tone marks exceed Latin-derived ascent and descent, so wrapped lines can collide. Engines without a dictionary for unspaced scripts can also treat a whole sentence as one unbreakable word. Both are pre-flight checks in [engine-seam.md](../engine-seam.md).
- Check a sample of every episode in the running game: [verify-in-engine.md](../verify-in-engine.md).
