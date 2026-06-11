# For the Plot

[![CI](https://github.com/Waiyakorn1879/for-the-plot/actions/workflows/ci.yml/badge.svg)](https://github.com/Waiyakorn1879/for-the-plot/actions/workflows/ci.yml)

> **You came for the porn. We translated the plot.**

A [Claude Code](https://claude.com/claude-code) plugin for translating Ren'Py visual novels into any language. It packages a complete, battle-tested fan-translation workflow as a skill that Claude follows end to end:

```
decompile → extract strings → build a game profile → translate → QA → build patch → deploy
```

The pipeline was proven on a full Thai translation of *Being a DIK* Episode 1 (2,600+ strings, character-aware speech registers, runtime patch that coexists with mods like SanchoMod) and then generalized for any game and any target language.

## What you get

- **`renpy-translation` skill** — Claude knows the whole workflow: decompiling `.rpa`/`.rpyc`, extracting dialog, setting up per-character speech registers, translating with full Ren'Py tag safety, running QA, and building a drop-in `game/tl/<language>/` patch.
- **Pipeline scripts** (cross-platform Python 3.8+, tested in CI):
  - `extract_strings.py` — pulls dialog, menu choices, on-screen text, and (with `--screens`) GUI/`_()` strings out of `.rpy` files
  - `translate_api.py` — optional bulk first-pass; providers: headless **Claude Code CLI (no API key)**, Anthropic API, or Gemini API (resumable, token-validated)
  - `qa_check.py` — technical checks (tags/variables/missing) plus declarative, language-specific register rules
  - `build_patch.py` — generates a runtime-filter translation patch plus native `translate strings` blocks for GUI text (no game source modification)
- **Game profile system** — one `profile.json` + style guide per game/language pair captures speakers, registers, glossary, fonts, and QA rules.
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

## Quickstart

1. Make a working folder next to (not inside) your game install.
2. Open Claude Code there and say something like:

   > Help me translate this Ren'Py game into French. The game is at D:\Games\SomeGame-1.0-pc

3. Claude walks the pipeline: decompiles scripts, extracts strings, interviews you to build the game profile (characters, formality rules, what stays untranslated), translates, QAs, and builds a patch you drop into `game/tl/<language>/`.

Two translation paths are supported:

- **Claude in-session** (default, best quality) — Claude translates batch by batch following your game's style guide. No API key needed.
- **API bulk first-pass** — `translate_api.py` machine-translates everything fast (needs an API key), then Claude reviews and fixes per the QA rules.

## Legal note

This repo ships **tools and style guides only** — no game scripts, no extracted text, no translations of copyrighted dialog, no fonts. When you publish a fan translation patch, check the game developer's policy on fan translations and never redistribute the game's own content.

## License

MIT
