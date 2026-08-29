# Game translation playbook

A complete, executable procedure for translating a game into another language with an AI assistant. **Ren'Py is the primary target and the only shipped engine adapter**, but the architecture, safety invariants, file contracts, and QA discipline apply to any engine.

This document is written **for an AI assistant** — any of them. Claude Code loads `SKILL.md`, which points here for everything that isn't Claude Code-specific. Gemini CLI, Codex, Cursor, ChatGPT, or a human with a terminal can be pointed at this file directly. The tooling is plain Python 3.8+ with no required dependencies, so nothing here needs a particular harness.

## §0 How to read this document

Every section is tagged. Know which rules you inherit and which you must rebuild before you start.

| Tag | Meaning |
|---|---|
| **[PORTABLE]** | Take as-is. Applies to any game, any engine, any target language, any assistant. |
| **[ADAPT]** | The *shape* of the rule transfers; the *content* is language- or project-specific. Rebuild the content. |
| **[RE-DERIVE]** | Entirely engine- or game-specific. Investigate from scratch. Nothing can be copied. |

## §1 Preconditions [PORTABLE]

- Python 3.8+. The deterministic core has **zero required dependencies**; provider SDKs are optional and only for the bulk path.
- Work in a dedicated project folder **next to** the game install, never inside it.
- **The game installation is read-only.** It is only ever read from. The finished patch is the single thing copied in, and it is removable.
- Never commit or publish game scripts, extracted strings, translation dictionaries of game text, archives, or commercial fonts. Tools and style guides only.

## §2 The pipeline

| # | Phase | Tag | Reference |
|---|---|---|---|
| 0 | Init | **[PORTABLE]** | `scripts/init_project.py` |
| 1 | Decompile | **[RE-DERIVE]** | `references/decompiling.md` |
| 2 | Extract | **[RE-DERIVE]** (output shape is [PORTABLE]) | `references/extraction.md`, `references/engine-seam.md` |
| 3 | Profile | **[PORTABLE]** structure, **[ADAPT]** content | `references/game-profile.md` |
| 4 | Translate | **[PORTABLE]** | `references/translating.md` |
| 5 | QA | **[PORTABLE]** method, **[ADAPT]** rules | `references/qa.md` |
| 6 | Patch | **[RE-DERIVE]** | `references/patching.md` |
| 7 | Deploy | **[RE-DERIVE]** | `references/patching.md` |

Read the reference for a phase **when you reach it**; don't preload everything.

Phase 0 is one command:

```
python scripts/init_project.py --game "<game install>" --language <id>
```

It scaffolds the project beside the game — profile, style-guide skeleton, QA rules, a `.gitignore` that keeps game text out of version control, and **`TRANSLATION.md`**, the project's own always-loaded instruction file, with `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` stubs pointing at it. That file is the point: a translation runs for hundreds of batches across many sessions, and a convention discovered at string 1,400 gets re-broken by string 1,450 unless it lives somewhere loaded every time.

## §2b Character records and relationships [PORTABLE] structure, [RE-DERIVE] cast

`profile.json` → `speakers` is the character dictionary. A record can carry `register`, default and **per-relationship** pronouns (`to`), `forbidden`, `must_use`, an inner-monologue override, and approved `examples`. It feeds the translation prompt as a persona card *and* `qa_check.py` as register rules, from one source — so the voice asked for is the voice checked.

Per-relationship pronouns are the high-value field in register-rich languages: the pronoun belongs to the pair, not the person.

Which pair applies to a given line is answered by `python scripts/relationships.py --profile profile.json` — from a scope you declared, a name addressed in vocative position in the source line, or a scene unit containing exactly two character speakers. Everything else is reported **unresolved, with a reason**, and behaves as it did before: the whole relationship table goes to the translator, who applies it. That refusal is the design, not a gap — a wrong addressee produces a wrong pronoun on a line that looks fine, so it is wrong silently and everywhere. There is deliberately no "who spoke nearby" tier.

Run the report before batch 1. Its most useful column is the pairs that resolve but have **no declared register yet** — that is the to-do list for the profile. It also lists speaker codes with no character record, which otherwise silently get the generic voice.

## §3 Execution modes [PORTABLE]

Ask the user which one they want before translating. Never assume.

**A. In-session — recommended.** The assistant translates directly in conversation, batch by batch, following the game's style guide, writing results into the progress JSON. Best register quality; pays the context cost once per session rather than once per batch. No API key. Protocol in `references/translating.md` (Path A).

**B. Bulk API first-pass.** `python translate_api.py --profile profile.json` machine-translates everything — resumable, token-validated, TM-backed. A bulk pass is a **draft**: always follow with a review driven by the QA report.

| `api.provider` | Backend |
|---|---|
| `deepseek` | DeepSeek's official API, pre-configured (`DEEPSEEK_API_KEY`, `deepseek-v4-flash`). **Thinking mode off by default** — reasoning tokens count against `max_tokens` and thinking mode rejects `temperature`. Opt in with `"thinking": true` for a quality pass. |
| `openai-compatible` | Any other OpenAI Chat Completions endpoint via `api.base_url`: OpenAI, OpenRouter, Ollama (local, no key), Azure. **stdlib HTTP, no SDK.** Verified live against Ollama; see `references/translating.md` for the per-backend caveats. |
| `gemini` | Google Gemini API |
| `anthropic` | Anthropic API |
| `claude-cli` | Headless `claude -p` on an existing Claude Code subscription — no API key |

