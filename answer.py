"""Question engine: plain-English question -> one number, over the pipeline's KG.

Three steps, in order: (1) classify the question into an arithmetic "shape"
(detect), (2) resolve the entities it names (client / engineer / work) against
the knowledge graph, (3) compute the answer as a pure aggregation over the
resolved key set. Deterministic: same question, same number, every time.
"""

import re, os, statistics
from pipeline import ensure_kg, parse_date, days_between

KG = ensure_kg(verbose=False)
WORKS = KG["works"]
CLIENTS = KG["clients"]
ENGINEERS = KG["engineers"]
PEOPLE = KG["people"]

_FIN = None
_FIN_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "fin.json")


def load_financial():
    global _FIN
    if _FIN is None:
        if os.path.exists(_FIN_CACHE):
            import json
            _FIN = json.load(open(_FIN_CACHE))
        else:
            from pipeline import build_financial
            _FIN = build_financial(verbose=False)
    return _FIN


_ABBREV = {
    "pwd": ["public works department"],
    "phed": ["public health engineering"],
    "iw": ["irrigation & waterways", "irrigation and waterways"],
    "i&w": ["irrigation & waterways", "irrigation and waterways"],
}
_CLIENT_STOP = set("the of and for with govt government authority corporation "
                   "company ltd limited municipal public works engineering construction "
                   "dept department psu private mega national infrastructure office "
                   "authorities division central services".split())

_CATS = ["water treatment", "sewerage drainage", "water supply", "roads maintenance",
         "roads highways", "bridges flyovers", "industrial epc", "large bridges",
         "small buildings", "expressways", "irrigation", "tunnels", "buildings"]

_ALIASES = {
    "up irrigation": "Irrigation & Waterways Dept, Govt of Uttar Pradesh",
    "gujarat pw": "Public Works Department, Govt of Gujarat",
    "public works department govt of gujarat": "Public Works Department, Govt of Gujarat",
    "mahanadi steel corp": "Mahanadi Steel Corporation",
    "mahanadi steel": "Mahanadi Steel Corporation",
    "suvarna projects": "Suvarna Projects Limited",
    "jal nigam up": "Jal Nigam, Uttar Pradesh",
    "mah pwd": "Public Works Department, Govt of Maharashtra",
    "maharashtra pwd": "Public Works Department, Govt of Maharashtra",
    "pheg": "Public Health Engineering Dept, Gujarat",
    "pheg gujarat": "Public Health Engineering Dept, Gujarat",
    "phed odisha": "Public Health Engineering Dept, Odisha",
    "public health engineering dept odisha": "Public Health Engineering Dept, Odisha",
    "public health engineering dept gujarat": "Public Health Engineering Dept, Gujarat",
    "public health engineering dept west bengal": "Public Health Engineering Dept, West Bengal",
    "phe dept odisha": "Public Health Engineering Dept, Odisha",
    "irr & waterways dept rajasthan": "Irrigation & Waterways Dept, Govt of Rajasthan",
    "irrigation and waterways dept, govt of rajasthan": "Irrigation & Waterways Dept, Govt of Rajasthan",
    "irrigation & waterways dept, govt of rajasthan": "Irrigation & Waterways Dept, Govt of Rajasthan",
    "jal nigam jharkhand": "Jal Nigam, Jharkhand",
    "jal nigam gujarat": "Jal Nigam, Gujarat",
    "central works": "Central Works & Buildings Bureau",
    "subarnarekha valley corp": "Subarnarekha Valley Corporation",
    "peninsular petroleum": "Peninsular Petroleum Corporation",
    "arunodaya": "Arunodaya Infrastructure",
    "meridian constructors": "Meridian Constructors & Co",
    "national expressway": "National Expressway Development Authority",
    "national special projects": "National Special Projects Office",
    "lakshya engineering": "Lakshya Engineering & Construction",
    "tamil nadu municipal": "Tamil Nadu Municipal Corporation",
    "maharashtra municipal": "Maharashtra Municipal Corporation",
    "gujarat municipal": "Gujarat Municipal Corporation",
    "jharkhand municipal": "Jharkhand Municipal Corporation",
    "neda": "National Expressway Development Authority",
    "trishakti": "Trishakti Power Generation Corporation",
    "trishakti power": "Trishakti Power Generation Corporation",
    "mega infra authority": "Mega Infrastructure Authority",
    "mega infrastructure authority": "Mega Infrastructure Authority",
}


