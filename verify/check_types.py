#!/usr/bin/env python3
"""Type gate: every answer in the submission CSV must be consistent with its
declared answer_type (percent in [0,100], days/count plausible integers,
money non-negative unless the question signals a signed mean-median).
"""
import argparse, csv, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOL = ROOT

_SIGNED_HINTS = re.compile(r"negative if (?:the )?(?:mean|average)", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("submission", help="CSV with question_id,answer")
    ap.add_argument("--questions", default=os.path.join(ROOT, "BITS-Hackathon-Dataset", "questions.json"))
    a = ap.parse_args()

    qs = json.load(open(a.questions))
    qs = qs["questions"] if isinstance(qs, dict) else qs
    types = {q["qid"]: q.get("answer_type") for q in qs}
    text = {q["qid"]: q.get("question", "") for q in qs}

    rows = list(csv.DictReader(open(a.submission)))
    bad = []
    for r in rows:
        qid, raw = r["question_id"].strip(), (r.get("answer") or "").strip()
        t = types.get(qid)
        if not raw or t is None:
            continue
        try:
            f = float(raw)
        except ValueError:
            bad.append((qid, t, raw, "not a number"))
            continue
        if t == "percent":
            if not (0 <= f <= 100):
                bad.append((qid, t, raw, "percent outside [0,100]"))
        elif t == "days":
            if not (0 <= f <= 30000 and f == int(f)):
                bad.append((qid, t, raw, "days not a plausible integer"))
        elif t == "count":
            if not (0 <= f <= 200 and f == int(f)):
                bad.append((qid, t, raw, "count not a plausible integer"))
        elif t == "money":
            if f < 0 and not _SIGNED_HINTS.search(text.get(qid, "")):
                bad.append((qid, t, raw, "negative money (not a signed mean-median)"))

    if bad:
        print(f"TYPE GATE FAILED ({len(bad)} inconsistent answers):")
        for qid, t, raw, why in bad:
            print(f"  {qid} [{t}] answered={raw} — {why}")
        return 1
    print(f"TYPE GATE OK: all {len(rows)} answers consistent with declared types")
    return 0


if __name__ == "__main__":
    sys.exit(main())
