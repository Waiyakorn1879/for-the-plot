"""Batched API translator for Ren'Py dialog (bulk first-pass).

- Loads the strings file (output of extract_strings.py)
- Translates in batches via an LLM API, driven entirely by profile.json
- Validates Ren'Py token preservation ([vars], {tags}, \\escapes), retries on mismatch
- Saves progress incrementally to the profile's progress_file (resumable)

This is the BULK path. Quality-critical dialog should be translated or
reviewed by Claude in-session following the game's translation guide
(see references/translating.md).

Providers (profile api.provider):
  gemini      — Google Gemini API (pip install google-genai; GEMINI_API_KEY)
  anthropic   — Anthropic API (pip install anthropic; ANTHROPIC_API_KEY)
  claude-cli  — headless `claude -p` via the locally installed Claude Code CLI;
                uses your existing subscription, NO API key needed

Usage:
  python translate_api.py --profile profile.json
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Tokens that must be preserved exactly
VAR_RE = re.compile(r'\[[^\]]+\]')
TAG_RE = re.compile(r'\{[^}]+\}')
ESC_RE = re.compile(r'\\[n"\'\\]')

TOKEN_RULES = """
TOKEN PRESERVATION (critical — broken tokens crash the game):
- Preserve the EXACT same number and order of these tokens:
  * Variable subs: [varname], [varname!t], [varname.attr]
  * Style tags: {i}...{/i}, {b}...{/b}, {color=#xxx}...{/color}, {size=NN}...{/size}, {w}, {w=N.N}, {p}, {nw}, {fast}
  * Escape sequences: \\n, \\", \\'
  * Percent signs: %% (literal %)
"""


def token_signature(text):
    """Return (vars, tags, escapes) sorted tuples for comparison."""
    return (
        sorted(VAR_RE.findall(text)),
        sorted(TAG_RE.findall(text)),
        sorted(ESC_RE.findall(text)),
    )


def load_profile(path):
    profile_path = Path(path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return profile, profile_path.parent


def build_system_instruction(profile, base_dir):
    game = profile.get("game_name", "a Ren'Py visual novel")
    lang = profile.get("language_name", profile.get("language_id", "the target language"))

    keep = profile.get("keep_untranslated", [])
    glossary = ""
    if keep:
        glossary = ("GLOSSARY — keep these EXACTLY as written (do not translate):\n- "
                    + ", ".join(keep) + "\n")

    style = ""
    style_file = profile.get("style_guide_file")
    if style_file:
        style_path = base_dir / style_file
        if style_path.is_file():
            style = "STYLE GUIDE:\n" + style_path.read_text(encoding="utf-8") + "\n"
        else:
            print(f"warning: style guide not found: {style_path}")

    return f"""You translate English dialog from the visual novel "{game}" into {lang}.

{glossary}
{style}
{TOKEN_RULES}

OUTPUT FORMAT:
Reply with ONLY a JSON array of objects: [{{"id": N, "tr": "..."}}, ...]
- id matches the input id
- tr is the translated string
- NO explanation, NO markdown fences, NO extra keys
"""


def speaker_blurb(speakers, code):
    s = speakers.get(code)
    if not s:
        return f"unknown speaker '{code}'"
    name = s.get("name", code)
    g = f" ({s['gender']})" if s.get("gender") else ""
    r = f" — {s['role']}" if s.get("role") else ""
    return f"{name}{g}{r}"


def _load_dotenv():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _provider_gemini(profile):
    """Google Gemini API. pip install google-genai; GEMINI_API_KEY in env/.env."""
    api = profile.get("api", {})
    _load_dotenv()
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY not set (env or .env)")
    client = genai.Client(api_key=key)
    model = api.get("model", "gemini-2.5-pro")
    temperature = api.get("temperature", 0.3)

    def call_model(system, user):
        resp = client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        return resp.text

    return call_model


def _provider_anthropic(profile):
    """Anthropic API. pip install anthropic; ANTHROPIC_API_KEY in env/.env."""
    api = profile.get("api", {})
    _load_dotenv()
    import anthropic

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY not set (env or .env)")
    client = anthropic.Anthropic(api_key=key)
    model = api.get("model", "claude-sonnet-4-6")
    temperature = api.get("temperature", 0.3)

    def call_model(system, user):
        resp = client.messages.create(
            model=model,
            system=system,
            max_tokens=8192,
            temperature=temperature,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text

    return call_model


def _provider_claude_cli(profile):
    """Headless `claude -p` — uses the locally installed Claude Code CLI and
    the user's existing subscription. No API key needed."""
    import shutil
    import subprocess

    api = profile.get("api", {})
    exe = shutil.which("claude")
    if not exe:
        sys.exit("claude CLI not found on PATH (install Claude Code, or pick another provider)")
    model = api.get("model", "sonnet")

    def call_model(system, user):
        # System instruction is merged into the prompt: works on every CLI
        # version and avoids command-line length limits by using stdin.
        proc = subprocess.run(
            [exe, "-p", "--model", model],
            input=system + "\n\n" + user,
            text=True, encoding="utf-8", capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI exited {proc.returncode}: {proc.stderr[:300]}")
        return proc.stdout

    return call_model


PROVIDERS = {
    "gemini": _provider_gemini,
    "anthropic": _provider_anthropic,
    "claude-cli": _provider_claude_cli,
}


def make_call_model(profile):
    """Return call_model(system, user) -> str for the profile's api.provider.

    To add a provider, register a factory in PROVIDERS that returns a function
    sending `system` as the system prompt and `user` as the user message and
    returning the raw text reply (a JSON array).
    """
    provider = profile.get("api", {}).get("provider", "gemini")
    factory = PROVIDERS.get(provider)
    if factory is None:
        sys.exit(f"unsupported provider '{provider}' — known: {', '.join(sorted(PROVIDERS))}")
    return factory(profile)


def translate_batch(call_model, system, speakers, lang_name, batch, retry=False):
    """batch: list of {id, text, speaker, kind}. Returns list of {id, tr}."""
    lines = []
    for item in batch:
        sp = speaker_blurb(speakers, item["speaker"])
        lines.append(
            f'{{"id": {item["id"]}, "speaker": "{sp}", "kind": "{item["kind"]}", '
            f'"text": {json.dumps(item["text"], ensure_ascii=False)}}}'
        )
    user_msg = (f"Translate these lines to {lang_name}. Output JSON array only.\n\n"
                "[\n" + ",\n".join(lines) + "\n]")

    if retry:
        user_msg += "\n\nIMPORTANT: Your previous output had mismatched Ren'Py tokens. " \
                    "Each output MUST contain the EXACT same [variables], {tags}, and \\escapes as the English."

    raw = call_model(system, user_msg).strip()
    # Strip code fences if any
    if raw.startswith("```"):
        raw = re.sub(r'^```\w*\n|```$', '', raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}\n  Raw: {raw[:300]}...")
        return []


def main():
    ap = argparse.ArgumentParser(description="Bulk API translation pass for Ren'Py strings")
    ap.add_argument("--profile", required=True, help="profile.json")
    ap.add_argument("--strings", help="strings file (overrides profile strings_file)")
    ap.add_argument("--progress", help="progress file (overrides profile progress_file)")
    args = ap.parse_args()

    profile, base = load_profile(args.profile)
    strings_file = Path(args.strings) if args.strings else base / profile.get("strings_file", "strings.json")
    progress_file = Path(args.progress) if args.progress else base / profile.get("progress_file", "translations.json")

    speakers = profile.get("speakers", {})
    # Standard pseudo-speakers, overridable via profile
    speakers.setdefault("_text", {"name": "(on-screen text)", "role": "narrator-style text shown on screen"})
    speakers.setdefault("_menu", {"name": "(menu choice)", "role": "a choice the player picks"})
    speakers.setdefault("narrator", {"name": "(narration)", "role": "third-person narration"})

    lang_name = profile.get("language_name", profile.get("language_id", "the target language"))
    batch_size = profile.get("api", {}).get("batch_size", 20)
    system = build_system_instruction(profile, base)
    call_model = make_call_model(profile)

    strings = json.loads(strings_file.read_text(encoding="utf-8"))
    for i, e in enumerate(strings):
        e["id"] = i

    if progress_file.exists():
        progress = json.loads(progress_file.read_text(encoding="utf-8"))
    else:
        progress = {}  # english -> translation

    todo = [e for e in strings if e["text"] not in progress]
    print(f"Total: {len(strings)} | Done: {len(progress)} | Todo: {len(todo)}")

    if not todo:
        print("All strings already translated.")
        return

    batch_num = 0
    for i in range(0, len(todo), batch_size):
        batch_num += 1
        batch = todo[i:i + batch_size]
        print(f"\nBatch {batch_num} ({i+1}-{i+len(batch)} of {len(todo)})...")
        try:
            result = translate_batch(call_model, system, speakers, lang_name, batch)
        except Exception as e:
            print(f"  API error: {e}. Sleeping 10s and retrying once.")
            time.sleep(10)
            try:
                result = translate_batch(call_model, system, speakers, lang_name, batch)
            except Exception as e2:
                print(f"  Still failing: {e2}. Skipping batch.")
                continue

        id_to_tr = {r["id"]: r["tr"] for r in result if "id" in r and "tr" in r}

        # Validate token preservation
        mismatches = []
        for item in batch:
            tr = id_to_tr.get(item["id"])
            if tr is None:
                mismatches.append(item)
                continue
            if token_signature(item["text"]) != token_signature(tr):
                mismatches.append(item)

        # Retry mismatches once
        if mismatches:
            print(f"  Retrying {len(mismatches)} mismatched/missing entries...")
            retry_result = translate_batch(call_model, system, speakers, lang_name, mismatches, retry=True)
            for r in retry_result:
                if "id" in r and "tr" in r:
                    id_to_tr[r["id"]] = r["tr"]

        # Commit accepted translations
        accepted = 0
        for item in batch:
            tr = id_to_tr.get(item["id"])
            if tr and token_signature(item["text"]) == token_signature(tr):
                progress[item["text"]] = tr
                accepted += 1
        print(f"  Accepted {accepted}/{len(batch)}. Total done: {len(progress)}")

        # Save incrementally
        progress_file.write_text(
            json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        time.sleep(0.5)  # polite

    print(f"\nDone. Total translated: {len(progress)}")


if __name__ == "__main__":
    main()