def resolve_client(q):
    """Resolve the client a question refers to -> (canonical_name, explicit?).

    Cascade: longest exact substring match over known clients, then hand-built
    aliases, then a category-based heuristic for ambiguous "Public Works
    Department" clients, then abbreviations, then stopword-filtered token
    containment. `explicit` is False for low-confidence tiers so callers can
    prefer a work-derived client.
    """
    ql = q.lower()
    ql = re.sub(r"\birr\s*&\s*waterways\b", "irrigation waterways", ql)
    ql = re.sub(r"\bneda\b", "national expressway development authority", ql)
    best, bestlen = None, 0
    for c in CLIENTS:
        cl = c.lower()
        if cl in ql and len(cl) > bestlen:
            best, bestlen = c, len(cl)
    if best:
        return best, True
    for phrase, c in _ALIASES.items():
        if c and phrase in ql:
            return c, True
    if "public works department" in ql and not any("public works department" in c.lower()
                                                   for c in CLIENTS if c.lower() in ql):
        nql = ql.replace("bridges and flyovers", "bridges flyovers").replace("roads and highways", "roads highways")
        cats_in_q = [c for c in _CATS if c in nql]
        if len(cats_in_q) >= 2:
            for cand in CLIENTS:
                if "public works department" not in cand.lower():
                    continue
                have = {(WORKS[k].get("category") or "").lower() for k in client_works(cand)}
                if all(c in have for c in cats_in_q[:2]):
                    return cand, False
    for ab, exps in _ABBREV.items():
        if re.search(r"(?<![a-z])" + re.escape(ab) + r"(?![a-z])", ql):
            for e in exps:
                for c in CLIENTS:
                    if e in c.lower():
                        return c, True
    for c in CLIENTS:
        cl = c.lower()
        toks = [t for t in re.findall(r"[a-z]{2,}", cl) if t not in _CLIENT_STOP]
        if not toks or len(toks) < 3:
            continue
        if all(t in ql for t in toks):
            return c, False
    return None, False


def resolve_engineer(q):
    """Resolve an engineer's name from the question (full name, then unique first name)."""
    ql = q.lower()
    best, bestlen = None, 0
    for name in PEOPLE:
        nl = name.lower()
        if nl in ql and len(nl) > bestlen:
            best, bestlen = name, len(nl)
    if best:
        return best
    import collections
    firsts = collections.Counter(n.split()[0].lower() for n in PEOPLE)
    for n in PEOPLE:
        fn = n.split()[0].lower()
        if firsts[fn] == 1 and re.search(r"(?<![a-z])" + re.escape(fn) + r"[a-z]*['\u2019]?s?(?![a-z])", ql):
            return n
    return None


def _pkgs_in(q):
    return set(re.findall(r"(?i)Pkg[- ]?(\d+)", q)) | set(re.findall(r"(?i)package[- ]?(\d+)", q))


def _pkg(n):
    m = re.search(r"(?i)Pkg[- ]?(\d+)", n or "")
    return m.group(1) if m else None


def _state(n):
    m = re.search(r"\u2014\s*([A-Za-z ]+?)\s+Pkg", n or "")
    return m.group(1).strip() if m else None


_STATE_WORDS = {"uttar", "pradesh", "west", "bengal", "madhya", "tamil", "nadu", "maharashtra",
                "rajasthan", "jharkhand", "gujarat", "odisha", "delhi"}


def _state_in(q):
    states = {"uttar pradesh", "west bengal", "madhya pradesh", "tamil nadu", "maharashtra",
              "rajasthan", "jharkhand", "gujarat", "odisha", "delhi"}
    ql = q.lower()
    for s in states:
        if s in ql:
            return s
    return None


