#!/usr/bin/env python3
import json, re, os, csv, statistics, datetime, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOL = ROOT
QS = json.load(open(os.path.join(ROOT, "BITS-Hackathon-Dataset", "questions.json")))["questions"]
KG = json.load(open(os.path.join(HERE, "kg_mine.json")))
WORKS = KG["works"]
CLIENTS = KG["clients"]
PEOPLE = set(KG["people"])

_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun",
                                       "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_ANCHOR = (2021, 3, 10)


def parse_date(t):
    m = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", t)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", t)
    if m:
        return (int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b", t)
    if m:
        return (int(m.group(3)), _MONTHS.get(m.group(1).lower()[:3]), int(m.group(2)))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})[,]?\s+(20\d{2})\b", t)
    if m:
        return (int(m.group(3)), _MONTHS.get(m.group(2).lower()[:3]), int(m.group(1)))
    if re.search(r"mar\s*10|march\s+10|mar(?:ch)?\s+20\d{2}", t, re.I):
        return _ANCHOR
    return None


def days(a, b):
    return (datetime.date(*b) - datetime.date(*a)).days


_STOP = set("the of and for with govt government authority corporation company ltd limited "
            "municipal public works engineering construction dept department psu private mega "
            "national infrastructure office authorities division central services".split())


def resolve_client(q):
    ql = re.sub(r"\s+", " ", q.lower())
    ql = re.sub(r"\birr\s*&\s*waterways\b", "irrigation waterways", ql)
    ql = re.sub(r"\bneda\b", "national expressway development authority", ql)
    best, bl = None, 0
    for c in CLIENTS:
        cl = c.lower()
        if cl in ql and len(cl) > bl:
            best, bl = c, len(cl)
    if best:
        return best, True
    aliases = {
        "mega infra authority": "Mega Infrastructure Authority",
        "mega infrastructure authority": "Mega Infrastructure Authority",
        "up irrigation": "Irrigation & Waterways Dept, Govt of Uttar Pradesh",
        "gujarat pw": "Public Works Department, Govt of Gujarat",
        "public works department govt of gujarat": "Public Works Department, Govt of Gujarat",
        "trishakti": "Trishakti Power Generation Corporation",
        "trishakti power": "Trishakti Power Generation Corporation",
        "irr & waterways dept rajasthan": "Irrigation & Waterways Dept, Govt of Rajasthan",
        "irrigation and waterways dept, govt of rajasthan": "Irrigation & Waterways Dept, Govt of Rajasthan",
        "irrigation & waterways dept, govt of rajasthan": "Irrigation & Waterways Dept, Govt of Rajasthan",
        "mah pwd": "Public Works Department, Govt of Maharashtra",
        "maharashtra pwd": "Public Works Department, Govt of Maharashtra",
        "pheg": "Public Health Engineering Dept, Gujarat",
        "pheg gujarat": "Public Health Engineering Dept, Gujarat",
        "phed odisha": "Public Health Engineering Dept, Odisha",
        "jal nigam up": "Jal Nigam, Uttar Pradesh",
        "central works": "Central Works & Buildings Bureau",
        "subarnarekha valley corp": "Subarnarekha Valley Corporation",
        "suvarna projects": "Suvarna Projects Limited",
        "mahanadi steel": "Mahanadi Steel Corporation",
        "peninsular petroleum": "Peninsular Petroleum Corporation",
        "arunodaya": "Arunodaya Infrastructure",
        "meridian constructors": "Meridian Constructors & Co",
        "national expressway": "National Expressway Development Authority",
        "national special projects": "National Special Projects Office",
        "lakshya engineering": "Lakshya Engineering & Construction",
        "tamil nadu municipal": "Tamil Nadu Municipal Corporation",
        "maharashtra municipal": "Maharashtra Municipal Corporation",
        "jammu municipal": None,
        "gujarat municipal": "Gujarat Municipal Corporation",
        "jharkhand municipal": "Jharkhand Municipal Corporation",
        "neda": "National Expressway Development Authority",
        "public health engineering dept odisha": "Public Health Engineering Dept, Odisha",
        "public health engineering dept gujarat": "Public Health Engineering Dept, Gujarat",
        "public health engineering dept west bengal": "Public Health Engineering Dept, West Bengal",
        "phe dept odisha": "Public Health Engineering Dept, Odisha",
        "jal nigam jharkhand": "Jal Nigam, Jharkhand",
        "jal nigam gujarat": "Jal Nigam, Gujarat",
    }
    for ph, c in aliases.items():
        if c and ph in ql:
            return c, True
    if "public works department" in ql and not any("public works department" in c.lower() for c in CLIENTS
                                                     if c.lower() in ql):
        nql = ql.replace("bridges and flyovers", "bridges flyovers").replace("roads and highways", "roads highways")
        cats_in_q = [c for c in _CATS if c in nql]
        if len(cats_in_q) >= 2:
            for cand in CLIENTS:
                if "public works department" not in cand.lower():
                    continue
                have = {(WORKS[k].get("category") or "").lower() for k in client_works(cand)}
                if all(c in have for c in cats_in_q[:2]):
                    return cand, False
    for ab, exp in (("pwd", "public works department"), ("phed", "public health engineering"),
                    ("iw", "irrigation waterways"), ("i&w", "irrigation waterways")):
        if re.search(r"(?<![a-z])" + re.escape(ab) + r"(?![a-z])", ql):
            for c in CLIENTS:
                if exp in c.lower():
                    return c, True
    for c in CLIENTS:
        toks = [t for t in re.findall(r"[a-z]{2,}", c.lower()) if t not in _STOP]
        if len(toks) >= 3 and all(t in ql for t in toks):
            return c, False
    return None, False


