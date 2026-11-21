# Thai

Thai has no spaces between words, gendered speech particles, and a pronoun system that depends on the relationship between speaker and listener. Read this at the Profile phase. The reference implementation is `examples/eternum-thai/` (Eternum, about 45,000 strings): copy its structure, never its content.

**Language id:** `thai`. Set `validation.target_script` to `"thai"` (the scaffold does this). The Thai-specific code is `GENDER_GRAMMAR` in `scripts/characters.py` and the library `scripts/thai_text.py`; there is no `langs/` module because there are no mechanical writing conventions to fix.

## Register

The pronoun belongs to the pair, not the person: the same protagonist uses one form with a close friend and another with a professor. Declare it per character and per relationship in `speakers` (`to`), as [game-profile.md](../game-profile.md) describes. `examples/eternum-thai/profile.json` (per-pair `to` blocks) and its `translation-guide.md` (a dyad table) show the matrix.

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

Values from the Eternum profile (`examples/eternum-thai/profile.json`); treat them as a starting point and measure in the engine:

- The original game fonts have no Thai glyphs. Set `font.regular` (Eternum used Prompt Medium, with Prompt SemiBold as the italic) and list the game's font files in `font.replace_fonts` (Eternum lists eleven).
- Eternum runs with `font.size_scale` 1.0 and `font.text_size` 28 ([patching.md](../patching.md)). A different Thai font can render smaller than the original one: raise `size_scale` if it does.
- Stacked vowels and tone marks exceed Latin-derived ascent and descent, so wrapped lines can collide. Engines without a dictionary for unspaced scripts can also treat a whole sentence as one unbreakable word. Both are pre-flight checks in [engine-seam.md](../engine-seam.md).
- Check a sample of every episode in the running game: [verify-in-engine.md](../verify-in-engine.md).

## Line breaking and rendering (v1.6.5)

- **Ren'Py wraps only at spaces.** In fixed-width boxes (tutorials, phone bubbles) Thai overflows. Insert a space at word boundaries every ~30 characters with `pythainlp.word_tokenize` for UI boxes; dialogue is fine with the translator's own phrase spacing.
- **Zero-width characters** (ZWSP etc.) are missing from common Thai fonts and show as tofu. Check the font's cmap before using any invisible character, including for watermarks.
- **Do not use `kerning`** (it detaches vowels and tone marks) and avoid faux bold on small text. Map *every* font the game references (scan the decompiled sources) to the Thai files; tiny styles (phone comments, achievements) need a `translate <lang> style <name>: size N` block.
- **PIL without libraqm cannot shape Thai**; render promo text in a browser or reuse real screenshots. Image-generation models mangle Thai text.
- Register belongs to the speaker pair *and* mood (กู/มึง in anger, ฉัน/นาย when calm); ค่ะ/คะ/ครับ follow speaker gender and addressee authority. A spelling-ban list in `qa_rules.json` is cheap and very effective.
