# Translating custom text subsystems (phones, computers, social feeds)

Text produced by game-specific Python code — chat messages assembled in functions, feed posts stored in lists, computer-screen content — never passes through `say_menu_text_filter`, and usually isn't a literal that `translate strings` can see either. Each such subsystem needs a small wrapper layer. This pattern shipped in production for Being a DIK's phone chat (two seasons of it), so the recipe below is proven.

**Designed for translators, not programmers:** you copy two files, and the only thing you ever edit is **text inside quotation marks** between the `EDIT ONLY` markers. Never change indentation, never rename anything outside quotes.

> Editor warning: use a code editor (VS Code, Notepad++). Word, Google Docs, and chat apps silently replace straight quotes `"` with curly ones `“ ”`, which crashes Ren'Py. If you pasted text from one of those, retype the quotes.

## Step 1: Find the producers

Search the decompiled sources for the subsystem's screen, then trace where its display text comes from. You're looking for the **functions that fill the data the screen renders**. They come in two shapes:

- **Array shape** — the function *rebuilds* a list every call (e.g. the reply choices you can tap). Tell-tale: the code assigns the whole list (`reply_array = [...]`).
- **Append shape** — the function *adds entries* to a persistent history (e.g. the message log). Tell-tale: the code calls `.append(...)` on a list that's saved with the game.

Write down each function name and the name of the list it fills. That's all the "programming" this task needs.

## Step 2: The sub-dict file

`tl/<lang>/<subsystem>/00_<subsystem>_dict.rpy` — translations plus two lookup helpers (exact-match with fallback to the original, same crash-proof contract as the main filter):

```renpy
init 5 python:
    _chatapp_tl = {
        "Source message text": "translated text",
        # ... extracted + translated like any other strings
    }

    def _chatapp_t(s):
        if renpy.game.preferences.language == "thai" and s in _chatapp_tl:
            return _chatapp_tl[s]
        return s

    def _chatapp_tlist(seq):
        return [_chatapp_t(s) for s in seq]
```

(Replace `thai` with your language id and `chatapp` with your subsystem name — find-and-replace across both files, then stop.)

## Step 3: The wrapper file

`tl/<lang>/<subsystem>/01_<subsystem>_wrappers.rpy`. The two helpers at the top are generic — **never edit them**. Each function you found in Step 1 becomes ONE line between the markers: `_ftp_wrap_array` for array-shape functions, `_ftp_wrap_append` for append-shape functions.

```renpy
init 5 python:
    _chatapp_missing = []

    def _ftp_wrap_array(func_name, array_name):
        # For functions that REBUILD a list each call (reply choices).
        fn = globals().get(func_name)
        if fn is None:
            _chatapp_missing.append(func_name)
            return
        def _wrapper(_orig=fn):
            _orig()
            globals()[array_name] = _chatapp_tlist(globals()[array_name])
        globals()[func_name] = _wrapper

    def _ftp_wrap_append(func_name, list_name):
        # For functions that APPEND to a persistent history list.
        fn = globals().get(func_name)
        if fn is None:
            _chatapp_missing.append(func_name)
            return
        def _wrapper(_orig=fn):
            _before = len(globals()[list_name])
            _orig()
            _lst = globals()[list_name]
            for _i in range(_before, len(_lst)):
                _lst[_i] = _chatapp_t(_lst[_i])
        globals()[func_name] = _wrapper

    # ---- EDIT ONLY BELOW: one line per function, names in quotes ----
    _ftp_wrap_array("chatapp_get_replies_alex", "chatapp_reply_array")
    _ftp_wrap_append("chatapp_them_replies_alex", "chatapp_alex_history")
    # ---- EDIT ONLY ABOVE ----

    if _chatapp_missing:
        print("FTP wrapper: %d function(s) not found: %s"
              % (len(_chatapp_missing), ", ".join(_chatapp_missing)))
```

Why this shape is safe by construction: a typo'd function name can't crash the game (it's reported and skipped); the `_orig=fn` default-argument binding freezes the original function so the wrapper can't recurse; the append wrapper only translates **newly added** entries, so histories restored from saves aren't re-processed; and because each line is just quoted names, there's no indentation, scope, or `global`-statement surgery to get wrong.

## Step 4: Extraction for the sub-dict

These strings live in Python lists/calls, so the standard extractor won't find them. Pragmatic approach: grep the subsystem's source files for quoted strings (`rg '"[^"]{4,}"' chatapp_*.rpy`), curate by eye, and feed them through the same progress-JSON → QA → translation loop as everything else. Keep them in the main progress file; only the generated sub-dict is separate.

## Step 5: Verify it took

1. Launch the game. **A crash on launch** = syntax problem in your edits — almost always curly quotes or a deleted comma. Re-check only the lines you touched.
2. Open the console (Shift+O, if the game has it enabled) or read `log.txt` in the game folder. A line like `FTP wrapper: 2 function(s) not found: ...` lists every name you typo'd or that doesn't exist in this game version — fix those names.
3. Open the subsystem in-game with your language active and confirm translated text.

| Symptom | Cause | Fix |
|---|---|---|
| Crash on launch | Curly quotes / broken syntax in edited lines | Retype quotes in a code editor; compare against the template |
| No errors, text stays original | Function name typo'd, or wrapped at an init priority earlier than where the game defines it | Check the `FTP wrapper:` report; raise the `init 5` number if the game defines its functions late |
| Reply choices translate, history doesn't (or vice versa) | Array/append shape mixed up | Swap `_ftp_wrap_array` ↔ `_ftp_wrap_append` for that line |
| Text translates once, then reverts after loading a save | The list is rebuilt from save data by a function you haven't wrapped | Find and wrap that loader function too |

## Appendix: unusual shapes

A few games produce text in ways the two helpers don't fit (dicts of messages, tuples, text built at render time). Those need a hand-written wrapper following the same principles — `dir()`/`globals()` guard, `_orig=fn` binding, translate only what's new — and are programmer territory; ask for help rather than improvising.

## Scoping

Inventory subsystems during extraction (see `extraction.md`) and agree scope with the user **before** translating the main script — per subsystem this is hours, not minutes. Typical scope cut in BaDIK: phone chat in, GUI/menus and mod UI out.