def resolve_engineer(q):
    ql = q.lower()
    best, bl = None, 0
    for n in PEOPLE:
        nl = n.lower()
        if nl in ql and len(nl) > bl:
            best, bl = n, len(nl)
    if best:
        return best
    firsts = collections.Counter(n.split()[0].lower() for n in PEOPLE)
    for n in PEOPLE:
        fn = n.split()[0].lower()
        if firsts[fn] == 1 and re.search(r"(?<![a-z])" + re.escape(fn) + r"[a-z]*['’]?s?(?![a-z])", ql):
            return n
    return None


def pkgs_in(q):
    return set(re.findall(r"(?i)Pkg[- ]?(\d+)", q)) | set(re.findall(r"(?i)package[- ]?(\d+)", q))


def _pkg(n):
    m = re.search(r"(?i)Pkg[- ]?(\d+)", n or "")
    return m.group(1) if m else None


def _state(n):
    m = re.search(r"—\s*([A-Za-z ]+?)\s+Pkg", n or "")
    return m.group(1).strip() if m else None


def state_in(q):
    states = {"uttar pradesh", "west bengal", "madhya pradesh", "tamil nadu", "maharashtra",
              "rajasthan", "jharkhand", "gujarat", "odisha", "delhi"}
    ql = q.lower()
    for s in states:
        if s in ql:
            return s
    return None


def resolve_work(q, eng=None):
    pkgs = pkgs_in(q)
    ql = q.lower()
    if not pkgs:
        stw = {"uttar", "pradesh", "west", "bengal", "madhya", "tamil", "nadu", "maharashtra",
               "rajasthan", "jharkhand", "gujarat", "odisha", "delhi"}
        toks = set(re.findall(r"[a-z]{4,}", ql)) - {"what", "from", "pmp", "work", "project",
                                                    "package", "final", "completion", "with", "the",
                                                    "how", "that", "his", "her"} - stw
        cands = []
        for k, w in WORKS.items():
            wt = set(re.findall(r"[a-z]{4,}", w["work"].lower())) - stw - {"pkg"}
            if len(toks & wt) >= 2:
                cands.append(k)
        st = state_in(q)
        if st:
            sc = [k for k in cands if (_state(WORKS[k].get("work")) or "").lower() == st]
            if len(sc) == 1:
                return sc[0]
            if sc:
                cands = sc
        if len(cands) == 1:
            return cands[0]
        if eng:
            ec = [k for k in cands if (WORKS[k].get("pm") or "").lower() == eng.lower()]
            if len(ec) == 1:
                return ec[0]
        return None
    cands = [k for k, w in WORKS.items() if _pkg(w.get("work")) in pkgs]
    if len(cands) == 1:
        return cands[0]
    st = state_in(q)
    for k in cands:
        if (_state(WORKS[k].get("work")) or "").lower() == st:
            return k
    if eng:
        ec = [k for k in cands if (WORKS[k].get("pm") or "").lower() == eng.lower()]
        if len(ec) == 1:
            return ec[0]
    if len(cands) >= 1 and len(pkgs) == 1:
        return cands[0]
    return None


