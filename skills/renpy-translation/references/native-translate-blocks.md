# Alternative: native Ren'Py `translate` blocks

Ren'Py's official translation mechanism. The SDK generates per-line translation stubs:

```
renpy.sh <project> translate <language>     # from the matching Ren'Py SDK
```

producing `game/tl/<language>/*.rpy` files of the form:

```
# game/script.rpy:123
translate french scene1_greeting_a1b2c3d4:
    mc "Salut, Troy !"

translate french strings:
    old "Say hey"
    new "Aller le voir"
```

Dialog lines get content-hashed IDs; menu choices and misc strings go into `translate <lang> strings:` old/new blocks.

## Choosing between this and the runtime filter

Use **native blocks** when:

- The same English line must translate differently in different scenes (per-occurrence IDs give you that for dialog; note `strings:` old/new entries are still global)
- The game officially supports translations / ships loose `.rpy` source
- You want standard tooling compatibility (translation editors that understand the tl format)

Use the **runtime filter** (this skill's default) when:

- You can't get an SDK matching the game's exact Ren'Py version (IDs are generated from the AST — a mismatched SDK produces wrong/missing IDs)
- The game updates frequently — updates change line hashes and silently orphan native translations, while a dict keyed on English text survives anything that doesn't reword the line
- Mods are in play, or the game is shipped as `.rpa` only and you're working from decompiled sources (decompiled output may not byte-match what the SDK expects)

## Workflow differences if you go native

- Extract with `--no-dedupe` (occurrences matter) or skip the extractor entirely and translate the generated stub files in place.
- The progress-file/QA loop still works: treat each stub's English comment as the key. `qa_check.py` checks operate on text pairs regardless of delivery mechanism.
- Deployment is the same folder (`game/tl/<language>/`), and Ren'Py shows the language in Preferences automatically if the GUI has a language screen; otherwise you still need a small toggle/auto-set helper like the filter patch's.
- Fonts still need handling (`gui.rpy` overrides or a font-swap helper as in `patching.md`).
