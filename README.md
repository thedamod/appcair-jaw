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
