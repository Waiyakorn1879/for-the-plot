"""Writing conventions of the target language: one source for the translation
prompt, the QA checks, and a mechanical fixer. Chinese is the only language
with conventions built in; each language is a module in `langs/`.

A convention the prompt asks for and QA does not check drifts by batch 50; one
QA checks and the prompt never stated produces a report nobody can act on. So
both read the same config, as characters.py does for a character's voice.

  python orthography.py --profile profile.json           # dry-run, prints counts
  python orthography.py --profile profile.json --write   # backs up, then fixes

--write applies only the mechanical fixes of the language module (Chinese:
punctuation width, ellipsis, spacing). A Simplified/Traditional leak is
REPORTED, never converted here: that mapping is one-to-many (发 is 發 or 髮)
and the standard library has no conversion data. `translate_api.py
--repair-variant` repairs those lines with the model, behind the same gates.
Tokens are masked while editing and every result is held to the validity gate.

The profile can opt out (`"orthography": false`) or tune a language
(Chinese: `"orthography": {"variant": "simplified", "allow_chars": "瞭"}`).
The rules of each language are documented in references/locales/.

This file is the stable entry point: other scripts import it, and it
dispatches to the module in `langs/` that claims the profile's language.
"""
import argparse
import json
from pathlib import Path

import langs
from langs import zh
from punctuation import _paths, _read
from validation import (backup_file, configure_console, validate_translation, validation_policy,
                        write_text_atomic)

CHOOSE = zh.CHOOSE      # kept for callers that import it from here


def config(profile):
    """-> the language module's config (plus `_module`), or None when the target
    has no conventions built in or the profile opts out."""
    module = langs.for_profile(profile)
    cfg = module.config(profile) if module else None
    if cfg is None:
        return None
    cfg["_module"] = module
    return cfg


def problem(profile, need_variant=True):
    """-> a message when the project is not settled enough to write text (for
    Chinese: no single, consistent script), else None. Always None for a
    language without conventions."""
    module = langs.for_profile(profile)
    return module.problem(profile, need_variant) if module else None


def prompt_rule(profile):
    """The conventions block for the system prompt ('' when there is none).
    Static per profile, so provider prompt caching is unaffected."""
    module = langs.for_profile(profile)
    return module.prompt_rule(profile) if module else ""


def issues(text, cfg):
    """-> labels for every convention `text` breaks. The mechanical ones are
    exactly what `normalize` would change, so the report and the fixer cannot
    disagree."""
    return cfg["_module"].issues(text, cfg)


def normalize(text, cfg=None):
    """`text` with the mechanical conventions applied; tokens untouched.
    Without a config it uses Chinese, the only language that has any."""
    return (cfg["_module"] if cfg else zh).normalize(text, cfg)


def wrong_variant(text, cfg):
    """-> characters of `text` from the other script variant, for languages that
    have one (Chinese); '' for the rest."""
    check = getattr(cfg["_module"], "wrong_variant", None)
    return check(text, cfg) if check else ""


def severity(label, cfg):
    """QA category (2 or 4) for one finding label."""
    return cfg["_module"].severity(label, cfg)


def prefix(cfg):
    """What QA puts before a label: 'zh' -> 'zh halfwidth'."""
    return cfg["_module"].PREFIX


def banner(cfg):
    """The line QA prints under its report header."""
    return cfg["_module"].banner(cfg)


def apply(stores, cfg, gate_policy):
    """Normalize every entry of `stores` in place.
    -> ({path: entries changed}, {label: entries}, entries skipped)."""
    changed, counts, skipped = {}, {}, 0
    for path, d, source_of in stores:
        for k, v in d.items():
            for label in issues(v, cfg):
                name = label.split(":")[0]
                counts[name] = counts.get(name, 0) + 1
            new = normalize(v, cfg)
            if new == v:
                continue
            if not validate_translation(source_of(k), new, gate_policy)[0]:
                skipped += 1
                continue
            changed[path] = changed.get(path, 0) + 1
            d[k] = new
    return changed, counts, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--write", action="store_true", help="apply (default: dry-run)")
    args = ap.parse_args()
    configure_console()

    pp = Path(args.profile)
    profile, base = json.loads(pp.read_text(encoding="utf-8")), pp.parent
    msg = problem(profile, need_variant=False)
    if msg:
        raise SystemExit(msg)
    cfg = config(profile)
    if cfg is None:
        raise SystemExit("no writing conventions are built in for this profile's language "
                         "(or the profile sets \"orthography\": false); nothing to do")
    module = cfg["_module"]
    sp_path, tr_path, _ = _paths(profile, base)
    stores = [(tr_path, _read(tr_path, {}), lambda k: k),
              (sp_path, _read(sp_path, {}), lambda k: k.split("::", 1)[-1])]
    changed, counts, skipped = apply(stores, cfg, validation_policy(profile, base))

    print(module.heading(cfg))
    for name in module.LABELS:
        print(f"  {name:<10}{counts.get(name, 0):6d} entr(ies){module.NOTES.get(name, '')}")
    for line in module.hints(cfg):
        print(line)
    print(f"{sum(changed.values())} entr(ies) to change")
    if skipped:
        print(f"{skipped} entr(ies) left alone: the result would fail the validity gate")
    if not args.write:
        print("dry-run: nothing written (use --write)")
        return
    for path, d, _ in stores:
        if path in changed:
            bak = backup_file(path)
            write_text_atomic(path, json.dumps(d, ensure_ascii=False, indent=2))
            print(f"wrote {path.name} (backup {bak.name})")


if __name__ == "__main__":
    main()
