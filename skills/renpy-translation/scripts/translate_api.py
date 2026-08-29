"""Batched API translator for Ren'Py dialog (bulk first-pass).

- Loads the strings file (output of extract_strings.py)
- Translates in batches via an LLM API, driven entirely by profile.json
- Validates Ren'Py token preservation ([vars], {tags}, \\escapes), retries on mismatch
- Saves progress incrementally to the profile's progress_file (resumable)

This is the BULK path, and a bulk pass is a draft. Quality-critical dialog
should be translated or reviewed in-session by whichever assistant you are
working in, following the game's translation guide (references/translating.md).

Providers (profile api.provider):
  gemini             — Google Gemini API (pip install google-genai; GEMINI_API_KEY)
  anthropic          — Anthropic API (pip install anthropic; ANTHROPIC_API_KEY)
  claude-cli         — headless `claude -p` via a locally installed Claude Code
                       CLI; uses your existing subscription, NO API key needed
  openai-compatible  — any OpenAI Chat Completions endpoint, selected with
                       api.base_url: OpenAI, DeepSeek, OpenRouter, Ollama,
                       Azure. stdlib HTTP only, no SDK to install.

Usage:
  python translate_api.py --profile profile.json
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from characters import cast_block, character_line, display_name, resolve_alias
from relationships import build_resolver, relationships_config
from translation_memory import (
    TranslationContext, TranslationMemory, resolve_tm_path, tm_enabled,
)
from validation import (
    ESC_RE, PCT_RE, REASONS, TAG_RE, VAR_RE,
    configure_console, policy_banner, validate_translation, validation_policy,
    write_text_atomic,
)

configure_console()

# ANSI CSI and OSC escape sequences (colors, cursor moves, window titles)
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')


def extract_json_array(raw):
    """Parse the first JSON array out of a possibly noisy model reply.

    Survives ANSI color codes, version banners or warnings before/after the
    array, code fences, and trailing chatter. Returns [] when no array exists.

    A top-level OBJECT is unwrapped to its first list value: JSON-mode
    endpoints (OpenAI response_format=json_object and friends) cannot return
    a bare array, so they wrap it — {"translations": [...]}. An object with
    no list value is not a batch reply and falls through to the scan below.
    """
    raw = ANSI_RE.sub("", raw).strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```\w*\n|```$', '', raw, flags=re.MULTILINE).strip()
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for value in result.values():
                if isinstance(value, list):
                    return value
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    idx = raw.find("[")
    while idx != -1:
        try:
            result, _end = decoder.raw_decode(raw, idx)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        idx = raw.find("[", idx + 1)
    return []

TOKEN_RULES = """
TOKEN PRESERVATION (critical — broken tokens crash the game):
- Preserve the EXACT same number and order of these tokens:
  * Variable subs: [varname], [varname!t], [varname.attr]
  * Style tags: {i}...{/i}, {b}...{/b}, {color=#xxx}...{/color}, {size=NN}...{/size}, {w}, {w=N.N}, {p}, {nw}, {fast}
  * Escape sequences: \\n, \\", \\'
  * Percent signs: %% (literal %)
"""


def token_signature(text):
    """Return (vars, tags, escapes, %%-count) for comparison.

    The %% count is included so the bulk gate and qa_check.py agree on what
    a preserved token set is — TOKEN_RULES already promises it.
    """
    return (
        sorted(VAR_RE.findall(text)),
        sorted(TAG_RE.findall(text)),
        sorted(ESC_RE.findall(text)),
        len(PCT_RE.findall(text)),
    )


def load_profile(path):
    profile_path = Path(path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return profile, profile_path.parent


# Explains the per-line `to` field. Appended ONLY when addressee resolution is
# enabled for this profile, so a project that declares no relationships gets
# byte-identical prompts to v1.4 — and so the system prompt stays static across
# batches, which is what makes provider prompt caching work.
ADDRESSEE_RULE = """ADDRESSEE:
- A line's "to" field names who it is spoken TO. Apply that speaker's rules for
  that specific person from the cast block (pronouns, register, address terms).
- When "to" is absent the addressee is not known. Use the speaker's default
  register; do not guess a relationship from the line's content."""


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

    addressee = (ADDRESSEE_RULE + "\n"
                 if relationships_config(profile)["enabled"] else "")

    return f"""You translate English dialog from the visual novel "{game}" into {lang}.

{glossary}
{style}
{TOKEN_RULES}
{addressee}
OUTPUT FORMAT:
Reply with ONLY a JSON array of objects: [{{"id": N, "tr": "..."}}, ...]
- id matches the input id
- tr is the translated string
- NO explanation, NO markdown fences, NO extra keys
"""


def speaker_blurb(speakers, code):
    """The short per-line label. The full voice brief is in the cast block."""
    return character_line(speakers, code)


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

    max_tokens = api.get("max_tokens", 8192)

    def call_model(system, user):
        resp = client.messages.create(
            model=model,
            system=system,
            max_tokens=max_tokens,
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
    import tempfile

    api = profile.get("api", {})
    exe = shutil.which("claude")
    if not exe:
        sys.exit("claude CLI not found on PATH (install Claude Code, or pick another provider)")
    model = api.get("model", "sonnet")
    timeout = api.get("timeout", 600)

    # Feature-detect optional flags once (offline, no API call) so we stay
    # compatible with older CLI versions that lack them.
    help_text = subprocess.run([exe, "-p", "--help"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace").stdout
    extra = []
    if "--max-turns" in help_text:
        extra += ["--max-turns", "1"]        # no agentic tool-use loops
    if "--output-format" in help_text:
        extra += ["--output-format", "text"]

    # Neutral cwd: don't let the work folder's CLAUDE.md / plugins / hooks
    # load into every call (token bloat + possible instruction injection).
    neutral_cwd = tempfile.gettempdir()

    def call_model(system, user):
        # One-shot session per call (no --continue/--resume): stateless by
        # construction, so context can never accumulate across batches.
        # System prompt is merged into the prompt and sent via stdin:
        # version-proof and immune to command-line length limits.
        proc = subprocess.run(
            [exe, "-p", "--model", model, *extra],
            input=system + "\n\n" + user,
            text=True, encoding="utf-8", errors="replace",
            capture_output=True, cwd=neutral_cwd, timeout=timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI exited {proc.returncode}: {proc.stderr[:300]}")
        return proc.stdout

    return call_model


# Absolute cap on automatic max_tokens escalation, so a pathological reply
# can't run up an unbounded bill on the operator's behalf.
MAX_TOKEN_CEILING = 65536

# DeepSeek's official API. Preset rather than a bare base_url because the
# defaults are the whole point:
#
#  * `thinking` is DISABLED. DeepSeek V4 enables it by default, and two things
#    follow. Reasoning tokens count against max_tokens, so a long chain of
#    thought can consume the entire budget and return an EMPTY answer; and
#    thinking mode rejects temperature/top_p/presence_penalty/frequency_penalty,
#    silently discarding the low temperature this pipeline relies on for
#    consistency. Batch translation is not a reasoning task — turning thinking
#    off removes the failure mode at its source and gives temperature back.
#    Set api.thinking = true to opt in for a quality-critical pass.
#  * `deepseek-v4-flash` is the default model: fast and cheap, which is what a
#    bulk first pass wants. Use `deepseek-v4-pro` for a harder pass.
DEEPSEEK = {
    "base_url": "https://api.deepseek.com",
    "api_key_env": "DEEPSEEK_API_KEY",
    "model": "deepseek-v4-flash",
    "supports_thinking": True,
    "thinking": False,
    "reasoning_effort": "high",
}

# Retired aliases. They used to select V4-Flash's non-thinking and thinking
# modes; DeepSeek withdrew them on 2026-07-24. Still passed through verbatim —
# refusing a model name we can't verify would be worse than warning — but the
# operator is told, because the API error for an unknown model is opaque.
RETIRED_MODELS = {
    "deepseek-chat": "deepseek-v4-flash (thinking off)",
    "deepseek-reasoner": "deepseek-v4-flash with api.thinking = true",
}


def warn_retired_model(model):
    replacement = RETIRED_MODELS.get(model)
    if replacement:
        print(f"warning: '{model}' was retired by DeepSeek on 2026-07-24. "
              f"Use {replacement}. Sending it anyway.")


def read_completion(data):
    """-> (content, problem). `problem` is None on success.

    Separates "the model answered" from "the model produced nothing useful".
    An empty answer is never returned as "": callers would hand it on as a
    translation-shaped nothing, and the whole batch would look merely
    unparseable instead of budget-starved.
    """
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    finish = choice.get("finish_reason")

    if content.strip():
        return content, None

    usage = data.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = details.get("reasoning_tokens") or 0
    completion_tokens = usage.get("completion_tokens") or 0
    # reasoning_content sits beside content; it is the model's scratchpad,
    # never the answer, so it is diagnosed and discarded — never translated.
    had_reasoning = bool((message.get("reasoning_content") or "").strip())

    if finish == "length":
        if reasoning_tokens or had_reasoning:
            msg = (f"empty answer: the reply hit max_tokens while still "
                   f"reasoning ({reasoning_tokens or 'unknown'} reasoning "
                   f"tokens of {completion_tokens} generated). Raise "
                   f"api.max_tokens, or set api.thinking = false — batch "
                   f"translation does not need a chain of thought.")
        else:
            msg = (f"empty answer: the reply hit max_tokens after "
                   f"{completion_tokens} tokens. Raise api.max_tokens or "
                   f"lower api.batch_size.")
        return None, {"message": msg, "truncated": True}

    if finish == "content_filter":
        return None, {"message": "empty answer: blocked by the provider's "
                                 "content filter. Adult-game dialog trips "
                                 "some providers; try another backend.",
                      "truncated": False}

    if had_reasoning:
        return None, {"message": "empty answer: the model returned only "
                                 "reasoning_content and no content. Set "
                                 "api.thinking = false for batch translation.",
                      "truncated": True}

    return None, {"message": f"empty answer from the model "
                             f"(finish_reason={finish!r}).",
                  "truncated": False}


def _provider_openai_compatible(profile, preset=None):
    """Any OpenAI Chat Completions endpoint, selected via api.base_url.

    Covers OpenAI, DeepSeek, OpenRouter, Ollama and Azure with one factory.
    Implemented over urllib rather than an SDK: ADR-002 keeps the deterministic
    core dependency-free, and these backends differ only in URL, key, and a
    few optional knobs carried by `preset`.
    """
    api = profile.get("api", {})
    preset = preset or {}
    _load_dotenv()

    get = lambda k, d=None: api.get(k, preset.get(k, d))

    base_url = get("base_url", "https://api.openai.com/v1").rstrip("/")
    key_env = get("api_key_env", "OPENAI_API_KEY")
    key_header = get("api_key_header", "Authorization")
    model = get("model", "gpt-4o-mini")
    temperature = get("temperature", 0.3)
    max_tokens = get("max_tokens", 8192)
    timeout = get("timeout", 600)
    json_mode = get("json_mode", False)
    supports_thinking = preset.get("supports_thinking", False)
    thinking = get("thinking", preset.get("thinking", False))
    reasoning_effort = get("reasoning_effort", preset.get("reasoning_effort"))
    escalate = get("escalate_max_tokens", True)

    warn_retired_model(model)

    key = os.getenv(key_env, "")
    is_local = any(h in base_url for h in ("localhost", "127.0.0.1", "0.0.0.0"))
    if not key and not is_local:
        sys.exit(f"{key_env} not set (env or .env) — required for {base_url}")

    url = base_url + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers[key_header] = f"Bearer {key}" if key_header == "Authorization" else key

    def build_payload(system, user, budget):
        payload = {
            "model": model,
            "max_tokens": budget,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if supports_thinking:
            payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
            if thinking:
                # Thinking mode rejects temperature/top_p/presence_penalty/
                # frequency_penalty, so it is omitted rather than sent and ignored.
                if reasoning_effort:
                    payload["reasoning_effort"] = reasoning_effort
            else:
                payload["temperature"] = temperature
        else:
            payload["temperature"] = temperature
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def post(payload):
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            # RuntimeError (not exit): the per-batch retry loop handles it,
            # so a rate limit costs one batch, not the whole run.
            raise RuntimeError(f"HTTP {e.code} from {url}: {detail}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"cannot reach {url}: {e.reason}")

    # Learned budget, shared across every call this run makes. Without this,
    # the outer per-batch retry restarts discovery from the original value and
    # each batch re-pays the same lesson.
    learned = {"max_tokens": max_tokens}

    def call_model(system, user):
        budget = learned["max_tokens"]
        for attempt in (1, 2):
            data = post(build_payload(system, user, budget))
            content, problem = read_completion(data)
            if problem is None:
                return content
            # An empty answer must never reach the caller as "": it would be
            # handed on as a translation-shaped nothing. Escalate once when the
            # budget was the cause, then fail loudly.
            if attempt == 1 and escalate and problem.get("truncated") \
                    and budget < MAX_TOKEN_CEILING:
                budget = min(budget * 4, MAX_TOKEN_CEILING)
                learned["max_tokens"] = budget
                print(f"  {problem['message']}")
                print(f"  Raising max_tokens to {budget} for the rest of this run.")
                continue
            raise RuntimeError(problem["message"])

    return call_model


def _provider_deepseek(profile):
    """DeepSeek's official API — an OpenAI-compatible endpoint with a
    thinking mode that this preset turns OFF by default. See DEEPSEEK."""
    return _provider_openai_compatible(profile, DEEPSEEK)


PROVIDERS = {
    "gemini": _provider_gemini,
    "anthropic": _provider_anthropic,
    "claude-cli": _provider_claude_cli,
    "openai-compatible": _provider_openai_compatible,
    "deepseek": _provider_deepseek,
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


RETRY_NAGS = {
    "TOKEN": "had mismatched Ren'Py tokens. Each output MUST contain the EXACT "
             "same [variables], {tags}, and \\escapes as the English.",
    "MISSING": "was missing entries. Return one object per input id, no more and no fewer.",
    "EMPTY": "contained empty translations. Every line needs real text.",
    "ECHO": "returned the English source unchanged for some lines. Every line MUST "
            "be translated — copying the source is not a translation.",
    "SCRIPT": "was not written in the target script for some lines. Write the "
              "translation in <LANG>'s own script, not in English.",
}


def translate_batch(call_model, system, speakers, lang_name, batch,
                    retry=False, reasons=("TOKEN",), resolver=None):
    """batch: list of {id, text, speaker, kind}. Returns list of {id, tr}.

    `reasons` selects the retry nag(s). Telling a model its tokens mismatched
    when it actually echoed the source teaches it the wrong lesson, so the
    retry names what really failed.

    `resolver` (v1.5) adds a "to" field naming the addressee on lines where one
    could be resolved confidently. Lines it declines to resolve carry no "to"
    at all rather than a guess — the cast block still shows the speaker's whole
    relationship table, which is exactly the v1.4 behavior for those lines.
    """
    # Persona cards for this batch's cast, emitted ONCE up front. Repeating a
    # full card on every line would multiply the prompt by the batch size; the
    # per-line label stays short and points back at the card by name.
    cast = cast_block(speakers, [item["speaker"] for item in batch])

    lines = []
    for item in batch:
        sp = speaker_blurb(speakers, item["speaker"])
        target = resolver.target_for(item) if resolver else None
        to = f'"to": "{display_name(speakers, target)}", ' if target else ""
        lines.append(
            f'{{"id": {item["id"]}, "speaker": "{sp}", {to}"kind": "{item["kind"]}", '
            f'"text": {json.dumps(item["text"], ensure_ascii=False)}}}'
        )
    user_msg = (f"Translate these lines to {lang_name}. Output JSON array only.\n\n"
                + (cast + "\n\n" if cast else "")
                + "[\n" + ",\n".join(lines) + "\n]")

    if retry:
        for code in reasons or ("TOKEN",):
            # str.replace, not .format — the TOKEN nag contains a literal {tags}
            nag = RETRY_NAGS.get(code, RETRY_NAGS["TOKEN"]).replace("<LANG>", lang_name)
            user_msg += f"\n\nIMPORTANT: Your previous output {nag}"

    raw = call_model(system, user_msg)
    result = extract_json_array(raw)
    if not result:
        print(f"  No JSON array in reply. Raw: {raw.strip()[:300]}...")
    return result


def _print_summary(context_hits, default_hits, llm_translations,
                   rejected=None, tm_rejected=None, samples=()):
    tm_hits = context_hits + default_hits
    total = tm_hits + llm_translations
    savings = (tm_hits / total * 100) if total else 0.0
    print("\nTranslation Summary")
    print("-------------------")
    print(f"TM Hits: {tm_hits}")
    print(f"Context Hits: {context_hits}")
    print(f"Default Hits: {default_hits}")
    print(f"LLM Calls: {llm_translations}")
    print(f"Savings: {savings:.1f}%")
    if tm_rejected:
        print(f"TM Rejected: {sum(tm_rejected.values())}")
    if rejected:
        print(f"Rejected (not saved, not cached): {sum(rejected.values())}")
        for code, n in sorted(rejected.items()):
            print(f"  {code} — {REASONS.get(code, code)}: {n}")
        for code, src in samples:
            print(f"    [{code}] {src[:70]}")
        print("  These stay untranslated and will be retried on the next run.")


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
    policy = validation_policy(profile)
    print(policy_banner(policy))
    call_model = make_call_model(profile)

    strings = json.loads(strings_file.read_text(encoding="utf-8"))
    for i, e in enumerate(strings):
        e["id"] = i

    # Addressee resolution (v1.5). One resolver for the whole run: the prompt
    # and the TM context must name the same person for the same line, or the
    # variant a run writes is not the variant the next run retrieves.
    resolver = build_resolver(profile, strings)
    if resolver.enabled:
        resolved = sum(1 for e in strings if resolver.target_for(e))
        print(f"Addressee resolution: on (min_confidence="
              f"{resolver.min_confidence}) — {resolved}/{len(strings)} line(s) "
              f"resolved. Run relationships.py for the full report.")

    if progress_file.exists():
        progress = json.loads(progress_file.read_text(encoding="utf-8"))
    else:
        progress = {}  # english -> translation

    # Translation Memory: the engine only talks to TranslationMemory, never the
    # JSON file. Seed it from existing progress (free bootstrap on first run),
    # then resolve TM hits BEFORE batching so only genuine misses reach the LLM.
    tm = None
    context_hits = 0
    default_hits = 0
    tm_rejected = {}
    if tm_enabled(profile):
        tm = TranslationMemory(
            resolve_tm_path(profile, base),
            source_language=profile.get("source_language", "en"),
            target_language=profile.get("language_id", profile.get("target_language", "th")),
        )
        tm.load()
        seeded = tm.import_progress(progress)
        if seeded:
            print(f"TM seeded with {seeded} existing translation(s).")

        for e in strings:
            if e["text"] in progress:
                continue
            # Canonical speaker: TM variants are speaker-anchored (ADR-005),
            # so an alias code would build a second, disjoint variant set for
            # one character and pay for the same translation twice.
            ctx = TranslationContext(speaker=resolve_alias(speakers, e.get("speaker")),
                                     target=resolver.target_for(e),
                                     file=e.get("file"), line=e.get("line"))
            hit = tm.lookup(e["text"], ctx)
            if hit is None:
                continue
            tr = hit["translation"]
            # Re-validate tokens against THIS source (a normalized hit may carry
            # different [vars]/{tags}); fall through to the LLM if they differ.
            if token_signature(e["text"]) != token_signature(tr):
                continue
            # Validate hits on READ as well as on write: a TM poisoned by an
            # older run would otherwise keep serving an echo back for free,
            # forever. Rejecting here lets the string fall through to the LLM,
            # so existing projects self-heal on their next pass.
            ok, code = validate_translation(e["text"], tr, policy)
            if not ok:
                tm_rejected[code] = tm_rejected.get(code, 0) + 1
                continue
            progress[e["text"]] = tr
            if hit["hit_type"] == "context":
                context_hits += 1
            else:
                default_hits += 1
        if tm_rejected:
            detail = ", ".join(f"{REASONS[c]}: {n}" for c, n in sorted(tm_rejected.items()))
            print(f"TM entries rejected on lookup ({detail}) — re-translating those.")
        if context_hits or default_hits:
            print(f"TM hits: {context_hits + default_hits} "
                  f"(context {context_hits}, default {default_hits}; skipped the LLM).")
            tm.save()
            # Persist progress now so the early-return-when-done path below still
            # writes translations.json (the file build_patch.py consumes).
            write_text_atomic(progress_file,
                              json.dumps(progress, ensure_ascii=False, indent=2))

    todo = [e for e in strings if e["text"] not in progress]
    print(f"Total: {len(strings)} | Done: {len(progress)} | Todo: {len(todo)}")

    if not todo:
        print("All strings already translated.")
        _print_summary(context_hits, default_hits, 0, tm_rejected=tm_rejected)
        return

    llm_translations = 0
    batch_num = 0
    rejected = {}
    rejected_samples = []
    for i in range(0, len(todo), batch_size):
        batch_num += 1
        batch = todo[i:i + batch_size]
        print(f"\nBatch {batch_num} ({i+1}-{i+len(batch)} of {len(todo)})...")
        try:
            result = translate_batch(call_model, system, speakers, lang_name, batch,
                                     resolver=resolver)
        except Exception as e:
            print(f"  API error: {e}. Sleeping 10s and retrying once.")
            time.sleep(10)
            try:
                result = translate_batch(call_model, system, speakers, lang_name,
                                         batch, resolver=resolver)
            except Exception as e2:
                print(f"  Still failing: {e2}. Skipping batch.")
                continue

        # Skip non-dict entries: a JSON-mode wrapper can hand back a list of
        # scalars, and `"id" in 1` raises.
        id_to_tr = {r["id"]: r["tr"] for r in result
                    if isinstance(r, dict) and "id" in r and "tr" in r}

        # Validate tokens AND output validity, so the retry names what failed
        def check(item):
            tr = id_to_tr.get(item["id"])
            if tr is None:
                return "MISSING"
            if token_signature(item["text"]) != token_signature(tr):
                return "TOKEN"
            ok, code = validate_translation(item["text"], tr, policy)
            return None if ok else code

        mismatches = [(item, code) for item in batch
                      for code in [check(item)] if code]

        # Retry mismatches once
        if mismatches:
            codes = sorted({c for _, c in mismatches})
            print(f"  Retrying {len(mismatches)} entries ({', '.join(codes)})...")
            retry_result = translate_batch(call_model, system, speakers, lang_name,
                                           [item for item, _ in mismatches],
                                           retry=True, reasons=codes,
                                           resolver=resolver)
            for r in retry_result:
                if isinstance(r, dict) and "id" in r and "tr" in r:
                    id_to_tr[r["id"]] = r["tr"]

        # Commit accepted translations. Anything still failing reaches NEITHER
        # the progress store nor the TM: caching an echo would approve it
        # permanently and serve it back free on every future run (ADR-017).
        accepted = 0
        for item in batch:
            tr = id_to_tr.get(item["id"])
            if not tr or token_signature(item["text"]) != token_signature(tr):
                continue
            ok, code = validate_translation(item["text"], tr, policy)
            if not ok:
                rejected[code] = rejected.get(code, 0) + 1
                if len(rejected_samples) < 5:
                    rejected_samples.append((code, item["text"]))
                continue
            progress[item["text"]] = tr
            accepted += 1
            llm_translations += 1
            if tm is not None:
                # Use the batch item's OWN context (under --no-dedupe many
                # items share text but differ by speaker; a text->entry map
                # would collapse them to one speaker and mis-tag variants).
                ctx = TranslationContext(
                    speaker=resolve_alias(speakers, item.get("speaker")),
                    target=resolver.target_for(item),
                    file=item.get("file"), line=item.get("line"))
                tm.add(item["text"], tr, ctx)
        print(f"  Accepted {accepted}/{len(batch)}. Total done: {len(progress)}")

        # Save incrementally (progress + TM, atomically, per batch)
        write_text_atomic(progress_file,
                          json.dumps(progress, ensure_ascii=False, indent=2))
        if tm is not None:
            tm.save()
        time.sleep(0.5)  # polite

    if tm is not None:
        tm.save()
    print(f"\nDone. Total translated: {len(progress)}")
    _print_summary(context_hits, default_hits, llm_translations,
                   rejected=rejected, tm_rejected=tm_rejected,
                   samples=rejected_samples)


if __name__ == "__main__":
    main()