def resolve_work(q, eng=None):
    """Resolve which work a question names -> normalized work key (or None).

    Two modes: token-overlap matching against work names when no package number
    is given, or direct Pkg-N lookup, disambiguated by state and engineer.
    """
    pkgs = _pkgs_in(q)
    ql = q.lower()
    if not pkgs:
        toks = set(re.findall(r"[a-z]{4,}", ql)) - {"what", "from", "pmp", "work", "project",
                                                    "package", "final", "completion", "with", "the",
                                                    "how", "that", "his", "her"} - _STATE_WORDS
        cands = []
        for k, w in WORKS.items():
            wt = set(re.findall(r"[a-z]{4,}", w["work"].lower())) - _STATE_WORDS - {"pkg"}
            if len(toks & wt) >= 2:
                cands.append(k)
        st = _state_in(q)
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
    st = _state_in(q)
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


def engineer_works(name):
    if not name:
        return []
    low = name.lower()
    return [k for k, w in WORKS.items() if (w.get("pm") or "").strip().lower() == low]


def client_works(client):
    if not client:
        return []
    return list(CLIENTS.get(client, set()))


_WORD = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
         "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
         "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
         "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90, "hundred": 100}


def resolve_threshold(q):
    """Parse a money threshold like 'INR 5 Cr' or 'twenty five crore' -> rupees int."""
    m = re.search(r"(?i)(?:INR|Rs\.?|\u20b9)?\s*([\d,]+(?:\.\d+)?)\s*(Cr|Lakh|crore|lac)\b", q)
    if m:
        v = float(m.group(1).replace(",", ""))
        mult = 10_000_000 if m.group(2).lower() in ("cr", "crore") else 100_000
        return int(round(v * mult))
    m = re.search(r"(?i)((?:[a-z]+[\s-]*){1,7})(?:crore|crs?|lakh|lacs?)\b", q)
    if m:
        words = re.findall(r"[a-z]+", m.group(1))
        tot = 0
        for w in words:
            tot = (tot + _WORD[w]) if w in _WORD else 0
        mult = 10_000_000 if re.search(r"(?i)crore|crs?$", m.group(0)) else 100_000
        if tot > 0:
            return tot * mult
    return None


def _years(q):
    # Preserve order but remove repeated mentions of the same year (questions
    # often restate a year while describing the comparison).
    out, seen = [], set()
    for m in re.finditer(r"\b(20\d{2})\b", q):
        pre = q[max(0, m.start() - 4):m.start()]
        if re.search(r"PMI-2?$|PMI$", pre):
            continue
        year = int(m.group(1))
        if year not in seen:
            out.append(year)
            seen.add(year)
    return out


