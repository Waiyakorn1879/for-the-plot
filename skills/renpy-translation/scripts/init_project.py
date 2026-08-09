"""Scaffold a translation project folder.

Creates the working folder beside the game — never inside it — with the
profile, the style guide, the QA rules, and the always-loaded instruction
file that keeps the project's own rules in context on every session.

The instruction file is the point. A translation runs for hundreds of
batches across many sessions; rules that live only in chat history get lost,
and a convention discovered at string 1,400 gets re-broken by string 1,450
unless it is written somewhere that is loaded every time. The content is
written once to TRANSLATION.md, and each harness gets a small stub pointing
at it (CLAUDE.md, AGENTS.md, GEMINI.md) so no harness has to be the
privileged one and the content never has to be duplicated.

Usage:
  python init_project.py --game "D:/Games/SomeGame-1.0-pc" --language thai
  python init_project.py --game ... --language french --name "Some Game" --dir ./work
"""
import argparse
import json
import sys
from pathlib import Path

from validation import (
    LANGUAGE_SCRIPT_HINTS, SCRIPT_RANGES, configure_console, write_text_atomic,
)

configure_console()


TRANSLATION_MD = """# {name} — {language_name} translation

Translating **{name}** into {language_name}. The game lives at `{game}` and is
**read-only**: nothing in this project ever modifies it. The single deliverable
is `{output_dir}/tl/{language_id}/`, which is copied into the game's `game/tl/`
and uninstalls by deleting that one folder.

## How to resume in a new session

The pipeline scripts were at `{scripts}` when this project was scaffolded.
**Re-check that path if it stops working** — a plugin install directory moves
on update, and this file is meant to outlive many sessions. Set `SCRIPTS` to
wherever they are now:

```
SCRIPTS={scripts}          # bash
$SCRIPTS = "{scripts}"     # PowerShell

# where am I
python $SCRIPTS/qa_check.py --profile profile.json --technical-only

# untranslated strings = entries in strings.json whose text is not a key
# in translations.json. Work through them in batches of 40-60, contiguous
# by file+line so scene context stays visible.

# after each session
python $SCRIPTS/qa_check.py --profile profile.json --technical-only   # zero cat-1
# periodically
python $SCRIPTS/qa_check.py --profile profile.json --report qa_report.txt

# build the patch
python $SCRIPTS/build_patch.py --profile profile.json
```

Translation method: **decide once and record it here.** In-session (an
assistant translating batch by batch) is the default and gives the best
register quality. A bulk API pass is a draft that always needs review.

> Method in use: _(fill in)_

## File map

| Path | What it is |
|---|---|
| `TRANSLATION.md` | this file — the project's rules, loaded every session |
| `profile.json` | machine config: speakers/characters, glossary, validation, paths |
| `translation-guide.md` | the style guide: registers, formality, slang policy |
| `qa_rules.json` | declarative register checks beyond what characters declare |
| `decompiled/` | decompiled game scripts (never commit) |
| `strings.json` | extracted source strings (never commit) |
| `translations.json` | **the progress store — the source of truth** (never commit) |
| `.ftp/translation_memory.json` | translation cache (never commit) |
| `{output_dir}/tl/{language_id}/` | the generated patch |
| `QC/` | review samples |

## Established voices

Characters are declared in `profile.json` → `speakers`. Each record feeds
**both** the translation prompt (as a persona card) and `qa_check.py` (as
register rules), so the voice asked for is the voice checked.

State the highest-frequency decision here in one line, because it settles the
majority of register questions:

> Who calls the protagonist what: _(fill in)_

## Known style corrections

**Every rule discovered mid-project goes here, in the same turn it is learned,
with the reason.** A rule without its reasoning gets misapplied; a rule that
stays in chat history gets re-broken within ten batches.

Then run the backward audit: the rule you just learned was broken in
everything translated before you learned it. `qa_check.py` re-scans the whole
corpus on every run, so adding a matching rule to `qa_rules.json` finds the
back catalogue for free.

<!-- Append below. This section only grows. -->

## Hard rules

1. Every `[variable]`, `{{tag}}`, `\\escape`, and `%%` survives translation
   identically — same count, sensible order. A missing token crashes or
   corrupts rendering; a duplicated one is just as broken.
2. A translation identical to its source, or containing none of the target
   script, is not a translation. It is refused before it is saved or cached.
3. Never modify the game's own files.
4. Never translate code-like strings: label, image, audio, screen, or
   transform names.
5. Inner-monologue markers `(...)` keep their wrapper.
6. Don't sanitize. Crude stays crude, formal stays formal.
7. Never commit game text — scripts, extracted strings, the progress store,
   the memory, or fonts. `.gitignore` already excludes them.

## Re-translation trap

Deleting keys from `translations.json` does **not** force re-translation: the
Translation Memory resolves hits before batching and puts the old value back
with no model call. Run with `tm.enabled: false` in `profile.json` to force it.
"""

