# mini-schinese: a worked Chinese example

A small **synthetic** example, the Chinese counterpart to `badik-thai`. The game is the fixture in `tests/fixtures/`, written for this repository, so there is no real game text here and no translation dictionary. Copy the structure, not the content.

| File | Shows |
|---|---|
| `profile.json` | the script choice (`schinese` + `orthography.variant`), the target-script gate, character records with `你` / `您` rules, a font block |
| `translation-guide.md` | the style-guide checklist from `references/locales/chinese.md` filled in |
| `qa_rules.json` | register rules that fire on a Chinese translation |

To try it end to end without any game: copy these three files into a new folder, put `tests/fixtures/mini_game.rpy` and `scenes.rpy` in `decompiled/`, run `extract_strings.py`, write or generate a few translations, then `qa_check.py` and `orthography.py`. `tests/test_locales.py` does exactly this.

For a real game, start from `init_project.py --language schinese`; do not copy this profile.
