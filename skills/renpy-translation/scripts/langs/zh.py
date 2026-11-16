"""Chinese writing conventions (Simplified and Traditional).

This is the only language module so far. It follows the contract described in
`langs/__init__.py`; `orthography.py` dispatches to it and owns the CLI.

What is checked for a Chinese target:

  variant     Simplified text carrying Traditional characters, or the reverse
  halfwidth   , . ? ! : ; next to a Chinese character (should be ，。？！：；)
  ellipsis    "...", "。。。" or a lone "…" (should be ……)
  space       a space between two Chinese characters

The variant comes from the language id (`schinese`, `tchinese`, `zh_cn` ...) or
from the profile, which also carries the opt-outs:

  "orthography": {"variant": "simplified", "allow_chars": "瞭"}
  "orthography": false        # no prompt rule, no checks

Variant detection uses the standard library's own GB2312 and Big5 tables, so
there is no character list to maintain: a character GB2312 has and Big5 lacks
is Simplified-only; a common (level 1) Big5 character GB2312 lacks is
Traditional-only. It is deliberately conservative. A Simplified form that
also exists in Big5 as some other character (后 里 只 干 面) is not flagged,
and a rare character legitimate in both can be: list it in `allow_chars`.
"""
import re

from validation import MASK_SRC, mask_tokens, unmask_tokens

NAME = "Chinese"
PREFIX = "zh"                  # QA labels read "zh halfwidth", "zh variant:們"
LABELS = ("variant", "halfwidth", "ellipsis", "space")
NOTES = {"variant": "  (reported only; translate_api.py --repair-variant fixes it)"}

SIMPLIFIED_IDS = {"schinese", "chinese_simplified", "simplified_chinese",
                  "zh_cn", "zh_sg", "zh_hans", "zhcn", "chs"}
TRADITIONAL_IDS = {"tchinese", "chinese_traditional", "traditional_chinese",
                   "zh_tw", "zh_hk", "zh_hant", "zhtw", "cht"}
CHINESE_IDS = SIMPLIFIED_IDS | TRADITIONAL_IDS | {"chinese", "zh", "mandarin"}

# QA's "short?" flag compares character counts. A faithful Chinese line is
# routinely a quarter of its English source ("I really can not believe it!" ->
# 我真不敢相信！), which the default 0.28 reports as truncated on most lines.
CHINESE_TRUNCATION_RATIO = 0.10

HAN = "㐀-䶿一-鿿"
_FULL = "，。？！：；、…—"
_TO_FULL = {",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；"}


def _lang_key(profile):
    return str(profile.get("language_id", "")).lower().replace("-", "_")


def config(profile):
    """-> conventions config, or None when the target has none built in (or the
    profile opts out with `"orthography": false`).

    `explicit` is True only when the profile itself names the variant. A
    variant read off the language id still drives the prompt and the review
    list, but must not turn an existing project's QA red on upgrade.
    """
    block = profile.get("orthography")
    if block is False:
        return None
    block = block if isinstance(block, dict) else {}
    lang = _lang_key(profile)
    declared = str(block.get("variant", "")).lower()
    if lang not in CHINESE_IDS and declared not in ("simplified", "traditional"):
        return None
    from_id = ("simplified" if lang in SIMPLIFIED_IDS
               else "traditional" if lang in TRADITIONAL_IDS else None)
    if declared in ("simplified", "traditional"):
        variant, explicit = declared, True
    else:
        variant, explicit = from_id, False
    return {"language": "chinese", "variant": variant, "explicit": explicit,
            # the language id says one script and the profile another
            "conflict": (from_id, declared) if from_id and declared in ("simplified", "traditional")
                        and from_id != declared else None,
            "allow_chars": set(block.get("allow_chars", "")),
            "truncation_ratio": CHINESE_TRUNCATION_RATIO}


CHOOSE = (
    "This is a Chinese target but the project does not say WHICH script. Ask the user "
    "before anything is translated:\n"
    "  Simplified  (Mainland China, Singapore)  -> language id schinese\n"
    "  Traditional (Taiwan, Hong Kong)          -> language id tchinese\n"
    "Then record it - scaffold with `init_project.py --language schinese|tchinese` or set "
    '"orthography": {"variant": "simplified"|"traditional"} in profile.json - and keep it: '
    "changing it later means re-translating the project.")


