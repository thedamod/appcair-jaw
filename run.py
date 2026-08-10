#!/usr/bin/env python3
import argparse, csv, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import answer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    t0 = time.perf_counter()
    qs = json.load(open(a.questions))
    qlist = qs["questions"] if isinstance(qs, dict) else qs
    rows = []
    for q in qlist:
        qid, text = q["qid"], q["question"]
        ans = answer.answer(text)
        rows.append((qid, ans))
        if a.debug:
            print(qid, text[:70], "=>", ans)
    with open(a.out, "w", newline="") as fh:
        out = csv.writer(fh)
        out.writerow(["question_id", "answer"])
        out.writerows(rows)
    nans = sum(1 for _, x in rows if x is not None)
    print(f"wrote {len(rows)} answers to {a.out} ({nans} non-null)")
    print(f"answered {len(rows)} questions in {time.perf_counter() - t0:.3f}s "
          f"({(time.perf_counter() - t0) / max(len(rows), 1) * 1000:.1f} ms/question)")


if __name__ == "__main__":
    main()