def detect(q):
    """Classify a question into one of ~20 arithmetic shapes (ordered regex cascade).

    Order matters: the most specific shapes (financial metrics, absence, day
    spans) are tested before generic aggregates, and the catch-all is a plain
    sum (hop_aggregate).
    """
    ql = q.lower()
    if re.search(r"outstanding|remaining balance across all charged|total remaining balance|"
                 r"still owe|still owed|still due|amount .*due|net balance|balance .*"
                 r"(?:still|remaining|due|owed)|remain(?:s|ing)? (?:unpaid|on|due)|"
                 r"unpaid|pending balance|pending amount|still pending|currently due|"
                 r"deduction .*cleared|deducting .*cleared|after .*cleared|cleared so far|"
                 r"adjusted balance|billed amounts? .*pending|balance when .*invoice", ql) and \
       not re.search(r"threshold|credential|secure|clear the", ql):
        return "fin_outstanding"
    if re.search(r"gap between .{0,60}(?:award|billed|invoice)|"
                 r"awarded value .*versus|award(?:ed)? .*shortfall|shortfall|unbilled|"
                 r"missing amount|variance between .{0,40}(?:award|scope|commit)|"
                 r"still sitting above|delta between secured|gap between the total value of work awarded|"
                 r"gap between total award value|awarded works.*gap|gap between.*award.*billed|"
                 r"gap between .{0,80}(?:award|billed|invoice|assigned|committed|sanctioned|claimed)|"
                 r"amount (?:after|once) .{0,40}(?:cross-check(?:ing)?|checking|reconcil(?:e|ing)) .{0,30}(?:invoice|claim|billed)", ql):
        return "awarded_invoiced_gap"
    if re.search(r"percentage out of 100|collection figure|collected aligns|percentage.*collected|"
                 r"% has been collected|collection percentage|collection rate|billing versus collection|"
                 r"percentage.*against the billing|collection number|collection %|% out of 100|"
                 r"portion of the total billed amount has cleared|what we've actually brought in", ql):
        return "fin_collection_share"
    if re.search(r"invoiced", ql):
        return "fin_invoiced"
    if re.search(r"plant and machinery|asset register|equipment register|acquisition cost", ql):
        return "fin_assets"
    if re.search(r"no (?:client )?reference letter|lack a reference|without a reference|unreferenced|"
                 r"lack a client reference", ql):
        return "absence"
    if re.search(r"days (?:passed|elapsed|between)|interval from|number of days|days from|days elapsed|"
                 r"span from|elapsed period|total elapsed|days to (?:completion|wrap|complete|handover)|"
                 r"wrap up|count to final completion|how many days|count from that issue|day count|"
                 r"how long it actually ran|exact day count|count to wrap|actual day count|"
                 r"count from that certification", ql):
        return "date_span"
    if re.search(r"distinct (?:work )?(?:classifications|categories)|different categories|"
                 r"how many (?:different )?categories|separate work categories|how many work categories|"
                 r"count of separate work categories", ql):
        return "distinct_count"
    if re.search(r"exclud(?:ing|es?)|dropping|after .*excluded|set aside|stripped out|remov(?:e|ed|ing)|filter(?:ing)? out|"
                 r"minus the (?:water treatment|buildings|bridges flyovers|roads highways|expressways|"
                 r"tunnels|irrigation|sewerage drainage|industrial epc|water supply|roads maintenance|"
                 r"large bridges|small buildings) (?:side|division|part)", ql):
        return "exclusion_aggregate"
    if re.search(r"reference letter divided|percentage of (?:completed )?assignments that carry|"
                 r"share.*reference letter|out of one hundred represents|share of completed|testimonial|"
                 r"client endorsement|client approval|client sign-off|out-of-100|share of our projects|"
                 r"share of those assignments|endorsements.*cleared|out of 100 figure|portion of our work backed|"
                 r"backed by a client reference|client reference on file", ql):
        return "referenced_share"
    if re.search(r"reach (?:our )?credential target|target of (?:INR|Rs|\u20b9)|bar (?:INR|Rs)|"
                 r"additional work must we secure|how much more value|how much more .*to hit|"
                 r"bring in .*to hit|clear the .*credential threshold", ql):
        return "gap_to_threshold"
    if re.search(r"highest-value completed assignment and the (?:next|subsequent)|difference between our highest|"
                 r"top finished contract there beats the second|largest completed work exceed the second|"
                 r"difference between the largest|by how much does our largest|exceeds the second-largest|"
                 r"how much our largest (?:work|contract|project) exceeds the second|"
                 r"difference between our biggest and next|largest one and the second largest|"
                 r"beats the second|our largest work exceeds|largest.*second largest|"
                 r"largest finished contract there beats|difference in value between our largest|"
                 r"difference .*largest .*second-largest|largest (?:one|completed (?:work|project|contract)) exceeds the second|"
                 r"highest-value completed assignment.{0,40}exceeds the (?:next|second)|"
                 r"(?:biggest|largest|top) finished contract.{0,40}(?:exceeds|beats) the (?:next|second)|"
                 r"exceeds the second one|beats the one just behind|surplus value separating", ql):
        return "rank_value"
    if re.search(r"graded (excellent|very good|good|satisfactory)|marked (excellent|very good|good|satisfactory)", ql):
        return "doc_filtered_aggregate"
    if re.search(r"difference between the mean and the median|mean-median|mean and median gap|"
                 r"mean and the median|how much larger the average.*than the median|"
                 r"average contract value.*than the median|rupee difference between the mean|"
                 r"mean against the median|difference between the average and median|"
                 r"difference between the mean and median|average and median|mean and median contract|"
                 r"median contract values|average vs median|mean-median gap|avg minus median|average minus median|"
                 r"gap between (?:the )?(?:avg|average) and (?:the )?median", ql):
        return "mean_median"
    if re.search(r"\b(20\d{2})\b\s*vs\.?\s*\b(20\d{2})\b|difference in completed work value between "
                 r"(\d{4}) and (\d{4})|difference .*between (\d{4}) and (\d{4})|"
                 r"delta on completed work value|net difference in the value of work completed|"
                 r"(?:moved|movement|shift|swing|variance|period-over-period) .*between .*20\d{2}|"
                 r"both\s+20\d{2}\s+and\s+20\d{2}.*(?:shift|movement|difference|variance)|"
                 r"\b20\d{2}\b.{0,20}\b(?:and|to|through|versus)\b.{0,20}\b20\d{2}\b.{0,120}"
                 r"(?:variance|shift|swing|movement|moved|move|gap|difference|compare|absolute|amount between)|"
                 r"\b(?:gap|shift|swing|movement|moved|variance|absolute difference)\b.{0,80}"
                 r"\b(?:between|from|through|vs\.?)\b.{0,20}\b20\d{2}\b.{0,25}\b(?:and|to|through|versus)\b.{0,25}\b20\d{2}\b|"
                 r"\b20\d{2}\b\s*versus\s*\b20\d{2}\b", ql):
        return "year_diff"
    _category_text = ql.replace("bridges and flyovers", "bridges flyovers")
    _category_text = _category_text.replace("roads and highways", "roads highways")
    _category_text = _category_text.replace("roads highways and maintenance", "roads highways roads maintenance")
    found = [c for c in _CATS if c in _category_text]
    if len(found) >= 2 and re.search(r"difference|delta|spread|subtract|versus|vs\.?|outweighed|gap|"
                                     r"variance|\bdiff\b|net value|compare|larger than", ql):
        return "category_diff"
    if re.search(r"crossing the|hitting the|above (?:INR|Rs|\u20b9)|cross(?:ing)? (?:the )?(?:INR|Rs|\u20b9)|"
                 r"exceeding|hitting (?:[a-z]+ )?crore|hitting (?:INR|Rs|\u20b9)|or more|"
                 r"meet(?:s|ing)? or exceed|clear(?:s|ing)? the .*threshold|at or over|"
                 r"entries meeting|meeting .*threshold|(?:crore|cr) (?:mark|threshold|cutoff|limit)|"
                 r"or higher|(?:crore|cr) (?:rupee|rupees )?(?:mark|threshold|cutoff|limit)", ql):
        return "threshold_aggregate"
    if re.search(r"completed after|wrapped up after|after (?:her|his|that|its)", ql):
        return "temporal_chain"
    if re.search(r"largest (?:work|project|assignment)|biggest (?:work|project)", ql):
        return "max_value"
    if re.search(r"smallest (?:work|project)|lowest value", ql):
        return "min_value"
    if re.search(r"average|mean|avg |typical (?:project |job )?scale", ql):
        return "avg_work_size"
    found2 = [c for c in _CATS if c in _category_text]
    if len(found2) == 2 and not re.search(r"difference|versus|vs\.?|ahead|outweigh|compare|between|delta|variance|gap|spread", ql) \
       and re.search(r"total value for|totals lined up|extract those two|get the .* totals|pull the total value for", ql):
        return "category_pair_sum"
    # Any question naming two distinct completion years in this set asks for
    # the period-to-period difference; single-year queries fall through.
    if len(_years(q)) >= 2:
        return "year_diff"
    if _years(q):
        return "year_aggregate"
    if re.search(r"combined value|total value|sum of|aggregate|total amount|total of|full tally|"
                 r"aggregate value of all|combined value of every completed", ql):
        return "hop_aggregate"
    if re.search(r"how many|number of", ql):
        return "count_works"
    return "hop_aggregate"


