"""O*NET occupation data for Hot Jobs, from the free O*NET database files (CC BY 4.0).

    python scripts/onet.py            # download O*NET 31.0 and write data/onet.json

What it keeps, by 6-digit occupation code (the code Hot Jobs already tags each posting with):
  t    occupation title                     ("Pharmacy Technicians")
  d    first sentence of its description    (for "About this kind of job")
  z    job zone, 1-5                         (how much preparation it takes)
  rel  related occupations, closest first    (for "Similar jobs hiring now")
  k    skill, tool and software terms        (so search can find jobs by what someone can do)
plus a title index (55,000+ job titles -> occupation) used to tag postings whose titles the
hand-written rules miss. Titles that O*NET files under more than one occupation are left out.

This page includes information from the O*NET 31.0 Database by the U.S. Department of Labor, Employment and
Training Administration (USDOL/ETA). Used under the CC BY 4.0 license. O*NET® is a trademark of USDOL/ETA.
Hot Jobs has modified the information (shortened descriptions, combined detailed occupations, selected terms);
USDOL/ETA has not approved, endorsed, or tested these modifications.
"""
import csv
import io
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import requests

VERSION = "31.0"
BASE = f"https://www.onetcenter.org/dl_files/database/db_{VERSION.replace('.', '_')}_csv/"
OUT = Path(__file__).resolve().parent.parent / "data" / "onet.json"
HEADERS = {"User-Agent": "LaneCountyHotJobs/0.1 (public beta; Collaborative Economic Development Oregon)"}

STOP = set("""a about above across after again against all also among an and any are around as at be because been before
being below between both but by can could did do does doing down during each either etc ensure few for from further had
has have having how if in into is it its itself just may might more most must no nor not of off on once only or other our
out over own per perform performing provide providing same should so some such than that the their them then there these
they this those through to too under until up upon use used using various very via was we were what when where which while
who whom why will with within without would you your activities appropriate assist assigned based duties including
information maintain maintaining necessary need needed new related records record required requirements review reviewing
specific such standard standards work working according other others procedures procedure prepare preparing determine
determining operations operating ensure identify identifying make making meet meetings plan planning daily general""".split())


def get(name):
    r = requests.get(BASE + name + ".csv", headers=HEADERS, timeout=120)
    r.raise_for_status()
    r.encoding = "utf-8"
    return list(csv.DictReader(io.StringIO(r.text)))


def soc6(code):
    return re.sub(r"\D", "", (code or "").split(".")[0])


def norm(t):
    t = re.sub(r"\(.*?\)", " ", (t or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def first_sentence(text):
    m = re.match(r"(.+?[.;])(\s|$)", (text or "").strip())
    return (m.group(1) if m else (text or "")).rstrip(";").strip()[:300]


def build():
    occ = {}
    primary = {}
    for r in get("occupation_data"):
        s, code = soc6(r["O*NET-SOC Code"]), r["O*NET-SOC Code"]
        if s not in occ or code.endswith(".00"):
            occ[s] = {"t": r["Title"], "d": first_sentence(r["Description"])}
            primary[s] = code
    for r in get("job_zones"):
        s = soc6(r["O*NET-SOC Code"])
        if s in occ and (r["O*NET-SOC Code"] == primary.get(s) or "z" not in occ[s]):
            occ[s]["z"] = int(float(r["Job Zone"]))

    # Related occupations, closest first: Primary-Short, then Primary-Long, then the rest, by O*NET's index.
    tier = {"Primary-Short": 0, "Primary-Long": 1, "Supplemental": 2}
    rel = defaultdict(list)
    for r in get("related_occupations"):
        a, b = soc6(r["O*NET-SOC Code"]), soc6(r["Related O*NET-SOC Code"])
        if a != b:
            rel[a].append((tier.get(r["Relatedness Tier"], 3), int(r["Index"] or 99), b))
    for s, items in rel.items():
        if s in occ:
            seen = []
            for _, _, b in sorted(items):
                if b not in seen:
                    seen.append(b)
            occ[s]["rel"] = seen[:12]

    # Terms people search by: software and important skills/knowledge by name, plus the most distinctive words
    # in each occupation's task statements (TF-IDF), e.g. "forklift", "pallets", "spreadsheets", "patients".
    terms = defaultdict(list)
    office = ("11", "13", "15", "17", "19", "21", "23", "25", "27", "29", "41", "43")  # software matters in these
    for r in get("software_skills"):
        s = soc6(r["O*NET-SOC Code"])
        if s[:2] in office and r.get("Hot Technology") == "Y":
            terms[s].append(r["Workplace Example"])
    for name in ("essential_skills", "transferable_skills", "knowledge"):
        for r in get(name):
            if r.get("Scale ID") == "IM" and float(r.get("Data Value") or 0) >= 3.5 and r.get("Recommend Suppress") != "Y":
                terms[soc6(r["O*NET-SOC Code"])].append(r["Element Name"])
    job_titles = get("job_titles")

    def distinctive(rows, field, top):
        words = defaultdict(Counter)
        for r in rows:
            for w in re.findall(r"\b[a-z]{4,}\b", (r.get(field) or "").lower()):
                if w not in STOP:
                    words[soc6(r["O*NET-SOC Code"])][w] += 1
        df = Counter(w for c in words.values() for w in c)
        n = len(words) or 1
        for s, c in words.items():
            terms[s] += sorted(c, key=lambda w: -c[w] * math.log(n / df[w]))[:top]
    distinctive(job_titles, "Job Title", 15)        # "forklift", "reach", "phlebotomist"
    distinctive(get("task_statements"), "Task", 25)  # "pallets", "spreadsheets", "patients"
    for s, t in terms.items():
        if s in occ:
            out, seen = [], set()
            for x in t:
                k = x.strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    out.append(k)
            occ[s]["k"] = out[:60]

    # Title index: every job title O*NET knows. A title O*NET lists under several occupations goes to the one whose
    # workers reported it (O*NET's "sample of reported titles"), or failing that the occupation listing it most often;
    # it's left out when that still doesn't single one out.
    votes = defaultdict(Counter)
    for r in job_titles:
        s = soc6(r["O*NET-SOC Code"])
        for t in (r.get("Job Title"), r.get("Short Title")):
            if t:
                votes[norm(t)][s] += 1
    reported = defaultdict(set)
    for r in get("sample_of_reported_titles"):
        reported[norm(r["Reported Job Title"])].add(soc6(r["O*NET-SOC Code"]))
    for s, o in occ.items():
        t = norm(o["t"])
        reported[t].add(s)
        if t.endswith("s"):
            reported[t[:-1]].add(s)  # "Pharmacy Technicians" -> "pharmacy technician"
    titles = {}
    for t in set(votes) | set(reported):
        if not t:
            continue
        if len(reported.get(t, ())) == 1:
            titles[t] = next(iter(reported[t]))
            continue
        c = votes.get(t)
        if c:
            top = c.most_common(2)
            if len(top) == 1 or top[0][1] >= 2 * top[1][1]:
                titles[t] = top[0][0]
    return {"version": VERSION, "credit": ("This page includes information from the O*NET 31.0 Database by the U.S. "
            "Department of Labor, Employment and Training Administration (USDOL/ETA). Used under the CC BY 4.0 license. "
            "O*NET® is a trademark of USDOL/ETA. Hot Jobs has modified the information; USDOL/ETA has not approved, "
            "endorsed, or tested these modifications."), "occ": occ, "titles": titles}


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"O*NET {data['version']}: {len(data['occ'])} occupations, {len(data['titles'])} titles "
          f"({OUT.stat().st_size // 1024} KB).", file=sys.stderr)
