"""Translation Memory (TM) for Ren'Py translation — the cost/consistency cache.

A durable, profile-scoped knowledge base of source -> translation pairs. The
bulk translator (translate_api.py) consults it BEFORE calling an LLM and writes
new translations back, so repeated strings (within a game or, optionally, across
games) never hit the model twice.

This module is the ONLY code that touches the TM JSON file. Everything else —
the translation engine, the CLI — goes through the TranslationMemory class
(see the README's hard constraint: the engine never opens the JSON directly).

Storage (default, project-local): <profile dir>/.ftp/translation_memory.json
Set profile "tm": {"path": "..."} to point at a shared/global file for
cross-game reuse (opt-in — reusing one game's character voice in another is a
register risk, which is why context metadata is stored per entry).

Schema (v2 — Contextual Translation Memory):
  {"version": 2, "source_language": "en", "target_language": "th",
   "entries": {"<exact source>": {
       "default_translation": "...",   # context-free fallback (first wins)
       "count": N, "last_used": "ISO8601Z", "confidence": 1.0,
       "variants": [                    # context-specific translations
         {"translation": "...", "speaker": "...", "target": "...",
          "scene": "...", "file": "...", "line": N,
          "count": N, "last_used": "ISO8601Z",
          "confidence": 1.0, "context_hash": null}
       ]}}}

v1 files ({"<source>": {"translation": "...", ...}}) migrate transparently on
load: the old translation becomes default_translation, variants start empty.

Lookup is deterministic (no AI, no fuzzy logic): a context's speaker/target/scene
score variants (+100/+50/+25); the highest score wins (ties broken by count, then
recency, then insertion order); a missing speaker or no match falls back to the
default. `file` is metadata only and never drives selection.

CLI (no `ftp` dispatcher exists; runs like the sibling scripts):
  python translation_memory.py stats  --profile profile.json
  python translation_memory.py export --profile profile.json --out tm.csv
  python translation_memory.py import --profile profile.json --in  tm.csv
  python translation_memory.py clean  --profile profile.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from validation import write_text_atomic

VERSION = 2

# Variant scoring weights (deterministic context selection — spec §"Lookup").
SCORE_SPEAKER = 100
SCORE_TARGET = 50
SCORE_SCENE = 25

# Context fields that, when present, justify creating a variant. `line` is
# recorded on a variant as metadata but does not by itself trigger one, and
# `file` is stored but never scored.
_VARIANT_TRIGGER_FIELDS = ("speaker", "target", "scene", "file")


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class TranslationContext:
    """Context passed into lookup()/add() for deterministic variant selection.

    All fields optional; a None (or all-empty) context behaves like the
    context-free path (default translation). `target` is reserved for the future
    Relationship Dictionary and is honored by scoring but not populated by the
    v1.3 engine. `file`/`line` are metadata only — never used for selection.
    """
    speaker: str | None = None
    target: str | None = None
    scene: str | None = None
    file: str | None = None
    line: int | None = None

    def has_variant_fields(self):
        """True if any field that warrants a variant is set (excludes line)."""
        return any(getattr(self, f) not in (None, "") for f in _VARIANT_TRIGGER_FIELDS)


def normalize_key(s):
    """Lookup key for normalized matching (never mutates the stored source).

    Collapses any run of real whitespace (spaces, tabs, CR/LF) to one space and
    trims the ends, so "Hello.", " Hello. ", "Hello.\\r\\n" and "Hello.  " all
    resolve to one entry. Case is preserved (case-sensitive per spec §2), and
    punctuation, [vars], {tags} and \\escapes are untouched: Ren'Py carries
    escapes as the two literal characters backslash+n, not a real newline, so
    \\s does not see them.
    """
    return re.sub(r"\s+", " ", s).strip()


def load_profile(path):
    """Read profile.json; return (profile, profile_dir). Mirrors the sibling
    scripts (kept local to avoid importing translate_api, which imports us)."""
    profile_path = Path(path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return profile, profile_path.parent


def resolve_tm_path(profile, base):
    """TM file path from profile, defaulting to <base>/.ftp/translation_memory.json.
    A relative profile tm.path is resolved against the profile directory."""
    tm_cfg = profile.get("tm") or {}
    p = tm_cfg.get("path")
    if p:
        p = Path(p)
        return p if p.is_absolute() else base / p
    return base / ".ftp" / "translation_memory.json"


def tm_enabled(profile):
    """TM is on unless explicitly disabled via profile tm.enabled = false."""
    return (profile.get("tm") or {}).get("enabled", True)


def _normalize_variant(v, now):
    """Fill forward-compat defaults on a variant dict (in place) and return it."""
    v.setdefault("count", 0)
    v.setdefault("last_used", now)
    if v.get("confidence") is None:
        v["confidence"] = 1.0
    if "context_hash" not in v:
        v["context_hash"] = None
    return v


def _migrate_entry(entry, now):
    """Return a v2 entry dict for any accepted entry shape, or None to skip.

    - v2 ({default_translation}/{variants}): normalize defaults in place.
    - v1 ({translation, count?, last_used?, ...}): convert — the old translation
      becomes default_translation, old context fields are dropped to the default
      (spec: migration is literal; the source still retrieves correctly), and
      variants start empty.
    """
    if not isinstance(entry, dict):
        return None
    if "default_translation" in entry or "variants" in entry:
        entry.setdefault("default_translation", None)
        entry.setdefault("count", 0)
        entry.setdefault("last_used", now)
        if entry.get("confidence") is None:
            entry["confidence"] = 1.0
        variants = entry.get("variants")
        entry["variants"] = [_normalize_variant(v, now)
                             for v in variants if isinstance(v, dict)] \
            if isinstance(variants, list) else []
        return entry if entry["default_translation"] is not None or entry["variants"] else None
    if "translation" in entry:  # v1 -> v2
        return {
            "default_translation": entry["translation"],
            "count": entry.get("count", 0),
            "last_used": entry.get("last_used", now),
            "confidence": 1.0,
            "variants": [],
        }
    return None


class TranslationMemory:
    """In-memory cache over the TM JSON. Load once, mutate the cache, save
    atomically. The engine imports this class and never opens the file itself."""

    def __init__(self, path, source_language="en", target_language="th"):
        self.path = Path(path)
        self.source_language = source_language
        self.target_language = target_language
        self.entries = {}        # exact source text -> entry dict (v2 shape)
        self._norm_index = {}     # normalize_key(source) -> exact source key

    # ---- persistence ----------------------------------------------------

    def load(self):
        """Read the TM into memory, migrating v1 -> v2 transparently. Tolerates a
        missing or corrupt file by starting empty (never crashes a run on a bad
        cache)."""
        self.entries = {}
        data = None
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                data = None
        if isinstance(data, dict):
            self.source_language = data.get("source_language", self.source_language)
            self.target_language = data.get("target_language", self.target_language)
            entries = data.get("entries")
            if isinstance(entries, dict):
                now = _now_iso()
                for src, entry in entries.items():
                    migrated = _migrate_entry(entry, now)
                    if migrated is not None:
                        self.entries[src] = migrated
        self._rebuild_index()
        return self

    def _rebuild_index(self):
        self._norm_index = {}
        for src in self.entries:
            self._norm_index.setdefault(normalize_key(src), src)

    def to_dict(self):
        return {
            "version": VERSION,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "entries": self.entries,
        }

    def save(self):
        """Atomic write (temp file in the same dir + os.replace) so an
        interrupted run can never leave a half-written or empty TM."""
        write_text_atomic(self.path,
                          json.dumps(self.to_dict(), ensure_ascii=False, indent=2))

    # ---- lookup / add ---------------------------------------------------

    def _find_entry(self, source):
        """Exact match, else normalized match, else None."""
        entry = self.entries.get(source)
        if entry is None:
            key = self._norm_index.get(normalize_key(source))
            if key is not None:
                entry = self.entries.get(key)
        return entry

    @staticmethod
    def _score(variant, context):
        """Additive context score (spec normative pseudocode). A field "matches"
        only when the context field is set and equal to the variant's. `file` is
        never scored."""
        s = 0
        if context.speaker is not None and variant.get("speaker") == context.speaker:
            s += SCORE_SPEAKER
        if context.target is not None and variant.get("target") == context.target:
            s += SCORE_TARGET
        if context.scene is not None and variant.get("scene") == context.scene:
            s += SCORE_SCENE
        return s

    def _default_hit(self, entry):
        """Bump + return the entry's default translation, or None if absent."""
        dt = entry.get("default_translation")
        if dt is None:
            return None
        entry["count"] = entry.get("count", 0) + 1
        entry["last_used"] = _now_iso()
        return {"translation": dt, "hit_type": "default"}

    def lookup(self, source, context=None):
        """Return a hit dict ({"translation", "hit_type": "context"|"default"})
        for an exact-or-normalized source match, else None (miss).

        Selection is deterministic:
          1. No entry -> None.
          2. No context, or context.speaker is None -> default_translation
             (an extraction miss must never pick an arbitrary variant).
          3. Otherwise score every variant (+100 speaker / +50 target /
             +25 scene); pick the highest (ties: count, then last_used, then
             insertion order); score 0 -> default_translation.
        The matched variant's (or the entry's) count/last_used is bumped.

        Callers MUST still validate token preservation against THIS source — a
        normalized hit's stored translation carries the original entry's
        [vars]/{tags}, which may differ (see translate_api.token_signature)."""
        entry = self._find_entry(source)
        if entry is None:
            return None

        variants = entry.get("variants") or []
        if context is None or context.speaker is None or not variants:
            return self._default_hit(entry)

        idx, best = max(
            enumerate(variants),
            key=lambda iv: (self._score(iv[1], context), iv[1].get("count", 0),
                            iv[1].get("last_used", ""), -iv[0]),
        )
        # A speaker match is a prerequisite for any variant hit (spec §3 +
        # the speaker-anchored priority tiers): target/scene only differentiate
        # AMONG speaker-matching variants. Without this gate a target/scene
        # coincidence on a WRONG speaker could outscore the default — exactly the
        # silent miscontextualization this feature exists to prevent (inert in
        # v1.3, where only speaker is ever set, but live once v1.5 fills target).
        # Since any speaker match scores >= SCORE_SPEAKER and a non-match <=
        # SCORE_TARGET + SCORE_SCENE, the top-ranked variant is speaker-matching
        # iff any speaker-matching variant exists.
        if best.get("speaker") != context.speaker:
            return self._default_hit(entry)

        best["count"] = best.get("count", 0) + 1
        best["last_used"] = _now_iso()
        return {"translation": best["translation"], "hit_type": "context", "variant": best}

    def lookup_fuzzy(self, source, threshold=0.9):
        """Similarity matching — deferred to v2 (returns None now).

        A future version will use difflib.SequenceMatcher by default (optional
        rapidfuzz), gate every hit on an identical token_signature, and
        auto-accept above a threshold with a written review log (no interactive
        prompt, which would break the batched/headless pipeline)."""
        return None

    def _make_variant(self, translation, context, now):
        return {
            "translation": translation,
            "speaker": context.speaker,
            "target": context.target,
            "scene": context.scene,
            "file": context.file,
            "line": context.line,
            "count": 1,
            "last_used": now,
            "confidence": 1.0,
            "context_hash": None,
        }

    def add(self, source, translation, context=None):
        """Upsert source -> translation.

        - New entry: default_translation = translation (first approved wins);
          if context carries speaker/target/scene/file, also seed one variant.
        - Existing entry, no usable context: DO NOT overwrite the default —
          bump the entry count/last_used only (spec amendment 4).
        - Existing entry, with context: if a variant already matches
          (translation, speaker, target, scene) bump its count only; otherwise
          append a new variant. Never touches default_translation.
        """
        now = _now_iso()
        has_ctx = context is not None and context.has_variant_fields()
        entry = self.entries.get(source)

        if entry is None:
            entry = {"default_translation": translation, "count": 0,
                     "last_used": now, "confidence": 1.0, "variants": []}
            self.entries[source] = entry
            self._norm_index.setdefault(normalize_key(source), source)
            if has_ctx:
                entry["variants"].append(self._make_variant(translation, context, now))
            return entry

        if not has_ctx:
            # First approved translation wins: never silently overwrite.
            if entry.get("default_translation") is None:
                entry["default_translation"] = translation
            entry["count"] = entry.get("count", 0) + 1
            entry["last_used"] = now
            return entry

        variants = entry.setdefault("variants", [])
        for v in variants:
            if (v.get("translation") == translation
                    and v.get("speaker") == context.speaker
                    and v.get("target") == context.target
                    and v.get("scene") == context.scene):
                v["count"] = v.get("count", 0) + 1
                v["last_used"] = now
                return entry
        variants.append(self._make_variant(translation, context, now))
        if entry.get("default_translation") is None:
            entry["default_translation"] = translation
        return entry

    # ---- bulk ops -------------------------------------------------------

    def import_progress(self, progress):
        """Seed/merge from a {english: translation} progress dict (the existing
        translations.json format). Only adds sources not already present.
        Returns the number added."""
        added = 0
        for src, tr in progress.items():
            if isinstance(src, str) and isinstance(tr, str) and src not in self.entries:
                self.add(src, tr)
                added += 1
        return added

    def stats(self):
        try:
            size = self.path.stat().st_size if self.path.exists() else 0
        except OSError:
            size = 0
        total_variants = 0
        total_uses = 0
        for e in self.entries.values():
            total_uses += e.get("count", 0)
            for v in e.get("variants") or []:
                total_variants += 1
                total_uses += v.get("count", 0)
        return {
            "total_entries": len(self.entries),
            "total_variants": total_variants,
            "file_size_bytes": size,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "total_uses": total_uses,
        }

    def export_csv(self, path):
        """Export the default (context-free) translations. Variant-aware CSV is a
        future feature — this flattens each entry to its default_translation."""
        path = Path(path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["source", "translation", "count", "last_used"])
            for src, e in self.entries.items():
                w.writerow([src, e.get("default_translation", ""),
                            e.get("count", 0), e.get("last_used", "")])
        return len(self.entries)

    def import_csv(self, path):
        """Merge a CSV (source,translation,count,last_used) into default
        translations. For existing keys, keep the higher count / newer timestamp.
        Returns (added, updated)."""
        added = updated = 0
        with Path(path).open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                src = row.get("source")
                tr = row.get("translation")
                if not src or tr is None:
                    continue
                try:
                    count = int(row.get("count") or 0)
                except (ValueError, TypeError):
                    count = 0
                last_used = row.get("last_used") or _now_iso()
                existing = self.entries.get(src)
                if existing is None:
                    self.entries[src] = {"default_translation": tr,
                                         "count": count or 1, "last_used": last_used,
                                         "confidence": 1.0, "variants": []}
                    self._norm_index.setdefault(normalize_key(src), src)
                    added += 1
                elif (count > existing.get("count", 0)
                      or last_used > existing.get("last_used", "")):
                    existing["default_translation"] = tr
                    existing["count"] = max(count, existing.get("count", 0))
                    existing["last_used"] = max(last_used, existing.get("last_used", ""))
                    updated += 1
        return added, updated

    def clean(self):
        """Drop empty/whitespace-only sources or empty default translations, and
        collapse entries that share a normalized key AND default translation
        (keeping the higher-count one). Returns the number of entries removed."""
        removed = 0
        for src in list(self.entries):
            tr = self.entries[src].get("default_translation", "")
            if not src.strip() or not str(tr or "").strip():
                del self.entries[src]
                removed += 1
        seen = {}  # (normalized source, default translation) -> kept source key
        for src in list(self.entries):
            entry = self.entries[src]
            sig = (normalize_key(src), entry.get("default_translation", ""))
            kept = seen.get(sig)
            if kept is None:
                seen[sig] = src
            elif entry.get("count", 0) > self.entries[kept].get("count", 0):
                del self.entries[kept]
                seen[sig] = src
                removed += 1
            else:
                del self.entries[src]
                removed += 1
        self._rebuild_index()
        return removed


