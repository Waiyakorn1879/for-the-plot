# Changelog

## 1.6.2

Fixes from a review of the 1.6.1 tools. No data format changes. QA is stricter, so a project that passed before may now report issues that were always there.

- **`qa_check.py` judges speaker overrides.** `speaker_translations.json` was never read by QA, so an echoed or token-damaged override passed and shipped — and overrides win over the dictionary at runtime. Every override now gets the category-1 checks (reported as `OVERRIDE ...`), and register rules judge each speaker on their override when they have one.
- **`build_patch.py` does not ship an override that fails the gate.** It is dropped with a warning and the line falls back to the dictionary translation.
- **`punctuation.py --write` can no longer save an empty translation.** A softened result is held to the validity gate; entries that would fail are left alone and counted.
- **`translate_api.py`:** a transport error during the retry call no longer aborts the run and loses the batch's accepted lines. Lines the model left out or whose tokens changed are now counted in the summary (`MISSING`, `TOKEN`) instead of being skipped silently.
- **`qa_check.py` finds a key spelled the other way** (escaped quote, curly apostrophe), as `edit_lines.py` and `pair_audit.py` already did, instead of reporting it MISSING.
- **`edit_lines.py` exits 1 when an edit is REJECTED** (edits that pass are still applied), matching `speaker_overrides.py merge`.
- **`find_twins.py` also checks the speaker overrides file.**
- **`build_patch.py` emits each key under the other apostrophe spelling too** (`It’s` / `It's`), for the dictionary and for speaker overrides. The runtime filter matches exactly, so a key typed with the wrong apostrophe used to leave that line in English. A spelling that is already a key of its own is never overwritten; the dict file gains one extra block and is otherwise unchanged.
- **Chinese targets** (`orthography.py`, `references/chinese.md`): the translation prompt states the conventions (one script, full-width punctuation, `……`, no inter-character spaces, ASCII tokens) and QA checks the same list. `orthography.py --write` fixes punctuation, ellipses and spacing; a Simplified/Traditional leak is reported, never converted. A leak is a hard issue only when the profile names the variant (new `schinese` / `tchinese` scaffolds do); on existing projects everything is a review flag. Turn off with `"orthography": false`.
- **Chinese targets, smaller changes:** the "short?" flag uses a 0.10 ratio (Chinese is far shorter than English); the exclamation policy handles `！`; a thought wrapped in full-width `（ ）` is recognised; `zh_cn`-style language ids are known.
- **`qa_check.py`'s untranslated-word flag ignores words inside tokens** (`[partner_name]` was reported as `roman:partner,name`).
- **`translate_api.py` backs up the progress file** before the first write of a run that changes it (`translations.json.bak-<timestamp>`; `--no-backup` to skip). A run with nothing to do makes no backup.
- **Scaffolded `.gitignore` now excludes `speaker_translations.json`, its todo file and `*.bak-*`.** All three hold game text and were not covered. Existing projects: add those three lines by hand.
- **`qa_check.py`** reports a missing strings or translations file with a message instead of a traceback.
- **CI:** Python 3.8 is now tested (the docs always claimed it), plus an advisory Windows job.
- **Docs:** PLAYBOOK §5 lists backups as implemented; this changelog is backfilled to 1.0.0.

## 1.6.1

Tooling from a second full-game (Thai) translation. No data format changes; every new key is optional.

- **Extractor:** accepts `"text"with dis08` (no space before `with`) — those lines were silently skipped, so re-extracting may yield more lines than before. The say-trailer regex is also linear now; a malformed line with many `with` words could previously hang it.
- **`edit_lines.py`:** fix specific lines by `file:line` with regex jobs. Dry-run by default, backup on `--write`, same validity gate as `speaker_overrides.py merge`, warns when a dictionary entry is shared with lines you are not editing.
- **`find_twins.py`:** dictionary keys that differ only by an escaped quote or a curly apostrophe yet translate differently (exit 1).
- **`pair_audit.py`:** register leaks inside two-speaker conversation runs; pairs are declared in `qa_rules.json`. A review list; it never feeds addressee resolution.
- **`punctuation.py`:** opt-in exclamation-mark policy (`punctuation.exclamation` in the profile) with an informational QA counter.
- **`thai_text.py`** and `mask_tokens` in `validation.py`: safe Thai word replacement that cannot touch variables, tags or escapes.
- **`build_patch.py`:** `font.text_size` is a one-time default that respects the player's own size choice.
- **Docs:** `references/verify-in-engine.md` — test-copy recipe, `APPDATA` redirect, install sanity check.