def problem(profile, need_variant=True):
    """-> a message when a Chinese target has no single, consistent script, else
    None (also None for every other language and for `"orthography": false`).

    The choice is made once, by the user, before the first line is translated,
    and then locked: an unknown script (`need_variant`) or a language id that
    contradicts the declared one stops the tools that would write text.
    """
    cfg = config(profile)
    if cfg is None:
        return None
    if cfg["conflict"]:
        had, declared = cfg["conflict"]
        return (f"language_id '{profile.get('language_id')}' is {had} Chinese but "
                f'"orthography": {{"variant": "{declared}"}} says {declared}. A project '
                "has one script. Ask the user which is meant, then make the two agree "
                "(changing a project that already has translations means re-translating it).")
    if need_variant and not cfg["variant"]:
        return CHOOSE
    return None


# ---- Simplified / Traditional -------------------------------------------

def _encodes(ch, codec):
    try:
        return ch.encode(codec)
    except UnicodeEncodeError:
        return None


_variant_sets = {}


def _only(variant):
    """Characters that belong to `variant` alone (built once, from codecs)."""
    if not _variant_sets:
        simp, trad = set(), set()
        for cp in range(0x4E00, 0xA000):
            ch = chr(cp)
            gb, b5 = _encodes(ch, "gb2312"), _encodes(ch, "big5")
            if gb and not b5:
                simp.add(ch)
            elif b5 and not gb and 0xA4 <= b5[0] <= 0xC6:   # Big5 level 1: common use
                trad.add(ch)
        _variant_sets.update(simplified=simp, traditional=trad)
    return _variant_sets[variant]


def wrong_variant(text, cfg):
    """-> the characters of `text` that belong to the OTHER variant, in order,
    each once. Empty when the variant is unknown."""
    if not cfg.get("variant"):
        return ""
    other = _only("traditional" if cfg["variant"] == "simplified" else "simplified")
    seen = []
    for ch in mask_tokens(text)[0]:
        if ch in other and ch not in cfg["allow_chars"] and ch not in seen:
            seen.append(ch)
    return "".join(seen)


# ---- mechanical conventions ---------------------------------------------
# Each step works on token-masked text, so a [variable], {tag} or escape can
# be neither changed nor split.

_ELLIPSIS_RE = re.compile(r"\.{3,}|。{2,}|…+")


def _fix_ellipsis(s):
    def six_dots(m):
        run = m.group(0)
        pairs = (len(run) + 1) // 2 if run[0] == "…" else 1
        return "……" * pairs
    return _ELLIPSIS_RE.sub(six_dots, s)


# Left context that makes a following ASCII mark Chinese punctuation: a Chinese
# character or a full-width mark, optionally through closing tokens ({/i}).
_AFTER_ZH = r"(?<=[" + HAN + _FULL + r"])((?:" + MASK_SRC + r")*)"
_HALF_AFTER_RE = re.compile(_AFTER_ZH + r"([,.?!:;])(?![0-9A-Za-z])[ \t]*")
_HALF_BEFORE_RE = re.compile(r"([,?!:;])[ \t]*(?=(?:" + MASK_SRC + r")*[" + HAN + r"])")


def _fix_halfwidth(s):
    prev = None
    while prev != s:        # "?!" turns one mark per pass: ？ then ！
        prev = s
        s = _HALF_AFTER_RE.sub(lambda m: m.group(1) + _TO_FULL[m.group(2)], s)
    return _HALF_BEFORE_RE.sub(lambda m: _TO_FULL[m.group(1)], s)


_SPACE_RE = re.compile(r"(?<=[" + HAN + _FULL + r"])[ \t]+(?=[" + HAN + _FULL + r"])")


def _fix_space(s):
    return _SPACE_RE.sub("", s)


_STEPS = (("ellipsis", _fix_ellipsis), ("halfwidth", _fix_halfwidth), ("space", _fix_space))


def issues(text, cfg):
    """-> labels for every convention `text` breaks, e.g.
    ["variant:們這", "halfwidth", "ellipsis"]. The mechanical ones are exactly
    what `normalize` would change, so the report and the fixer cannot disagree."""
    out = []
    wrong = wrong_variant(text, cfg)
    if wrong:
        out.append("variant:" + wrong[:6])
    masked = mask_tokens(text)[0]
    for name, fix in _STEPS:        # in order, each on the previous step's result
        fixed = fix(masked)
        if fixed != masked:
            out.append(name)
        masked = fixed
    return out


