# The engine seam

Ren'Py is this workflow's primary purpose and its only shipped engine adapter. But only a small part of the pipeline actually knows what Ren'Py is: **two programs and two files**. Everything else — the profile system, the progress store, the Translation Memory, QA, token parity — is engine-neutral and works unchanged on any game whose text you can get in and out of.

This document states the contracts at that boundary, so supporting another engine is a known, bounded amount of work rather than a rewrite. It deliberately ships **no** Unity/Godot/Unreal code: an adapter nobody runs is an adapter that rots.

```
[ game files ]                                       [ game files ]
      │                                                    ▲
      ▼                                                    │
  EXTRACTOR  ──► strings.json ──► [ engine-neutral ] ──► PATCHER
  (engine-        Contract 1        profile · TM ·        Contract 2
   specific)                        translate · QA        (engine-specific)
                                          │
                                    translations.json
```

## Contract 1 — what an extractor must emit (`strings.json`)

A UTF-8 JSON array of objects. `extract_strings.py` is the Ren'Py implementation.

| Field | Requirement |
|---|---|
| `text` | The **exact** source string as the engine stores it. Escape sequences stay as the two literal characters (`\` then `n`), not as a real newline. No unescaping, no surrounding quotes, no normalization. This value is the primary key of the entire pipeline. |
| `speaker` | A stable speaker code, or one of the pseudo-speakers `narrator`, `_text`, `_menu`, `_screen`, `_ui`. Used for register selection and TM context variants. |
| `file`, `line` | Provenance. Must be **stable across re-extraction** — QA's context window (`qa_check.py`) and the TM's variant metadata both rely on them. Never use a value that shifts when unrelated text changes. |
| `kind` | One of `say`, `narrator`, `menu`, `text`, `screen`, `ui`. `screen`/`ui` mark strings a runtime say-filter cannot see, which is what routes them into a different part of the patch. |
| `label` | *Optional.* The name of the enclosing scene unit, or `null`. Emit it only if your engine states scene boundaries **outright**; a boundary you inferred is a boundary that will be wrong somewhere, and here that produces a wrong pronoun rather than a visible error. Omitting `label` and `label_cast` costs one resolution tier and nothing else. |
| `label_cast` | *Optional, required with `label` for the dyad tier.* Every speaker code that speaks anywhere in that label, on each of that label's dialog entries. Must be computed **before deduplication** — that is the entire point of the field. Dedupe drops an occurrence whose text appeared earlier, so a third character whose only line in a scene is "Yeah." vanishes from the corpus; a consumer counting surviving speakers would read a three-person scene as a two-person one and resolve confidently to the wrong addressee. Dedupe can only *remove* speakers, so the error runs in exactly one direction, and it is the dangerous one. Emit `label` without `label_cast` and the resolver reports `no-cast` rather than guessing. |

Rules:

- **A field this contract does not define must not be invented.** Consumers read `label` because it is specified here; extra keys are ignored, and a consumer that started depending on one would silently break every other adapter.
- **Dedupe by exact text, first occurrence wins** (unless the caller asks for per-occurrence output, which the delivery mechanism must then support).
- **Never emit** identifiers, label/screen/image/audio names, pure-interpolation strings (`"[points]"`), or empty strings. Translating an identifier breaks the game silently — the worst failure class there is.
- If your engine has a *mixed column* (a field that is sometimes player-facing copy and sometimes an internal code), classify it in the extractor and record the result in `kind`. The translator must never have to guess. A workable heuristic: a value matching `^[a-z0-9_.]+$` — all lowercase, only dots and underscores, no spaces — is an engine code; real UI copy has a space, a capital, or punctuation.

**Exit condition before you trust an extractor:** you can extract everything, change one string, rebuild, and see the change in the running game. Do this *before* translating at scale, not after.

## Contract 2 — what a patcher must consume (`translations.json`)

A flat UTF-8 JSON object mapping each `text` from Contract 1, **byte-identically**, to its translation. `build_patch.py` is the Ren'Py implementation.

- A **missing key means untranslated**, and the delivery mechanism must **fail soft** — display the source text. It must never crash, and it must never render an empty string.
- Whatever in-band markup the engine parses (`{tags}`, `[variables]`, `<color=…>`, `{0}` placeholders, `\n`) must survive into the output untouched and in the engine's own convention.
- The patch should be removable. In Ren'Py that means everything lives in `game/tl/<language>/` and uninstalling is deleting one folder; the game's own files are never modified.

## What is engine-specific and what isn't

**`[RE-DERIVE]` — the Ren'Py adapter. Replace all of this for a new engine:**

- `scripts/extract_strings.py`, `scripts/build_patch.py`
- `references/decompiling.md`, `references/patching.md`, `references/native-translate-blocks.md`, `references/custom-subsystems.md`

**`[PORTABLE]` — unchanged for any engine:**

- The profile system (`profile.json` + `translation-guide.md` + `qa_rules.json`) and `references/game-profile.md`
- `scripts/translation_memory.py`, `scripts/validation.py`, `scripts/qa_check.py`, `scripts/characters.py`
- `scripts/relationships.py` — with one caveat: the **vocative** tier reads the English source and assumes English word order and punctuation. It switches itself off when `source_language` is not `en`; the declared and dyad tiers stay available.
- The progress store, token parity, the validation gate, the 4-category QA model
- `references/translating.md`, `references/qa.md`, and `PLAYBOOK.md`

Supporting another engine means writing exactly two programs that satisfy the contracts above, and changing nothing else.

## Before translating at scale on a new engine

Each of these changes your string budget or your text conventions, and each is far more expensive to discover at string 50,000 than at string 50:

1. **Does the renderer break lines in your target script at all?** Engines with no dictionary for unspaced scripts (Thai, Japanese, Chinese, Lao, Khmer) can treat a whole sentence as one unbreakable word. The fix is usually injecting zero-width spaces at tokenizer-determined boundaries at build time — and formatting spans must be protected from receiving one inside them.
2. **Do the font's declared metrics fit your script's glyphs?** Stacking vowels and tone marks routinely exceed Latin-derived ascent/descent, so wrapped lines collide. Measure; don't assume.
3. **What is the length budget on fixed-width UI slots?** Many target languages run 1.5–3× longer than English. Identify the tightest slots early and keep a list of keys that must stay short.
4. **Which strings are unreachable?** Text hardcoded on UI prefabs or in binaries exists in no string table. Find these early and *tell the user what will stay untranslated*, rather than hunting for them at 95% complete.
5. **Which fonts does the UI actually use at runtime?** Serialized font references can be overridden by a localization system at runtime. Cover every font in the chain.
