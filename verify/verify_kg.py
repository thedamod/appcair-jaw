#!/usr/bin/env python3
"""Clean-room KG rebuild: a second, independently written parser that rebuilds
the knowledge graph from the corpus and must match the pipeline's cached KG
field-for-field with zero differences. Two parsers agreeing means the KG is
not an artifact of one buggy regex.
"""
import fitz, glob, os, re, json, collections, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "BITS-Hackathon-Dataset", "documents")
KG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "kg.json")

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun",
                                       "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def doc_text(path):
    d = fitz.open(path)
    try:
        return "\n".join(p.get_text() for p in d)
    finally:
        d.close()


def parse_date(t):
    m = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", t)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", t)
    if m and int(m.group(3)) > 2000:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b", t)
    if m:
        return (int(m.group(3)), _MONTHS.get(m.group(1).lower()[:3]), int(m.group(2)))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})[,]?\s+(20\d{2})\b", t)
    if m:
        return (int(m.group(3)), _MONTHS.get(m.group(2).lower()[:3]), int(m.group(1)))
    return None


_UNIT = [("crore", 10_000_000), ("cr", 10_000_000), ("lakh", 100_000), ("lac", 100_000)]


def parse_money(t):
    m = re.search(r"(?:INR|Rs\.?|₹)\s*([\d][\d,]*\.?\d*)\s*(Crore|Cr|Lakh|Lac)?", t, re.I)
    if not m:
        m = re.search(r"([\d][\d,]*)\s*/-?", t)
    if not m:
        return None
    num = m.group(1).replace(",", "")
    mult = 1
    if m.lastindex and m.group(2):
        u = m.group(2).lower()
        mult = dict(_UNIT)[u]
    try:
        return int(round(float(num) * mult))
    except ValueError:
        return None


def label_value(t, label):
    m = re.search(r"(?m)^" + re.escape(label) + r"\s*:?\s*$", t)
    if m:
        rest = t[m.end():]
        for ln in rest.split("\n"):
            s = ln.strip()
            if s:
                return s
    m = re.search(r"(?m)^" + re.escape(label) + r"\s*:\s*(.+)$", t)
    if m:
        return m.group(1).strip()
    return None


def client_canon(raw):
    if not raw:
        return None
    n = re.sub(r"\s*\([^)]*\)\.?$", "", raw.strip())
    return re.sub(r"\s+", " ", n).strip().rstrip(".").strip()


_WORK_QUOTED = re.compile(r"[“\"]([^“\"]*?(?:—|-|–)\s*[A-Za-z ]+?\s*Pkg-?\d+[^“\"]*?)[”\"]", re.S)


def extract_work(t):
    m = _WORK_QUOTED.search(t)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    v = label_value(t, "Name of Work") or label_value(t, "Project Name") or label_value(t, "Work")
    if v and re.search(r"(?i)Pkg", v):
        return v
    return None


_GRADE_RE = [
    (re.compile(r"graded\s+(excellent|very good|good|satisfactory)", re.I), None),
    (re.compile(r"assessed the completed work as (excellent|very good|good|satisfactory)", re.I), None),
    (re.compile(r"(?is)taken over on.{0,40}satisfactory"), "satisfactory"),
]


def parse_grade(t):
    for rx, fixed in _GRADE_RE:
        m = rx.search(t)
        if m:
            return fixed if fixed else m.group(1).lower()
    return None


