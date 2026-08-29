# Phase 2: Extracting translatable strings

```
python extract_strings.py --src decompiled/ --out strings.json
# or, once the profile exists:
python extract_strings.py --profile profile.json --screens
```

Output: a JSON list of `{text, speaker, file, line, kind, label, label_cast}` where `kind` is:

- `say` — `speaker "text"` dialog lines
- `narrator` — bare quoted strings (narration)
- `menu` — player choice captions (`"Choice text":` / `"Choice text" if cond:`)
- `text` — `show text "..."` on-screen text
- `screen` (with `--screens`) — literal `text`/`textbutton`/`label`/`tooltip` strings inside `screen` blocks (speaker `_screen`)
- `ui` (with `--screens`) — `_("...")`-wrapped strings anywhere, including python blocks and `$` lines (speaker `_ui`)

`label` is the enclosing Ren'Py label (or `null` outside any) — the script's own scene boundary. `label_cast` (on dialog lines) is every speaker code appearing in that label, recorded **before** deduplication, and it is what `relationships.py` reads to decide whether a scene has exactly two people in it. The two fields are separate because dedupe drops a line whose text appeared earlier: a character whose only line in a scene is "Yeah." leaves no trace in the corpus, and counting who is left would read a three-person scene as a two-person one. **Re-extract after upgrading from a pre-v1.5 project**, or that resolution tier is simply unavailable (the report will say so).

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
- Check `sorted({s["speaker"] for s in strings})` — this is also the input for building the profile's speaker table. Once the profile exists, `relationships.py --profile profile.json` lists any speaker code that still has no record.
- Check that labels came through: `len({(s["file"], s["label"]) for s in strings if s["label"]})` should look like the number of scenes in the game, not 0 or 1. Every `say` entry with a `label` should also carry a non-empty `label_cast`.
- Spot-check a few extracted strings against the source to confirm quotes/escapes survived (`\"` stays as the two characters `\"`).
