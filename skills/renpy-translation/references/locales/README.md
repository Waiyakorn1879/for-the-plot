# Locale files

One file per target language (or per script), holding everything that is specific to it: register and speech rules, writing conventions, fonts, and the decisions to ask the user before starting. The core documents stay language-neutral and point here.

| Target | Language ids | Read |
|---|---|---|
| Thai | `thai` | [thai.md](thai.md) |
| Chinese, Simplified | `schinese`, `zh_cn`, `zh_sg`, `zh_hans`, `chinese_simplified` | [chinese.md](chinese.md), then [chinese-simplified.md](chinese-simplified.md) |
| Chinese, Traditional | `tchinese`, `zh_tw`, `zh_hk`, `zh_hant`, `chinese_traditional` | [chinese.md](chinese.md), then [chinese-traditional.md](chinese-traditional.md) |

`init_project.py` prints the files to read for the language it scaffolds. Any other language has no locale file yet: the generic pipeline applies, and the first project in it is the one that writes the file.

## Some languages need a decision first

A locale file can name a choice that must be made by the user before anything is scaffolded. Ask; never pick for them. Today that is Chinese: Simplified or Traditional, then locked for the project.

## Adding a language

1. **Write the locale file here**, from what the first real project learns: the register system, speech rules, writing conventions, fonts. Add a row to the table above and to `STATIC_DOCS` in `scripts/langs/__init__.py`.
2. **If the language has conventions a tool can check**, add a module to `scripts/langs/` that follows the contract in that package's docstring (the Chinese module is `zh.py`), and add it to `MODULES`. The prompt rule and the QA checks must read the same config: a rule the prompt asks for and QA does not check drifts by batch 50.
3. **If speakers' own words inflect by gender**, add the language to `GENDER_GRAMMAR` in `scripts/characters.py`.
4. **Add tests**, and an entry in the changelog. Do not commit game text: a worked example uses a synthetic game (see `examples/mini-schinese/`), not a real one.

Build the second language's module from a real project, not in advance: an interface designed from one example is a guess.
