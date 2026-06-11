# Phase 1: Decompiling Ren'Py archives

Goal: turn the game's packed scripts into readable `.rpy` files in your work folder.

## Where the scripts live

- `game/*.rpa` — packed archives. Script archives are usually named `scripts.rpa`, `scripts_<something>.rpa`, or per-episode/patch variants. Image/music `.rpa` files are irrelevant.
- `game/**/*.rpyc` — compiled scripts. Some games ship loose `.rpyc` without archives.
- If loose `.rpy` files already exist, you may not need to decompile at all.

**Always copy archives/`.rpyc` files OUT of the game folder first and work on the copies.** Never decompile in place — leftover `.rpy` files inside `game/` get compiled and loaded by the engine and can corrupt behavior.

## Find the game's Ren'Py version

Check `<game>/renpy/` or the log/traceback files, or run the exe once and read `log.txt` (first lines state the version). Tool compatibility depends on it:

- Ren'Py 6/7 = Python 2 bytecode; Ren'Py 8 = Python 3 bytecode.
- unrpyc has version-specific releases/branches — use one that matches the game's major version.

## Step 1: unpack .rpa → .rpyc

```
pip install unrpa
python -m unrpa -mp extracted/ path\to\copy_of_scripts.rpa
```

## Step 2: decompile .rpyc → .rpy

Use [unrpyc](https://github.com/CensoredUsername/unrpyc) (download the release matching the game's Ren'Py version):

```
python unrpyc.py extracted\*.rpyc
```

Each `.rpyc` produces a sibling `.rpy`. Move the `.rpy` files for the content you're translating into your profile's `source_dir`.

## Pitfalls

- **Mismatched unrpyc version** → unpickle errors or garbage AST. Get the release for the game's Ren'Py generation.
- **Obfuscated/protected games** may need unrpyc's `--try-harder` flag.
- Decompiled output is reconstructed source, not the developer's original — line numbers and formatting differ between unrpyc versions. Keep one decompiled snapshot per project and don't re-decompile mid-project, or `strings.json` line references will drift.
- Some text lives outside script archives (GUI strings in `gui.rpa`, screens). The runtime-filter patch only covers text that flows through say/menu — see `patching.md` for handling custom UI subsystems.
