# Bid Intelligence over a Document Estate

BITS Pilani × APPCAIR — JAW 2026 Hackathon.

Deterministic, rule-based document intelligence: parses a 687-file synthetic
corporate corpus (678 PDFs + 9 Excel workbooks) into a structured knowledge
graph and answers precise numerical questions. No ML model, no network calls.

**Official evaluator, sample set: 21/21 = 100%.**
Full 333-question submission regenerates in ~0.3 s from cache.

## Layout

| Path | Role |
|---|---|
| `pipeline.py` | PDF + workbook extraction → knowledge graph (config-driven, `config/fields.json`) |
| `answer.py` | Question engine: shape detection → entity resolution → aggregation |
| `run.py` | Runner: questions JSON → submission CSV |
| `verify/` | Clean-room KG rebuild, independent recomputation, type gate, regression harness |
| `cache/` | Serialized knowledge graph / financial facts |
| `submission_full.csv` | 333-question submission |
| `submission_sample_check.csv` | 21-question sample submission (21/21) |

## Setup

```bash
pip install -r requirements.txt
git clone https://github.com/satvikGIKA/BITS-Hackathon-Dataset
```

The dataset directory is expected at the repo root (it is gitignored).

## Usage

```bash
# answer a question set
python3 run.py --questions BITS-Hackathon-Dataset/sample_questions.json --out submission.csv

# score with the official evaluator
python3 BITS-Hackathon-Dataset/evaluate.py --submission submission.csv \
    --questions BITS-Hackathon-Dataset/sample_questions.json
```

## Verification

```bash
python3 verify/regression.py
```

Gates: official sample evaluator 21/21 · clean-room KG rebuild matches the
pipeline KG field-for-field · independent recomputation agrees with
`submission_full.csv` on ≥330/333 with 0 wrong (3 questions are
under-determined from their text) · every answer consistent with its declared
type.

## How it works

```
687 documents                     questions.json
 (678 PDFs + 9 workbooks)              |
        |                              v
        |        +-----------------------------------+
        +------> | pipeline.py   extraction -> KG    |
        |        | config/fields.json drives parsing |
        |        +-----------------+-----------------+
        |                          |
        |                  cache/kg.json, cache/fin.json
        |               (rebuilt only if corpus changes)
        |                          |
        |                          v
        |        +-----------------------------------+
        +------> | answer.py   question engine       |
        |        | detect() -> resolve entities ->   |
        |        | aggregate over the KG             |
        +------> | (fin facts pulled in when asked)  |
                 +-----------------+-----------------+
                                   |
                                   v
                 +-----------------------------------+
                 | run.py  -> submission CSV         |
                 +-----------------------------------+
```

**Three stages, one deterministic path:**

1. **Extract** — `pipeline.py` scans each PDF for `label → value` pairs (both
the stacked and inline layouts), parses every rupee rendering losslessly
(`INR 33.38 Cr` = `33,38,00,000` = `333800000`), pulls prose-only facts with
fallback regexes, and merges the two certificate sides of each work by
normalized quoted work name. The 9 workbooks are reduced to per-sheet totals
and per-client sums (`invoiced`, `received`, `outstanding`).
2. **Index** — the result is a knowledge graph: `works` (155, keyed by work
name), `clients` (canonical name → works), `engineers` (PM → works), `people`
(engineers + credentialed staff). Serialized to `cache/` behind a SHA-256
corpus fingerprint, so it is rebuilt only when the corpus changes.
3. **Answer** — `answer.py` classifies each question into one of ~20 arithmetic
shapes (`detect`), resolves the entities it names (client cascade, work
token-overlap, engineer first-name), and computes the answer as a pure
aggregation over the resolved works.

## Glossary

| Term | Meaning in this codebase |
|---|---|
| **Knowledge graph (KG)** | The extracted world model: `works` records with
`client / value / completion_date / pm / grade / category`, plus inverse
indexes `clients` and `engineers`, plus the `people` set. Everything the
question engine reads; nothing is read from raw documents at answer time. |
| **Entity resolution** | Deciding which real-world thing a question names:
"Jal Nigam, Jharkhand" → one canonical client key; "Asha Nair's PMP work" →
one work key. Done by cascading matchers, not ML. |
| **Canonicalization** | Mapping surface spellings to one key — client names
have their `(…)` suffix stripped, work names are whitespace-normalized,
money is converted to a plain rupee integer. |
| **Merge key** | The normalized work name used to join the two certificate
sides (company-issued and client-issued) of the same work. |
| **Shape detection** | Classifying a question as one of ~20 arithmetic
operations (`count`, `sum`, `mean−median`, `threshold`, `date_span`…), via an
ordered regex cascade. |
| **Aggregation** | The actual arithmetic over the resolved set of works:
sums, counts, max/min, rank gaps, percentages. |
| **Clean-room rebuild** | A second, independently written parser that must
reproduce the KG with zero differences — two parsers agreeing means the KG is
not an artifact of one buggy regex. |
| **Corpus fingerprint** | SHA-256 over every corpus file's path + mtime + size;
the cache is invalidated (and the KG rebuilt) only when it changes. |
| **Under-determined question** | A question whose text does not pin down one
answer (e.g. ambiguous entity reference); the harness flags these `UNRESOLVED`
instead of guessing. |

## Repo hygiene

- Dead code was removed before submission (`anchor_client`, `_target_keys`,
  `answer_role_split`, …); the regression suite is the guarantee nothing
  changed.
- The two caches are committed on purpose: they are the extracted "database",
  and make the full 333-question submission regenerate in ~0.3 s.
- No secrets, no network calls, no model weights — just `pip install
  -r requirements.txt` and the dataset clone.

