# Phase 4: Translating

Both paths write to the same resumable progress file (`profile.json` → `progress_file`): a flat JSON object `{ "english text": "translation" }`. Keys must match the extracted English **exactly** (same escapes, same tags).

## Path A — Claude in-session (default; quality path)

Protocol per working session:

1. Load the game's `translation-guide.md` into context. For long sessions, re-skim it whenever register questions come up — drift is the main failure mode.
2. Pick the next untranslated strings: entries of `strings.json` whose `text` is not yet in the progress file. Work in batches of ~20, keeping batches contiguous by file+line so scene context is visible.
3. For each line, consider: who is speaking (speaker code → profile), to whom (look at surrounding lines — register often depends on the listener, not the speaker), and kind (`menu` choices are usually imperative/short; monologue keeps its `(...)` wrapper).
4. Write the batch into the progress file (read-modify-write the JSON; never truncate it).
5. After each session: `python qa_check.py --profile profile.json --technical-only` — zero category-1 issues before moving on. Run the full QA periodically.

Quality rules that matter more than speed:

- Translate **meaning and register**, not words. Jokes, idioms, and innuendo get target-language equivalents.
- Consistency: recurring phrases (greetings, catchphrases, UI-ish strings) should translate identically every time — keep a small consistency table in the guide as you go.
- When the same English line is spoken in incompatible contexts (runtime-filter limitation: one translation per string), pick the most frequent context's register or a register-neutral phrasing, and log the string in the profile's notes.

## Path B — API bulk first-pass

```
python translate_api.py --profile profile.json
```

- Needs `GEMINI_API_KEY` in env or `.env` (or adapt `make_call_model()` for another provider).
- Batches per `profile.api.batch_size`, injects speaker blurbs and the style guide into the prompt, validates token preservation, retries mismatches once, saves incrementally — safe to interrupt and rerun.
- Strings that fail token validation twice stay untranslated (they'll display in the original language) — list them at the end from `strings.json` minus progress keys.

**A bulk pass is a draft, not a deliverable.** Follow it with the full QA (`qa_check.py`) and a Claude review of: every flagged issue, all `menu` strings (short strings machine-translate worst), and a random sample of major-character dialog against the style guide.
