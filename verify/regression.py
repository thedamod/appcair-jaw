#!/usr/bin/env python3
"""Regression harness: the five gates that make the submission trustworthy.

1. run.py on the official sample set, scored by the real evaluator (21/21)
2. clean-room KG rebuild (verify_kg.py) matches the pipeline KG field-for-field
3. independent recomputation (verify_verdict2.py) agrees with the submission
   on >=330/333 with zero outright wrong answers
4. type gate (check_types.py) on the outgoing CSV
Exit 0 only if every gate passes.
"""
import os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOL = ROOT
DATASET = os.path.join(ROOT, "BITS-Hackathon-Dataset")

SAMPLES = os.path.join(DATASET, "sample_questions.json")
QUESTIONS = os.path.join(DATASET, "questions.json")
SUBMISSION = os.path.join(SOL, "submission_full.csv")
EVALUATE = os.path.join(DATASET, "evaluate.py")
RUN = os.path.join(SOL, "run.py")

FAILS = []


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        sample_out = tf.name
    r = run(["python3", RUN, "--questions", SAMPLES, "--out", sample_out], cwd=SOL)
    check("run.py answers sample set", r.returncode == 0, r.stderr.strip()[:120])
    r = run(["python3", EVALUATE, "--submission", sample_out, "--questions", SAMPLES], cwd=ROOT)
    total_ok = "TOTAL 21.00 / 21" in r.stdout or "100.00%" in r.stdout
    check("official sample evaluator 21/21", total_ok,
          [ln for ln in r.stdout.splitlines() if "TOTAL" in ln][-1:] or r.stdout.strip()[:120])

    r = run(["python3", os.path.join(HERE, "verify_kg.py")], cwd=HERE)
    check("clean-room KG rebuild matches pipeline KG", r.returncode == 0,
          r.stderr.strip()[:120] or r.stdout.strip().splitlines()[-1:])

    r = run(["python3", os.path.join(HERE, "verify_verdict2.py")], cwd=HERE)
    out = r.stdout
    agree_ok = "AGREE': 330" in out or "AGREE': 331" in out or "AGREE': 332" in out or "AGREE': 333" in out
    zero_wrong = "CSV wrong (0)" in out
    check("reconstruction suite >= 330 AGREE", agree_ok,
          [ln for ln in out.splitlines() if "CSV correct" in ln][-1:] or "")
    check("reconstruction suite 0 wrong", zero_wrong)

    r = run(["python3", os.path.join(HERE, "check_types.py"), SUBMISSION], cwd=SOL)
    check("type gate on outgoing CSV", r.returncode == 0 and "TYPE GATE OK" in r.stdout,
          r.stdout.strip().splitlines()[-1:] or r.stderr.strip()[:120])

    os.unlink(sample_out)
    print()
    if FAILS:
        print(f"REGRESSION FAILED: {len(FAILS)} gate(s) did not pass")
        return 1
    print("REGRESSION OK: all gates pass — safe to submit submission_full.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
