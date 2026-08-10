import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pipeline as P

DOC_TYPES = {
    "completion_certificate": P._DOC_TYPES["completion_certificate"],
    "company_completion_certificate": P._DOC_TYPES["company_completion_certificate"],
    "reference_letter": P._DOC_TYPES["reference_letter"],
}


def known_labels(doc_type):
    return set(DOC_TYPES[doc_type]["label_to_field"].keys())


def label_inventory(doc_type):
    counts = collections.Counter()
    examples = collections.defaultdict(list)
    for f in glob.glob(os.path.join(P.DOCS, doc_type, "*.pdf")):
        txt = P.doc_text(f)
        for label, value in P.extract_table_pairs(txt):
            key = label.lower().rstrip(":")
            counts[key] += 1
            if len(examples[key]) < 3:
                examples[key].append(value[:60])
    return counts, examples


def coverage():
    total_docs = 0
    for dt in DOC_TYPES:
        files = glob.glob(os.path.join(P.DOCS, dt, "*.pdf"))
        total_docs += len(files)
        known = known_labels(dt)
        counts, examples = label_inventory(dt)
        unknown = {k: c for k, c in counts.items() if k not in known}
        matched = sum(c for k, c in counts.items() if k in known)
        print(f"\n{doc_type_label(dt)}  ({len(files)} docs, {len(counts)} distinct labels)")
        print(f"  known: {sum(1 for k in counts if k in known)} labels "
              f"({matched} pair hits) | unmapped: {len(unknown)} labels")
        for k, c in sorted(unknown.items(), key=lambda x: -x[1]):
            print(f"    UNMAPPED x{c:3d}  {k!r:48s} e.g. {examples[k][0]!r}")
    print(f"\nTOTAL DOCS: {total_docs}")


def doc_type_label(dt):
    return dt.replace("_", " ").title()


def guess_field(label):
    l = label.lower()
    money = any(t in l for t in ("amount", "value", "cost", "price", "fee",
                                 "payment", "sanctioned", "expenditure", "rate"))
    if money:
        return "value" if "work" in l or "contract" in l else "value"
    if "date" in l:
        return "date"
    if "manager" in l or "engineer" in l or "pm" == l:
        return "pm"
    if "name" in l or "client" in l or "department" in l:
        return "client"
    if "grade" in l or "quality" in l or "inspection" in l:
        return "grade"
    return None


def emit_config(min_count):
    out = {}
    for dt in DOC_TYPES:
        known = known_labels(dt)
        counts, examples = label_inventory(dt)
        labels = []
        for k, c in sorted(counts.items(), key=lambda x: -x[1]):
            if c < min_count or k in known:
                continue
            field = guess_field(k)
            labels.append({"label": examples[k][0] if examples[k] else k,
                           "field": field or "text"})
        if labels:
            out[dt] = labels
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-config", action="store_true")
    ap.add_argument("--min-count", type=int, default=1)
    args = ap.parse_args()
    if args.emit_config:
        emit_config(args.min_count)
    else:
        coverage()
