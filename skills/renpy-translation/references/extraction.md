# Phase 2: Extracting translatable strings

```
python extract_strings.py --src decompiled/ --out strings.json
# or, once the profile exists:
python extract_strings.py --profile profile.json
```

Output: a JSON list of `{text, speaker, file, line, kind}` where `kind` is:

- `say` — `speaker "text"` dialog lines
- `narrator` — bare quoted strings (narration)
- `menu` — player choice captions (`"Choice text":` / `"Choice text" if cond:`)
- `text` — `show text "..."` on-screen text

By default duplicates are removed by exact text (first occurrence kept for context) — correct for the runtime-filter patch, which is a one-to-one dict. Pass `--no-dedupe` when targeting native `translate` blocks.

## What the extractor catches and misses

Catches: standard dialog, narration, menu choices, `show text`. Skips: comments, `$` one-liners, `python:` blocks, lines whose "speaker" is a Ren'Py keyword.

**Misses (by design — verify per game):**

- Strings inside `screen` definitions (`text "..."`, `textbutton "..."`) — GUI labels, custom phone/computer UIs
- Strings built in Python (`renpy.say`, string concatenation, f-strings, lists of messages)
- `_()`-wrapped translatable strings in code
- Character name definitions (`define x = Character("Name")`)

After extraction, grep the sources for `screen `, `text "`, `textbutton "`, and `renpy.say` to estimate what a custom-UI pass would need. Decide with the user whether GUI/custom subsystems are in scope (they usually need their own wrapper approach — see `patching.md`).

## Sanity checks

- Compare per-file string counts against eyeballing the file — a file with dialog but 0 extracted strings means an unusual say format.
- Check `sorted({s["speaker"] for s in strings})` — this is also the input for building the profile's speaker table.
- Spot-check a few extracted strings against the source to confirm quotes/escapes survived (`\"` stays as the two characters `\"`).
