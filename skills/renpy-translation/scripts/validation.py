"""Shared validation helpers and the atomic file writer.

Engine-neutral and harness-neutral: nothing here knows about Ren'Py, and
nothing here talks to a model. `translate_api.py` uses it to refuse bad
output *before* it reaches the progress store or the Translation Memory;
`qa_check.py` uses the same predicates so the bulk gate and the QA gate
agree on what counts as a translation.

The core rule (ADR-017): a translation identical to its source, or
containing none of the target script, is not a translation. Token parity
alone never caught this — an echoed English string has an identical token
signature.

This module holds stateless helpers only. Shared *stores* (the Translation
Memory) keep their single access boundary; see ADR-010.
"""

import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path


def configure_console():
    """Force UTF-8 on stdout AND stderr.

    Target-script text must never be routed through a legacy Windows console:
    cp1252/cp874 raises UnicodeEncodeError on the first non-Latin character.
    stderr matters as much as stdout — `sys.exit("message")` writes there, and
    an error message that itself crashes on encoding is the worst kind.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

# ---- canonical token regexes -------------------------------------------
# Single home for these; translate_api.py and qa_check.py both import them.
VAR_RE = re.compile(r"\[[^\]]+\]")          # Ren'Py interpolation: [mc_name]
TAG_RE = re.compile(r"\{[^}]+\}")           # text tags: {i}, {/b}, {w=0.5}
ESC_RE = re.compile(r'\\[n"\'\\]')          # escapes: \n \" \' \\
PCT_RE = re.compile(r"%%")                  # literal percent in a % format string

# Everything that carries no translatable content on its own.
_VAR_TAG_RE = re.compile(r"\[[^\]]+\]|\{[^}]+\}")

# Ren'Py text tags that take a matching {/close}. Everything else — {w}, {p},
# {nw}, {fast}, {clear}, {image=...}, {space=N}, {a=...} link targets and any
# unknown tag — is treated as standalone and ignored by the nesting check.
# Ren'Py TOLERATES an unclosed paired tag (it auto-closes at end of string);
# what it rejects at runtime is a {/close} that does not match the innermost
# open tag. A token-count check cannot see that: the multiset is unchanged.
PAIRED_TAGS = frozenset({
    "a", "alpha", "alt", "b", "color", "cps", "font", "i", "k",
    "noalt", "outlinecolor", "plain", "rb", "rt", "s", "size", "u",
})


def _tag_name(token):
    """('i', False) from '{i}', ('color', False) from '{color=#fff}',
    ('i', True) from '{/i}'. Returns ('', close) for '{}' / '{ }'."""
    inner = token[1:-1].strip()
    close = inner.startswith("/")
    if close:
        inner = inner[1:].strip()
    parts = inner.replace("=", " ").split()
    return (parts[0].lower() if parts else ""), close


def tag_nesting_ok(text):
    """False when a {/close} text tag does not match the innermost open tag.

    Regression-only signal: callers compare source against translation, so a
    faithfully copied broken source is never flagged. Unclosed paired tags are
    NOT a failure (Ren'Py auto-closes them); a mis-nested or unmatched close
    IS (Ren'Py raises), and it survives token parity because the tag multiset
    is identical — "{i}a{/i} {b}b{/b}" vs "{i}a {b}b{/i} {/b}".
    """
    stack = []
    for token in TAG_RE.findall(text.replace("{{", "").replace("}}", "")):
        name, close = _tag_name(token)
        if name not in PAIRED_TAGS:
            continue
        if close:
            if not stack or stack[-1] != name:
                return False
            stack.pop()
        else:
            stack.append(name)
    return True


# ---- script ranges ------------------------------------------------------
# Codepoint ranges that count as "the target script wrote something here".
# An empty range list means the check cannot discriminate (Latin targets),
# so it is skipped rather than always passing or always failing.
SCRIPT_RANGES = {
    "latin": [],
    "thai": [(0x0E00, 0x0E7F)],
    "lao": [(0x0E80, 0x0EFF)],
    "khmer": [(0x1780, 0x17FF)],
    "myanmar": [(0x1000, 0x109F)],
    "japanese": [(0x3040, 0x309F), (0x30A0, 0x30FF), (0x4E00, 0x9FFF)],
    "chinese": [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)],
    "korean": [(0xAC00, 0xD7AF), (0x1100, 0x11FF)],
    "cyrillic": [(0x0400, 0x04FF)],
    "greek": [(0x0370, 0x03FF)],
    "arabic": [(0x0600, 0x06FF)],
    "hebrew": [(0x0590, 0x05FF)],
    "devanagari": [(0x0900, 0x097F)],
    "georgian": [(0x10A0, 0x10FF)],
    "armenian": [(0x0530, 0x058F)],
}

# language_id (as used in profile.json) -> script name. Only ever used to
# *suggest* a target script; enforcement still requires an explicit opt-in.
LANGUAGE_SCRIPT_HINTS = {
    "thai": "thai", "lao": "lao", "khmer": "khmer", "burmese": "myanmar",
    "japanese": "japanese", "chinese": "chinese", "schinese": "chinese",
    "tchinese": "chinese", "korean": "korean",
    "russian": "cyrillic", "ukrainian": "cyrillic", "bulgarian": "cyrillic",
    "serbian": "cyrillic", "greek": "greek",
    "arabic": "arabic", "persian": "arabic", "urdu": "arabic",
    "hebrew": "hebrew", "hindi": "devanagari", "nepali": "devanagari",
    "marathi": "devanagari", "georgian": "georgian", "armenian": "armenian",
    "french": "latin", "spanish": "latin", "german": "latin",
    "italian": "latin", "portuguese": "latin", "polish": "latin",
    "turkish": "latin", "dutch": "latin", "vietnamese": "latin",
    "indonesian": "latin", "czech": "latin", "swedish": "latin",
}


def _cp(value):
    """Codepoint from a hex string ("0E00") or an int (0x0E00)."""
    return int(value, 16) if isinstance(value, str) else int(value)


def parse_ranges(spec):
    """Accept "0E00-0E7F", [lo, hi], ["0E00", "0E7F"], or a list of those."""
    if isinstance(spec, str):
        lo, _, hi = spec.partition("-")
        return [(_cp(lo), _cp(hi or lo))]
    if not spec:
        return []
    # A flat pair of scalars is one range, not two one-character ranges.
    if len(spec) == 2 and all(isinstance(v, int) for v in spec):
        return [(_cp(spec[0]), _cp(spec[1]))]
    if len(spec) == 2 and all(isinstance(v, str) and "-" not in v for v in spec):
        return [(_cp(spec[0]), _cp(spec[1]))]
    ranges = []
    for item in spec:
        ranges.extend(parse_ranges(item))
    return ranges


def resolve_target_script(profile):
    """-> (ranges | None, origin) where origin is explicit / inferred / none.

    Only an *explicit* `validation.target_script` enables enforcement.
    Inference from `language_id` is reported to the operator as a hint, so
    upgrading the tooling can never turn on a new hard failure by itself.
    """
    spec = (profile.get("validation") or {}).get("target_script")
    if spec:
        if isinstance(spec, dict):
            return parse_ranges(spec.get("ranges", [])), "explicit"
        name = str(spec).lower()
        if name in SCRIPT_RANGES:
            return list(SCRIPT_RANGES[name]), "explicit"
        return parse_ranges(spec), "explicit"

    hint = LANGUAGE_SCRIPT_HINTS.get(str(profile.get("language_id", "")).lower())
    if hint:
        return list(SCRIPT_RANGES[hint]), "inferred"
    return None, "none"


def validation_policy(profile):
    """The single source of validation policy, shared by both scripts."""
    cfg = profile.get("validation") or {}
    ranges, origin = resolve_target_script(profile)
    return {
        "echo_check": cfg.get("echo_check", True),
        # Enforced only when the operator named the script explicitly.
        "script_check": bool(cfg.get("script_check", True))
                        and origin == "explicit" and bool(ranges),
        "script_ranges": ranges or [],
        "script_origin": origin,
        "min_script_chars": cfg.get("min_script_chars", 1),
        "allow_identical": set(cfg.get("allow_identical", [])),
        "keep_untranslated": [k for k in profile.get("keep_untranslated", []) if k],
    }


def policy_banner(policy):
    """One line telling the operator what is actually being enforced."""
    echo = "on" if policy["echo_check"] else "off"
    if policy["script_check"]:
        return f"Validation: echo={echo}, script=on ({len(policy['script_ranges'])} range(s))"
    if policy["script_origin"] != "none" and not policy["script_ranges"]:
        # A Latin-script target shares its codepoints with the source, so the
        # check cannot discriminate. Saying "enable it" would be false advice.
        return f"Validation: echo={echo}, script=n/a (Latin-script target)"
    if policy["script_origin"] == "inferred":
        return (f"Validation: echo={echo}, script=off "
                f"(inferred from language_id — set validation.target_script to enable)")
    return f"Validation: echo={echo}, script=off (no validation.target_script)"


# ---- predicates ---------------------------------------------------------

def translatable_residue(text, keep_untranslated=()):
    """What is left to translate after stripping tokens and kept terms.

    Kept proper nouns are removed *before* the decision, not merely compared
    against the whole string: "Maya!" and "Sage and Maya" are legitimately
    identical in the translation when both names are in keep_untranslated.
    (Mirrors the keep_lower exemption qa_check.py applies to roman_check.)

    Twin of has_translatable_content() in extract_strings.py — deliberately
    duplicated rather than imported, to keep the engine adapter a leaf.
    """
    stripped = _VAR_TAG_RE.sub("", text)
    stripped = ESC_RE.sub("", stripped)
    stripped = PCT_RE.sub("", stripped)
    for term in sorted(keep_untranslated, key=len, reverse=True):
        stripped = re.sub(re.escape(term), "", stripped, flags=re.IGNORECASE)
    return stripped.strip() if any(c.isalnum() for c in stripped) else ""


def is_echo(source, translation):
    """True when the translation is the source back again.

    Insensitive to whitespace and case so "hello  there" / "Hello there"
    is still recognised as an echo; sensitive to everything else.
    """
    norm = lambda s: " ".join(s.split()).casefold()
    return norm(source) == norm(translation)


def has_target_script(text, ranges, minimum=1):
    if not ranges:
        return True
    hits = 0
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in ranges):
            hits += 1
            if hits >= minimum:
                return True
    return False


def validate_translation(source, translation, policy):
    """-> (ok, code) with code in EMPTY / TAGNEST / ECHO / SCRIPT / None.

    Gate order: empty -> nesting -> residue -> allow_identical -> echo -> script.
    The residue gate is what lets "Maya", "...", and "[points]" through; the
    nesting gate runs BEFORE it because a mis-nested tag crashes rendering
    whether or not there was anything to translate ("{i}Maya{/i}" with Maya
    kept has empty residue but still must not lose its tag structure).
    """
    if translation is None or not translation.strip():
        return False, "EMPTY"

    if tag_nesting_ok(source) and not tag_nesting_ok(translation):
        return False, "TAGNEST"

    if not translatable_residue(source, policy.get("keep_untranslated", ())):
        return True, None

    if source in policy.get("allow_identical", ()):
        return True, None

    if policy.get("echo_check", True) and is_echo(source, translation):
        return False, "ECHO"

    if policy.get("script_check") and not has_target_script(
            translation, policy.get("script_ranges", []),
            policy.get("min_script_chars", 1)):
        return False, "SCRIPT"

    return True, None


REASONS = {
    "EMPTY": "returned an empty translation",
    "TAGNEST": "produced a mismatched Ren'Py close tag",
    "ECHO": "returned the source text untranslated",
    "SCRIPT": "did not write in the target script",
}


def multiset_diff(source_tokens, translation_tokens):
    """-> (missing, extra) as sorted lists, counting duplicates.

    Set difference would pass a translation that adds or duplicates a tag.
    """
    src, tr = Counter(source_tokens), Counter(translation_tokens)
    missing = sorted((src - tr).elements())
    extra = sorted((tr - src).elements())
    return missing, extra


# ---- atomic write -------------------------------------------------------

def write_text_atomic(path, text, encoding="utf-8"):
    """Write via a temp file in the same directory + os.replace.

    An interrupted run can never leave a half-written or empty file. This is
    the pattern ADR-010 already established for the Translation Memory; the
    progress store is the declared source of truth and needs it more.

    `newline=""` writes LF verbatim on every platform, instead of letting
    Python translate to CRLF on Windows. This is deliberate: a patch built on
    Windows and one built on Linux are then byte-identical, which matters
    because these files ship to players and get diffed between releases. LF
    also matches the `.rpy` convention everywhere else in this project.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
