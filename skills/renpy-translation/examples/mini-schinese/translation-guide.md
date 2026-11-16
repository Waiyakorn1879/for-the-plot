# Pocket Cafe → Simplified Chinese: style guide (worked example)

This is a small, **synthetic** example: the game is the test fixture in `tests/fixtures/`, written for this repository, not a real title. It shows the structure a Chinese project's guide should have. Read `references/locales/chinese.md` and `chinese-simplified.md` first.

## 1. Script and region
Simplified Chinese, Mainland usage. One script only: never mix in Traditional forms.

## 2. Punctuation
Full-width `，。？！：；、`. An ellipsis is `……`, a dash `——`. Quotation marks are `“ ”` with `‘ ’` inside. Titles of works use `《 》`. Tokens (`[name]`, `{i}`, `\n`, `%%`) stay ASCII and unchanged. No spaces between Chinese characters.

## 3. Names
Transliterate, and spell each one the same way everywhere: Nora → 诺拉, Emma → 艾玛, Reed → 里德. Record each in the terminology dictionary. Join the parts of a longer foreign name with `·`.

## 4. Thoughts
A line wrapped in `( )` is an inner thought. Keep the half-width brackets around the whole line and write the thought in the character's own voice.

## 5. Address
Default `你`. `您` only from the protagonist to the professor, and from nobody to a peer. Peers drop pronouns where Chinese would.

## 6. Voice (see `profile.json` → `speakers`)
- **Reed:** short, dry, casual. Self-reference `我`. `您` to the professor only; a peer rule (`to.nora.forbidden`) makes QA flag it anywhere else.
- **Nora:** blunt and clipped; softens with `吧` or `啦` only when she is being kind.
- **Professor:** formal and complete, no slang.

## 7. Profanity and slang
Translate intent with the Mainland equivalent of the same strength. Do not sanitise, and do not escalate.

## 8. Fonts
Set `font.regular` to a Simplified build of Source Han Sans (or Noto Sans CJK SC) and copy the file into the game's `game/` folder. Do not commit the font; link to its source.