## 1.6.0

- **Terminology Dictionary** (`terminology.py`): a term lifecycle from DISCOVERED to ENFORCED, an exact word-bounded matcher that refuses equal-priority ties, a preflight report, a sweep for candidate terms, and migration from `keep_untranslated`.
- ENFORCED terms are checked by the shared validity gate at every point: bulk save, Translation Memory read, and QA category 1. The retry names each violation per line.
- **`speaker_overrides.py`:** per-speaker translations for texts said by both genders (`todo` / `merge` / `status`).

## 1.5.2

- **`replay_vars.py`:** finds variables a gallery replay would crash on and writes a `store_defaults` skeleton.
- **Extractor:** all Ren'Py say forms (attributes, `with` / `nointeract` / `id` / argument trailers), `renpy.input` prompts, a warning for dialogue-shaped lines it skips, and `also_spoken_by` on deduplicated texts.
- **Thai gender-aware speech** in the prompt and in QA: male/female particles enforced, unisex for unknown speakers, extras and mixed-gender shared lines. QA judges a shared text against every speaker.
- **Profile-driven runtime hooks** in the patch: replay safety net, nameplate patterns, input sync, text size.
- **`build_patch.py`** warns when a generated file was edited by hand.

## 1.5.1

Hardening from an outside architecture review.

- **TAGNEST:** a close tag that does not match the innermost open tag is refused by the shared gate (bulk save, retry, QA category 1, TM read). The tag count is unchanged by such an error, so token parity could not see it.
- **Prompt boundary:** the system prompt states that input is data, not instructions.
- **Reply parser** prefers the array that looks like a batch reply over the first array of any shape.

## 1.5.0

- **Relationship Dictionary** (`relationships.py`): resolves who each line is spoken to from named evidence only: a declared scope, a name in vocative position, or a scene label with exactly two speakers. Everything else is reported unresolved with a reason; there is deliberately no "who spoke nearby" tier.
- Resolved addressees feed the translation prompt, the Translation Memory variant key, and category-3 QA rules.

## 1.4.0

- **`init_project.py`:** scaffolds the project folder beside the game, including `TRANSLATION.md` as the single always-loaded instruction file with `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` stubs pointing at it.
- **Character Dictionary:** `profile.json` -> `speakers` carries register, forbidden/required vocabulary, examples, a monologue override and per-relationship pronouns. Each record becomes both a persona card in the prompt and a QA rule.
- **DeepSeek provider preset**, thinking mode off by default. Empty replies are diagnosed with their real cause, retried once at a raised token budget, and never saved.
- **Fixes:** stderr is UTF-8 on every script; `alias_of` now resolves in the Translation Memory context and in hand-written QA rules.

## 1.3.0

- **Contextual Translation Memory:** one source text can hold a default translation plus speaker-aware variants, selected deterministically. Version 1 memory files migrate on load.

## 1.2.0

- **Translation Memory** (`translation_memory.py`): a persistent source-to-translation cache consulted before every model call, with `stats` / `export` / `import` / `clean`. A re-run makes no model calls; a game update translates only the new lines.

## 1.1.2

- The assistant always asks which translation method to use (in-session, API key, or agent) before translating.

## 1.1.1

- Reply parsing survives ANSI codes, banners, code fences and trailing chatter.
- `claude-cli` provider: per-call timeout, neutral working directory, feature detection.
- `_()` extraction matches single-quoted strings; the `old` side of `translate strings` blocks is decoded and re-encoded so nested quotes and backslashes match.

## 1.1.0

- **GUI strings:** `extract_strings.py --screens` and a native `translate <language> strings:` file in the patch.
- **Providers:** Gemini, Anthropic and headless Claude Code CLI.
- Test suite and CI.

## 1.0.0

- First release: the Ren'Py translation workflow (decompile, extract, profile, translate, QA, runtime-filter patch) as a Claude Code plugin.
