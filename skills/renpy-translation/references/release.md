# Phase 8: Packaging and release

Do this after `verify-in-engine.md`'s release smoke checklist passes. A patch that works for you is not yet something a stranger can install.

## The zip

Patch folder, font files, any first-launch / credit files that live in `game/`, and a `README.txt` with the **target language first, English second**:

- what it is, and the exact game and engine version it was built for (for example `v1.5.18, Ren'Py 8.3.4`). A game update silently invalidates the dictionary; say how to re-extract;
- install, **uninstall** (delete the patch folder), how to switch language, how to type in the target script;
- known limits: baked-in image text, anything the coverage audit left out (`extraction.md`), saves;
- terms: fan work, not affiliated, no selling, keep the credit, font licence;
- contact.

**Upgrade path.** Tell people to delete the previous patch folder before copying the new one. Two copies define everything twice and crash. If the folder layout changed between builds (`tl/<lang>` → `<lang>_patch`), say so in bold. Keep one zip filename when you update in place.

## Credit and watermark

- Translator credit on the main menu and in the README, not inside the dictionary.
- A watermark is ownership evidence, not protection: canary dictionary entries (fake English keys that never occur) mapped to unique target sentences derived by HMAC from a secret plus a recipient tag. Keep the secret and the log out of the zip, and say honestly that anyone who looks can remove it. With a public link, per-recipient tags are pointless: ship one build.

## Promo

Official cover art and real screenshots cropped to the speaker box. Avoid revealing crops. Text must be real rendered text (see the locale file for scripts that mis-shape).

## Never publish

Game text, extracted strings, translation dictionaries, archives or commercial fonts stay out of this repository (AGENTS.md rule 4). The zip you hand to testers is yours to distribute; this repo is tools and guides only.
