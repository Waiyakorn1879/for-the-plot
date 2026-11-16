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