STUBS = {
    "CLAUDE.md": "# {name} — {language_name} translation\n\n"
                 "Project rules, file map, and the resume runbook live in "
                 "@TRANSLATION.md — read it before translating anything.\n",
    "AGENTS.md": "# {name} — {language_name} translation\n\n"
                 "Read `TRANSLATION.md` first: it has the project's rules, the "
                 "file map, and the exact commands to resume.\n\n"
                 "The pipeline scripts are plain Python 3.8+ with no required "
                 "dependencies and take `--profile profile.json`.\n",
    "GEMINI.md": "# {name} — {language_name} translation\n\n"
                 "Read `TRANSLATION.md` first: it has the project's rules, the "
                 "file map, and the exact commands to resume.\n",
}

GUIDE_MD = """# {name} → {language_name} style guide

Loaded into the translation prompt automatically (`profile.json` →
`style_guide_file`) and re-read whenever a register question comes up.

## Register system

_The highest-value section for languages with pronoun/formality systems.
For each major relationship, decide the speech level in BOTH directions:
protagonist↔friends, protagonist↔love interests (and how it shifts as routes
progress), protagonist↔authority figures, rivals→protagonist._

Per-character pronouns belong in `profile.json` → `speakers[code]` and its
`to` map, where the tooling can read them. Use this file for the reasoning
and for anything prose-shaped.

## Slang and profanity policy

_Translate intent, not words. List the game's recurring profanity and idioms
with target-language equivalents by context. State explicitly whether NSFW
register may be sanitized (usually: no)._

## Recurring phrases

_Greetings, catchphrases, UI-ish strings that must translate identically
every time. Add to this table as you meet them._

| English | {language_name} | Note |
|---|---|---|

## Style corrections

_Categories that go wrong in almost every project — fill in as they bite:_

- **No synonym stacking.** Two words for the same quality side by side reads
  as padding. Use an intensifier instead.
- **No transliterated loanwords for voice-critical slang.** Translate the
  word's social function, not its sound.
- **Idiom vs literal.** Keep a list of polysemous words that get
  literal-translated by mistake.
- **Domain terminology.** Police, legal, medical, and military vocabulary
  have established equivalents. Use them; verify with a native speaker.
- **Emphasis uses the game's own markup**, never whitespace or invented
  markers.
- **Address terms carry status, gender, and register at once.** Verify them;
  don't reason them out.
"""

QA_RULES_JSON = {
    "window": 12,
    "roman_check": True,
    "groups": {},
    "rules": [],
    "_comment": (
        "Character `forbidden` lists in profile.json become category-2 rules "
        "automatically — put them there, not here. Use this file for rules that "
        "depend on CONTEXT rather than on speaker identity (e.g. crude register "
        "while an authority figure is in the scene), via `near`. See "
        "references/qa.md. When tuning a rule to fire less, re-run it against "
        "lines you know violate it: in an unspaced script, suppressing a false "
        "positive routinely erases a real violation."
    ),
}

GITIGNORE = """# Game text — never commit or publish any of this.
decompiled/
strings.json
translations.json
.ftp/
output/
QC/
*.rpa
*.rpyc

# Fonts are usually licensed; link to the source instead.
*.ttf
*.otf
"""


def build_profile(name, language_id, language_name, output_dir):
    profile = {
        "game_name": name,
        "language_id": language_id,
        "language_name": language_name,
        "source_dir": "decompiled",
        "strings_file": "strings.json",
        "progress_file": "translations.json",
        "output_dir": output_dir,
        "style_guide_file": "translation-guide.md",
        "qa_rules_file": "qa_rules.json",
        "speakers": {},
        "keep_untranslated": [],
        "validation": {},
        "api": {"provider": "openai-compatible", "batch_size": 20, "temperature": 0.3},
    }
    script = LANGUAGE_SCRIPT_HINTS.get(language_id.lower())
    # Only pre-set an enforceable script. A Latin-script target shares
    # codepoints with the source, so the check cannot discriminate.
    if script and SCRIPT_RANGES.get(script):
        profile["validation"]["target_script"] = script
    return profile