**C. Headless agent CLI.** Mode B with `claude-cli`. Works without a key, but each spawned agent re-pays its own context overhead, so it completes fewer strings per unit of quota than in-session.

## §4 The in-session protocol [PORTABLE]

The core loop, in full, is `references/translating.md` Path A. The short form:

```
1. Load translation-guide.md into context.
2. Take the next 40-60 untranslated strings from strings.json,
   contiguous by file+line so scene context is visible.
3. For each: who speaks, to whom (relationships.py answers this where it can;
   where it doesn't, read the surrounding lines), what kind of line.
4. Read-modify-write the progress JSON. Never truncate it.
5. python qa_check.py --profile profile.json --technical-only  -> zero cat-1.
6. Repeat. Report progress briefly; don't stop for approval each batch.
```

Hygiene that has each shipped a real bug: a single `\"` for nested quotes, never `\\\"` · never route target-script text through a Windows console · explicit UTF-8 on every read and write · never leave a line as its source text.

## §5 Safety invariants [PORTABLE]

What guarantees the pipeline actually makes, stated honestly — believing in a protection you don't have is worse than knowing you lack it.

**Implemented:**

1. **The progress store is the source of truth.** `translations.json` maps source → translation. Everything downstream is regenerated from it.
2. **Resumable by construction.** Every run skips what is already done; interrupt and rerun freely.
3. **Token parity is enforced.** Every `[variable]`, `{tag}`, `\escape`, and `%%` must survive translation identically. Violations are refused at the bulk gate and reported as category 1 by QA.
4. **Validate before persisting.** Output that echoes its source, comes back empty, or misses the target script reaches **neither** the progress store **nor** the Translation Memory. Caching a bad translation would approve it permanently. Cached entries are re-validated on lookup too, so a memory poisoned by an older run self-heals.
5. **Atomic writes.** The progress store, the TM, extracted strings, generated patch files, and QA reports are all written via temp-file + replace. An interrupted run cannot leave a truncated file.
6. **The game install is never modified.** The patch is the only artifact that crosses over, and deleting one folder uninstalls it.

**Not yet implemented — plan around these (roadmap v1.8):**

- **No pristine backup and no `restore` command.** Manual workaround: copy `translations.json` before any bulk run.
- **No round-trip verification before write.** The patch generator's escaping is not re-parsed and compared before the file lands.
- **No failures store.** A batch that fails twice is reported to the console and then forgotten; nothing durable records *why* a string is still untranslated.

## §6 The engine seam [PORTABLE]

Two file contracts separate the engine adapter from everything else — what any extractor must emit into `strings.json`, and what any patcher must consume from `translations.json`. Full spec, plus the pre-flight checklist to run on a new engine before translating at scale: **`references/engine-seam.md`**.

## §7 QA discipline [PORTABLE]

Full detail in `references/qa.md`. The parts that generalize:

- **Four categories.** 1: technical (missing, untranslated, token damage) — must be zero before a build. 2–3: register violations by speaker and by relationship. 4: phrasing flags for human review.
- **A relationship rule only fires on a resolved pairing.** Category-3 rules restricted by addressee (`to`/`to_group`, or generated from `to[other].forbidden`) skip every line whose addressee is unknown. A gate that guessed the pairing would flag correct text, and people stop reading a report that cries wolf.
- **Scanners report, they never mutate.** A tool that silently rewrites translations destroys the audit trail. AI proposes; a human commits.
- **Tune scanners toward noise, never toward silence.** In an unspaced script, suppressing a false positive can erase a real violation. A false positive costs a glance; a false negative ships.
- **The backward-audit rule.** Every newly-discovered convention triggers an audit of everything already translated: discover → write it into the guide *in the same turn* → scan → fix → re-verify. Budget for 5–15 of these over a full game.
- **QC sampling** (manual today): periodically produce a random sample of 40–60 rows — random, not contiguous, because contiguous samples hide problems that cluster by speaker. Write it as CSV with a UTF-8 BOM (`utf-8-sig`) so it opens correctly in Excel, include a side-by-side column against any pre-existing translation, and **deliver it as a file, never pasted inline into chat**.
- **Screenshots are a separate QC channel** from text review and catch a different class of problem: clipping, wrapping, overlap, blank labels.

## §8 Traps index [PORTABLE]

| Trap | Where |
|---|---|
| Deleting progress keys doesn't force re-translation — the TM restores them | `references/translating.md` |
| JSON escaping: single `\"`, never `\\\"` | `references/translating.md` |
| Target-script text through a Windows console = mojibake or a crash | `references/translating.md` |
| Suppressing scanner false positives can hide real violations | `references/qa.md` |
| One rendering per source line (runtime filter) | `SKILL.md`, `references/native-translate-blocks.md` |
| Text built dynamically in Python is invisible to the extractor | `references/custom-subsystems.md` |
| Line references drift when the game is re-decompiled | `references/decompiling.md` |
| A pre-v1.5 `strings.json` has no scene labels, so addressee resolution loses a tier until you re-extract | `references/extraction.md` |
| Untranslated output used to pass silently — now a hard failure | `references/qa.md` |
| Reasoning models can burn the whole `max_tokens` budget on thinking and return an empty answer | `references/translating.md` |
