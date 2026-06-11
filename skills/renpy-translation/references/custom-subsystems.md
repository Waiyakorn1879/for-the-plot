# Translating custom text subsystems (phones, computers, social feeds)

Text produced by game-specific Python code — chat messages assembled in functions, feed posts stored in lists, computer-screen content — never passes through `say_menu_text_filter` and usually isn't a literal the `translate strings` mechanism can see either. Each such subsystem needs a small wrapper layer. This pattern shipped in production for Being a DIK's phone chat (two seasons of it), so the recipe below is proven.

## Step 1: Find the producer

Search the decompiled sources for the subsystem's screen, then trace where its display text comes from. You're looking for the **function or statement that fills the data structure** the screen renders — e.g. functions appending to a per-character history list, or building an array of selectable replies. Wrap the producer, not the screen: producers are few, screen widgets are many.

## Step 2: A sub-dict + lookup helpers

Drop a `tl/<lang>/<subsystem>/00_<subsystem>_<lang>_dict.rpy`:

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

Exact-match with fallback to the original — same crash-proof contract as the main filter.

## Step 3: Wrap the producers

`tl/<lang>/<subsystem>/01_<subsystem>_wrappers.rpy`, at an init priority **after** the game defines the functions:

```renpy
init 5 python:
    # Guard with dir() so a game update that removes/renames the function
    # degrades to untranslated instead of crashing on game start.
    if 'chatapp_get_replies_alex' in dir():
        _orig_replies_alex = chatapp_get_replies_alex
        def _wrap_replies_alex(_orig=_orig_replies_alex):
            _orig()
            global chatapp_reply_array
            chatapp_reply_array = _chatapp_tlist(chatapp_reply_array)
        chatapp_get_replies_alex = _wrap_replies_alex

    if 'chatapp_them_replies_alex' in dir():
        _orig_history_alex = chatapp_them_replies_alex
        def _wrap_history_alex(_orig=_orig_history_alex):
            global chatapp_alex_history
            _before = len(chatapp_alex_history)
            _orig()
            # translate only the entries this call appended
            for _i in range(_before, len(chatapp_alex_history)):
                chatapp_alex_history[_i] = _chatapp_t(chatapp_alex_history[_i])
        chatapp_them_replies_alex = _wrap_history_alex
```

Hard-won details baked into this template:

- **`_orig=...` default-arg binding** freezes the original function at wrap time; a plain closure would recurse once the global is reassigned.
- **`if '<name>' in dir():` guards** make the whole layer survive game updates.
- **Translate only newly appended entries** (`_before` index) — histories persist in saves; re-translating old entries is wasted work and double-translates if the dict ever maps translated→translated.
- **One wrapper pair per character/feed** is verbose but greppable; resist the urge to metaprogram it — the function names rarely follow a perfectly uniform scheme.

## Step 4: Extraction for the sub-dict

These strings live in Python lists/calls, so the standard extractor won't find them. Pragmatic approach: grep the subsystem's source files for quoted strings (`rg '"[^"]{4,}"' chatapp_*.rpy`), curate by eye, and feed them through the same progress-JSON → QA → translation loop as everything else. Keep them in the main progress file; only the generated sub-dict is separate.

## Scoping

Inventory subsystems during extraction (see `extraction.md`) and agree scope with the user **before** translating the main script — per subsystem this is hours, not minutes. Typical scope cut in BaDIK: phone chat in, GUI/menus and mod UI out.