def main():
    ap = argparse.ArgumentParser(
        description="Scaffold a Ren'Py translation project folder")
    ap.add_argument("--game", required=True,
                    help="path to the game install (read-only; used for the file map)")
    ap.add_argument("--language", required=True,
                    help="target language id, e.g. thai / french / japanese")
    ap.add_argument("--language-name", help="display name (default: capitalized id)")
    ap.add_argument("--name", help="game name (default: the game folder's name)")
    ap.add_argument("--dir", default=".", help="project folder to create (default: .)")
    ap.add_argument("--output-dir", default="output", help="patch build directory")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing profile.json")
    args = ap.parse_args()

    game = Path(args.game).expanduser()
    project = Path(args.dir).expanduser()

    if not game.exists():
        sys.exit(f"game path does not exist: {game}")

    # The game installation is read-only (ADR-014). Writing the project inside
    # it would put working files — and eventually a .gitignore — in someone
    # else's install, and make "delete the patch folder" no longer a clean
    # uninstall.
    try:
        resolved_project = project.resolve()
        resolved_game = game.resolve()
        if resolved_project == resolved_game or resolved_game in resolved_project.parents:
            sys.exit(f"refusing to create the project inside the game install:\n"
                     f"  game:    {resolved_game}\n"
                     f"  project: {resolved_project}\n"
                     f"Work in a folder BESIDE the game, never inside it.")
    except OSError:
        pass

    language_id = args.language.lower()
    language_name = args.language_name or language_id.capitalize()
    name = args.name or game.name

    project.mkdir(parents=True, exist_ok=True)
    profile_path = project / "profile.json"
    if profile_path.exists() and not args.force:
        sys.exit(f"{profile_path} already exists — refusing to overwrite "
                 f"(pass --force if you mean it)")

    fields = {
        "name": name, "language_id": language_id, "language_name": language_name,
        # Absolute: the file map is read from other sessions and other shells,
        # where a path relative to today's cwd means nothing.
        "game": game.resolve().as_posix(), "output_dir": args.output_dir,
        "scripts": Path(__file__).parent.as_posix(),
    }

    written = []

    def write(rel, text):
        write_text_atomic(project / rel, text)
        written.append(rel)

    write("profile.json", json.dumps(
        build_profile(name, language_id, language_name, args.output_dir),
        ensure_ascii=False, indent=2) + "\n")
    write("TRANSLATION.md", TRANSLATION_MD.format(**fields))
    write("translation-guide.md", GUIDE_MD.format(**fields))
    write("qa_rules.json", json.dumps(QA_RULES_JSON, ensure_ascii=False, indent=2) + "\n")
    write(".gitignore", GITIGNORE)

    for stub, template in STUBS.items():
        path = project / stub
        # Never clobber an existing harness file — it may hold unrelated rules.
        if path.exists():
            print(f"  kept existing {stub} (add a pointer to TRANSLATION.md yourself)")
            continue
        write(stub, template.format(**fields))

    for sub in ("decompiled", "QC"):
        (project / sub).mkdir(exist_ok=True)

    print(f"Scaffolded {name} → {language_name} in {project.resolve()}")
    for rel in written:
        print(f"  + {rel}")
    print("  + decompiled/  QC/")
    if not (profile_path.parent / "profile.json").exists():
        return
    script_hint = ""
    if "target_script" not in build_profile(name, language_id, language_name, "x")["validation"]:
        script_hint = ("\n  ! validation.target_script is unset — no enforceable script "
                       f"is known for '{language_id}'.\n"
                       "    Set it in profile.json if the target uses a non-Latin script.")
    print(f"""
Next:
  1. Decompile the game's .rpa/.rpyc into decompiled/   (references/decompiling.md)
  2. python {fields['scripts']}/extract_strings.py --profile profile.json --screens
  3. Fill in profile.json -> speakers and keep_untranslated, and
     translation-guide.md, by interviewing whoever knows the game
     (references/game-profile.md)
  4. Translate (references/translating.md){script_hint}""")


if __name__ == "__main__":
    main()