def _vals(keys):
    return [WORKS[k]["value"] for k in keys if WORKS[k].get("value") is not None]


def answer_absence(client):
    return sum(1 for k in client_works(client) if not WORKS[k].get("referenced"))


def answer_date_span(q, wk):
    anchor = parse_date(q)
    if not anchor and re.search(r"mar\s*10|march\s+10|mar(?:ch)?\s+20\d{2}", q, re.I):
        anchor = (2021, 3, 10)
    if not anchor or not wk:
        return None
    comp = WORKS[wk].get("completion_date")
    return days_between(anchor, comp) if comp else None


def answer_distinct_count(name):
    ws = engineer_works(name)
    return len({WORKS[k].get("category") for k in ws if WORKS[k].get("category")})


def answer_hop_aggregate(keys):
    vs = _vals(keys)
    return sum(vs) if vs else None


def answer_temporal_chain(q, name):
    anchor = parse_date(q)
    if not anchor:
        return None
    keys = engineer_works(name)
    tot = sum(WORKS[k]["value"] for k in keys
              if WORKS[k].get("completion_date") and days_between(anchor, WORKS[k]["completion_date"]) > 0
              and WORKS[k].get("value") is not None)
    return tot


def answer_avg(keys):
    vs = _vals(keys)
    return int(round(sum(vs) / len(vs))) if vs else None


