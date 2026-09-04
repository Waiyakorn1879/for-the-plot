# Lessons learned: Being a DIK → Thai

What shipping the Thai patch taught us — EP1 first (2,638 strings → 2,636 translated, 99.9%), then Episodes 1–8 (~36,000 strings, 99%+), with Season 3 in progress and an in-game phone-chat sub-patch on the side. Read this when starting a new game — most of it generalizes.

## Numbers that calibrate expectations

- EP1 alone: 2,638 unique strings across 8 decompiled `.rpy` files (one 234 KB main script + freeroams + a report screen). Full game EP1–8: ~36,000, plus ~1,000 more in the phone system that the say-filter can't see (its own sub-dictionaries and wrapper layer).
- API bulk pass: 99%+ acceptance with token validation + one retry. A handful of strings per episode with unstable tag formatting failed validation twice and were left displaying English — acceptable; chasing the last fraction of a percent isn't worth it. EP1 ran on Gemini 2.5 Pro at batches of 20; by Season 3 the bulk pass had moved to the headless **Claude Code CLI provider** (no API key) at batches of 200, with the style guide loaded once per session instead of re-sent per batch.
- The QA + register-fix loop took comparable effort to the initial translation, **every episode**. It does not amortize — each episode brings new scenes, new pairings, and new register edge cases. Budget for it per episode, not once.
- Register knowledge compounds across episodes: the pronoun matrix and per-character `forbidden` lists built for EP1 carried forward, and the Translation Memory made repeated lines and game-version bumps free. New-character cost (Season 3 adds Zoey, Nicole, Elena) is a profile edit, not a re-translation.

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

## What v1.4 changes about this example

The pronoun matrix in `pronoun-reference.md` was written and maintained **by
hand**, and it is the single most valuable artifact in this project — but
nothing could read it. Prose can't be injected into a prompt or checked by a
tool, so every pronoun rule had to be re-stated as a QA regex and re-explained
to the translator in every session.

The machine-readable half of that knowledge now lives in `profile.json` →
`speakers`, and `mc` / `my` / `sa` / `isa` here are filled in as a worked
example of the shape:

- **`to` maps are the point.** `mc` declares เรา/แก for Sage, Maya and Josy but
  ผม/คุณ for Isabella, Jill and Cathy. That is exactly what
  `pronoun-reference.md` says in prose — but now the translation prompt shows
  it automatically for whichever characters appear in the batch.
- **`forbidden` replaces a QA rule.** Maya's "ไม่ใช้ กู/มึง เด็ดขาด" was a
  hand-written pattern; it is now a field on her record that produces the QA
  rule *and* the `NEVER use` line in her persona card, from one source.
- **`monologue.self_pronoun`** captures "inner monologue always uses กู",
  which previously survived only as a paragraph in `character-profiles.md`.

Keep `character-profiles.md` and `pronoun-reference.md`: they hold the
*reasoning*, the English speech patterns, and the cases that don't reduce to
fields. The record is the enforceable subset, not a replacement.

Note the remaining overlap in `qa_rules.json`: the blanket `กู ← female` and
`มึง ← female` rules predate character records and now double-report for Maya
and Isabella, who declare those terms forbidden individually. On a new project,
prefer per-character `forbidden` for speaker-identity rules and keep
`qa_rules.json` for **context**-dependent ones (`near`), which records can't
express.

## What v1.5 changes about this example

The section above says the quiet part: *register is a context problem*, and
the context that mattered was **who MC is talking to**. This project answered
that with the ±12-line proximity heuristic, because nothing better existed. It
worked well enough to catch most violations — as a *report*. It was never
trustworthy enough to decide a pronoun.

v1.5 separates those two jobs. `relationships.py` resolves the addressee from
evidence it can name — a declared scope, a name addressed in vocative position
in the English, or a Ren'Py label with exactly two character speakers — and
says *unresolved* for everything else. What that buys, concretely, on a
project shaped like this one:

- **The prompt names the listener.** On a resolved line the translator is told
  `"to": "Sage"` rather than being handed MC's whole six-row `to` table and
  asked to work it out from the scene. The table still travels for the lines
  that don't resolve.
- **`to[…].forbidden` makes the pronoun matrix enforceable per pair.** MC's
  Isabella row said *"professor — formal, never กู/มึง"* in a `note` — a
  sentence no tool could read. It is now a field, and it generates the
  category-3 rule automatically. Compare that with the `near`-based
  `ผม-group กู` rule, which fires on *company* rather than on *addressee*.
- **`relationships.py --profile profile.json` is the audit that did not exist.**
  The 20+ one-off fix scripts this project wrote were all answering questions
  the report answers by construction: which pairs actually occur, which of them
  have no declared register yet, and which speaker codes never got a record at
  all (`ice`, `dad2`, `kid` in this profile are exactly that shape).

The overlap note above now has a second case: on a line whose addressee
resolves to Isabella, both the new per-relationship rule and the older
`ผม-group กู` proximity rule can report the same violation. That is redundancy,
not a false positive, and this repo's stated bias is toward noise over silence
— but on a new project, prefer the addressee-based rule and keep `near` for
the register questions that genuinely depend on **who is present** rather than
on who is addressed (a crude line is crude because a professor is in the room,
whoever it was aimed at).

What v1.5 still does not fix, and this project would still hit: one English
line can only carry one translation in the runtime-filter patch. Knowing that
MC said "You." to Sage in one scene and to Isabella in another does not let
the patch ship both renderings — that needs native translate blocks and
occurrence-aware translation.