def parse_cc(t):
    rec = {"work": extract_work(t)}
    if not rec["work"]:
        return None
    v = label_value(t, "Contract Value (Original)") or label_value(t, "Contract Value") \
        or label_value(t, "Executed Value") or label_value(t, "Value of Work")
    if v:
        rec["value"] = parse_money(v)
    m = re.search(r"(?:gross executed value|executed value|at a gross value|at an executed value|at a value)\s+of\s+([^\n]+)", t, re.I)
    if rec.get("value") is None and m:
        rec["value"] = parse_money(m.group(1))
    v = label_value(t, "Completion Date") or label_value(t, "Date of Completion")
    if v:
        rec["completion_date"] = parse_date(v)
    m = re.search(r"completed in all respects on\s+([^\n]+?)(?:\s+at|\s*$)", t, re.I)
    if rec.get("completion_date") is None and m:
        rec["completion_date"] = parse_date(m.group(1))
    v = label_value(t, "Contractor's Project Manager") or label_value(t, "Project Manager") \
        or label_value(t, "Project Lead")
    if v:
        rec["pm"] = v
    m = re.search(r"supervised on the contractor'?s side by\s+([A-Za-z .]+?)(?:\.|$)", t, re.I)
    if rec.get("pm") is None and m:
        rec["pm"] = m.group(1).strip()
    v = label_value(t, "Nature / Category") or label_value(t, "Nature of Work") or label_value(t, "Category")
    if v:
        rec["category"] = _title_category(v)
    m = re.search(r"[“\"]\s*[^“”\"]*?—\s*[A-Za-z ]+?\s*Pkg-\d+\s*[”\"]\s*\(([^)]+)\)", t, re.S)
    if rec.get("category") is None and m:
        rec["category"] = _title_category(m.group(1))
    rec["grade"] = parse_grade(t)
    return rec


def parse_ccc(t):
    rec = {"work": extract_work(t)}
    if not rec["work"]:
        return None
    rec["client_raw"] = label_value(t, "Client")
    v = label_value(t, "Executed Value") or label_value(t, "Contract Value")
    if v:
        rec["value"] = parse_money(v)
    v = label_value(t, "Completion") or label_value(t, "Completion Date")
    if v:
        rec["completion_date"] = parse_date(v)
    v = label_value(t, "Project Lead") or label_value(t, "Project Manager")
    if v:
        rec["pm"] = v
    v = label_value(t, "Category")
    if v:
        rec["category"] = _title_category(v)
    rec["grade"] = parse_grade(t)
    return rec


def parse_ref(t):
    return {"work": extract_work(t)}


def parse_pcert_name(t):
    m = re.search(r"This is to certify that\s*\n\s*([A-Za-z .]+)", t)
    if m:
        return m.group(1).strip()
    m = re.search(r"certify that\s+([A-Za-z .]+?)\s*\n", t)
    return m.group(1).strip() if m else None


def parse_cv_name(t):
    v = label_value(t, "Name")
    return v if v and len(v) < 60 else None


def _wkey(n):
    return re.sub(r"\s+", " ", (n or "").strip()).lower()


def _title_category(c):
    if not c:
        return c
    c = re.sub(r"\s+", " ", c.strip())
    return re.sub(r"\b([a-z])", lambda m: m.group(1).upper(), c)