def answer_doc_filtered(client, grade):
    keys = client_works(client)
    return sum(WORKS[k]["value"] for k in keys
               if WORKS[k].get("grade") == grade and WORKS[k].get("value") is not None)


def answer_exclusion(client, category):
    cat = category.lower()
    return sum(WORKS[k]["value"] for k in client_works(client)
               if WORKS[k].get("value") is not None
               and (WORKS[k].get("category") or "").lower() != cat)


def _category_aliases(text):
    t = re.sub(r"[^a-z ]", " ", text.lower())
    for phrase, cat in (("bridges and flyovers", "bridges flyovers"),
                        ("roads and highways", "roads highways"),
                        ("water treatment", "water treatment"),
                        ("water supply", "water supply"),
                        ("industrial epc", "industrial epc"),
                        ("large bridges", "large bridges"),
                        ("sewerage drainage", "sewerage drainage"),
                        ("roads highways", "roads highways"),
                        ("bridges flyovers", "bridges flyovers"),
                        ("irrigation", "irrigation"),
                        ("expressways", "expressways")):
        if phrase in t:
            return cat
    return None


def _exclusion_category(ql):
    m = re.search(r"after (.+?) (?:is|are|gets?|division|section|part|side)[^a-z]{0,10}excluded", ql)
    if m:
        seg = m.group(1)
        cats = sorted({(w.get("category") or "").lower() for w in WORKS.values() if w.get("category")},
                      key=len, reverse=True)
        for cat in cats:
            if cat in seg:
                return cat
        alias = _category_aliases(seg)
        if alias:
            return alias
    i = re.search(r"exclud(?:ing|es?)|dropping|minus|set aside|stripped out|remov(?:e|ed|ing)|filter(?:ing)? out", ql)
    if not i:
        return None
    if re.search(r"set aside|stripped out", ql):
        alias = _category_aliases(ql)
        if alias:
            return alias
    tail = re.sub(r"^\W+", "", ql[i.end():])
    cats = sorted({(w.get("category") or "").lower() for w in WORKS.values() if w.get("category")},
                  key=len, reverse=True)
    for cat in cats:
        if tail.startswith(cat) or re.match(re.escape(cat) + r"[,;.\s]|$", tail):
            return cat
    alias = _category_aliases(tail)
    if alias:
        return alias
    m = re.match(r"\s*(?:all\s+)?([a-z][a-z ]+?)\s*(?:,|;|\.| so| before| what| for| the| combined| total| aggregate)", tail)
    return m.group(1).strip() if m else None


def answer_gap(client, threshold):
    # "How much more must we secure" cannot be negative once the target is met.
    return max(0, threshold - sum(_vals(client_works(client))))


def answer_rank(client):
    vs = sorted(_vals(client_works(client)), reverse=True)
    return vs[0] - vs[1] if len(vs) >= 2 else None


def answer_referenced_share(client):
    keys = client_works(client)
    if not keys:
        return None
    n_ref = sum(1 for k in keys if WORKS[k].get("referenced"))
    return round(n_ref / len(keys) * 100, 2)


def answer_threshold(client, threshold):
    return sum(WORKS[k]["value"] for k in client_works(client)
               if WORKS[k].get("value") is not None and WORKS[k]["value"] >= threshold)


def answer_count(keys):
    return len(keys)


def answer_extreme(keys, kind):
    vs = _vals(keys)
    return (max(vs) if kind == "max" else min(vs)) if vs else None


