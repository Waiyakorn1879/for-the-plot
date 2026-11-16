# Chinese targets

Read this at the Profile phase when the target is Chinese. It covers what both scripts share: the choice of script, punctuation, what the tools check, and fonts. What differs per script is in [chinese-simplified.md](chinese-simplified.md) and [chinese-traditional.md](chinese-traditional.md); read the one you chose.

The code is `scripts/langs/zh.py`, reached through `scripts/orthography.py`.

## 1. Ask the user which script, then lock it

Simplified and Traditional are two scripts, and usually two vocabularies. **Ask the user before scaffolding; never choose for them.** A project that mixes the two is rewritten, not patched, so the choice is made once and then enforced:

- `init_project.py` refuses a generic `chinese` / `zh` language id (add `--variant simplified|traditional` if you need a custom id) and writes the choice to `profile.json`.
- `translate_api.py` stops, before any text is written, if the script is unknown or the language id and `orthography.variant` disagree. So does `qa_check.py` on a disagreement.
- Changing it later means re-translating: `--repair-variant` fixes stray characters, not a project written in the wrong script.

| Language id | Variant | Typical audience |
|---|---|---|
| `schinese` (also `zh_cn`, `zh_hans`, `chinese_simplified`) | Simplified | Mainland China, Singapore |
| `tchinese` (also `zh_tw`, `zh_hk`, `zh_hant`, `chinese_traditional`) | Traditional | Taiwan, Hong Kong |
| `chinese`, `zh` | not known: refused by the scaffold | scaffold with `--variant`, or set `"orthography": {"variant": "..."}` |

`init_project.py --language schinese` writes the variant into the profile, a `language_name` of "Simplified Chinese", and `validation.target_script: "chinese"`. The language id is also the folder name under `game/tl/`, so keep it a plain identifier (`zh_cn`, not `zh-CN`).

Traditional is not Simplified with the characters swapped. Taiwan and the Mainland use different words for everyday things, so a Traditional translation is written for its region. Say which region in the style guide.

| Concept | Mainland (Simplified) | Taiwan (Traditional) |
|---|---|---|
| software | 软件 | 軟體 |
| video | 视频 | 影片 |
| taxi | 出租车 | 計程車 |
| network | 网络 | 網路 |
| information | 信息 | 資訊 |
| program | 程序 | 程式 |
| default | 默认 | 預設 |
| mouse | 鼠标 | 滑鼠 |
| quality | 质量 | 品質 |

## 2. Conventions the prompt states and QA checks

One list, used in three places: the bulk translator's system prompt, `qa_check.py`, and the fixer `orthography.py`. In-session, follow the same list.

| Convention | Right | Wrong |
|---|---|---|
| Full-width punctuation next to Chinese text | `你好，我来了。` | `你好,我来了.` |
| Ellipsis is two U+2026 characters | `等等……` | `等等...`, `等等。。。`, `等等…` |
| No spaces between Chinese characters | `睡不着` | `睡 不 着` |
| One script only | `我们说过` | `我們说过` |
| Tokens stay ASCII | `[name]`, `{i}`, `\n`, `%%` | `［name］`, `【name】`, `｛i｝`, `％％` |
| Digits and Latin letters stay half-width | `3.5`, `OK` | `３．５` |

Quotation marks: an escaped `\"` in the source is a token and must stay `\"` (hard rule 1). For marks the translator adds, each script has its own (see the variant file): Simplified `“ ”`, Traditional `「 」`.

Inner thoughts: a source line wrapped in `( )` keeps its brackets. Either `(…)` or full-width `（…）` is recognised as a thought by QA and by `pair_audit.py`; pick one in the style guide.

Names: decide per name whether it stays in Latin letters (`keep_untranslated`) or is transliterated (a Terminology entry, so it is spelled one way everywhere). Join the parts of a transliterated foreign name with `·` (U+00B7).

## 3. Register

Chinese has no gendered particles, so no gender rule is built in. Voice is carried by:

- **你 / 您.** `您` only where a relationship calls for respect. Put it in `forbidden` for characters who would never use it, or in a relationship's `to[other].forbidden`.
- **Self-reference and address terms** (老子, 本小姐, 人家, 哥, 学长 / 學長 …). These are the Chinese equivalent of a pronoun matrix: declare them per character and per pair in `speakers`, exactly as [game-profile.md](../game-profile.md) describes.
- **Sentence-final particles** (啊 吧 呢 嘛 啦 呀). Give each major character two or three approved `examples`; that steers a model better than describing the voice.

## 4. What the tools do

`qa_check.py` adds, for a Chinese target:

