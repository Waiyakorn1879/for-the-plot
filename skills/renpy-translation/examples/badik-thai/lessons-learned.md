# Lessons learned: Being a DIK → Thai

What shipping the EP1 Thai patch (2,638 strings → 2,636 translated, 99.9%) taught us. Read this when starting a new game — most of it generalizes.

## Numbers that calibrate expectations

- EP1 alone: 2,638 unique strings across 8 decompiled `.rpy` files (one 234 KB main script + freeroams + a report screen).
- API bulk pass (Gemini 2.5 Pro, batches of 20, token validation + one retry): 99.9% acceptance. 2 strings with unstable tag formatting failed validation twice and were left displaying English — acceptable; chasing the last 0.1% wasn't worth it.
- The QA + register-fix loop took comparable effort to the initial translation. Budget for it.

## Register is a context problem, not a speaker problem

The big quality issue wasn't vocabulary — it was Thai pronouns. MC's correct pronoun depends on **who he's talking to** (กู/มึง with frat bros, ผม with professors and most women, เรา with close female friends), and the speaker metadata alone can't tell you that. Two mitigations that worked:

1. The context-window heuristic (±12 strings in the same file → who's in the scene) caught most violations mechanically. It's now `qa_check.py`'s `near` condition.
2. A pronoun matrix per character relationship (see `pronoun-reference.md`) written down BEFORE translating beats fixing afterwards. We learned this the expensive way — 20+ one-off audit/fix scripts existed before the matrix did.

Inner monologue is exempt: MC thinks in กู even about people he'd address as ผม. Hence `skip_monologue` in the rules.

## Runtime filter: what held up

- `config.say_menu_text_filter` + exact-match dict survived game restarts, mod presence, and bad strings (misses just render English — zero crashes in practice).
- **Chain, don't replace, existing filters.** SanchoMod installs its own filter; translating first and then calling the mod's filter (and re-installing via `start`/`after_load` callbacks, with an `_owned` marker to avoid double-wrapping) made the two coexist.
- Ren'Py compiling the patch to `.rpyc` on first launch is the cheapest syntax check there is.

## Fonts

TH Krub renders ~25–30% smaller than the game's Audrey/Candara at the same point size → `size_scale: 1.3` plus per-style base sizes. Two mechanisms were both needed: explicit style overrides for the main text styles AND `config.font_replacement_map` as a catch-all for styles we missed. Hooking `renpy.change_language` to re-apply font overrides keeps the toggle key working mid-session.

## What the say-filter could NOT reach

The in-game phone chat system renders text through its own screens/functions — the filter never sees it. It needed dedicated sub-dictionaries plus wrapper functions around the phone-reply producers, per season (`game/tl/thai/phone/`). Lesson: inventory custom text subsystems (phone, computer, social feed, gallery captions) during extraction and scope them explicitly with the user.

Also intentionally out of scope, and worth agreeing upfront for any game: GUI/menu strings inside `gui.rpa`, mod menus, and character name displays (kept English to preserve their color tags).

## Process

- Keep the progress JSON as the single source of truth; every other artifact (patch files, QA reports) regenerates from it.
- Resumability paid off constantly — API failures, interrupted sessions, re-translation of weak batches all just re-ran.
- When the user corrects a pattern ("MC must use ผม with all female characters he just met"), encode it as a QA rule immediately; corrections that live only in conversation get re-violated by the next batch.
