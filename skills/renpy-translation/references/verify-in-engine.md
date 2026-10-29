# Verify in the real engine

Script QA cannot see a line that is well-formed, validated, and wrong for the scene. Every serious late problem on the first Thai project was found by *looking at the running game*. Do this for a sample of every episode before release. Recipe verified on Ren'Py 8.3.2, Windows; other versions may differ.

## Safety first
- **Never run the game from the real install.** Make a test copy on the same drive: junctions or hard links of the game folder, then copy only your patch folder (`game/tl/<lang>/`) in.
- **Redirect `APPDATA`** to a folder inside the copy before the *first* launch (lint counts). Ren'Py rewrites `persistent` and saves there; an unredirected launch touches the player's real ones.
- Mute with `SDL_AUDIODRIVER=dummy`. `SDL_VIDEODRIVER=dummy` fails ("Invalid window"); a real GL window is needed.
- Close only the test process afterwards: filter by `ExecutablePath` containing the test-copy path, never "all python.exe".

## Install sanity check (do this before judging any output)
- List loose `game/*.rpy(c)` that shadow scripts inside archives (`.rpa`). Ren'Py scans the filesystem first and skips duplicates, so an older loose script silently overrides the newer archived one.
- Compare `config.version` with `build_info.json`.
- Run `lint` on the copy. Hundreds of undefined names usually mean a hybrid install: tell users to use a clean one.

## Drive a scene
Put `game/zz_test.rpy` in the copy:

```
label before_main_menu:
    $ renpy.change_language("<lang>")
    $ main_menu = False
    $ <variables the scene needs>
    jump <label>
testcase play:
    $ _test.timeout = 400.0        # without it: "Testcase stuck"
    pause 14.0
    $ renpy.screenshot("<abs path>/<run-prefix>_00.png")
    click pos (900, 500)           # advances one line; window pixel coordinates
    pause 1.2
    # repeat the screenshot/click/pause block once per line
```

Run: `lib/py3-windows-x86_64/python.exe <Game>.py . test play` from the copy.

- Did **not** work: `click "text"`, `click pattern "text"` (parse error), `run Start()` (ends the test), `advance`.
- A label deep in a long script cannot be entered mid-way. Build a short replica label in `zz_test.rpy` with the same `scene`/`show` lines and the same say statements (source text + speaker). The patch looks lines up by text and speaker, so the screen shows what the player sees. Set any flags the scene needs.
- First load can take 1–2 minutes with a large dictionary. Wait for the first screenshot before calling it a freeze. Delete stale `.rpyc` of the generated patch files after each rebuild.
- Give screenshots a per-run prefix and count the files afterwards; an unformatted name makes every shot overwrite one file. Don't `rm shots/*.png`.
- Read many lines cheaply by cropping the dialogue strip (about y 78–92 %, x 15–85 %) from each shot and stacking the crops into one image.

## Windows shell traps
Git Bash heredocs turn `\b` into control characters (put regex scripts in a real file); `/tmp` is invisible to Windows Python; PowerShell 5.1 has no `&&`.