| Label | Meaning | Category |
|---|---|---|
| `zh variant:們這` | characters of the other script | 2 when the profile names the variant, else 4 |
| `zh region:软体` | a word from the other region (Mainland word in Taiwan text or the reverse); `REGION_TERMS` in `langs/zh.py`, off for Hong Kong | 4 |
| `zh halfwidth` | `, . ? ! : ;` next to a Chinese character | 4 |
| `zh ellipsis` | `...`, `。。。` or a lone `…` | 4 |
| `zh scriptword:后里` | a Simplified form used where Traditional needs another (Traditional projects only) | 4 |
| `zh dash` | `--`, or a lone `—` / `–` / `―`, next to Chinese text (should be `——`) | 4 |
| `zh width` | full-width Latin letters or digits (should be half-width) | 4 |
| `zh space` | a space between two Chinese characters | 4 |

It also lowers the default "short?" threshold to 0.10. A faithful Chinese line is often a quarter the length of its English source, and the general default of 0.28 flags most of them. Set `truncation_ratio` in `qa_rules.json` to override.

```
python orthography.py --profile profile.json           # dry-run: counts
python orthography.py --profile profile.json --write   # fix halfwidth, ellipsis, space
```

The fixer masks tokens, holds every result to the validity gate, and backs the stores up first. Run it after a bulk pass and before the review.

**A variant leak is repaired by the model, never by a table.** Simplified to Traditional is one-to-many (`发` is `發` or `髮`), so a mechanical swap produces wrong characters that look right, and the standard library has no conversion data. Instead:

```
python translate_api.py --profile profile.json --repair-variant           # dry-run: shows each fix
python translate_api.py --profile profile.json --repair-variant --write   # backs up, then saves
```

Only the flagged lines (dictionary and speaker overrides) are sent, with the characters that are wrong named. An answer is saved only if it clears the gate a fresh translation does (tokens, echo, script, terms) **and** no longer leaks **and** is about the same length as the line it replaces, so a rewrite is refused. A refused line is retried once, then left exactly as it was and listed; the exit status is 1 while any remain. Review the dry-run before `--write`: it is a conversion, not a re-translation, but it is still model output. In-session, do the same by hand: take the `zh variant` lines from the QA report and fix them with `edit_lines.py`. A project with a different converter (OpenCC) can use it instead; nothing here depends on it.

How the variant check works, and its limits: it uses Python's own GB2312 and Big5 tables. A character GB2312 has and Big5 lacks is Simplified-only; a common Big5 character GB2312 lacks is Traditional-only. It is conservative on purpose. A Simplified form that is also a real Traditional character (后 里 只 干 面 气) cannot be told by table, so in a Traditional project the common wrong uses (然后, 这里, 一只猫, 干净, 吃面 and a few more; the list is `_SIMPLIFIED_USES` in `langs/zh.py`) are listed for review as `zh scriptword:...`. That label is never a hard failure and `--repair-variant` does not touch it, because 后, 只 and 面 are right in other words (母后, 只会, 方面). A line whose characters are identical in both scripts (我求之不得) cannot be judged, so a clean report does not prove the text is free of the other script. A rare character legitimate in both can be flagged: list it in `"orthography": {"allow_chars": "瞭"}`.

The exclamation policy (`punctuation.py`) handles full-width marks: `？！` becomes `？` and a dropped `！` becomes `。`.

To turn all of this off: `"orthography": false`.

## 5. Fonts and line breaking

- **The game's own font almost certainly has no Chinese glyphs.** Without a `font` block in the profile, every line renders as empty boxes. Set `font.regular` and list the game's font files in `font.replace_fonts` (see [patching.md](../patching.md)).
- **Use a font built for your variant.** Source Han Sans / Noto Sans CJK ship as separate builds per region under the SIL Open Font License (named in the variant file). A Simplified-only font shows boxes for Traditional characters, and the builds draw some shared characters differently.
- **File size.** A full CJK font is 8 to 20 MB. That is normal; do not subset it unless you regenerate the subset on every update.
- **Line breaking.** Chinese has no spaces, so the engine must be willing to break between characters. Ren'Py's default `language` style (`"unicode"`) follows the Unicode line-breaking algorithm, which does. Still check in the engine: a long line in the dialog box, a menu choice, and a line with `{w}` or `{i}` tags.
- **Length.** Chinese is shorter than English, so fixed-width UI slots rarely overflow, but a larger `font.size_scale` is often wanted for legibility. Decide it on real dialog ([verify-in-engine.md](../verify-in-engine.md)).

The Ren'Py points above were written without access to the Ren'Py documentation site; treat them as a checklist to confirm in the engine, not as a specification.

## 6. Style guide checklist

Put these in `translation-guide.md` before translating:

1. Variant and region (Simplified/Mainland, Traditional/Taiwan, Traditional/Hong Kong).
2. Which names stay Latin and which are transliterated, with the spelling of each.
3. Thought brackets: `( )` or `（ ）`.
4. Who uses `您`, and to whom.
5. Each major character's self-reference, address terms and favourite particles, with examples.
6. The profanity policy, with the equivalents to use.
7. Honorific suffixes and titles (先生, 小姐, 同学 / 同學, 老师 / 老師) per relationship.
