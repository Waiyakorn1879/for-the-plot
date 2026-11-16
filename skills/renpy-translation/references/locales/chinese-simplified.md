# Chinese, Simplified (schinese)

Read [chinese.md](chinese.md) first. This file is only what is specific to Simplified Chinese.

**Audience:** Mainland China, Singapore. **Language ids:** `schinese`, `zh_cn`, `zh_sg`, `zh_hans`, `chinese_simplified`. The scaffold writes `"orthography": {"variant": "simplified"}`.

- **Quotation marks:** `“ ”`, with `‘ ’` for a quote inside a quote. Titles of works: `《 》`.
- **Vocabulary:** Mainland usage (see the table in chinese.md). Terms written in Simplified characters but borrowed from Taiwan usage read as foreign to a Mainland player.
- **Characters:** the QA label `zh variant:...` lists Traditional-only characters found in the text (`們 這 說 為 麼` and the like). It is conservative: text identical in both scripts cannot be judged. Do not use `妳`; the prompt says so.
- **Fonts:** a Simplified build, such as Source Han Sans SC or Noto Sans CJK SC. Do not commit the font file; link to its source.
- **Example:** `examples/mini-schinese/`, a small synthetic profile with character records and QA rules.
