# Phase 2: Extracting translatable strings

```
python extract_strings.py --src decompiled/ --out strings.json
# or, once the profile exists:
python extract_strings.py --profile profile.json --screens
```

Output: a JSON list of `{text, speaker, file, line, kind}` where `kind` is:

- `say` — `speaker "text"` dialog lines
- `narrator` — bare quoted strings (narration)
- `menu` — player choice captions (`"Choice text":` / `"Choice text" if cond:`)
- `text` — `show text "..."` on-screen text
- `screen` (with `--screens`) — literal `text`/`textbutton`/`label`/`tooltip` strings inside `screen` blocks (speaker `_screen`)
- `ui` (with `--screens`) — `_("...")`-wrapped strings anywhere, including python blocks and `$` lines (speaker `_ui`)

By default duplicates are removed by exact text (first occurrence kept for context) — correct for the runtime-filter patch, which is a one-to-one dict. Pass `--no-dedupe` when targeting native `translate` blocks.

**Use `--screens` when GUI text is in scope.** `screen`/`ui` strings can't be reached by the runtime say filter; `build_patch.py` routes them into a `translate <lang> strings:` file instead (see `patching.md`). Pure-interpolation literals like `"[points]"` and empty strings are skipped.

## What the extractor catches and misses

Catches: standard dialog, narration, menu choices, `show text`; with `--screens` also screen-language literals and `_()` strings. Skips: comments, `$` one-liners, `python:` blocks, lines whose "speaker" is a Ren'Py keyword.

**Still misses (by design — verify per game):**

- Strings built dynamically in Python (`renpy.say`, concatenation, `%`/`.format`, lists of chat messages) — these need the wrapper pattern in `custom-subsystems.md`
- Character name definitions (`define x = Character("Name")`)

After extraction, grep the sources for `renpy.say`, list-of-strings assignments, and the screens of any phone/computer/feed UI to estimate what a custom-subsystem pass would need. Decide with the user whether those are in scope **before** translating (see `custom-subsystems.md`).

## Sanity checks

- Compare per-file string counts against eyeballing the file — a file with dialog but 0 extracted strings means an unusual say format.
- Check `sorted({s["speaker"] for s in strings})` — this is also the input for building the profile's speaker table.
- Spot-check a few extracted strings against the source to confirm quotes/escapes survived (`\"` stays as the two characters `\"`).