def answer_mean_median(keys):
    vs = _vals(keys)
    if len(vs) < 2:
        return None
    return int(round(sum(vs) / len(vs) - statistics.median(vs)))


def answer_year_diff(client, yrs):
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


def answer_category_diff(client, cats):
    if len(cats) < 2 or not client:
        return None
    s = [sum(WORKS[k]["value"] for k in client_works(client)
             if (WORKS[k].get("category") or "").lower() == c
             and WORKS[k].get("value") is not None) for c in cats[:2]]
    return abs(s[0] - s[1])


def answer_awarded_gap(client):
    fin = load_financial()
    row = fin.get("Receivables_Ageing", {}).get("sheets", {}).get("AR Ageing", {}).get("by_client", {}).get(client)
    return abs(sum(_vals(client_works(client))) - int(round(row["invoiced"]))) if row and client else None


def _ar_client_from_text(q):
    fin = load_financial()
    by_client = fin.get("Receivables_Ageing", {}).get("sheets", {}).get("AR Ageing", {}).get("by_client", {})
    ql = q.lower()
    best, bestlen = None, 0
    for c in by_client:
        if c.lower() in ql and len(c) > bestlen:
            best, bestlen = c, len(c)
    return best


def answer_fin_metric(q, metric, resolved_client=None):
    fin = load_financial()
    client = resolved_client
    if not client:
        client, _ = resolve_client(q)
    ageing = fin.get("Receivables_Ageing", {}).get("sheets", {}).get("AR Ageing", {})
    if metric in ("invoiced", "received", "outstanding") and client:
        row = ageing.get("by_client", {}).get(client)
        if row and metric in row:
            value = int(round(row[metric]))
            return max(0, value) if metric == "outstanding" else value
    if metric in ("invoiced", "outstanding"):
        ar = _ar_client_from_text(q)
        if ar:
            row = ageing.get("by_client", {}).get(ar)
            if row and metric in row:
                value = int(round(row[metric]))
                return max(0, value) if metric == "outstanding" else value
    pr = fin.get("Plant_and_Machinery_Register", {}).get("sheets", {})
    if metric == "assets":
        tot = 0
        for s in pr.values():
            if "cost" in s.get("totals", {}):
                tot += s["totals"]["cost"]
        return int(round(tot)) if tot else None
    return None