def client_of_work(k):
    return WORKS[k].get("client")


def client_works(c):
    return CLIENTS.get(c, [])


def engineer_works(n):
    low = n.lower() if n else None
    return [k for k, w in WORKS.items() if (w.get("pm") or "").lower() == low]


def _vals(keys):
    return [WORKS[k]["value"] for k in keys if WORKS[k].get("value") is not None]


import openpyxl
AGE = {}
wb = openpyxl.load_workbook(os.path.join(ROOT, "BITS-Hackathon-Dataset", "documents",
                                         "workbooks", "Receivables_Ageing.xlsx"),
                            data_only=True, read_only=True)
for r in wb["AR Ageing"].iter_rows(values_only=True):
    if r[0] == "Invoice No" or not isinstance(r[3], (int, float)):
        continue
    cl = re.sub(r"\s*\([^)]*\)\.?$", "", str(r[1]).strip()).rstrip(".").strip()
    g = AGE.setdefault(cl, [0.0, 0.0, 0.0])
    g[0] += float(r[3]); g[1] += float(r[5]); g[2] += float(r[6])
wb.close()

_WORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}

_CATS = ["water treatment", "sewerage drainage", "water supply", "roads maintenance",
         "roads highways", "bridges flyovers", "industrial epc", "large bridges",
         "small buildings", "expressways", "irrigation", "tunnels", "buildings"]


def resolve_threshold(q):
    m = re.search(r"(?i)(?:INR|Rs\.?|₹)?\s*([\d,]+)\s*(Cr|Lakh|crore|lac)\b", q)
    if m:
        v = int(m.group(1).replace(",", ""))
        return v * (10_000_000 if m.group(2).lower() in ("cr", "crore") else 100_000)
    m = re.search(r"(?i)((?:[a-z]+[\s-]*){1,7})(?:crore|crs?|lakh|lacs?)\b", q)
    if m:
        words = re.findall(r"[a-z]+", m.group(1))
        tot = 0
        for w in words:
            tot = tot + _WORD[w] if w in _WORD else 0
        mult = 10_000_000 if "cr" in m.group(0).lower() else 100_000
        return tot * mult if tot else None
    return None


def _years(q):
    out = []
    for m in re.finditer(r"\b(20\d{2})\b", q):
        pre = q[max(0, m.start() - 4):m.start()]
        if re.search(r"PMI-2?$|PMI$", pre):
            continue
        out.append(int(m.group(1)))
    return out


