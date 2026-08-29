"""Addressee resolution: which character is a line spoken *to*.

v1.4 shipped the declaration half of relationships — `speakers[code].to` holds
(speaker, addressee) -> pronoun/register overrides, and the whole table is shown
to the translator. What was missing is *resolution*: knowing which row of that
table applies to a given line. Until something answers that, no tool can act on
a declared relationship; the Contextual TM's reserved `target` slot (ADR-006)
stays empty and QA can only approximate the addressee by proximity.

This module answers it, or refuses to. Refusal is the feature: a wrong
addressee produces a wrong pronoun on a line that otherwise looks fine — wrong
silently and everywhere — which is exactly why ADR-018 declined to infer it.
So every answer carries the tier of evidence it came from, and a project can
require more evidence than the default:

    declared  — a scope in profile "relationships"."declared" names the pair.
                Human-authored; as certain as the profile itself.
    vocative  — the English source addresses someone by name in vocative
                position ("Hey, Maya." / "Maya, look at this."). A bare mention
                ("I saw Maya yesterday") is NOT vocative and does not resolve.
                Note this tier can essentially never resolve *to the
                protagonist*: most Ren'Py games render their name as a
                `[variable]`, which is stripped before matching, and a
                player-chosen name cannot be listed in `called` anyway. The
                most common addressee in the game is the one it cannot see,
                which is a large part of why the dyad tier exists.
    dyad      — the enclosing Ren'Py label has exactly two character speakers,
                so a line by one is addressed to the other. The cast comes from
                the extractor's `label_cast` field, never from counting who
                still speaks in the corpus: extraction deduplicates by text, and
                a minor character whose only line in a scene is "Yeah." loses it
                to an earlier duplicate. Counting survivors would turn that
                three-party scene into an apparent two-party one — the one
                direction the error can go, and the dangerous one.

Nothing else resolves. In particular there is no sliding-window "who spoke
nearby" tier: in a three-party scene a window that happens to catch two people
yields a confident-looking wrong answer, which is the rejected heuristic
ADR-018 named. A label boundary is extracted, not inferred, and the dyad test
runs over the *entire* label, so a third speaker anywhere in it refuses the
whole label rather than mis-resolving part of it.

Consequences of that strictness, stated plainly:
  - strings.json files extracted before v1.5 carry no `label`/`label_cast`, so
    the dyad tier is unavailable until re-extraction. The resolver degrades to
    *unresolved*, never to a guess.
  - inner monologue ("(...)"), narration, menus and screen text never resolve;
    they have no addressee to get wrong.
  - the dyad tier's real precondition is "exactly two characters are *present*",
    and what it can observe is "exactly two characters *speak*". A third person
    who is in the scene but silent is invisible to it, exactly as a third person
    dropped by dedupe would be. `declared` scopes exist for both cases; knowing
    who is present across a scene is Context Summarization (v3.1).

Usage as a library:

    resolver = build_resolver(profile, strings)
    target = resolver.target_for(entry)      # canonical code, or None

`target_for` applies the min-confidence gate; `resolve` returns the full
finding (tier + reason + conflict) for reports.

Usage as a report — the acceptance mechanism for the whole feature, since this
repo ships no game text to measure coverage against:

    python relationships.py --profile profile.json
    python relationships.py --profile profile.json --report addressees.txt
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from characters import (
    PSEUDO_SPEAKERS, display_name, is_character, is_monologue, resolve_alias,
)
from validation import configure_console, write_text_atomic

configure_console()

# Evidence tiers, ordered least to most certain. A project raises the bar with
# profile "relationships"."min_confidence".
TIERS = ("dyad", "vocative", "declared")
TIER_RANK = {tier: rank for rank, tier in enumerate(TIERS)}
DEFAULT_MIN_CONFIDENCE = "dyad"

# Why a line did not resolve. Reported, never silently swallowed.
REASONS = {
    "disabled": "resolution is off for this profile",
    "pseudo": "narration, menu or screen text — no addressee",
    "monologue": "inner monologue (...) — addressed to no one",
    "no-label": "line has no enclosing label (re-extract to enable the dyad tier)",
    "no-cast": "the corpus does not state who speaks in this label — re-extract",
    "cast-mismatch": "this speaker is not in the label's stated cast",
    "multi-party": "the label has three or more character speakers",
    "solo": "the label has only this speaker",
    "multi-vocative": "more than one character is addressed by name",
    "below-threshold": "resolved, but under the profile's min_confidence",
}

# A name counts as vocative only when set off by punctuation (or a string
# boundary) on BOTH sides. "Hey, Maya." resolves; "I saw Maya yesterday" is a
# mention of a third party, which is a different translation problem entirely.
_VOCATIVE_EDGE = ",.!?;:-—–\"'“”‘’()"
_TAG_VAR_RE = re.compile(r"\[[^\]]*\]|\{[^}]*\}")


@dataclass
class Addressee:
    """One resolution finding. `code` is None when nothing resolved."""
    code: str | None = None
    tier: str | None = None
    reason: str = ""
    conflict: bool = False          # vocative and dyad disagreed
    alternatives: dict = field(default_factory=dict)   # tier -> code

    def __bool__(self):
        return self.code is not None


def relationships_config(profile):
    """The `relationships` block, with defaults filled in.

    `enabled` defaults to whether the profile declares any relationship data at
    all — a `to` map on some character, or an explicit `declared` scope list.
    A profile that never mentions relationships therefore behaves exactly as it
    did in v1.4: nothing is resolved, no `target` reaches the TM, and the
    translation prompt is unchanged.
    """
    cfg = dict(profile.get("relationships") or {})
    speakers = profile.get("speakers") or {}
    declares_to = any(isinstance(rec, dict) and rec.get("to")
                      for rec in speakers.values())
    if "enabled" not in cfg:
        cfg["enabled"] = bool(declares_to or cfg.get("declared"))
    cfg.setdefault("min_confidence", DEFAULT_MIN_CONFIDENCE)
    if cfg["min_confidence"] not in TIER_RANK:
        cfg["min_confidence"] = DEFAULT_MIN_CONFIDENCE
    cfg.setdefault("declared", [])
    return cfg


def _strip_markup(text):
    """Drop [variables] and {tags} so their punctuation can't fake a vocative
    edge — and so a name inside a tag argument is never read as an address."""
    return _TAG_VAR_RE.sub(" ", text)


class AddresseeResolver:
    """Resolves the addressee of a line, or declines to.

    Construction is O(strings): one pass to learn each label's cast. Resolution
    is then O(1) per line apart from vocative scanning, which is O(names).
    """

    def __init__(self, speakers, strings, config=None, source_language="en"):
        self.speakers = speakers or {}
        self.config = config if isinstance(config, dict) else {}
        self.enabled = bool(self.config.get("enabled", True))
        self.min_confidence = self.config.get("min_confidence", DEFAULT_MIN_CONFIDENCE)
        if self.min_confidence not in TIER_RANK:
            self.min_confidence = DEFAULT_MIN_CONFIDENCE
        self.source_language = source_language

        self.label_cast = {}                 # (file, label) -> canonical codes
        self.unlabeled_lines = 0
        self.unknown_speakers = Counter()    # codes absent from the profile
        self._index_strings(strings or [])
        self.labels_seen = len(self.label_cast)

        self.declared = [s for s in (self.config.get("declared") or [])
                         if isinstance(s, dict)]
        # Vocative matching reads the English source. It is the one tier that
        # assumes a source language; a non-English source loses the tier rather
        # than resolving on patterns that do not apply to it.
        self.vocatives = self._build_vocatives() if source_language == "en" else {}

    # ---- indexing -------------------------------------------------------

    def _index_strings(self, strings):
        """Index each label's cast **as the extractor stated it**.

        Deliberately not `add(speaker)` per line: that would count who survived
        deduplication, which under-counts and therefore over-resolves.
        """
        for entry in strings:
            code = entry.get("speaker")
            if code and code not in self.speakers and code not in PSEUDO_SPEAKERS:
                self.unknown_speakers[code] += 1
            if not self._is_character(code):
                continue
            label = entry.get("label")
            if not label:
                self.unlabeled_lines += 1
                continue
            cast = entry.get("label_cast")
            if not cast:
                continue
            self.label_cast.setdefault(
                (entry.get("file"), label),
                {self._canon(c) for c in cast if self._is_character(c)})

    def _build_vocatives(self):
        """Name -> canonical code, for every name a character can be called by.

        Sources: the record's `name`, the names of codes that alias it, and an
        optional `called` list for nicknames the script uses in dialog. A name
        claimed by two characters is dropped: an ambiguous name is no evidence.
        """
        owners = defaultdict(set)
        for code, record in self.speakers.items():
            if not isinstance(record, dict) or code in PSEUDO_SPEAKERS:
                continue
            canonical = self._canon(code)
            for name in [record.get("name")] + list(record.get("called") or []):
                if isinstance(name, str) and len(name.strip()) > 1:
                    owners[name.strip()].add(canonical)
        return {name: next(iter(codes)) for name, codes in owners.items()
                if len(codes) == 1}

    # ---- helpers --------------------------------------------------------

    def _canon(self, code):
        return resolve_alias(self.speakers, code)

    def _is_character(self, code):
        return bool(code) and is_character(self.speakers, code)

    def label_party(self, entry):
        """Canonical character codes speaking in this line's label, or None.

        None means the corpus never stated the cast — not that the scene is
        empty. The two are reported differently.
        """
        label = entry.get("label")
        if not label:
            return None
        return self.label_cast.get((entry.get("file"), label))

    # ---- tiers ----------------------------------------------------------

    def _declared(self, entry, speaker):
        """First matching declared scope wins; scopes are checked in order.

        A scope constrains on any of `file`, `label`, and `lines` [first, last]
        (inclusive), and names the pair with either `pairs` (speaker code ->
        addressee code) or `cast` (exactly two codes, read as a dyad).
        """
        for scope in self.declared:
            if scope.get("file") and scope["file"] != entry.get("file"):
                continue
            if scope.get("label") and scope["label"] != entry.get("label"):
                continue
            lines = scope.get("lines")
            if isinstance(lines, (list, tuple)) and len(lines) == 2:
                line = entry.get("line")
                if line is None or not (lines[0] <= line <= lines[1]):
                    continue
            pairs = scope.get("pairs")
            if isinstance(pairs, dict):
                target = None
                for from_code, to_code in pairs.items():
                    if self._canon(from_code) == speaker:
                        target = to_code
                        break
                if target:
                    return self._canon(target)
                continue
            cast = scope.get("cast")
            if isinstance(cast, (list, tuple)) and len(cast) == 2:
                canonical = [self._canon(c) for c in cast]
                if speaker in canonical:
                    return canonical[1] if canonical[0] == speaker else canonical[0]
        return None

    def _vocative(self, entry, speaker):
        """(code, reason) — a name addressed in vocative position, or (None, r).

        Returns the reason "multi-vocative" when two different characters are
        addressed in one line: two addressees is not one addressee, and picking
        either would be the silent guess this module refuses to make.
        """
        if not self.vocatives:
            return None, ""
        text = _strip_markup(entry.get("text") or "")
        found = set()
        for name, code in self.vocatives.items():
            if code == speaker:
                continue          # self-address is not an addressee
            if self._is_vocative(text, name):
                found.add(code)
        if len(found) == 1:
            return found.pop(), ""
        return None, ("multi-vocative" if found else "")

    @staticmethod
    def _is_vocative(text, name):
        pattern = r"(?<![^\W\d_])" + re.escape(name) + r"(?![^\W\d_])"
        for match in re.finditer(pattern, text):
            before = text[:match.start()].rstrip()
            after = text[match.end():].lstrip()
            left_ok = not before or before[-1] in _VOCATIVE_EDGE
            right_ok = not after or after[0] in _VOCATIVE_EDGE
            if left_ok and right_ok:
                return True
        return False

    def _dyad(self, entry, speaker):
        """(code, reason) — the other half of a two-character label."""
        party = self.label_party(entry)
        if party is None:
            return None, ("no-cast" if entry.get("label") else "no-label")
        if speaker not in party:
            # The stated cast disagrees with the line in front of us. Refuse
            # rather than pick from a cast that evidently is not this scene's.
            return None, "cast-mismatch"
        if len(party) == 1:
            return None, "solo"
        if len(party) > 2:
            return None, "multi-party"
        return next(c for c in party if c != speaker), ""

    # ---- resolution -----------------------------------------------------

    def resolve(self, entry):
        """The full finding for one strings.json entry (never raises)."""
        if not self.enabled:
            return Addressee(reason="disabled")

        code = entry.get("speaker")
        if not self._is_character(code):
            return Addressee(reason="pseudo")
        if is_monologue(entry.get("text") or ""):
            return Addressee(reason="monologue")

        speaker = self._canon(code)
        alternatives = {}

        declared = self._declared(entry, speaker)
        if declared:
            alternatives["declared"] = declared
        vocative, voc_reason = self._vocative(entry, speaker)
        if vocative:
            alternatives["vocative"] = vocative
        dyad, dyad_reason = self._dyad(entry, speaker)
        if dyad:
            alternatives["dyad"] = dyad

        # Two independent tiers naming different people is worth surfacing even
        # though precedence settles it: a systematic disagreement usually means
        # a declared scope is stale or a label really has a third party in it.
        conflict = bool(vocative and dyad and vocative != dyad)

        for tier in ("declared", "vocative", "dyad"):
            found = alternatives.get(tier)
            if found:
                return Addressee(code=found, tier=tier, conflict=conflict,
                                 alternatives=alternatives)

        return Addressee(reason=voc_reason or dyad_reason or "no-label",
                         alternatives=alternatives)

    def meets_threshold(self, finding):
        return bool(finding.code) and \
            TIER_RANK[finding.tier] >= TIER_RANK[self.min_confidence]

    def target_for(self, entry):
        """The canonical addressee code, or None when the evidence is short of
        the profile's min_confidence. This is what consumers call: everything
        downstream sees either a confident answer or nothing at all."""
        finding = self.resolve(entry)
        return finding.code if self.meets_threshold(finding) else None

    # ---- reporting ------------------------------------------------------

    def audit(self, strings):
        """Resolve every line and return counters for the report."""
        stats = {
            "lines": len(strings),
            "character_lines": 0,
            "tiers": Counter(),
            "reasons": Counter(),
            "pairs": Counter(),
            "conflicts": [],
            "below_threshold": 0,
            "labels": {"total": self.labels_seen, "dyad": 0, "multi": 0, "solo": 0},
            "unlabeled_lines": self.unlabeled_lines,
            "unknown_speakers": self.unknown_speakers,
        }
        for cast in self.label_cast.values():
            if len(cast) == 2:
                stats["labels"]["dyad"] += 1
            elif len(cast) > 2:
                stats["labels"]["multi"] += 1
            else:
                stats["labels"]["solo"] += 1

        for entry in strings:
            if not self._is_character(entry.get("speaker")):
                continue
            stats["character_lines"] += 1
            finding = self.resolve(entry)
            if finding.conflict and len(stats["conflicts"]) < 10:
                stats["conflicts"].append((entry, finding))
            if not finding.code:
                stats["reasons"][finding.reason or "no-label"] += 1
                continue
            if not self.meets_threshold(finding):
                stats["below_threshold"] += 1
                stats["reasons"]["below-threshold"] += 1
                continue
            stats["tiers"][finding.tier] += 1
            stats["pairs"][(self._canon(entry["speaker"]), finding.code)] += 1
        return stats


def load_profile(path):
    profile_path = Path(path)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    return profile, profile_path.parent


def build_resolver(profile, strings):
    """The one construction path every consumer uses, so the enable rule and
    the min-confidence gate cannot drift between the prompt and the QA gate."""
    return AddresseeResolver(
        profile.get("speakers") or {},
        strings,
        relationships_config(profile),
        source_language=profile.get("source_language", "en"),
    )


def format_report(profile, resolver, stats):
    out = io.StringIO()
    sep = "=" * 72

    def emit(line=""):
        out.write(line + "\n")

    speakers = resolver.speakers
    resolved = sum(stats["tiers"].values())
    total = stats["character_lines"]
    pct = (resolved / total * 100) if total else 0.0

    emit("#" * 72)
    emit(f"  ADDRESSEE RESOLUTION — {profile.get('game_name', '?')} -> "
         f"{profile.get('language_name', profile.get('language_id', '?'))}")
    emit(f"  Resolution: {'on' if resolver.enabled else 'OFF'} | "
         f"min_confidence: {resolver.min_confidence}")
    emit("#" * 72)

    emit()
    emit(sep)
    emit(f"  RESOLVED  {resolved}/{total} character lines ({pct:.1f}%)")
    emit(sep)
    for tier in reversed(TIERS):
        emit(f"  {tier:<10} {stats['tiers'].get(tier, 0):6d}")

    emit()
    emit(sep)
    emit(f"  UNRESOLVED  ({total - resolved} lines)")
    emit(sep)
    if not stats["reasons"]:
        emit("  none.")
    for reason, count in stats["reasons"].most_common():
        emit(f"  {reason:<16} {count:6d}   {REASONS.get(reason, '')}")

    labels = stats["labels"]
    emit()
    emit(sep)
    emit("  LABELS")
    emit(sep)
    if not labels["total"]:
        emit("  No label casts in strings.json — re-extract with the current")
        emit("  extract_strings.py to enable the dyad tier.")
    else:
        emit(f"  total {labels['total']}   dyad {labels['dyad']}   "
             f"multi-party {labels['multi']}   solo {labels['solo']}")
    if stats["unlabeled_lines"]:
        emit(f"  {stats['unlabeled_lines']} character line(s) outside any label.")

    emit()
    emit(sep)
    emit("  PAIRS RESOLVED  (declare how each pair speaks in speakers[x].to)")
    emit(sep)
    if not stats["pairs"]:
        emit("  none.")
    top_pairs = stats["pairs"].most_common(25)
    width = max((len(f"{display_name(speakers, s)} -> {display_name(speakers, t)}")
                 for (s, t), _ in top_pairs), default=0)
    for (speaker, target), count in top_pairs:
        record = speakers.get(speaker) or {}
        declared = "declared" if (record.get("to") or {}).get(target) else "NOT DECLARED"
        pair = f"{display_name(speakers, speaker)} -> {display_name(speakers, target)}"
        emit(f"  {pair:<{width}}   {count:5d}   [{declared}]")

    if stats["conflicts"]:
        emit()
        emit(sep)
        emit(f"  CONFLICTS  ({len(stats['conflicts'])} shown — vocative vs dyad)")
        emit(sep)
        for entry, finding in stats["conflicts"]:
            alt = finding.alternatives
            emit(f"  {entry.get('file')}:{entry.get('line')}  spk={entry.get('speaker')}"
                 f"  vocative={alt.get('vocative')}  dyad={alt.get('dyad')}"
                 f"  -> {finding.code} ({finding.tier})")
            emit(f"    EN: {(entry.get('text') or '')[:70]}")

    if stats["unknown_speakers"]:
        emit()
        emit(sep)
        emit(f"  UNKNOWN SPEAKER CODES  ({len(stats['unknown_speakers'])})")
        emit(sep)
        emit("  These codes speak in the script but have no record in the profile,")
        emit("  so they get the generic register instead of a voice. Add them to")
        emit("  `speakers` (or point them at a real character with `alias_of`).")
        for code, count in stats["unknown_speakers"].most_common(30):
            emit(f"  {code:<20} {count:6d} line(s)")

    emit()
    return out.getvalue()


def main():
    ap = argparse.ArgumentParser(
        description="Report addressee resolution coverage for a translation project")
    ap.add_argument("--profile", required=True, help="profile.json")
    ap.add_argument("--strings", help="strings file (overrides profile strings_file)")
    ap.add_argument("--report", help="also write the report to this file")
    args = ap.parse_args()

    profile, base = load_profile(args.profile)
    strings_file = Path(args.strings) if args.strings \
        else base / profile.get("strings_file", "strings.json")
    if not strings_file.is_file():
        sys.exit(f"strings file not found: {strings_file}")
    strings = json.loads(strings_file.read_text(encoding="utf-8"))

    resolver = build_resolver(profile, strings)
    report = format_report(profile, resolver, resolver.audit(strings))
    print(report)
    if args.report:
        write_text_atomic(Path(args.report), report)
        print(f"Report written to {args.report}")


if __name__ == "__main__":
    main()