def open_tm(profile, base):
    """Construct and load the profile's TM."""
    tm = TranslationMemory(
        resolve_tm_path(profile, base),
        source_language=profile.get("source_language", "en"),
        target_language=profile.get("language_id", profile.get("target_language", "th")),
    )
    tm.load()
    return tm


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", required=True, help="profile.json")

    ap = argparse.ArgumentParser(description="Translation Memory tool (ftp tm)")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("stats", parents=[common], help="show TM size and usage")
    p_exp = sub.add_parser("export", parents=[common], help="export TM to CSV")
    p_exp.add_argument("--out", required=True, help="output CSV path")
    p_imp = sub.add_parser("import", parents=[common], help="merge a CSV into the TM")
    p_imp.add_argument("--in", dest="infile", required=True, help="input CSV path")
    sub.add_parser("clean", parents=[common], help="remove empty/duplicate entries")
    args = ap.parse_args()

    profile, base = load_profile(args.profile)
    tm = open_tm(profile, base)

    if args.action == "stats":
        s = tm.stats()
        print("Translation Memory")
        print("------------------")
        print(f"Path:        {tm.path}")
        print(f"Languages:   {s['source_language']} -> {s['target_language']}")
        print(f"Entries:     {s['total_entries']}")
        print(f"Variants:    {s['total_variants']}")
        print(f"Total uses:  {s['total_uses']}")
        print(f"File size:   {s['file_size_bytes']} bytes")
    elif args.action == "export":
        n = tm.export_csv(args.out)
        print(f"Exported {n} entries to {args.out}")
    elif args.action == "import":
        added, updated = tm.import_csv(args.infile)
        tm.save()
        print(f"Imported: {added} added, {updated} updated. Total entries: {len(tm.entries)}")
    elif args.action == "clean":
        removed = tm.clean()
        tm.save()
        print(f"Removed {removed} entries. Total entries: {len(tm.entries)}")


if __name__ == "__main__":
    main()