def main():
    works = {}
    refs = []
    for f in sorted(glob.glob(os.path.join(DOCS, "company_completion_certificate", "*.pdf"))):
        rec = parse_ccc(doc_text(f))
        if not rec:
            print("CCC unparsed:", os.path.basename(f))
            continue
        w = works.setdefault(_wkey(rec["work"]), {"work": rec["work"]})
        for k in ("client", "value", "completion_date", "pm", "category", "grade"):
            if rec.get(k) is not None:
                w[k] = rec[k]
        w["client"] = client_canon(rec.get("client_raw"))
    for f in sorted(glob.glob(os.path.join(DOCS, "completion_certificate", "*.pdf"))):
        rec = parse_cc(doc_text(f))
        if not rec:
            print("CC unparsed:", os.path.basename(f))
            continue
        w = works.setdefault(_wkey(rec["work"]), {"work": rec["work"]})
        for k in ("value", "completion_date", "pm", "category", "grade"):
            if rec.get(k) is not None:
                w[k] = rec[k]
        if not w.get("client"):
            w["client"] = None
    for f in sorted(glob.glob(os.path.join(DOCS, "completion_certificate", "*.pdf"))):
        t = doc_text(f)
        rec = parse_cc(t)
        if not rec:
            continue
        k = _wkey(rec["work"])
        if k in works and not works[k].get("client"):
            first = next((l.strip() for l in t.split("\n") if l.strip()), None)
            works[k]["client"] = client_canon(first)
    for f in sorted(glob.glob(os.path.join(DOCS, "reference_letter", "*.pdf"))):
        t = doc_text(f)
        rw = parse_ref(t)
        hit = None
        if rw and rw.get("work"):
            k = _wkey(rw["work"])
            if k in works:
                hit = k
        if hit is None:
            low = re.sub(r"\s+", " ", t).lower()
            for k in works:
                if k in low:
                    hit = k
                    break
        if hit:
            works[hit]["referenced"] = True
    people = set()
    for f in sorted(glob.glob(os.path.join(DOCS, "personnel_certificate", "*.pdf"))):
        n = parse_pcert_name(doc_text(f))
        if n:
            people.add(n)
    for f in sorted(glob.glob(os.path.join(DOCS, "cv", "*.pdf"))):
        n = parse_cv_name(doc_text(f))
        if n:
            people.add(n)

    clients, engineers = collections.defaultdict(set), collections.defaultdict(set)
    for k, w in works.items():
        if w.get("client"):
            clients[w["client"]].add(k)
        if w.get("pm"):
            engineers[w["pm"]].add(k)
    people |= set(engineers)

    mine = {"works": works, "clients": dict(clients), "engineers": dict(engineers), "people": people}
    gold = json.load(open(KG))["kg"]

    print(f"independent build: works={len(works)} clients={len(clients)} "
          f"engineers={len(engineers)} people={len(people)}")
    print(f"pipeline kg:       works={len(gold['works'])} clients={len(gold['clients'])} "
          f"engineers={len(gold['engineers'])} people={len(gold['people'])}")

    gk = set(gold["works"]); mk = set(works)
    print("\nwork-key diffs:  only-pipeline=%d only-mine=%d" % (len(gk - mk), len(mk - gk)))
    for k in sorted(gk - mk)[:10]:
        print("   only pipeline:", k, "->", gold["works"][k].get("work"))
    for k in sorted(mk - gk)[:10]:
        print("   only mine:", k, "->", works[k].get("work"))

    fields = ["client", "category", "value", "completion_date", "pm", "grade", "referenced"]
    fdiffs = collections.Counter()
    rows = []
    for k in sorted(gk & mk):
        g, m = gold["works"][k], works[k]
        row = []
        for fld in fields:
            gv, mv = g.get(fld), m.get(fld)
            same = gv == (list(mv) if isinstance(mv, tuple) else mv)
            if not same:
                fdiffs[fld] += 1
                row.append((fld, g.get(fld), m.get(fld)))
        rows.append((k, row))
    print("\nfield mismatches (pipeline vs mine):")
    for fld, n in sorted(fdiffs.items(), key=lambda x: -x[1]):
        print(f"   {fld:18s} {n}")
    print("\ndetail (up to 30):")
    for k, row in rows:
        if row:
            print(" ", k)
            for fld, g, m in row[:6]:
                print(f"      {fld}: pipeline={g!r} mine={m!r}")
        if sum(1 for _, r in rows if r) >= 30:
            break

    json.dump({"works": works, "clients": {k: sorted(v) for k, v in clients.items()},
               "engineers": {k: sorted(v) for k, v in engineers.items()},
               "people": sorted(people)},
              open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "kg_mine.json"), "w"), indent=1)
    print("\nsaved kg_mine.json")
    bad = sum(fdiffs.values()) + len(gk - mk) + len(mk - gk)
    print("KG MATCH: 0 differences" if bad == 0 else f"KG MISMATCH: {bad} differences")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
