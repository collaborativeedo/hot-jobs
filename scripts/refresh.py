"""Nightly refresh for the Lane County Hot Jobs index.

Pulls every Lane County posting from the QualityInfo Job Finder (Oregon
Employment Department), cleans and tags it, keeps a first-seen / last-seen
history, and writes docs/jobs.json for the widget to read.

QualityInfo's robots.txt allows automated access. OED's own job site
(secure.emp.state.or.us) does not, so this script never visits it: it only
reads the QualityInfo listing pages and records the links they contain.

Run: python scripts/refresh.py            (live pull)
     python scripts/refresh.py --fixture tests/fixture_page.html   (offline test)
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
import rules  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "jobs.json"
STATE = ROOT / "data" / "state.json"
EMPLOYERS = ROOT / "data" / "employers.json"
EMPLOYERS_CSV = ROOT / "docs" / "employers.csv"
TRACE_CSV = ROOT / "docs" / "to-trace.csv"

ENDPOINT = "https://www.qualityinfo.org/jfind"
PARAMS = {
    "p_p_id": "QiDatatoolJobfinder_INSTANCE_6Wky8xJkv6LX",  # QualityInfo's Job Finder component; check here first if pulls start failing
    "p_p_lifecycle": "2",
    "p_p_state": "normal",
    "p_p_mode": "view",
    "p_p_resource_id": "getReportHtml",
    "p_p_cacheability": "cacheLevelPage",
    "rt": "",
    "jobFindSearchTerm": "",
    "occCodeTypePref": "19",
    "jobFindArea": "4104000039",  # Lane County
    "jobFindDistance": "25",
    "jobFindSource": "",
}
DAYS = 30            # pull postings from the last 30 days so open jobs are not dropped early
MISSES_TO_CLOSE = 3  # a job closes after this many nightly runs without appearing
PAUSE = 1.0          # seconds between page requests, to be polite
HEADERS = {"User-Agent": "LaneCountyHotJobs/0.1 (nonprofit workforce pilot; Collaborative Economic Development Oregon)"}


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def parse_page(html):
    """Return (total_openings, [job dicts]) for one QualityInfo results page."""
    soup = BeautifulSoup(html, "html.parser")
    total = soup.find("input", id="totalOpenings")
    total = int(total["value"]) if total and total.get("value", "").isdigit() else None
    jobs = []
    for block in soup.select("div.openingdiv"):
        a = block.select_one("span.jobtitle a")
        if not a:
            continue
        summary = block.select_one("div.summary")
        snippet = ""
        if summary:
            for more in summary.select("a"):
                more.decompose()
            snippet = clean(summary.get_text(" "))
        wage = block.select_one(".wagelink a")
        soc = (wage.get("href", "") if wage else "").replace("#wage", "")
        posted = clean(block.select_one(".date").get_text()) if block.select_one(".date") else ""
        m = re.search(r"(\d+) days? ago", posted)
        days = int(m.group(1)) if m else (1 if "yesterday" in posted.lower() else 0)
        src = clean(block.select_one(".opening_source").get_text()) if block.select_one(".opening_source") else ""
        jobs.append({
            "title": clean(a.get_text()),
            "city": clean(block.select_one(".location").get_text()) if block.select_one(".location") else "",
            "url": a.get("href", "").replace("http://secure.emp", "https://secure.emp"),
            "source": src.replace("External Job Board - ", "").replace("Oregon Employment Department", "OED"),
            "days": days,
            "soc": soc if soc.isdigit() else "",
            "occupation": clean(wage.get_text()).replace("Typical Wages for", "").strip() if wage else "",
            "snippet": snippet,
        })
    return total, jobs


def pull_live():
    jobs, last_sig = [], None
    session = requests.Session()
    session.headers.update(HEADERS)
    for page in range(1, 500):
        params = dict(PARAMS, jobFindDays=str(DAYS), jobFindPageNumber=str(page))
        r = session.get(ENDPOINT, params=params, timeout=60)
        r.raise_for_status()
        total, batch = parse_page(r.text)
        if not batch:
            break
        sig = "|".join(j["title"] + j["url"] for j in batch)
        if sig == last_sig:  # QualityInfo repeats the last page past the end
            break
        last_sig = sig
        jobs.extend(batch)
        if total and len(jobs) >= total:
            break
        time.sleep(PAUSE)
    return total, jobs


def job_id(j):
    return hashlib.sha1((j["url"] or j["title"] + j["city"]).encode()).hexdigest()[:12]


def dedupe(jobs):
    seen, out = set(), []
    for j in jobs:
        key = (j["title"].lower(), j["city"], j["snippet"][:60].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(j)
    return out


def tag(j):
    text = f'{j["title"]} {j["snippet"]} {j["url"]}'
    j["type"] = rules.type_of_work(j["soc"])
    j["industries"] = rules.industries(text)
    j["employer"] = rules.employer(text)
    j["route"] = rules.route(j["url"])
    j["rural"] = j["city"] not in rules.METRO
    j["priority"] = j["type"] in rules.PRIORITY or any(i in rules.PRIORITY for i in j["industries"])
    return j


def update_employers(jobs, today):
    """Keep a running record of every employer the nightly run has seen.

    Writes docs/employers.csv for the registry Google Sheet to pull in, and
    docs/to-trace.csv listing postings that do not name an employer.
    """
    emps = json.loads(EMPLOYERS.read_text()) if EMPLOYERS.exists() else {}
    for e in emps.values():
        e["open_now"] = 0
        e["cities_now"] = []
    for j in jobs:
        name = j["employer"]
        plat = rules.platform(j["url"])
        if not name:
            if not plat:
                continue  # unnamed OED or job-board posting: goes to to-trace.csv instead
            name = f"Unnamed employer ({plat})"
        e = emps.setdefault(name, {"first_seen": today, "industry": rules.employer_industry(name),
                                   "platform": "", "careers_page": "", "found_via": [], "total_seen": 0,
                                   "open_now": 0, "cities_now": []})
        e["last_seen"] = today
        e["open_now"] += 1
        if j["city"] not in e["cities_now"]:
            e["cities_now"].append(j["city"])
        if j["route"] not in e["found_via"]:
            e["found_via"].append(j["route"])
        if plat and not e["platform"]:
            e["platform"] = plat
            e["careers_page"] = rules.careers_page(j["url"], plat)
            e["example_posting"] = j["url"]
    for e in emps.values():
        e["total_seen"] = e.get("total_seen", 0) + (1 if e["open_now"] else 0)
    EMPLOYERS.write_text(json.dumps(emps, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    cols = ["Employer", "Industry", "Hiring platform", "Careers page", "Lane postings open now", "Lane cities now",
            "Found via", "First seen", "Last seen", "Nights seen hiring", "Example posting"]
    with EMPLOYERS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for name, e in sorted(emps.items(), key=lambda kv: (-kv[1]["open_now"], kv[0].lower())):
            w.writerow([name, e.get("industry", ""), e.get("platform", ""), e.get("careers_page", ""), e["open_now"],
                        ", ".join(sorted(e["cities_now"])), ", ".join(sorted(e["found_via"])), e["first_seen"],
                        e.get("last_seen", ""), e.get("total_seen", 0), e.get("example_posting", "")])
    with TRACE_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Job title", "City", "How it was posted", "Posting link", "First seen"])
        for j in jobs:
            if not j["employer"] and not rules.platform(j["url"]):
                w.writerow([j["title"], j["city"], j["route"], j["url"], j.get("first_seen", today)])
    return len(emps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="parse a saved results page instead of pulling live")
    args = ap.parse_args()

    if args.fixture:
        # Offline test: write to tests/out/ so real data is never touched.
        global OUT, STATE, EMPLOYERS, EMPLOYERS_CSV, TRACE_CSV
        t = ROOT / "tests" / "out"
        t.mkdir(parents=True, exist_ok=True)
        OUT, STATE, EMPLOYERS = t / "jobs.json", t / "state.json", t / "employers.json"
        EMPLOYERS_CSV, TRACE_CSV = t / "employers.csv", t / "to-trace.csv"
        for f in (STATE, EMPLOYERS):
            f.unlink(missing_ok=True)
        total, raw = parse_page(Path(args.fixture).read_text(encoding="utf-8"))
    else:
        total, raw = pull_live()

    if not raw:
        # Never overwrite good data with an empty pull: fail loudly so the run shows red.
        sys.exit("No listings parsed. QualityInfo may have changed its page; check PARAMS and parse_page().")

    jobs = [tag(j) for j in dedupe(raw)]
    today = dt.date.today().isoformat()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    live_ids = set()
    for j in jobs:
        jid = job_id(j)
        live_ids.add(jid)
        rec = state.get(jid, {"first_seen": today})
        rec.update(last_seen=today, misses=0, title=j["title"], employer=j["employer"], city=j["city"], soc=j["soc"])
        state[jid] = rec
        j["id"] = jid
        j["first_seen"] = rec["first_seen"]
    for jid, rec in state.items():
        if jid not in live_ids:
            rec["misses"] = rec.get("misses", 0) + 1
            if rec["misses"] >= MISSES_TO_CLOSE and "closed" not in rec:
                rec["closed"] = today

    out = {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "source": "QualityInfo Job Finder, Oregon Employment Department",
        "area": "Lane County, Oregon",
        "window_days": DAYS,
        "reported_total": total,
        "count": len(jobs),
        "jobs": [{k: j[k] for k in ("id", "title", "city", "employer", "type", "industries", "rural", "priority",
                                    "route", "source", "days", "first_seen", "soc", "occupation", "url")}
                 | {"snippet": j["snippet"][:160]} for j in jobs],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    n_emp = update_employers(jobs, today)
    print(f"Employers on record: {n_emp}.")
    print(f"QualityInfo reported {total}; parsed {len(raw)}; kept {len(jobs)} after duplicates; "
          f"{sum(1 for r in state.values() if 'closed' in r)} closed to date.")


if __name__ == "__main__":
    main()
