"""Safe text edits on Thai translations (library, not a CLI).

Thai has no spaces, so `\b` and "not followed by a letter" lookarounds are
wrong for it: they block a valid pronoun stuck to the next word (`แกเอง`).
Two traps cost real re-runs:

  * `[ะ-์]` looks like "vowel signs and tone marks" but U+0E40-0E44
    (เ แ โ ใ ไ) sit inside that range. They are LEADING vowels that start the
    next word, so `(?![ก-ฮะ-์])` rejects `แกเอง`, `แกใส่`.
  * a pronoun is often the first letters of an unrelated word (`แก` in `แกง`,
    `กู` in `กูเกิล`, `นาย` in `นายแบบ`), or a suffix of one (`ป้าแก`).

So exclusions are explicit word lists, never a character class.
"""
import re

from validation import mask_tokens, unmask_tokens

THAI_CONSONANTS = "ก-ฮ"
# Following/trailing marks that bind a vowel or tone to the PREVIOUS letter.
# U+0E31, U+0E34-0E3A, U+0E47-0E4E -- NOT the leading vowels U+0E40-0E44.
THAI_COMBINING = "ัิ-ฺ็-๎"


def replace_word(text, old, new, not_before=(), not_after=()):
    """Replace `old` with `new` in the prose of `text`, leaving variables, tags
    and escapes untouched.

    not_before: prefixes that make `old` part of another word (`ป้า` + แก).
    not_after:  suffixes that do (`ง`, `น`, `เกิล` ... after กู / แก).
    Both are literal strings, matched exactly.
    """
    pat = "".join(f"(?<!{re.escape(p)})" for p in not_before) + re.escape(old)
    if not_after:
        pat += "(?!" + "|".join(re.escape(s) for s in not_after) + ")"
    masked, toks = mask_tokens(text)
    return unmask_tokens(re.sub(pat, new, masked), toks)
