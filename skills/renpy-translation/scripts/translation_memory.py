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

Schema:
  {"version": 1, "source_language": "en", "target_language": "th",
   "entries": {"<exact source>": {"translation": "...", "count": N,
                                   "last_used": "ISO8601Z", ...context}}}

CLI (no `ftp` dispatcher exists; runs like the sibling scripts):
  python translation_memory.py stats  --profile profile.json
  python translation_memory.py export --profile profile.json --out tm.csv
  python translation_memory.py import --profile profile.json --in  tm.csv
  python translation_memory.py clean  --profile profile.json
"""
import argparse
import csv
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1

# Context fields stored per entry (spec §7 — kept for future context-aware
# translation; NOT used for matching in v1).
CONTEXT_FIELDS = ("speaker", "scene", "file", "line")


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


class TranslationMemory:
    """In-memory cache over the TM JSON. Load once, mutate the cache, save
    atomically. The engine imports this class and never opens the file itself."""

    def __init__(self, path, source_language="en", target_language="th"):
        self.path = Path(path)
        self.source_language = source_language
        self.target_language = target_language
        self.entries = {}        # exact source text -> entry dict
        self._norm_index = {}     # normalize_key(source) -> exact source key

    # ---- persistence ----------------------------------------------------

    def load(self):
        """Read the TM into memory. Tolerates a missing or corrupt file by
        starting empty (never crashes the translation run on a bad cache)."""
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
                for src, entry in entries.items():
                    if isinstance(entry, dict) and "translation" in entry:
                        self.entries[src] = entry
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ---- lookup / add ---------------------------------------------------

    def lookup(self, source):
        """Return the entry dict for an exact match, else a normalized match,
        else None. Bumps count + last_used on a hit (records reuse).

        Callers MUST still validate token preservation against THIS source
        (a normalized hit's stored translation carries the original entry's
        [vars]/{tags}, which may differ) — see translate_api.token_signature."""
        entry = self.entries.get(source)
        if entry is None:
            key = self._norm_index.get(normalize_key(source))
            if key is not None:
                entry = self.entries.get(key)
        if entry is None:
            return None
        entry["count"] = entry.get("count", 0) + 1
        entry["last_used"] = _now_iso()
        return entry

    def lookup_fuzzy(self, source, threshold=0.9):
        """Similarity matching — deferred to v2 (returns None in v1).

        v2 will use difflib.SequenceMatcher by default (optional rapidfuzz),
        gate every hit on an identical token_signature, and auto-accept above a
        threshold with a written review log (no interactive prompt, which would
        break the batched/headless pipeline)."""
        return None

    def add(self, source, translation, **context):
        """Upsert source -> translation. New entries start at count=1; updates
        refresh translation/last_used and merge any provided context fields."""
        now = _now_iso()
        entry = self.entries.get(source)
        if entry is None:
            entry = {"translation": translation, "count": 1, "last_used": now}
            self.entries[source] = entry
            self._norm_index.setdefault(normalize_key(source), source)
        else:
            entry["translation"] = translation
            entry["last_used"] = now
        for k in CONTEXT_FIELDS:
            v = context.get(k)
            if v is not None and v != "":
                entry[k] = v
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
        return {
            "total_entries": len(self.entries),
            "file_size_bytes": size,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "total_uses": sum(e.get("count", 0) for e in self.entries.values()),
        }

    def export_csv(self, path):
        path = Path(path)
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["source", "translation", "count", "last_used"])
            for src, e in self.entries.items():
                w.writerow([src, e.get("translation", ""),
                            e.get("count", 0), e.get("last_used", "")])
        return len(self.entries)

    def import_csv(self, path):
        """Merge a CSV (source,translation,count,last_used). For existing keys,
        keep the higher count / newer timestamp. Returns (added, updated)."""
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
                    self.entries[src] = {"translation": tr, "count": count or 1,
                                         "last_used": last_used}
                    self._norm_index.setdefault(normalize_key(src), src)
                    added += 1
                elif (count > existing.get("count", 0)
                      or last_used > existing.get("last_used", "")):
                    existing["translation"] = tr
                    existing["count"] = max(count, existing.get("count", 0))
                    existing["last_used"] = max(last_used, existing.get("last_used", ""))
                    updated += 1
        return added, updated

    def clean(self):
        """Drop empty/whitespace-only sources or empty translations, and collapse
        entries that share a normalized key AND translation (keeping the
        higher-count one). Returns the number of entries removed."""
        removed = 0
        for src in list(self.entries):
            tr = self.entries[src].get("translation", "")
            if not src.strip() or not str(tr).strip():
                del self.entries[src]
                removed += 1
        seen = {}  # (normalized source, translation) -> kept source key
        for src in list(self.entries):
            entry = self.entries[src]
            sig = (normalize_key(src), entry.get("translation", ""))
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
