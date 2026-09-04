# For the Plot — agent guide

This repo is a **game translation workflow**: a set of Python tools plus the procedure for using them to translate a visual novel into another language, end to end. Ren'Py is the primary target and the only shipped engine adapter.

It ships as a Claude Code plugin, but nothing about the workflow requires Claude. The tools are plain Python 3.8+ with no required dependencies, and the procedure is written for any assistant.

## Start here

- **Any agentic tool** (Codex, Cursor, Gemini CLI, ChatGPT with file access, or a human): read **`skills/renpy-translation/PLAYBOOK.md`**. It is the complete, harness-neutral procedure.
- **Claude Code**: the plugin loads `skills/renpy-translation/SKILL.md` automatically. It defers to the same reference docs.

Per-phase detail lives in `skills/renpy-translation/references/`. Read a reference when you reach that phase, not before.

## The tools

All in `skills/renpy-translation/scripts/`, cross-platform, UTF-8, stdlib-only:

| Script | Purpose |
|---|---|
| `init_project.py` | **start here** — scaffold a project folder beside the game (`--game`, `--language`) |
| `extract_strings.py` | game sources → `strings.json` |
| `translate_api.py` | bulk translation → progress JSON (providers: `deepseek` / `openai-compatible` / `gemini` / `anthropic` / `claude-cli`) |
| `qa_check.py` | technical + register QA; exit 1 while hard issues remain |
| `build_patch.py` | progress JSON → drop-in patch files |
| `translation_memory.py` | translation cache: `stats` / `export` / `import` / `clean` |
| `relationships.py` | who each line is spoken to: resolution + coverage report |
| `characters.py` | character records → persona cards + QA register rules (library, not a CLI) |
| `validation.py` | shared output-validity gate and atomic writer (library, not a CLI) |

Every one takes `--profile profile.json`. Run them directly:

```
python skills/renpy-translation/scripts/qa_check.py --profile profile.json --technical-only
```

## Hard rules

1. **Token preservation is non-negotiable.** Every `[variable]`, `{tag}`, `\escape`, and `%%` in the source must appear in the translation, identical and in sensible order. A missing token crashes or corrupts rendering. Paired style tags (`{i}`, `{b}`, `{color}`…) must also keep their nesting — `{b}{i}x{/i}{/b}`, never `{b}{i}x{/b}{/i}` — a crossed close passes the count check but raises in Ren'Py (QA code `TAGNEST`).
2. **Never modify game source files.** The patch lives entirely in its own folder and uninstalls by deleting it.
3. **A translation identical to its source, or containing none of the target script, is not a translation.** It is never saved and never cached.
4. **Never commit or publish game text** — scripts, extracted strings, translation dictionaries, archives, or commercial fonts. This repo is tools and style guides only.

## Working on the repo itself

`pytest` from the repo root runs the suite — every script has a test file, and the manifests/phase-sync checks in `.github/workflows/ci.yml` are runnable by hand.

Two design notes worth knowing before changing anything:

- **`validation.py`, `characters.py` and `relationships.py` are the only shared imports.** Every other tool talks through files. The validity gate, the atomic writer, the character records, and addressee resolution live there because each must be *identical* everywhere — a check the bulk translator enforces and QA doesn't is worse than no check, a voice the prompt asks for but the gate doesn't check is worse than either alone, and a QA rule that judges a different pairing than the prompt named is worse still. Shared helpers may be imported; shared stores (the Translation Memory) may not.
- **Addressee resolution must be able to refuse.** `relationships.py` answers only from evidence it can name in a report, and returns *unresolved* with a reason otherwise. A wrong addressee yields a wrong pronoun on a well-formed line — invisible to every other check. Do not add a tier that fires when the others decline (ADR-020).
- **Nothing unvalidated is persisted.** An echoed source has an identical token signature, so token parity alone once let untranslated English into the progress store *and* into the cache, where it was served back for free forever. Rejection happens before both writes, and on cache reads too.
