# Phases 6–7: Building and deploying the runtime-filter patch

```
python build_patch.py --profile profile.json
```

Writes to `<output_dir>/tl/<language_id>/`:

- `00_<lang>_filter.rpy` — installs a `config.say_menu_text_filter` hook (exact-match dict lookup, active only when `preferences.language == "<lang>"`), a toggle key, optional auto-set-on-first-launch, and the optional font swap.
- `01_<lang>_dict.rpy` (`02_`, ... with `--split-size`) — the generated English→target dictionary. `init 0`, so it loads after the filter's `init -1` bootstrap.

## How the filter behaves (design decisions worth knowing)

- **Translate-then-chain:** the filter wraps any pre-existing `say_menu_text_filter` (mods like SanchoMod install one) and runs translation FIRST, then the mod's filter — dict keys must match the raw English the engine emits, not mod-styled text. Install is re-attempted via `start`/`after_load` callbacks because mods may install their filter later than us.
- **Exact-match lookup:** an untranslated or altered string silently falls back to the original language — the patch can never crash dialog.
- **Debug counters:** the toggle key's `renpy.notify` shows dict size, filter calls/hits, and whether our filter is still installed (`OVERRIDDEN` means a mod stomped it after init — investigate init order).
- The empty `translate <lang> python: pass` block is what registers the language with Ren'Py so `preferences.language` can be set to it.

## Fonts (non-Latin targets)

With a `font` section in the profile, the filter also: overrides the `font` (and scaled `size`) of the standard text styles when the language is active, and fills `config.font_replacement_map` so any style it missed still falls back to the target font. **The font files themselves must be copied into `game/`** (top level) alongside the patch. Adjust `size_scale` after seeing real dialog in-game.

## Deploy & verify

1. Copy `<output_dir>/tl/<lang>/` → `<game>/game/tl/<lang>/`, plus font files into `<game>/game/`.
2. Launch the game. Ren'Py compiles the patch on first launch — the appearance of `.rpyc` siblings next to your `.rpy` files proves zero syntax errors. A traceback screen instead means a malformed generated file (almost always a quoting issue in the dict; find the line in the traceback).
3. Switch language (Preferences picker if the game has one, else the toggle key / auto-set) and play a few scenes: dialog, a menu choice, inner monologue, and a scene with `[variables]` in text.
4. Uninstall = delete `<game>/game/tl/<lang>/`. Nothing else is touched.

## Custom text subsystems (phones, computers, social feeds)

Text rendered by custom `screen`s or Python code never passes through `say_menu_text_filter`. Per subsystem: find where the text is produced (search the decompiled sources for the screen/function), then wrap that producer — e.g. a `NN_<subsystem>_dict.rpy` with its own lookup dict and a thin wrapper around the original function, dropped into the same `tl/<lang>/` folder. Budget real time for this: in Being a DIK, the phone chat system needed its own dicts plus wrapper functions per season. Confirm scope with the user before committing to it.