def classify(q):
    ql = q.lower()
    if re.search(r"outstanding|remaining balance across all charged|total remaining balance", ql) and \
       not re.search(r"threshold|credential|secure|clear the", ql):
        return "fin_outstanding"
    if re.search(r"percentage out of 100|collection figure|collected aligns|percentage.*collected|"
                 r"% has been collected|collection percentage|collection rate|billing versus collection|"
                 r"percentage.*against the billing|collection number|collection %|% out of 100|"
                 r"portion of the total billed amount has cleared|what we've actually brought in", ql):
        return "fin_collection_share"
    if re.search(r"invoiced", ql):
        return "fin_invoiced"
    if re.search(r"plant and machinery|asset register|equipment register|acquisition cost", ql):
        return "fin_assets"
    if re.search(r"gap between the total value of work awarded and the amount|still sitting above what we've|"
                 r"delta between secured work and submitted claims|gap between total award value|awarded works.*gap|"
                 r"gap between.*award.*billed", ql):
        return "awarded_invoiced_gap"
    if re.search(r"no (?:client )?reference letter|lack a reference|without a reference|unreferenced|"
                 r"lack a client reference", ql):
        return "absence"
    if re.search(r"days (?:passed|elapsed|between)|interval from|number of days|days from|days elapsed|"
                 r"span from|elapsed period|total elapsed|days to (?:completion|wrap|complete|handover)|"
                 r"wrap up|count to final completion|how many days|count from that issue|day count|"
                 r"how long it actually ran|exact day count|count to wrap|actual day count|count from that certification", ql):
        return "date_span"
    if re.search(r"distinct (?:work )?(?:classifications|categories)|different categories|"
                 r"how many (?:different )?categories|separate work categories|how many work categories|"
                 r"count of separate work categories", ql):
        return "distinct_count"
    if re.search(r"exclud(?:ing|es?)|dropping|after .*excluded|"
                 r"minus the (?:water treatment|buildings|bridges flyovers|roads highways|expressways|tunnels|irrigation|sewerage drainage|industrial epc|water supply|roads maintenance|large bridges|small buildings) (?:side|division|part)", ql):
        return "exclusion_aggregate"
    if re.search(r"reference letter divided|percentage of (?:completed )?assignments that carry|"
                 r"share.*reference letter|out of one hundred represents|share of completed|testimonial|"
                 r"client endorsement|client approval|client sign-off|out-of-100|share of our projects|"
                 r"share of those assignments|endorsements.*cleared|out of 100 figure|portion of our work backed|"
                 r"backed by a client reference|client reference on file", ql):
        return "referenced_share"
    if re.search(r"reach (?:our )?credential target|target of (?:INR|Rs|₹)|bar (?:INR|Rs)|"
                 r"additional work must we secure|how much more value", ql):
        return "gap_to_threshold"
    if re.search(r"highest-value completed assignment and the (?:next|subsequent)|difference between our highest|"
                 r"top finished contract there beats the second|largest completed work exceed the second|"
                 r"difference between the largest|by how much does our largest|exceeds the second-largest|"
                 r"how much our largest (?:work|contract|project) exceeds the second|"
                 r"difference between our biggest and next|largest one and the second largest|"
                 r"beats the second|our largest work exceeds|largest.*second largest|"
                 r"largest finished contract there beats", ql):
        return "rank_value"
    if re.search(r"graded (excellent|very good|good|satisfactory)|marked (excellent|very good|good|satisfactory)", ql):
        return "doc_filtered_aggregate"
    if re.search(r"difference between the mean and the median|mean-median|mean and median gap|"
                 r"mean and the median|how much larger the average.*than the median|"
                 r"average contract value.*than the median|mean scale|rupee difference between the mean|"
                 r"mean against the median|difference between the average and median|"
                 r"difference between the mean and median|average and median|mean and median contract|"
                 r"median contract values|average vs median|mean-median gap|avg minus median|average minus median", ql):
        return "mean_median"
    if re.search(r"\b(20\d{2})\b\s*vs\.?\s*\b(20\d{2})\b|difference in completed work value between "
                 r"(\d{4}) and (\d{4})|difference .*between (\d{4}) and (\d{4})|"
                 r"delta on completed work value|net difference in the value of work completed", ql):
        return "year_diff"
    found = [c for c in _CATS if c in ql.replace("bridges and flyovers", "bridges flyovers")
             .replace("roads and highways", "roads highways")]
    if len(found) >= 2 and re.search(r"difference|delta|spread|subtract|versus|vs\.?|outweighed|gap", ql):
        return "category_diff"
    if re.search(r"crossing the|hitting the|above (?:INR|Rs|₹)|cross(?:ing)? (?:the )?(?:INR|Rs|₹)|exceeding|"
                 r"hitting (?:[a-z]+ )?crore|hitting (?:INR|Rs|₹)|or more", ql):
        return "threshold_aggregate"
    if re.search(r"completed after|wrapped up after|after (?:her|his|that|its)", ql):
        return "temporal_chain"
    if re.search(r"largest (?:work|project|assignment)|biggest (?:work|project)", ql):
        return "max_value"
    if re.search(r"smallest (?:work|project)|lowest value", ql):
        return "min_value"
    if re.search(r"average|mean|avg ", ql):
        return "avg_work_size"
    if _years(q):
        return "year_aggregate"
    if re.search(r"combined value|total value|sum of|aggregate|total amount|total of|full tally|"
                 r"aggregate value of all|combined value of every completed", ql):
        return "hop_aggregate"
    if re.search(r"how many|number of", ql):
        return "count_works"
    return "hop_aggregate"


