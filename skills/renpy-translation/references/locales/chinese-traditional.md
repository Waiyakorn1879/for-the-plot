# Chinese, Traditional (tchinese)

Read [chinese.md](chinese.md) first. This file is only what is specific to Traditional Chinese.

**Audience:** Taiwan, Hong Kong. **Language ids:** `tchinese`, `zh_tw`, `zh_hk`, `zh_hant`, `chinese_traditional`. The scaffold writes `"orthography": {"variant": "traditional"}`.

- **Quotation marks:** `「 」`, with `『 』` for a quote inside a quote. Titles of works: `《 》`.
- **Region first.** Decide Taiwan or Hong Kong in the style guide before translating. The prompt assumes Taiwan usage unless the style guide says otherwise. Vocabulary differs (see the table in chinese.md); do not write Mainland terms in Traditional characters.
- **Vocabulary check.** QA assumes Taiwan usage and lists Mainland words (`zh region:軟件`) for review. For a Hong Kong project use `zh_hk` or set `"orthography": {"region": "hk"}`; the check is then off. 酒店 is flagged too, though it can be right (a bar or club in Taiwan).
- **Hong Kong and spoken Cantonese.** Written dialogue in Hong Kong may use Cantonese characters (嘅 咗 唔) that Standard Written Chinese does not. That is a style decision for the whole project: state it in the guide, and give the characters who speak that way approved `examples`.
- **Characters:** the QA label `zh variant:...` lists Simplified-only characters found in the text (`们 这 说 为 么` and the like). The check is conservative, so a clean report does not prove there are none.
- **Fonts:** a build for your region, such as Source Han Sans TC (Taiwan) or HK (Hong Kong), or the matching Noto Sans CJK build. Do not commit the font file; link to its source.
