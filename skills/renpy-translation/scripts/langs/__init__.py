"""Per-language writing conventions.

`orthography.py` is the stable entry point (CLI and imports); it dispatches here.
A language module is one file in this package exposing:

  NAME, PREFIX, LABELS, NOTES        display name, QA label prefix, the checks
                                     in report order, notes for the CLI report
  claims(profile) -> bool            does this module handle the target language
  config(profile) -> dict | None     the shared config (None = opted out). Keys the
                                     callers read: `explicit` (the profile itself
                                     chose, so a finding may be a hard failure) and
                                     `truncation_ratio` (QA's "short?" threshold)
  problem(profile, need_variant)     message when the project is not settled enough
                                     to write text (Chinese: which script), else None
  prompt_rule(profile) -> str        block for the translation system prompt
  issues(text, cfg) -> [label]       every convention `text` breaks ("name[:detail]")
  normalize(text, cfg) -> str        the mechanical fix; must change exactly what
                                     `issues` reports as mechanical
  severity(label, cfg) -> 2 | 4      QA category for a finding
  heading(cfg), banner(cfg), hints(cfg)   report text
  locale_docs(language_id) -> tuple  files under references/locales/

To add a language: write the module, add it to MODULES, add its docs to
references/locales/, and add tests. A prompt rule QA does not check drifts by
batch 50, and a check the prompt never stated produces a report nobody can act
on, so `prompt_rule` and `issues` read the same config.

Languages with a locale file but no module (Thai today) are listed in
STATIC_DOCS: guidance without checks.
"""
from . import zh

MODULES = (zh,)

# language id -> locale files, for languages that have guidance but no module
STATIC_DOCS = {"thai": ("thai.md",)}


def _key(language_id):
    return str(language_id or "").lower().replace("-", "_")


def for_profile(profile):
    """-> the language module that handles `profile`, or None."""
    for module in MODULES:
        if module.claims(profile):
            return module
    return None


def locale_docs(language_id):
    """-> file names under references/locales/ to read for a language id."""
    key = _key(language_id)
    docs = list(STATIC_DOCS.get(key, ()))
    for module in MODULES:
        docs.extend(d for d in module.locale_docs(key) if d not in docs)
    return tuple(docs)