def answer_one(q):
    ql = q["question"].lower()
    shape = classify(q["question"])
    client, explicit = resolve_client(q["question"])
    eng = resolve_engineer(q["question"])
    wk = resolve_work(q["question"], eng)
    if not explicit and wk:
        client = client_of_work(wk)
    keys = client_works(client) if client else (engineer_works(eng) if eng else None)

    if shape == "fin_collection_share":
        row = AGE.get(client)
        return round(row[1] / row[0] * 100, 2) if row and row[0] else None
    if shape == "fin_outstanding":
        row = AGE.get(client) if client else None
        if row is None and eng is None:
            for c in AGE:
                if c.lower() in ql and len(c) > 10:
                    row = AGE.get(c)
                    break
        return int(round(row[2])) if row else None
    if shape == "fin_invoiced":
        row = AGE.get(client) if client else None
        if row is None:
            for c in AGE:
                if c.lower() in ql and len(c) > 10:
                    row = AGE.get(c)
                    break
        if not row:
            return None
        if re.search(r"\bpercentage\b|%|collected|collection (?:figure|rate|percentage)|collected aligns", ql):
            return round(row[1] / row[0] * 100, 2)
        return int(round(row[0]))
    if shape == "fin_assets":
        return None
    if shape == "awarded_invoiced_gap":
        row = AGE.get(client)
        return sum(_vals(client_works(client))) - int(round(row[0])) if row and client else None
    if shape == "absence":
        return sum(1 for k in client_works(client) if not WORKS[k].get("referenced"))
    if shape == "date_span":
        anchor = parse_date(q["question"])
        if not anchor:
            return None
        if not wk and eng:
            terms = set(re.findall(r"[a-z]{4,}", ql))
            wk = max(engineer_works(eng),
                     key=lambda k: len(terms & set(re.findall(r"[a-z]{4,}", WORKS[k]["work"].lower()))),
                     default=None)
        if not wk:
            return None
        cd = WORKS[wk].get("completion_date")
        return days(anchor, cd) if cd else None
    if shape == "distinct_count":
        return len({WORKS[k].get("category") for k in engineer_works(eng) if WORKS[k].get("category")}) if eng else None
    if shape == "exclusion_aggregate":
        if not client:
            return None
        cat = None
        m = re.search(r"after (.+?) (?:is|are|gets?|division|section|part|side)[^a-z]{0,10}excluded", ql)
        if m:
            seg = m.group(1)
            for c in _CATS:
                if c in seg:
                    cat = c
                    break
            if cat is None:
                aliases = {"water treatment": "water treatment", "bridges and flyovers": "bridges flyovers"}
                for ph, c in aliases.items():
                    if ph in seg:
                        cat = c
                        break
        if cat is None:
            m = re.search(r"exclud(?:ing|es?)|dropping|minus", ql)
            if m:
                tail = re.sub(r"^\W+", "", ql[m.end():])
                cats = sorted({w.get("category", "").lower() for w in WORKS.values() if w.get("category")},
                              key=len, reverse=True)
                cat = next((c for c in cats
                            if tail.startswith(c) or re.match(re.escape(c) + r"[,;.\s]|$", tail)), None)
                if not cat:
                    aliases = {"water treatment": "water treatment", "roads maintenance": "roads maintenance",
                               "bridges and flyovers": "bridges flyovers", "roads and highways": "roads highways",
                               "industrial epc": "industrial epc", "sewerage drainage": "sewerage drainage",
                               "water supply": "water supply", "large bridges": "large bridges"}
                    for ph, c in aliases.items():
                        if ph in tail:
                            cat = c
                            break
        if not cat:
            return None
        return sum(WORKS[k]["value"] for k in client_works(client)
                   if WORKS[k].get("value") is not None
                   and (WORKS[k].get("category") or "").lower() != cat)
    if shape == "referenced_share":
        if not client:
            return None
        kk = client_works(client)
        return round(sum(1 for k in kk if WORKS[k].get("referenced")) / len(kk) * 100, 2)
    if shape == "gap_to_threshold":
        th = resolve_threshold(q["question"])
        return th - sum(_vals(client_works(client))) if th is not None and client else None
    if shape == "rank_value":
        vs = sorted(_vals(client_works(client)), reverse=True)
        return vs[0] - vs[1] if len(vs) >= 2 else None
    if shape == "doc_filtered_aggregate":
        m = re.search(r"(excellent|very good|good|satisfactory)", ql)
        return sum(WORKS[k]["value"] for k in client_works(client)
                   if WORKS[k].get("grade") == m.group(1) and WORKS[k].get("value") is not None) \
            if m and client else None
    if shape == "mean_median":
        vs = _vals(client_works(client)) if client else []
        if len(vs) < 2:
            return None
        return int(round(sum(vs) / len(vs) - statistics.median(vs)))
    if shape == "avg_work_size":
        vs = _vals(keys) if keys else []
        return int(round(sum(vs) / len(vs))) if vs else None
    if shape == "threshold_aggregate":
        th = resolve_threshold(q["question"])
        return sum(WORKS[k]["value"] for k in client_works(client)
                   if WORKS[k]["value"] >= th) if th is not None and client else None
    if shape == "temporal_chain":
        anchor = parse_date(q["question"])
        if not anchor or not eng:
            return None
        return sum(WORKS[k]["value"] for k in engineer_works(eng)
                   if WORKS[k].get("completion_date") and days(anchor, WORKS[k]["completion_date"]) > 0
                   and WORKS[k].get("value") is not None)
    if shape == "max_value":
        return max(_vals(keys)) if keys else None
    if shape == "min_value":
        return min(_vals(keys)) if keys else None
    if shape == "year_diff":
        yrs = _years(q["question"])
        if len(yrs) < 2 or not client:
            return None
        by = {}
        for k in client_works(client):
            cd = WORKS[k].get("completion_date")
            if cd:
                by[cd[0]] = by.get(cd[0], 0) + WORKS[k].get("value", 0)
        a, b = yrs[0], yrs[1]
        if a not in by and b not in by:
            return None
        return abs(by.get(b, 0) - by.get(a, 0))
    if shape == "year_aggregate":
        yrs = _years(q["question"])
        if not yrs or not client:
            return None
        yk = [k for k in client_works(client) if WORKS[k].get("completion_date")
              and WORKS[k]["completion_date"][0] == yrs[0]]
        if re.search(r"value|sum|total|contract amounts", ql):
            return sum(_vals(yk))
        return len(yk)
    if shape == "category_diff":
        nl = ql.replace("bridges and flyovers", "bridges flyovers").replace("roads and highways", "roads highways")
        found = [c for c in _CATS if c in nl]
        if len(found) < 2 or not client:
            return None
        s = [sum(WORKS[k]["value"] for k in client_works(client)
                 if (WORKS[k].get("category") or "").lower() == c
                 and WORKS[k].get("value") is not None) for c in found[:2]]
        return abs(s[0] - s[1])
    if shape == "hop_aggregate":
        vs = _vals(keys) if keys else []
        return sum(vs) if vs else None
    if shape == "count_works":
        return len(keys) if keys else None
    return None


