# Terminology Dictionary (v1.6)

Place names, items, in-world jargon, recurring phrases: the vocabulary that must come out the same every time. It lives in `terminology.json` beside `profile.json` (`terminology_file` to rename it). `profile.json` → `keep_untranslated` still works and migrates in as APPROVED `keep` terms; a project with no `terminology.json` behaves exactly as before.

```
python terminology.py sweep     --profile profile.json     # seed DISCOVERED terms from strings.json
python terminology.py add       --profile profile.json "Dark Harbor" --target "..." --priority 10
python terminology.py promote   --profile profile.json "Dark Harbor" [--target T] [--priority N]
python terminology.py preflight --profile profile.json     # run before batch 1; exit 1 on blocking issues
python terminology.py import    --profile profile.json other_glossary.json
```

## A term

```json
{"source": "Dark Harbor", "scope": "transliterate", "target": "...", "stage": "REVIEWED",
 "priority": 10, "forbidden": ["..."], "note": "the port city", "provenance": "human"}
```

`scope` is `translate`, `transliterate`, or `keep` (then `target` is the source itself). `provenance` is `corpus_sweep`, `human`, or `imported`.

## Lifecycle — one step at a time, never automatic

| Stage | Feeds the prompt | Hard-fails QA | `promote` needs |
|---|---|---|---|
| `DISCOVERED` | no | no | a `target` (or scope `keep`) to reach CANDIDATE |
| `CANDIDATE` | no | no | an integer `priority` to reach REVIEWED |
| `REVIEWED` | yes | no | |
| `APPROVED` | yes | no | |
| `ENFORCED` | yes, marked MANDATORY | **yes — category 1** | no unresolved conflict to reach ENFORCED |

Imported terms never arrive above CANDIDATE. `sweep` only ever *adds* DISCOVERED entries; it never rewrites yours.

## How terms match

Exact surface form: word-bounded, case-sensitive, blind to `[vars]` and `{tags}` (so `Rust` never matches inside `Rusty` or `[Rust]`). Longest match wins, left to right ("Dark Rush" beats "Rush"). Two terms with the identical trigger: higher `priority` wins. **Equal priority and different renderings is unresolved**: neither guides the prompt or enforces anything, and preflight names the pair. Nothing is picked by file order.

## Enforcement

An ENFORCED term whose trigger appears in a source line requires its `target` (or the source itself, for `keep`) in the translation and none of its `forbidden` variants. This is the shared validity gate: the bulk translator will not save a violation (it retries once, naming each offending line and the exact form wanted or forbidden: `line 7: "Dark Harbor" must appear as "..."`), a cached TM hit is re-checked on read, and `qa_check.py` reports it as category 1 (`TERM:missing:<term>` / `TERM:forbidden:<term>`), including under `--technical-only`. Below ENFORCED a term never blocks anything.

## Preflight

Prints the count per stage, provenance, every unresolved identical-trigger conflict, invalid terms (missing priority/target), longest-match shadows (informational), and APPROVED terms the gate cannot yet check. It exits 1 only when an ENFORCED term is in conflict or invalid.

## What it does not do

No fuzzy or semantic matching, no synonym learning. The sweep is a plain heuristic (capitalized phrases seen twice, capitalized mid-sentence words seen `--min-count` times); common nouns need a part-of-speech tagger and are not attempted. Review its output before promoting anything.
