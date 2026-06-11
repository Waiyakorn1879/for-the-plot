# For the Plot

> **You came for the porn. We translated the plot.**

A [Claude Code](https://claude.com/claude-code) plugin for translating Ren'Py visual novels into any language. It packages a complete, battle-tested fan-translation workflow as a skill that Claude follows end to end:

```
decompile → extract strings → build a game profile → translate → QA → build patch → deploy
```

The pipeline was proven on a full Thai translation of *Being a DIK* Episode 1 (2,600+ strings, character-aware speech registers, runtime patch that coexists with mods like SanchoMod) and then generalized for any game and any target language.

## What you get

- **`renpy-translation` skill** — Claude knows the whole workflow: decompiling `.rpa`/`.rpyc`, extracting dialog, setting up per-character speech registers, translating with full Ren'Py tag safety, running QA, and building a drop-in `game/tl/<language>/` patch.
- **Pipeline scripts** (cross-platform Python 3.8+):
  - `extract_strings.py` — pulls dialog, menu choices, and on-screen text out of `.rpy` files
  - `translate_api.py` — optional bulk first-pass via an LLM API (resumable, token-validated)
  - `qa_check.py` — technical checks (tags/variables/missing) plus declarative, language-specific register rules
  - `build_patch.py` — generates a runtime-filter translation patch (no game source modification)
- **Game profile system** — one `profile.json` + style guide per game/language pair captures speakers, registers, glossary, fonts, and QA rules.
- **A complete worked example** — the *Being a DIK* → Thai profile, including a 35-character speech-register guide and the lessons learned shipping it.

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
