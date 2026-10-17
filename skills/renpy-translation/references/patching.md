# Phases 6–7: Building and deploying the runtime-filter patch

```
python build_patch.py --profile profile.json
```

Writes to `<output_dir>/tl/<language_id>/`:

- `00_<lang>_filter.rpy` — installs a `config.say_menu_text_filter` hook (exact-match dict lookup, active only when `preferences.language == "<lang>"`), a toggle key, optional auto-set-on-first-launch, and the optional font swap.
- `01_<lang>_dict.rpy` (more parts with `--split-size`) — the generated English→target dictionary. `init 0`, so it loads after the filter's `init -1` bootstrap.
- `02_<lang>_strings.rpy` — only when the strings file (profile `strings_file` or `--strings`) contains `screen`/`ui` kinds with translations: a `translate <lang> strings:` block of `old`/`new` pairs. This is Ren'Py's native string-translation mechanism — it's what reaches screen-language text and `_()` strings, which the say filter cannot. Those texts are excluded from the runtime dict.

## How the filter behaves (design decisions worth knowing)

- **Translate-then-chain:** the filter wraps any pre-existing `say_menu_text_filter` (mods like SanchoMod install one) and runs translation FIRST, then the mod's filter — dict keys must match the raw English the engine emits, not mod-styled text. Install is re-attempted via `start`/`after_load` callbacks because mods may install their filter later than us.
- **Exact-match lookup:** an untranslated or altered string silently falls back to the original language — the patch can never crash dialog.
- **Debug counters:** the toggle key's `renpy.notify` shows dict size, filter calls/hits, and whether our filter is still installed (`OVERRIDDEN` means a mod stomped it after init — investigate init order).
- The empty `translate <lang> python: pass` block is what registers the language with Ren'Py so `preferences.language` can be set to it.

## Runtime hooks from the profile (all optional)

The generated filter contains nothing game-specific on its own. These profile keys switch on the hooks a particular game needs; a profile without them builds exactly as before.

| Key | Effect |
|---|---|
| `nameplates_file` | JSON `{speaker name: translated name}`; translates say-box names and `Character.name` |
| `nameplate_patterns` | `[{"suffix": "'s Echo", "format": "... {base}"}]` — derived names; `{base}` is the name minus the suffix, looked up in the nameplates |
| `input_prompts_file` | JSON `{prompt: translation}` for `renpy.input` prompts |
| `input_sync` | `[{"prompt": "What is your name?", "vars": {"short": "name[:2]"}}]` — after the player types, recompute variables from `name` (games that precompute forms of the protagonist's name) |
| `store_defaults` | `{var: value}` seeded when undefined, so **scene replays** (gallery) don't `NameError` on variables only set during play. List only names the game never `default`s — a seeded name makes Ren'Py's own `default` skip it |
| `safe_store_files` | `["gallery"]` — a missing store variable read from a frame in a file with this substring returns `""` instead of raising |
| `font.text_size` | cap dialogue size (Thai often needs ~28) |

Find replay variables by testing the in-game gallery with the patch installed; an `Uncaught Exception … has no attribute 'x'` names the next one to add. **Never hand-edit the generated `00_<lang>_filter.rpy`** — the next build overwrites it; put the change in the profile.

## Fonts (non-Latin targets)

With a `font` section in the profile, the filter also: overrides the `font` (and scaled `size`) of the standard text styles when the language is active, and fills `config.font_replacement_map` so any style it missed still falls back to the target font. **The font files themselves must be copied into `game/`** (top level) alongside the patch. Adjust `size_scale` after seeing real dialog in-game.

## Deploy & verify

1. Copy `<output_dir>/tl/<lang>/` → `<game>/game/tl/<lang>/`, plus font files into `<game>/game/`.
2. Launch the game. Ren'Py compiles the patch on first launch — the appearance of `.rpyc` siblings next to your `.rpy` files proves zero syntax errors. A traceback screen instead means a malformed generated file (almost always a quoting issue in the dict; find the line in the traceback).
3. Switch language (Preferences picker if the game has one, else the toggle key / auto-set) and play a few scenes: dialog, a menu choice, inner monologue, and a scene with `[variables]` in text.
4. Uninstall = delete `<game>/game/tl/<lang>/`. Nothing else is touched.

## Custom text subsystems (phones, computers, social feeds)

Text built dynamically in Python (chat histories, feed posts) is reachable by neither the say filter nor `translate strings`. It needs the wrapper-sub-dict pattern — full recipe with a proven code template in `custom-subsystems.md`. Budget real time for this and confirm scope with the user before committing to it.