def main():
    sub = {}
    for r in csv.DictReader(open(os.path.join(SOL, "submission_full.csv"))):
        sub[r["question_id"]] = r["answer"].strip()
    rows = []
    for q in QS:
        shape = classify(q["question"])
        mine = answer_one(q)
        csvv = sub.get(q["qid"])
        try:
            csvf = float(csvv) if csvv not in (None, "") else None
        except ValueError:
            csvf = None
        same = mine is not None and csvf is not None and abs(mine - csvf) < 1e-6
        t = q["answer_type"]
        type_ok = True
        if csvf is not None:
            if t == "percent":
                type_ok = 0 <= csvf <= 100
            elif t == "days":
                type_ok = 0 <= csvf <= 30000 and csvf == int(csvf)
            elif t == "count":
                type_ok = 0 <= csvf <= 200 and csvf == int(csvf)
        if mine is None:
            verdict = "UNRESOLVED"
        elif same:
            verdict = "AGREE"
        elif not type_ok:
            verdict = "CSV_WRONG_SHAPE"
        else:
            verdict = "DISAGREE"
        rows.append({"qid": q["qid"], "shape": shape, "type": t, "csv": csvf, "mine": mine,
                     "verdict": verdict, "same": same, "q": q["question"]})
    agg = collections.Counter(r["verdict"] for r in rows)
    print("verdicts:", dict(agg))
    agree = sum(1 for r in rows if r["verdict"] == "AGREE")
    print(f"CSV correct (independent agreement): {agree}/{len(rows)} ({agree/len(rows):.1%})")
    unresolved = [r for r in rows if r["verdict"] == "UNRESOLVED"]
    print(f"unresolved: {len(unresolved)}")
    for r in unresolved:
        print(f"   {r['qid']} [{r['type']}|{r['shape']}] csv={r['csv']} | {r['q'][:110]}")
    bad = [r for r in rows if r["verdict"] in ("CSV_WRONG_SHAPE", "DISAGREE")]
    print(f"\nCSV wrong ({len(bad)}):")
    for r in bad:
        print(f"   {r['qid']} [{r['type']}|{r['shape']}] csv={r['csv']} verified={r['mine']}")
    json.dump(rows, open(os.path.join(HERE, "verdicts.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
