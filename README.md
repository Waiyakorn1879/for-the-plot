# For the Plot

[![CI](https://github.com/Waiyakorn1879/for-the-plot/actions/workflows/ci.yml/badge.svg)](https://github.com/Waiyakorn1879/for-the-plot/actions/workflows/ci.yml)

> **You came for the porn. We translated the plot.**

A complete, battle-tested fan-translation workflow for Ren'Py visual novels, packaged as a [Claude Code](https://claude.com/claude-code) plugin — but written so **any** AI assistant can follow it end to end:

```
decompile → extract strings → build a game profile → translate → QA → build patch → deploy
```

The pipeline was proven on a full Thai translation of *Being a DIK* Episode 1 (2,600+ strings, character-aware speech registers, runtime patch that coexists with mods like SanchoMod) and then generalized for any game and any target language.

## What you get

- **`renpy-translation` skill** — the whole workflow: decompiling `.rpa`/`.rpyc`, extracting dialog, setting up per-character speech registers, translating with full Ren'Py tag safety, running QA, and building a drop-in `game/tl/<language>/` patch. Claude Code loads it automatically; every other tool reads the same procedure from [`PLAYBOOK.md`](skills/renpy-translation/PLAYBOOK.md).
- **Pipeline scripts** (cross-platform Python 3.8+, stdlib-only, tested in CI):
  - `init_project.py` — scaffolds the project folder beside the game: wired-up profile, style-guide skeleton, QA rules, a `.gitignore` that keeps game text out of version control, and `TRANSLATION.md` — the project's own always-loaded instruction file, with `CLAUDE.md`/`AGENTS.md`/`GEMINI.md` stubs pointing at it
  - `extract_strings.py` — pulls dialog, menu choices, on-screen text, and (with `--screens`) GUI/`_()` strings out of `.rpy` files, tagging each with the scene label it came from
  - `translate_api.py` — optional bulk first-pass. Providers: **`deepseek`** (preset for DeepSeek's official API — just set `DEEPSEEK_API_KEY`), **`openai-compatible`** (OpenAI, OpenRouter, Ollama, Azure — one factory, no SDK), Gemini, Anthropic, or headless **Claude Code CLI (no API key)**. Resumable and token-validated; consults the Translation Memory before every call so known lines never hit the model twice. Empty replies — the classic reasoning-model failure, where thinking tokens eat the whole `max_tokens` budget — are diagnosed with the real cause, retried once at a raised budget, and never saved as a translation
  - `validation.py` — the shared gate that refuses to save or cache a "translation" that's just the English back again, or that contains none of the target script
  - `translation_memory.py` — a **Contextual Translation Memory** (TM): a durable source→translation cache that makes repeats and game-update re-runs free. As of v1.3 it stores **speaker-aware variants**, so when the same English line ("You.") needs a different rendering per character, the right one is retrieved deterministically from cache instead of re-translated — zero extra API cost (`stats` / `export` / `import` / `clean`)
  - `relationships.py` — **addressee resolution**: which character each line is spoken *to*, answered only from evidence it can name — a scope you declared, a name addressed in vocative position in the English, or a scene label containing exactly two speakers — and reported as *unresolved, with the reason* for everything else. There is deliberately no "who spoke nearby" guess: a wrong addressee yields a wrong pronoun on a line that looks perfectly fine, which is wrong silently and everywhere. Its report is also the project's audit — resolution rate per tier, **which resolved pairs still have no declared register**, tier disagreements, and speaker codes with no character record
  - `qa_check.py` — technical checks (tags/variables/escapes/`%%`/missing/untranslated) plus declarative, language-specific register rules, including relationship rules that fire only on a resolved pairing
  - `build_patch.py` — generates a runtime-filter translation patch plus native `translate strings` blocks for GUI text (no game source modification)
- **Character records** — `profile.json` → `speakers` is a real character dictionary: register, forbidden/required vocabulary, approved examples, an inner-monologue override, and **per-relationship pronouns** (in register-rich languages the pronoun belongs to the *pair*, not the person — the same protagonist uses one form with a close friend and another with a professor). Each record becomes a persona card in the translation prompt **and** a QA register rule, from one source — so the voice you asked for is the voice that gets checked. Every field is optional.
- **Relationship records** — the other half of that: which pair applies to a given line. Resolved lines carry the addressee into the translation prompt, into the Translation Memory's variant key, and into category-3 QA rules generated from a relationship's own `forbidden` list. Unresolved lines behave exactly as before — the whole relationship table goes to the translator, who decides. `min_confidence` lets a project refuse a tier it doesn't trust, and a hand-authored `declared` scope always wins.
- **Game profile system** — one `profile.json` + style guide per game/language pair captures characters, registers, glossary, fonts, validation, and QA rules.
- **A complete worked example** — the *Being a DIK* → Thai profile, including a 35-character speech-register guide and the lessons learned shipping it.

## How it works

The default patch mechanism is a **runtime text filter**: a `config.say_menu_text_filter` hook that looks every dialog/menu line up in a generated English→target dictionary when your language is active, and silently falls back to the original text on a miss — so the patch can never crash dialog. The filter chains with any filter a mod (e.g. SanchoMod) already installed instead of replacing it. GUI text that the say filter can't see (screen widgets, `_()` strings) rides along in a native `translate <language> strings:` file. Text that games build dynamically in Python (phone chats, social feeds) needs a small wrapper layer — the skill documents a production-proven template for that.

Because the dictionary is keyed on the game's own English text, the patch typically survives game updates, needs no Ren'Py SDK, and uninstalls by deleting one folder.

## Worked example

`skills/renpy-translation/examples/badik-thai/` is the real profile used to ship a Thai translation of *Being a DIK* EP1 (2,638 strings, 99.9% coverage): a 35-character speech-register profile, a Thai pronoun matrix by relationship, declarative QA rules that catch register violations mechanically, and a lessons-learned writeup. Copy its structure — not its content — when starting your own game.

## Install

In Claude Code:

```
/plugin marketplace add Waiyakorn1879/for-the-plot
/plugin install for-the-plot@for-the-plot
```

**Using another tool?** Clone the repo and point your assistant at [`AGENTS.md`](AGENTS.md) (or [`skills/renpy-translation/PLAYBOOK.md`](skills/renpy-translation/PLAYBOOK.md) directly). The scripts are plain Python with no required dependencies and run from any shell.

## Quickstart

1. Scaffold a project next to (not inside) your game install:

   ```
   python skills/renpy-translation/scripts/init_project.py \
       --game "D:/Games/SomeGame-1.0-pc" --language french --dir SomeGame-French
   ```

2. Open your assistant in that folder and say something like:

   > Help me translate this Ren'Py game into French. The game is at D:\Games\SomeGame-1.0-pc

3. It walks the pipeline: decompiles scripts, extracts strings, interviews you to build the game profile (characters, formality rules, what stays untranslated), translates, QAs, and builds a patch you drop into `game/tl/<language>/`.

You're always asked which translation method you want before starting — pick one of three:

- **In-session** (recommended, best quality and highest throughput) — the assistant translates batch by batch following your game's style guide. No API key needed, and the style guide is loaded once per session instead of re-sent per batch.
- **API key** — `translate_api.py` machine-translates everything fast via DeepSeek, OpenAI, OpenRouter, a local Ollama, Azure, Gemini, or Anthropic, then the assistant reviews and fixes per the QA rules.
- **Agent** — `translate_api.py` with the headless Claude Code CLI provider; no API key, but each spawned agent re-pays its own context overhead, so it finishes fewer strings per unit of quota than in-session.

## Not just Ren'Py, not just Claude

Ren'Py is the primary target and the only shipped engine adapter — but only `extract_strings.py`, `build_patch.py`, and four reference docs actually know what Ren'Py is. The profile system, progress store, Translation Memory, QA engine, and token-parity rules are engine-neutral. [`references/engine-seam.md`](skills/renpy-translation/references/engine-seam.md) specifies the two file contracts at that boundary, so supporting another engine means writing two programs and changing nothing else.

## Legal note

This repo ships **tools and style guides only** — no game scripts, no extracted text, no translations of copyrighted dialog, no fonts. When you publish a fan translation patch, check the game developer's policy on fan translations and never redistribute the game's own content.

## License

MIT