# ---- the prompt ----------------------------------------------------------

_VARIANT_RULE = {
    "simplified": (
        "Simplified Chinese, Mainland usage",
        "- Script: Simplified characters only. Never mix in Traditional forms (們 這 說 為 麼) "
        "and do not use 妳.\n",
        "“ ” (inner ‘ ’)"),
    "traditional": (
        "Traditional Chinese, Taiwan usage unless the style guide says otherwise",
        "- Script: Traditional characters only. Never mix in Simplified forms (们 这 说 为 么). "
        "Use the region's own vocabulary, not Mainland terms written in Traditional characters.\n",
        "「 」 (inner 『 』)"),
    None: (
        "Chinese",
        "- Script: the style guide names Simplified or Traditional. Use that one only and "
        "never mix the two.\n",
        "the marks the style guide names"),
}


def prompt_rule(profile):
    """The conventions block for the system prompt ('' when there is none).
    Static per profile, so provider prompt caching is unaffected."""
    cfg = config(profile)
    if cfg is None:
        return ""
    name, script, quotes = _VARIANT_RULE[cfg["variant"]]
    return (
        f"CHINESE WRITING CONVENTIONS ({name}):\n"
        f"{script}"
        "- Punctuation is full-width: ，。？！：；、 Never leave a half-width , . ? ! : ; next to "
        "a Chinese character.\n"
        "- An ellipsis is …… (two U+2026 characters). Translate \"...\" as ……, never 。。。 or a "
        "single …. A dash is ——.\n"
        "- Tokens stay ASCII, exactly as in the source: [name], {i}, \\n, \\\", %%. Never write "
        "［name］, 【name】, ｛i｝ or ％％. An escaped quote \\\" in the source is a token: keep it "
        f"as \\\". For quotation marks you add yourself use {quotes}.\n"
        "- No spaces between Chinese characters or around full-width punctuation. Digits and "
        "Latin letters stay half-width.\n"
        "- Foreign names: follow the glossary. If a name is transliterated, spell it the same "
        "way every time and join its parts with · (U+00B7).\n"
        "- A line wrapped in ( ) is an inner thought: keep the brackets around the whole line.\n"
        "- 他 / 她 / 它 follow the referent. 你 is the default; 您 only where a persona card or "
        "relationship asks for respect.\n"
        "- Write natural spoken Chinese, not word-for-word English: drop pronouns Chinese "
        "would drop, do not stack 的, do not use 被 for a neutral passive, and let "
        "sentence-final particles (啊 吧 呢 嘛 啦 呀) carry tone that English carries with "
        "stress or punctuation.\n")

# ---- the contract orthography.py and the QA report use -------------------

def claims(profile):
    """True if this module handles `profile`'s target language."""
    block = profile.get("orthography")
    declared = str(block.get("variant", "")).lower() if isinstance(block, dict) else ""
    return _lang_key(profile) in CHINESE_IDS or declared in ("simplified", "traditional")


def normalize(text, cfg=None):
    """`text` with the mechanical conventions applied; tokens untouched."""
    masked, toks = mask_tokens(text)
    for _, fix in _STEPS:
        masked = fix(masked)
    return unmask_tokens(masked, toks)


def severity(label, cfg):
    """QA category for a finding: a script leak is a hard category-2 issue only
    when the profile itself names the variant; everything else is for review."""
    return 2 if label.startswith("variant") and cfg["explicit"] else 4


def heading(cfg):
    return f"Chinese conventions (variant: {cfg['variant'] or 'not set'})"


def banner(cfg):
    """The line QA prints under its report header."""
    variant = cfg["variant"] or "not set - set orthography.variant to check it"
    return (f"Chinese conventions: variant={variant}"
            + (" (a leak is a hard issue)" if cfg["explicit"] else "")
            + "; orthography.py --write fixes the mechanical ones")


def hints(cfg):
    """Extra lines for the orthography.py report."""
    if cfg["variant"]:
        return []
    return ['  variant is not checked: set "orthography": {"variant": "simplified"} '
            'or "traditional" in the profile']


def locale_docs(language_id):
    """Locale files (under references/locales/) for a language id."""
    if language_id in SIMPLIFIED_IDS:
        return ("chinese.md", "chinese-simplified.md")
    if language_id in TRADITIONAL_IDS:
        return ("chinese.md", "chinese-traditional.md")
    return ("chinese.md",) if language_id in CHINESE_IDS else ()
