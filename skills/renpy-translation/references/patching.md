# Phases 6–7: Building and deploying the runtime-filter patch

```
python build_patch.py --profile profile.json
```

Writes to `<output_dir>/<language_id>_patch/` (`--layout tl` writes `<output_dir>/tl/<language_id>/` instead; see *Where the patch lives*):

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
| `font.text_size` | cap dialogue size (see the language's locale file) |

Run `python replay_vars.py --src decompiled/ [--json]` to list variables assigned only during play (the ones a replay will not have) with a neutral starting value each; confirm which your gallery touches. An `Uncaught Exception … has no attribute 'x'` in the gallery names any it missed. **Never hand-edit the generated `00_<lang>_filter.rpy`** — the next build overwrites it; put the change in the profile. Since v1.5.2 the file carries a `# build-hash:` line, and a build prints a `WARNING` if the file was edited after its last build.

## Per-speaker translations for shared texts

One English text has one dictionary translation. When a male and a female character both say "Hi!", that translation is unisex by design. To give each their own, run `python speaker_overrides.py todo --profile profile.json`: it lists every (speaker, text) pair, for texts said by *both* genders, that has no override yet (speakers of unknown gender and minor extras keep the unisex line). Fill the `tr` fields — in-session, by API, or by hand; ask the user which, as for any translation — then `speaker_overrides.py merge --profile profile.json --file <filled list>`. Merge applies the bulk translator's validity gate, token parity, and the speaker's own gender rule, and saves only what passes into `speaker_translations.json` (`{"code::text": "translation"}`, speaker code as extracted). `build_patch.py` turns that file into overrides; the runtime filter looks up the speaker from the `Say` statement it runs inside. `status` shows progress. Needs a `strings.json` from v1.5.2 or later (it carries `also_spoken_by`).

## Fonts (non-Latin targets)

With a `font` section in the profile, the filter also: overrides the `font` (and scaled `size`) of the standard text styles when the language is active, and fills `config.font_replacement_map` so any style it missed still falls back to the target font. **The font files themselves must be copied into `game/`** (top level) alongside the patch. Adjust `size_scale` after seeing real dialog in-game.

## Deploy & verify

1. Copy `<output_dir>/<lang>_patch/` → `<game>/game/<lang>_patch/`, plus font files into `<game>/game/`. Upgrading from another layout: delete the old patch folder first (two copies = duplicate definitions = crash).
2. Launch the game. Ren'Py compiles the patch on first launch — the appearance of `.rpyc` siblings next to your `.rpy` files proves zero syntax errors. A traceback screen instead means a malformed generated file (almost always a quoting issue in the dict; find the line in the traceback).
3. Switch language (Preferences picker if the game has one, else the toggle key / auto-set) and play a few scenes: dialog, a menu choice, inner monologue, and a scene with `[variables]` in text.
4. **Load a save** (same session and after a restart): the release-blocking check, see `verify-in-engine.md`.
5. Uninstall = delete `<game>/game/<lang>_patch/`. Nothing else is touched.

## Custom text subsystems (phones, computers, social feeds)

Text built dynamically in Python (chat histories, feed posts) is reachable by neither the say filter nor `translate strings`. It needs the wrapper-sub-dict pattern — full recipe with a proven code template in `custom-subsystems.md`. Budget real time for this and confirm scope with the user before committing to it.

## Where the patch lives (v1.6.5)

**Never put init code under `game/tl/<lang>/`.** Ren'Py loads that folder late, and the store snapshot a save-load restores does not contain variables defined there, so the callbacks in `config` (which survive) hit `NameError` the moment a save is loaded. It reproduces on every launch, even with `config.default_language` set, and a script-only check never sees it. `build_patch.py` therefore defaults to `--layout flat` (`game/<lang>_patch/`, always loaded at init; the hooks already check the active language at runtime, so players on English are unaffected). `--layout tl` remains for native `translate` blocks, which are language data, not code. Custom hooks you add (first-launch switch, credit screen) go in `game/` or the patch folder, never `tl/`.

## Runtime-hook facts (verified on Ren'Py 8.3.4)

- **`config.replace_text` gets each text segment *between tags*, not the whole string.** `"{u}HEADER{/u}\nBody"` arrives as `HEADER`, then `Body` (the `\n` is its own token, and a space after it stays on the segment). A tagged or multi-line string needs one key per segment, plus the body without its leading `\n` / space.
- **`config.say_menu_text_filter` receives the raw say text, not the speaker.** Speaker-specific overrides use the Say-frame lookup in the generated filter.
- **Engine text is unescaped** (real newline, bare quote); `strings.json` keeps source escapes (`\n`, `\"`). A lookup that misses for no visible reason is usually this. Dump the say statements a real run executes and diff them against `strings.json` (the *engine hit rate*; one project measured 30,050 hit / 169 miss / 0 bad).
- **Engine-mutated text** (`.upper()`, `.replace("_"," ")`, `"{} Game".format(...)`) cannot match a stored key. Options: a case-insensitive lookup restricted to text that equals its own upper-case, a small manual map for derived strings, segment keys.
- **Ren'Py's own UI** (Quit / Main Menu / overwrite and delete confirmations, save-slot strings) is not in the game source at all. Add the common ones by hand.
- **Chain, never replace**, any existing `replace_text` / filter. A test harness that installs its own wrapper *before* the language switch captures the pre-language function and silently disables the real one.
- **A swallowed exception looks like "text stays English".** Hooks must not raise, so count and log what they swallow behind a debug flag.
- `translate <lang> strings:` and `translate <lang> style <name>:` work from any file; an empty `translate <lang> python: pass` registers the language.

## First launch and main menu

- `renpy.change_language()` cannot run at init. Call it once from a `config.periodic_callbacks` function and flag it in `persistent`, so the player can pick English afterwards.
- `config.overlay_screens` do **not** draw on the main menu. Show a credit screen from a periodic callback when `renpy.get_screen("main_menu")` exists, and **re-show it whenever a new `main_menu` instance appears** (a language change rebuilds the menu and drops the screen). Keep both in `game/`, not in the patch folder, so they work in any language state.
- **Never translate name data.** `Character` hashing and relationship dicts are keyed on `.name`. Swap names at render time with an exact-match `replace_text`, and skip the swap on credit screens (a staff member named "Adam" must stay a name).

## Not fixable by a text patch

Main-menu buttons, quick-menu bars, headings and popups drawn as bitmaps carry their text in the image. List them in the delivered README as *needs image editing*; a scan for imagebuttons with no `Text` finds them. Text that outgrows a fixed box is visible only in a screenshot.