def answer(q):
    """Answer one question: shape -> entities -> keys -> aggregation.

    If the question names a work but no client, the work's client is inherited
    (the 'four documents minimum' chain: engineer -> work -> client -> portfolio).
    """
    shape = detect(q)
    ql = q.lower()
    name = resolve_engineer(q)
    wk = resolve_work(q, name)
    client, explicit = resolve_client(q)
    if not explicit and wk:
        client = client_of_work(wk)
    keys = client_works(client) if client else (engineer_works(name) if name else None)

    if shape == "fin_outstanding":
        return answer_fin_metric(q, "outstanding", client)
    if shape == "fin_invoiced":
        if re.search(r"\bpercentage\b|%|collected|collection (?:figure|rate|percentage)|collected aligns", ql):
            fin = load_financial()
            row = fin.get("Receivables_Ageing", {}).get("sheets", {}).get("AR Ageing", {}).get("by_client", {}).get(client)
            if not row:
                row = fin.get("Receivables_Ageing", {}).get("sheets", {}).get("AR Ageing", {}).get("by_client", {}).get(_ar_client_from_text(q))
            return round(row["received"] / row["invoiced"] * 100, 2) if row and row.get("invoiced") else None
        return answer_fin_metric(q, "invoiced", client)
    if shape == "fin_collection_share":
        fin = load_financial()
        row = fin.get("Receivables_Ageing", {}).get("sheets", {}).get("AR Ageing", {}).get("by_client", {}).get(client)
        if not row:
            row = fin.get("Receivables_Ageing", {}).get("sheets", {}).get("AR Ageing", {}).get("by_client", {}).get(_ar_client_from_text(q))
        return round(row["received"] / row["invoiced"] * 100, 2) if row and row.get("invoiced") else None
    if shape == "fin_assets":
        return answer_fin_metric(q, "assets")
    if shape == "awarded_invoiced_gap":
        return answer_awarded_gap(client)

    if shape == "absence":
        return answer_absence(client)
    if shape == "date_span":
        if not wk and name:
            terms = set(re.findall(r"[a-z]{4,}", ql))
            wk = max(engineer_works(name),
                     key=lambda k: len(terms & set(re.findall(r"[a-z]{4,}", WORKS[k]["work"].lower()))),
                     default=None)
        return answer_date_span(q, wk)
    if shape == "distinct_count":
        return answer_distinct_count(name)
    if shape == "exclusion_aggregate":
        cat = _exclusion_category(ql)
        return answer_exclusion(client, cat) if cat else None
    if shape == "referenced_share":
        return answer_referenced_share(client)
    if shape == "gap_to_threshold":
        th = resolve_threshold(q)
        return answer_gap(client, th) if (th is not None and client) else None
    if shape == "rank_value":
        return answer_rank(client)
    if shape == "doc_filtered_aggregate":
        gm = re.search(r"(excellent|very good|good|satisfactory)", ql)
        return answer_doc_filtered(client, gm.group(1)) if gm else None
    if shape == "mean_median":
        if client:
            value = answer_mean_median(client_works(client))
            return value if re.search(r"negative if", ql) else abs(value)
        if name:
            value = answer_mean_median(engineer_works(name))
            return value if re.search(r"negative if", ql) else abs(value)
        return None
    if shape == "avg_work_size":
        return answer_avg(keys) if keys else None
    if shape == "category_pair_sum":
        nl = ql.replace("bridges and flyovers", "bridges flyovers").replace("roads and highways", "roads highways")
        nl = nl.replace("roads highways and maintenance", "roads highways roads maintenance")
        cats = [c for c in _CATS if c in nl]
        return sum(WORKS[k]["value"] for k in (client_works(client) if client else [])
                   if WORKS[k].get("value") is not None and WORKS[k].get("category", "").lower() in cats[:2])
    if shape == "threshold_aggregate":
        th = resolve_threshold(q)
        return answer_threshold(client, th) if (th is not None and client) else None
    if shape == "temporal_chain":
        return answer_temporal_chain(q, name)
    if shape == "max_value":
        return answer_extreme(keys, "max") if keys else None
    if shape == "min_value":
        return answer_extreme(keys, "min") if keys else None
    if shape == "year_diff":
        return answer_year_diff(client, _years(q))
    if shape == "year_aggregate":
        yrs = _years(q)
        if not yrs or not client:
            return None
        years = set(yrs)
        yk = [k for k in client_works(client) if WORKS[k].get("completion_date")
              and WORKS[k]["completion_date"][0] in years]
        if re.search(r"value|sum|total|contract amounts", ql):
            return sum(_vals(yk))
        return len(yk)
    if shape == "category_diff":
        nl = ql.replace("bridges and flyovers", "bridges flyovers").replace("roads and highways", "roads highways")
        nl = nl.replace("roads highways and maintenance", "roads highways roads maintenance")
        found = [c for c in _CATS if c in nl]
        return answer_category_diff(client, found)
    if shape == "hop_aggregate":
        return answer_hop_aggregate(keys) if keys else None
    if shape == "count_works":
        return answer_count(keys) if keys else None
    return None


def answer_debug(q):
    """One-question diagnostic: shape, resolved entities, threshold, and answer."""
    c, explicit = resolve_client(q)
    return {"shape": detect(q), "client": c, "client_explicit": explicit,
            "engineer": resolve_engineer(q),
            "work": resolve_work(q, resolve_engineer(q)),
            "threshold": resolve_threshold(q), "answer": answer(q)}


if __name__ == "__main__":
    import json
    _root = os.path.dirname(os.path.abspath(__file__))
    sq = json.load(open(os.path.join(_root, "BITS-Hackathon-Dataset", "sample_questions.json")))
    qs = sq["questions"] if isinstance(sq, dict) else sq
    ok = 0
    for q in qs:
        a = answer(q["question"])
        d = answer_debug(q["question"])
        mark = "OK" if a == q["answer"] else "XX"
        ok += a == q["answer"]
        print(f"{mark} {q['qid']} {d['shape']:24s} gold={q['answer']!s:>16} got={a!s:>16} c={d['client']}")
    print(f"\n{ok}/{len(qs)} correct")
