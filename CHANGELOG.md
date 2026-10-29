# Changelog

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
