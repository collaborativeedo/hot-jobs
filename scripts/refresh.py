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
from collections import Counter
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
import direct  # noqa: E402
import enrich  # noqa: E402
import ats  # noqa: E402
import dashboard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "jobs.json"
STATE = ROOT / "data" / "state.json"
EMPLOYERS = ROOT / "data" / "employers.json"
EMPLOYERS_CSV = ROOT / "docs" / "employers.csv"
TRACE_CSV = ROOT / "docs" / "to-trace.csv"
TRACE_EMP_CSV = ROOT / "docs" / "employers-to-trace.csv"  # employers we see only secondhand, ranked by openings
NLX_ALL = []
PULLED = ROOT / "data" / "pulled.json"
SOURCES = ROOT / "data" / "sources.json"        # hiring systems learned automatically, pulled directly each night
DOMAIN_NAMES = ROOT / "data" / "domain-names.json"  # employer names read from careers sites' own pages
SOURCES_CSV = ROOT / "docs" / "sources.csv"
EMPLOYER_SITES = ROOT / "data" / "employer-sites.json"  # employers found by name, with their careers pages
# Hiring systems the nightly run finds on its own (trace step) go in their own file, so the run never edits the
# hand-kept list above and a staff change made while the run is going can't be overwritten when results are saved.
EMPLOYER_SITES_FOUND = ROOT / "data" / "employer-sites-found.json"


def registry_sites():
    """The hand-kept registry plus hiring systems the nightly run found; the hand-kept entry wins."""
    sites = json.loads(EMPLOYER_SITES.read_text()) if EMPLOYER_SITES.exists() else []
    have = {(e.get("careers_url") or "").lower().rstrip("/") for e in sites}
    if EMPLOYER_SITES_FOUND.exists():
        sites += [e for e in json.loads(EMPLOYER_SITES_FOUND.read_text())
                  if (e.get("careers_url") or "").lower().rstrip("/") not in have]
    return sites
RUNLOG = ROOT / "data" / "run-log.json"    # what each nightly run did, including errors
WAGES = ROOT / "data" / "wages.json"            # average pay by occupation for Lane County and Oregon (QualityInfo)
OED_DETAILS = ROOT / "data" / "oed-details.json"  # hours, pay and description from WorkSource Oregon listing pages
QI_LAST = ROOT / "data" / "qualityinfo-last.json"  # last good QualityInfo pull, used if QualityInfo is down  # every posting from the last pull, before the widget filter

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
SHOW_DAYS = 14       # the widget shows postings up to this many days old; older ones are often already filled
KNOWN_NAMES = []        # filled in add_details
ADD_DETAILS_LOG = []
SHOW_DAYS_CHECKED = 45  # ...or up to this many days old when checked live in the last few nights (not job-board reposts)
CHECKED_WITHIN = 4      # days: a "Checked" date this recent counts as live (matches the saved-read limit)
SKIP_HOSTS = ("indeed.com", "simplyhired.com")  # reposts here are often expired or behind a "confirm you're human" check
MAX_OED_PAGES = 600  # WorkSource listing pages read per night (each is read once, then cached)
WAGE_TABLE = {}      # filled while reading QualityInfo pages
HEADERS = {"User-Agent": "LaneCountyHotJobs/0.1 (nonprofit workforce public beta; Collaborative Economic Development Oregon)"}


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def parse_page(html):
    """Return (total_openings, [job dicts]) for one QualityInfo results page."""
    soup = BeautifulSoup(html, "html.parser")
    WAGE_TABLE.update(enrich.parse_wage_boxes(soup))
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
            "city": re.sub(r"(?i)^\[?unknown city\]?$", "Lane County", clean(block.select_one(".location").get_text())) if block.select_one(".location") else "Lane County",
            "url": a.get("href", "").replace("http://secure.emp", "https://secure.emp"),
            "source": src.replace("External Job Board - ", "").replace("Oregon Employment Department", "OED"),
            "days": days,
            "soc": soc if soc.isdigit() else "",
            "occupation": clean(wage.get_text()).replace("Typical Wages for", "").strip() if wage else "",
            "snippet": snippet,
        })
    return total, jobs


def pull_live(log):
    """Every Lane County posting from QualityInfo. Retries each page before giving up."""
    jobs, last_sig, total = [], None, None
    session = requests.Session()
    session.headers.update(HEADERS)
    for page in range(1, 500):
        params = dict(PARAMS, jobFindDays=str(DAYS), jobFindPageNumber=str(page))
        for attempt in range(1, 4):
            try:
                r = session.get(ENDPOINT, params=params, timeout=60)
                r.raise_for_status()
                break
            except requests.RequestException as e:
                log.append(f"QualityInfo page {page}, try {attempt}: {type(e).__name__}: {str(e)[:200]}")
                if attempt == 3:
                    raise
                time.sleep(30 * attempt)
        total, batch = parse_page(r.text)
        if not batch:
            if page == 1:
                log.append(f"QualityInfo page 1 had no listings (HTTP {r.status_code}, {len(r.text)} bytes): "
                           + re.sub(r"\s+", " ", r.text)[:300])
            break
        sig = "|".join(j["title"] + j["url"] for j in batch)
        if sig == last_sig:  # QualityInfo repeats the last page past the end
            break
        last_sig = sig
        jobs.extend(batch)
        if total and len(jobs) >= total:
            break
        time.sleep(PAUSE)
    log.append(f"QualityInfo: {len(jobs)} listings from {page} pages (reported {total}).")
    return total, jobs


def write_run_log(entry):
    runs = json.loads(RUNLOG.read_text()) if RUNLOG.exists() else []
    runs = (runs + [entry])[-40:]
    RUNLOG.parent.mkdir(parents=True, exist_ok=True)
    RUNLOG.write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")


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
    j["type"] = rules.type_of_work(j["soc"]) if j.get("soc") else rules.type_from_title(j["title"])
    j["industries"] = rules.industries(text)
    j["employer"] = j.get("employer") or rules.employer(text) or rules.employer_from_url(j["url"])
    j["route"] = rules.route(j["url"])
    j["rural"] = j["city"] not in rules.METRO
    j["priority"] = j["type"] in rules.PRIORITY or any(i in rules.PRIORITY for i in j["industries"])
    return j


_GENERIC_NAME = re.compile(r"^(careers?|jobs?|home|job search|search jobs|join our team|current openings|employment|"
                           r"opportunities|welcome|apply|candidate experience|job board|career site|recruiting|"
                           r"paycom|adp|workforce now|paychex|icims|oracle|ultipro|ukg|successfactors|"
                           r"applicant tracking|login|sign in)( (page|site|portal|search))?$", re.I)


def site_name(fetcher, url):
    """An organization's name from its own web page (og:site_name, then the page title), or ''."""
    try:
        h = fetcher.get(url).text[:200000]
    except Exception as e:  # noqa: BLE001
        print(f"  name lookup skipped for {url}: {e}")
        return ""
    soup = BeautifulSoup(h, "html.parser")
    og = soup.find("meta", attrs={"property": "og:site_name"})
    cands = [og.get("content", "")] if og else []
    if soup.title:
        cands += re.split(r"\s+[|\-–—:]\s+", soup.title.get_text())
    for c in cands:
        c = clean(c)
        c = re.sub(r"(?i)^(careers?|jobs?)\s+(at|with)\s+", "", c)
        c = re.sub(r"(?i)\s*(careers?|jobs?|job board|career site)( (at|with))?\s*$", "", c).strip()
        if c and not _GENERIC_NAME.match(c) and len(c) <= 60:
            return c
    return ""


def auto_name_domains(jobs, fetcher, today):
    """Name employers on unfamiliar careers sites and hiring-platform pages from the page's own name.

    Runs without anyone's review: results are cached in data/domain-names.json, and a page that
    gave no usable name is retried after 30 days.
    """
    names = json.loads(DOMAIN_NAMES.read_text()) if DOMAIN_NAMES.exists() else {}
    tried = 0
    for j in jobs:
        plat = rules.platform(j["url"])
        if j["employer"] or not plat:
            continue
        if plat == "Employer website":
            key = re.sub(r"^https?://([^/]+).*$", r"\1", j["url"]).lower()
            page = f"https://{key}/"
        else:
            page = rules.careers_page(j["url"], plat)
            key = page
        if not page:
            continue
        rec = names.get(key)
        if rec is None or (not rec["name"] and (dt.date.fromisoformat(today) - dt.date.fromisoformat(rec["checked"])).days > 30):
            if tried >= 60:
                continue
            tried += 1
            rec = names[key] = {"name": site_name(fetcher, page), "checked": today}
        if rec["name"]:
            j["employer"] = rec["name"]
    DOMAIN_NAMES.write_text(json.dumps(names, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def read_oed_pages(jobs, fetcher, today, log):
    """Hours, pay and full description from WorkSource Oregon listing pages (never the contact question)."""
    cache = json.loads(OED_DETAILS.read_text()) if OED_DETAILS.exists() else {}
    live, fetched, failed = set(), 0, 0
    for j in jobs:
        page = j.get("oed_url") or (j["url"] if j["route"] == "WorkSource Oregon listing" else "")
        o = enrich.oed_ord(page) if page else ""
        if not o:
            continue
        live.add(o)
        if o not in cache and fetched < MAX_OED_PAGES and not late(0.8):
            fetched += 1
            try:
                cache[o] = dict(enrich.parse_oed_page(fetcher.get(page).text), fetched=today)
            except Exception as e:  # noqa: BLE001
                failed += 1
                if failed <= 3:
                    log.append(f"WorkSource page {o}: {type(e).__name__}: {str(e)[:150]}")
                if failed >= 15 and fetched == failed:
                    log.append("WorkSource pages: stopped after repeated failures.")
                    break
        if o in cache:
            j["oed"] = cache[o]
    cache = {k: v for k, v in cache.items() if k in live}
    OED_DETAILS.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    log.append(f"WorkSource pages: {fetched} read tonight, {failed} failed, {len(cache)} on file.")


RUN_START = time.time()
RUN_LIMIT = float(__import__("os").environ.get("HOTJOBS_RUN_MINUTES", "200")) * 60  # soft limit; the workflow's is 300
PROGRESS = ROOT / "data" / "run-progress.json"  # saved as the run goes, so a run that is stopped still shows where


def late(share=1.0):
    """True once this run has used the given share of its time limit; later steps then use saved results."""
    return time.time() - RUN_START > RUN_LIMIT * share


def progress(step, **kw):
    try:
        PROGRESS.write_text(json.dumps({"step": step, "minutes": round((time.time() - RUN_START) / 60, 1),
                                        "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), **kw}),
                            encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


WORKPLACE_TYPE = {"Healthcare": "Healthcare & human services", "Retail": "Retail & sales",
                  "Restaurants & hospitality": "Hospitality & leisure", "Education & childcare": "Childcare & education",
                  "Construction & trades": "Construction & trades", "Manufacturing": "Manufacturing",
                  "Banking & finance": "Finance & accounting", "Technology": "Technology",
                  "Transportation & logistics": "Transportation & logistics", "Food & beverage": "Manufacturing",
                  "Wood products & forestry": "Natural resources", "Bioscience": "Engineering & science",
                  "Nonprofit & social services": "Healthcare & human services",
                  "Engineering & professional services": "Engineering & science"}
REMOTE_CAP = 15  # remote postings kept per employer per night
BROWSER_BUDGET = 70 * 60  # seconds of careers-page reading per night; the rest use their last read
POSTING_DETAILS = ROOT / "data" / "posting-details.json"  # pay and hours read from employers' own posting pages
MAX_POSTING_PAGES = 1500
_DATA_API = re.compile(r"myworkdayjobs|oraclecloud|ultipro|ukg\.net", re.I)  # full text read through direct.posting_text
_JS_ONLY = re.compile(r"myworkdayjobs|oraclecloud|ultipro|ukg\.net|icims\.com|peacehealth|successfactors|taleo|"
                      r"governmentjobs|schooljobs|workforcenow\.adp|paylocity", re.I)


def read_posting_pages(jobs, fetcher, today, log):
    """Posted pay and hours from the employer's own posting page, when the hiring system's list leaves them out."""
    cache = json.loads(POSTING_DETAILS.read_text()) if POSTING_DETAILS.exists() else {}
    live, fetched, failed = set(), 0, 0
    def read(j):
        """Full text of one posting: from the hiring system's own data (Workday, Oracle, UKG) or the page itself."""
        text = direct.posting_text(fetcher, j["url"])
        if text is None:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(fetcher.get(j["url"]).text, "html.parser")
            for t in soup(["script", "style", "nav", "footer", "header"]):
                t.decompose()
            text = re.sub(r"\s+", " ", soup.get_text(" "))
        return {"pay": enrich.posted_pay(text), "hours": enrich.job_hours(j["title"], "", text[:4000]),
                "flags": enrich.text_flags(text[:20000]), "fetched": today}

    todo, queued = [], set()
    for j in jobs:
        if not j.get("direct"):
            continue
        if _JS_ONLY.search(j["url"]) and not _DATA_API.search(j["url"]):
            continue
        k = direct.posting_key(j["url"])
        live.add(k)
        if k not in cache and k not in queued and len(todo) < MAX_POSTING_PAGES:
            queued.add(k)
            todo.append((k, j))
    # Read in parallel; the fetcher still spaces requests to each site.
    from concurrent.futures import ThreadPoolExecutor
    def _one(item):
        k, j = item
        if late(0.8):
            return k, None
        try:
            return k, read(j)
        except Exception:  # noqa: BLE001 - blocked or gone; try again another night
            return k, False
    with ThreadPoolExecutor(max_workers=8) as pool:
        for k, rec in pool.map(_one, todo):
            if rec:
                cache[k] = rec
                fetched += 1
            elif rec is False:
                failed += 1
    for j in jobs:
        if not j.get("direct"):
            continue
        k = direct.posting_key(j["url"])
        rec = cache.get(k)
        if rec:
            j["pay"] = j.get("pay") or rec.get("pay", "")
            j["hours"] = j.get("hours") or rec.get("hours", "")
            j["_page_flags"] = rec.get("flags")
    cache = {k: v for k, v in cache.items() if k in live}
    POSTING_DETAILS.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    log.append(f"Employer posting pages: {fetched} read tonight, {failed} failed, "
               f"{sum(1 for v in cache.values() if v.get('pay'))} of {len(cache)} on file state pay.")


def write_occupations(show):
    """docs/occupations.json: O*NET details for the occupations of the jobs shown, for the widget's "About this kind
    of job", "Similar jobs hiring now" and skill search. Related occupations are kept only when they're hiring."""
    occ = enrich.onet().get("occ") or {}
    here = Counter(j.get("soc") for j in show if j.get("soc"))
    out = {}
    for s in here:
        o = occ.get(s)
        if not o:
            continue
        out[s] = {"t": o["t"], "d": o.get("d", ""), "z": o.get("z"), "k": o.get("k", [])[:30],
                  "rel": [r for r in o.get("rel", []) if r in here and r != s][:4]}
    path = OUT.parent / "occupations.json"
    path.write_text(json.dumps({"credit": enrich.onet().get("credit", ""), "occ": out}, ensure_ascii=False,
                               separators=(",", ":")), encoding="utf-8")


def known_employer_names(jobs):
    """Employer names to look for in posting text: the registry, plus employers already named on tonight's postings."""
    names = [j["employer"] for j in jobs if j.get("employer")]
    try:
        names += [e["employer"] for e in registry_sites() if e.get("employer")]
    except Exception:  # noqa: BLE001
        pass
    return names


def add_details(jobs, wages):
    """Employer, pay, hours and kind of workplace for each posting."""
    global KNOWN_NAMES
    KNOWN_NAMES = known_employer_names(jobs)
    coded = 0
    for j in jobs:  # reference numbers come off the shown title; the full title is kept (and searchable)
        clean = enrich.display_title(j["title"])
        if clean != j["title"]:
            j["title_full"], j["title"] = j["title"], clean
        if not j.get("soc"):  # no occupation from QualityInfo or the title rules: try O*NET's job titles
            raw = j.get("title_full") or j["title"]
            s = enrich.rule_soc(raw) or enrich.onet_soc(raw)
            if s:
                j["soc"], j["type"], j["soc_src"] = s, rules.type_of_work(s), "onet"
                coded += 1
    ADD_DETAILS_LOG.append(f"O*NET: {coded} postings matched to an occupation by their title.")
    for j in jobs:
        oed = j.pop("oed", None) or {}
        desc = oed.get("description", "")
        text = f'{j["title"]}. {j["snippet"]}. {desc}'
        if not j["employer"]:
            j["employer"] = rules.employer(desc) if desc else ""
        j["employer"] = enrich.clean_employer(j["employer"])
        if not j["employer"]:
            j["employer"] = enrich.clean_employer(enrich.employer_from_text(f'{j["snippet"]}. {desc}', j["title"]))
        if not j["employer"]:  # an employer we already know, named word for word in the posting
            j["employer"] = enrich.employer_from_known(f'{j["title"]}. {j["snippet"]}. {desc}', KNOWN_NAMES)
        j["pay"] = j.get("pay") or enrich.posted_pay(oed.get("wage", "")) or enrich.posted_pay(text)
        # An occupation average would mislead for interns and trainees, so none is shown for them.
        j["typical_pay"] = "" if re.search(r"\b(intern|internship|trainee|apprentice|student)\b", j["title"], re.I) \
            else enrich.typical_pay(j.get("soc"), wages)
        j["hours"] = j.get("hours") or enrich.oed_hours(oed) or enrich.job_hours(j["title"], j["snippet"], desc)
        j["workplaces"] = enrich.workplaces(j["employer"], rules.employer_industry(j["employer"]), j["industries"])
        if j["type"] == "Other":  # no occupation from the title: fall back on what the employer does
            j["type"] = next((WORKPLACE_TYPE[w] for w in j["workplaces"] or [] if w in WORKPLACE_TYPE), "Other")
        if j.get("remote") or (j["city"] == "Remote") or ats.is_remote(j["title"], ""):
            j["remote"] = True
            j["workplaces"] = (j["workplaces"] or []) + ["Remote"]
        j["apply_via"] = apply_label(j)
        j["_text"] = text


# ---- Fewer barriers and dead links ---------------------------------------------------------------------------

FEEDBACK = ROOT / "data" / "listing-feedback.json"  # "Was this job still open?" answers, from scripts/traffic.py
_GONE = re.compile(r"no longer (available|accepting|open|exists|active|posted)|position has been filled|"
                   r"(job|posting|position|requisition) (has )?(expired|closed|been removed)|"
                   r"this job (is )?(closed|unavailable)|job not found|page not found", re.I)


_LANE_WORD = re.compile(r"\b(" + "|".join(direct.LANE_CITIES) + r"|lane county|river ?bend)\b", re.I)


def drop_out_of_area(jobs, log):
    """Last check on every source: a title naming another city or state (and no Lane County place) is not here."""
    keep, gone = [], []
    for j in jobs:
        t = ats._REMOTE.sub(" ", j["title"])
        (gone if ats._NOT_HERE.search(t) and not _LANE_WORD.search(j["title"]) else keep).append(j)
    log.append(f"Out of area: dropped {len(gone)} postings whose titles name another place"
               + (f" (e.g. {gone[0]['title'][:60]!r})." if gone else "."))
    return keep


_SENIOR = re.compile(r"\b(senior|sr\.?|lead|leader|manager|mgr|director|supervisor|chief|head|principal|"
                     r"superintendent|foreman|forewoman|captain|ii|iii|iv|journey\w*|master|specialist [2-9])\b", re.I)


def tag_barriers(jobs, log, offline=False):
    """Labels for the "Fewer barriers" filters: near an LTD stop, no degree needed, training, fair chance."""
    levels, no_degree = {}, (lambda soc, lv: None)
    try:
        import reference
        levels, no_degree = reference.soc_education(log), reference.no_degree
        if not offline:
            reference.transit_tags(jobs, log)
    except Exception as e:  # noqa: BLE001 - the tags are extras; the run goes on without them
        log.append(f"Reference data unavailable: {type(e).__name__}: {str(e)[:120]}")
    # Employers known to hire with a fair-chance policy (data/fair-chance-employers.json, confirmed by staff):
    # every posting of theirs gets the tag, whatever the posting itself says.
    fair = []
    try:
        fair = [re.compile(e["match"], re.I) for e in json.loads((ROOT / "data" / "fair-chance-employers.json").read_text())]
    except Exception:  # noqa: BLE001
        pass
    for j in jobs:
        occ = no_degree(j.get("soc"), levels) if j.get("soc") and levels else None
        j["eases"] = enrich.eases(j.pop("_text", j["title"]), occ, j.pop("_page_flags", None),
                                  None if j.get("remote") else j.get("near_bus"))
        if "fair_chance" not in j["eases"] and any(rx.search(j.get("employer") or "") for rx in fair):
            j["eases"].append("fair_chance")
        # Entry level: O*NET rates the occupation job zone 1 or 2 (little or some preparation), and the title isn't a
        # senior, lead or management role.
        z = (enrich.onet().get("occ") or {}).get(j.get("soc") or "", {}).get("z")
        if z and z <= 2 and not _SENIOR.search(j.get("title_full") or j["title"]):
            j["eases"].append("entry")
    n = lambda k: sum(1 for j in jobs if k in j["eases"])  # noqa: E731
    log.append(f"Fewer barriers: near bus {n('bus')}, no degree {n('no_degree')}, entry level {n('entry')}, training {n('training')}, "
               f"fair chance {n('fair_chance')} of {len(jobs)} postings.")


def _is_dead(url):
    import requests
    from urllib.parse import urlparse
    try:
        r = requests.get(url, headers={"User-Agent": direct.UA}, timeout=15, allow_redirects=True, stream=True)
        try:
            if r.status_code in (404, 410):
                return f"gone ({r.status_code})"
            if r.status_code >= 400:
                return ""  # blocked or erroring: not proof the job is gone
            a, b = urlparse(url), urlparse(r.url)
            if r.history and a.netloc.split(".")[-2:] == b.netloc.split(".")[-2:]:
                segs_a = [x for x in a.path.split("/") if x]
                segs_b = [x for x in b.path.split("/") if x]
                if len(segs_a) >= 2 and len(segs_b) < len(segs_a) and segs_a[-1] not in r.url and a.query not in b.query:
                    return "redirected to a general page"
            head = r.raw.read(150000, decode_content=True).decode("utf-8", "ignore")
            visible = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", head)))
            if _GONE.search(visible[:60000]):
                return "page says the job is closed"
            if len(visible.strip()) < 300:
                return ""  # a bot check or script-only page: it shows nothing, so it proves nothing either way
            return "ok"  # the page loaded and still shows the job
        finally:
            r.close()
    except Exception:  # noqa: BLE001 - timeouts and network errors are not proof either
        return ""


def drop_dead_links(jobs, log):
    """Drop postings whose link is gone, redirects to a general page, says the job is closed, or that job seekers
    reported closed. Postings read tonight from a hiring system are skipped: the system just listed them."""
    from concurrent.futures import ThreadPoolExecutor
    check = [j for j in jobs if not j.get("direct") and j.get("url")]
    if late(0.9):
        log.append("Dead links: not checked tonight (time limit).")
        check = []
    with ThreadPoolExecutor(max_workers=24) as pool:
        verdicts = dict(zip([j["url"] for j in check], pool.map(_is_dead, [j["url"] for j in check])))
    feedback = json.loads(FEEDBACK.read_text()) if FEEDBACK.exists() else {}
    keep, why = [], Counter()
    for j in jobs:
        v = verdicts.get(j["url"], "")
        if v == "ok":
            j["verified"] = dt.date.today().isoformat()  # shown as "Link checked today"
            v = ""
        fb = feedback.get(job_id(j), {})
        if not v and fb.get("no", 0) >= 2 and fb.get("no", 0) > 2 * fb.get("yes", 0):
            v = "job seekers said it was closed"
        if v:
            why[v.split(" (")[0]] += 1
        else:
            keep.append(j)
    dropped = len(jobs) - len(keep)
    log.append(f"Dead links: checked {len(check)}, dropped {dropped} ({dict(why)}).")
    return keep, dropped


def national_labor_exchange(raw, log):
    """Lane County postings from the National Labor Exchange that QualityInfo doesn't already list.
    A posting counts as already listed when QualityInfo has the same title in the same town (and, when both name
    an employer, the same employer) or the same link."""
    try:
        import nlx
        found = nlx.pull(log)
    except Exception as e:  # noqa: BLE001 - NLx is an extra source; the run goes on without it
        log.append(f"NLx pull failed: {type(e).__name__}: {str(e)[:150]}")
        return []
    NLX_ALL[:] = found  # every NLx posting, including copies of QualityInfo jobs: their links feed the trace step
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()  # noqa: E731
    emp = lambda t: re.sub(r"[^a-z0-9]", "", re.sub(r"\b(inc|llc|co|corp|company|the|usa)\b", "", (t or "").lower()))  # noqa: E731
    have_title, rows = {}, {}
    for j in raw:
        have_title.setdefault((norm(j["title"]), j["city"]), set()).add(emp(rules.employer(f'{j["title"]} {j["snippet"]}') or ""))
        rows.setdefault((norm(j["title"]), j["city"]), []).append(j)
    named = 0
    have_url = {direct.posting_key(j["url"]) for j in raw if j.get("url")}
    keep = []
    for j in found:
        names = have_title.get((norm(j["title"]), j["city"]))
        e = emp(j.get("employer"))
        if direct.posting_key(j["url"]) in have_url:
            continue
        if names is not None and (not e or "" in names or any(n and (n in e or e in n) for n in names)):
            # Same job on QualityInfo, which often leaves the employer out: take the name NLx gives.
            nlx_name = enrich.clean_employer(j.get("employer") or "")
            for r in rows.get((norm(j["title"]), j["city"]), []):
                if nlx_name and not r.get("employer"):
                    r["employer"] = nlx_name
                    named += 1
            continue
        keep.append(j)
    log.append(f"NLx: {len(found)} Lane County postings, {len(found) - len(keep)} already on QualityInfo, {len(keep)} added; "
               f"{named} QualityInfo postings got their employer name from NLx.")
    return keep


def apply_label(j):
    if j["route"] == "WorkSource Oregon listing":
        return "Apply through WorkSource Oregon"
    if j["route"] == "Reposted by a job board":
        host = re.sub(r"^https?://(www\.)?([^/]+).*$", r"\2", j["url"]).lower()
        return f"Apply on {host}"
    if not j["employer"]:
        return "Apply on the employer's site"
    return f"Apply on {j['employer']}' site" if j["employer"].endswith("s") else f"Apply on {j['employer']}'s site"


def pull_direct(qi_jobs, fetcher, today):
    """Learn hiring systems from posting links, pull each one directly, and merge.

    A direct posting replaces its QualityInfo copy (same posting on the same hiring system) and any
    WorkSource Oregon copy with the same employer, title and city, so job seekers land on the employer's
    own page.
    """
    sources = json.loads(SOURCES.read_text()) if SOURCES.exists() else {}
    for j in qi_jobs:
        found = direct.source_from_url(j["url"])
        if not found:
            continue
        key, src = found
        rec = sources.setdefault(key, dict(src, first_seen=today, employer=""))
        if rec.get("tenant", "").lower() in rules.TENANT_NAMES:
            rec["employer"] = rules.TENANT_NAMES[rec["tenant"].lower()]
        if not rec.get("employer") and j["employer"] and not j["employer"].startswith("Unnamed"):
            rec["employer"] = j["employer"]
    for src in sources.values():
        t = (src.get("tenant") or "").lower()
        if t in rules.TENANT_NAMES and not src.get("named"):
            src["employer"] = rules.TENANT_NAMES[t]
    # Employers found by name: add each careers page as a source. A page on a known hiring system uses that
    # system's connector; any other page is read with the browser reader.
    sites = registry_sites()
    for site in sites:
        url = site.get("careers_url") or ""
        if not url or re.search(r"governmentjobs\.com|schooljobs\.com", url, re.I):
            continue  # public employers on NEOGOV are already covered by the location search
        if re.search(r"\.icims\.com", url, re.I) and "in_iframe" not in url:
            url = re.sub(r"^(https?://[^/]+).*$", r"\1", url) + "/jobs/search?ss=1&in_iframe=1"
        found = direct.source_from_url(url) or ats.source_from_url(url)
        key, src = found if found else (f"page:{url.lower().rstrip('/')}", {"platform": "Careers page", "url": url,
                                                                             "host": re.sub(r"^https?://([^/]+).*$", r"\1", url).lower()})
        rec = sources.setdefault(key, dict(src, first_seen=today, employer=""))
        found_auto = bool(site.get("list")) and site.get("list") != "Eugene tech (Matt)"
        rec["remote_ok"] = not found_auto  # hand-checked Lane County employers: their remote jobs are listed too
        rec.update(employer=site["employer"], local=("maybe" if found_auto else True) if site.get("local") else False,
                   home=site.get("home", ""), named=True,
                   weekly=bool(site.get("weekly")), rotate=site.get("list") == "QualityInfo employer database")
    for host in ("www.governmentjobs.com", "www.schooljobs.com"):  # public employers; one search covers all of them
        sources.setdefault(f"neogov:{host}", {"platform": "NEOGOV", "host": host, "first_seen": today,
                                              "employer": "", "multi": True})
    if "peacehealth" not in sources:
        sources["peacehealth"] = {"platform": "PeaceHealth careers site", "host": "careers.peacehealth.org",
                                  "first_seen": today, "employer": "PeaceHealth"}

    for key, src in sources.items():
        if src.get("multi") or src.get("employer") or src.get("name_checked") == today:
            continue
        src["name_checked"] = today
        page = {"UKG (UltiPro)": f"https://{src['host']}/{src.get('tenant', '')}/JobBoard/{src.get('board', '')}",
                "Oracle Recruiting": f"https://{src['host']}/hcmUI/CandidateExperience/en/sites/{src.get('site', '')}"}.get(src["platform"])
        if page:
            src["employer"] = site_name(fetcher, page)
    title_soc = {}
    if STATE.exists():
        for rec in json.loads(STATE.read_text()).values():
            if rec.get("soc"):
                title_soc.setdefault(rec["title"].lower(), rec["soc"])
    for j in qi_jobs:
        if j["soc"]:
            title_soc.setdefault(j["title"].lower(), j["soc"])

    got = []
    connectors = dict(direct.CONNECTORS, **ats.CONNECTORS)
    browser = ats.Browser()
    # Hiring-system feeds first (fast); then careers pages, least recently read first, so the browser budget rotates.
    queue = sorted(sources.items(), key=lambda kv: (kv[1].get("platform") == "Careers page",
                                                    kv[1].get("cache_date") or "", kv[0]))
    import time
    import zlib
    browser_secs, day_no = 0.0, dt.date.fromisoformat(today).toordinal()

    def fresh_cache(src):
        return src.get("cache_date") and (day_no - dt.date.fromisoformat(src["cache_date"]).toordinal()) <= 4

    # Hiring-system feeds are read in parallel (each site still gets one request at a time, a second apart);
    # their results are then handled in order below. A feed not finished by the time limit uses its last read.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    prefetched = {}
    api = [(k, s, connectors[s["platform"]]) for k, s in queue
           if s["platform"] != "Careers page" and s["platform"] in connectors
           and not (s.get("weekly") and not s.get("lane_openings") and s.get("last_run")
                    and zlib.crc32(k.encode()) % 7 != day_no % 7)]

    def _fetch(item):
        k, s, f = item
        try:
            return k, f(fetcher, s), None
        except Exception as e:  # noqa: BLE001
            return k, None, e
    pool = ThreadPoolExecutor(max_workers=16)
    futs = [pool.submit(_fetch, it) for it in api]
    try:
        for n, fut in enumerate(as_completed(futs, timeout=max(60.0, RUN_LIMIT * 0.45 - (time.time() - RUN_START)))):
            k, rows, err = fut.result()
            prefetched[k] = (rows, err)
            if n % 50 == 0:
                progress("Employer hiring systems", done=n, of=len(api))
    except Exception:  # noqa: BLE001 - time limit: the rest use their last read
        pass
    pool.shutdown(wait=False, cancel_futures=True)
    unfinished = {k for k, _, _ in api if k not in prefetched}

    def take(key, fn, src):
        if key in unfinished:
            if fresh_cache(src):
                return [dict(r, _cached=src["cache_date"]) for r in src.get("cache_rows") or []]
            raise TimeoutError("not read tonight (time limit)")
        if key in prefetched:
            rows, err = prefetched.pop(key)
            if err:
                raise err
            return rows
        return fn(fetcher, src)

    handled = 0
    while queue:
        key, src = queue.pop(0)
        handled += 1
        if handled % 50 == 0:
            progress("Employer hiring sites and careers pages", handled=handled, left=len(queue),
                     browser_minutes=round(browser_secs / 60, 1))
            SOURCES.write_text(json.dumps(sources, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        turn = zlib.crc32(key.encode())
        # Pages that rarely have openings are read once a week, on a day set by their address, to keep the run short.
        if src.get("weekly") and not src.get("lane_openings") and src.get("last_run") and turn % 7 != day_no % 7:
            continue
        if src["platform"] == "Careers page":
            fn = lambda f, s: ats.pull_careers_page(f, s, browser)  # noqa: E731
            # Careers pages found through the QualityInfo employer database are read every third night; in between,
            # and once tonight's browser time is used up, the postings from the last read carry over (up to 4 days).
            due = not (src.get("rotate") and src.get("last_run") and turn % 3 != day_no % 3)
            if not due or browser_secs > BROWSER_BUDGET or late(0.7):
                fn = (lambda f, s: [dict(r, _cached=s["cache_date"]) for r in s.get("cache_rows") or []]) if fresh_cache(src) else None  # noqa: E731
                if fn is None:
                    continue
        else:
            fn = connectors.get(src["platform"])
        if not fn:
            continue
        before, t0 = fetcher.calls, time.time()
        try:
            rows = take(key, fn, src)
            if src["platform"] == "Careers page":
                browser_secs += time.time() - t0
                if isinstance(rows, list) and fetcher.calls >= before and time.time() - t0 > 0.05:
                    src["cache_rows"], src["cache_date"] = rows[:200], today
            if isinstance(rows, dict) and rows.get("handoff"):
                # The careers page runs on a hiring system we can read directly: switch to it from now on.
                nkey, nsrc = rows["handoff"]
                if nkey not in sources:
                    sources[nkey] = dict(nsrc, first_seen=today, employer=src.get("employer", ""), local=src.get("local"),
                                         home=src.get("home", ""), named=src.get("named", False),
                                         remote_ok=src.get("remote_ok", False))
                    queue.append((nkey, sources[nkey]))
                src.update(status=f"uses {nsrc['platform']}", last_run=today, lane_openings=0)
                continue
            if src["platform"] != "Careers page" and key not in unfinished and isinstance(rows, list):
                src["cache_rows"], src["cache_date"] = [{k: v for k, v in r.items() if k != "_cached"} for r in rows[:400]], today
            src.update(status="ok", last_run=today, lane_openings=len(rows))
        except PermissionError as e:
            rows = []
            rs = fetcher.robots_status.get(f"https://{src['host']}")
            why = str(e) if str(e).startswith("site ") else (
                "site asks crawlers not to visit" if rs in (200, None) else f"robots.txt unavailable ({rs})")
            src.update(status=f"skipped: {why}", last_run=today, lane_openings=0)
            print(f"  {key}: {e}")
        except Exception as e:  # noqa: BLE001  one failing source never stops the run
            rows = []
            code = getattr(getattr(e, "response", None), "status_code", None)
            why = "site blocks automated access" if code in (401, 403, 429) else type(e).__name__
            src.update(status=f"error: {why}" + (f" ({code})" if code else ""), last_run=today, lane_openings=0)
            print(f"  {key}: {type(e).__name__}: {e}")
        print(f"  {key}: {len(rows)} Lane openings ({fetcher.calls - before} requests)")
        name = src.get("employer") or rules.employer_from_url(f"https://{src['host']}/{src.get('tenant', '')}")
        name = re.sub(r"\s+(External|Candidate Experience page|US)$", "", name or "").replace("JPMC", "JPMorgan Chase")
        if name == "IP Global":
            name = "International Paper"
        if re.search(r"[A-Za-z]\d{3,}", name):  # an account code such as "Buc1007Bucc", not a name
            name = ""
        if src.get("multi"):
            name = ""
        remote = [r for r in rows if r.get("remote")]
        if len(remote) > REMOTE_CAP:  # national remote roles: the newest few per employer, so they don't crowd out local jobs
            keep = {id(r) for r in sorted(remote, key=lambda r: r.get("days") if r.get("days") is not None else 99)[:REMOTE_CAP]}
            rows = [r for r in rows if not r.get("remote") or id(r) in keep]
        if src["platform"] == "Careers page":  # also screens postings carried over from an earlier read
            rows = [r for r in rows if ats.looks_like_job(r.get("title"))]
        for r in rows:
            emp = name or r.get("org") or ""
            if not src.get("multi") and not src.get("employer") and r.get("org"):
                src["employer"] = emp = r["org"]
            got.append({"title": r["title"], "city": r["city"], "url": r["url"],
                        "source": "Employer direct", "days": r["days"],
                        "soc": enrich.soc_for_title(r["title"], title_soc), "occupation": "",
                        "snippet": r.get("snippet", ""), "employer": emp, "direct": True,
                        "hours": r.get("hours") or enrich.job_hours(r.get("info", "")),
                        "pay": enrich.posted_pay(r.get("info", "")), "remote": bool(r.get("remote")),
                        # read from the employer's own hiring system tonight (or on the night of the saved read)
                        "verified": r.get("_cached") or today})
    browser.close()
    SOURCES.write_text(json.dumps(sources, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    with SOURCES_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Employer", "Hiring system", "Address", "Lane openings last night", "Status", "First seen", "Last run"])
        for key, src in sorted(sources.items(), key=lambda kv: -kv[1].get("lane_openings", 0)):
            w.writerow([src.get("employer") or ("Public employers in Lane County" if src.get("multi") else key), src["platform"], src.get("url") or f"https://{src['host']}/{src.get('site', src.get('tenant', src.get('token', '')))}",
                        src.get("lane_openings", 0), src.get("status", ""), src.get("first_seen", ""), src.get("last_run", "")])

    # Merge: one row per posting, direct first.
    seen, merged = {}, []
    for j in got:
        k = direct.posting_key(j["url"])
        if k not in seen:
            seen[k] = j
            merged.append(j)
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()  # noqa: E731
    # Employer names differ between sources ("PacificSource" vs "Pacificsource Health Plans"): match on the first word.
    ek = lambda e: (re.sub(r"^the\s+", "", norm(e)).split() or [""])[0]  # noqa: E731
    direct_tc = {(ek(j["employer"]), norm(j["title"]), j["city"]): j for j in merged if j["employer"]}
    replaced = 0
    for j in qi_jobs:
        k = direct.posting_key(j["url"])
        if k in seen:
            d = seen[k]
            d["soc"] = d["soc"] or j["soc"]
            d["occupation"] = j.get("occupation", "")
            d["snippet"] = d["snippet"] or j["snippet"]
            d["days"] = j["days"] if d["days"] is None else d["days"]
            replaced += 1
            continue
        d = direct_tc.get((ek(j["employer"]), norm(j["title"]), j["city"])) if j["employer"] else None
        if j["route"] != "Employer's hiring site" and d is not None:
            # Keep what the secondhand copy knew: occupation code (for typical pay) and its WorkSource page (posted pay).
            d["soc"] = d["soc"] or j["soc"]
            d["occupation"] = d.get("occupation") or j.get("occupation", "")
            d["snippet"] = d["snippet"] or j["snippet"]
            if j["route"] == "WorkSource Oregon listing":
                d["oed_url"] = j["url"]
            replaced += 1
            continue
        merged.append(j)
    print(f"Direct: {len(got)} postings from {sum(1 for s in sources.values() if s.get('status') == 'ok')} "
          f"hiring systems; replaced {replaced} secondhand copies.")
    return merged


def _rough_name(name):
    """True for names an earlier text-reading pass produced with a heading or filler in front."""
    t = enrich._tidy_name(name)
    return not t or not name.startswith(t.split()[0])


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
        via = "Pulled directly from its hiring system" if j.get("direct") else j["route"]
        if via not in e["found_via"]:
            e["found_via"].append(via)
        if plat and not e["platform"]:
            e["platform"] = plat
            e["careers_page"] = rules.careers_page(j["url"], plat)
            e["example_posting"] = j["url"]
    for e in emps.values():
        e["total_seen"] = e.get("total_seen", 0) + (1 if e["open_now"] else 0)
    # Drop names an earlier, rougher text-reading pass produced ("Click HERE Providence"), once they are not hiring.
    for name in [k for k, e in emps.items() if not e["open_now"] and not k.startswith("Unnamed")
                 and (_rough_name(k) or enrich.clean_employer(k) != k)]:
        del emps[name]
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


def _first_word(name):
    return (re.sub(r"^the\s+", "", re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()).split() or [""])[0]


def trace_employers(jobs, today, log):
    """Employers we only see secondhand (WorkSource, NLx, job boards), ranked by Lane County openings.

    For each, every link seen tonight for that employer (including NLx copies of QualityInfo jobs) is checked for a
    hiring system we can read; one found is added to the registry, so the employer is read directly from the next
    night on. Written to docs/employers-to-trace.csv for the registry sheet."""
    sources = json.loads(SOURCES.read_text()) if SOURCES.exists() else {}
    reg = registry_sites()
    found_file = json.loads(EMPLOYER_SITES_FOUND.read_text()) if EMPLOYER_SITES_FOUND.exists() else []
    direct_names = {_first_word(s.get("employer")) for s in sources.values() if s.get("employer")}
    direct_names |= {_first_word(e.get("employer")) for e in reg if e.get("careers_url")}
    direct_names |= {_first_word(j["employer"]) for j in jobs if j.get("direct") and j["employer"]}
    direct_names.discard("")
    links = {}
    for j in list(jobs) + list(NLX_ALL):
        name = enrich.clean_employer(j.get("employer") or "")
        if name and j.get("url"):
            links.setdefault(_first_word(name), set()).add(j["url"])
    groups = {}
    for j in jobs:
        if j.get("direct") or not j["employer"] or j.get("remote"):
            continue
        k = _first_word(j["employer"])
        if k in direct_names:
            continue
        g = groups.setdefault(k, {"name": j["employer"], "n": 0, "routes": set(), "example": j["url"]})
        g["n"] += 1
        g["routes"].add(j["route"])
    added = []
    for k, g in groups.items():
        found = None
        for u in sorted(links.get(k, ())):
            f = direct.source_from_url(u) or ats.source_from_url(u)
            if f and f[1].get("platform") not in ("NEOGOV",):
                found = (u, f)
                break
        if found:
            u, (key, src) = found
            if key in sources:
                g["status"] = f"Hiring system already read ({src['platform']}); its jobs here go under another name"
            else:
                entry = {"employer": g["name"], "careers_url": u, "local": True, "home": "", "found": today,
                         "list": "Found from postings (trace)"}
                reg.append(entry)
                found_file.append(entry)
                added.append(g["name"])
                g["status"] = f"Added tonight: {src['platform']}, read directly from the next run"
        else:
            g["status"] = "No readable hiring-system link seen yet"
    if added:
        EMPLOYER_SITES_FOUND.write_text(json.dumps(found_file, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with TRACE_EMP_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Employer", "Lane openings seen secondhand", "Seen via", "Status", "Example posting", "Date"])
        for g in sorted(groups.values(), key=lambda g: (-g["n"], g["name"].lower())):
            w.writerow([g["name"], g["n"], ", ".join(sorted(g["routes"])), g["status"], g["example"], today])
    log.append(f"Employers to trace: {len(groups)} seen only secondhand ({sum(g['n'] for g in groups.values())} openings); "
               f"{len(added)} hiring systems added from their links" + (f" ({', '.join(added[:5])})." if added else "."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", help="parse a saved results page instead of pulling live")
    args = ap.parse_args()
    log = []
    run_date = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    marks = [("start", time.time())]  # phase timings for the staff dashboard's "Nightly processes" section

    def mark(name):
        marks.append((name, time.time()))
        progress(f"finished {name}", steps=minutes())

    def minutes():
        return [{"step": n, "minutes": round((t - marks[i][1]) / 60, 1)} for i, (n, t) in enumerate(marks[1:])]

    if args.fixture:
        # Offline test: write to tests/out/ so real data is never touched.
        global OUT, STATE, EMPLOYERS, EMPLOYERS_CSV, TRACE_CSV
        t = ROOT / "tests" / "out"
        t.mkdir(parents=True, exist_ok=True)
        OUT, STATE, EMPLOYERS = t / "jobs.json", t / "state.json", t / "employers.json"
        global PULLED, PROGRESS
        PULLED, PROGRESS = t / "pulled.json", t / "run-progress.json"
        EMPLOYERS_CSV, TRACE_CSV = t / "employers.csv", t / "to-trace.csv"
        for f in (STATE, EMPLOYERS):
            f.unlink(missing_ok=True)
        total, raw = parse_page(Path(args.fixture).read_text(encoding="utf-8"))
    else:
        try:
            total, raw = pull_live(log)
        except Exception as e:  # noqa: BLE001
            log.append(f"QualityInfo pull failed: {type(e).__name__}: {str(e)[:300]}")
            total, raw = None, []
        if raw:
            QI_LAST.write_text(json.dumps({"date": run_date, "total": total, "jobs": raw}, ensure_ascii=False), encoding="utf-8")
        elif QI_LAST.exists():
            # QualityInfo is down or changed: keep going with the last good list so direct pulls still refresh.
            last = json.loads(QI_LAST.read_text())
            total, raw = last["total"], last["jobs"]
            log.append(f"Using the last good QualityInfo list from {last['date']} ({len(raw)} listings).")

    if not raw:
        # Never overwrite good data with an empty pull: fail loudly so the run shows red.
        mark("QualityInfo")
        write_run_log({"date": run_date, "ok": False, "notes": log, "steps": minutes()})
        sys.exit("No listings parsed. QualityInfo may have changed its page; check PARAMS and parse_page().")

    mark("QualityInfo")
    if not args.fixture:
        raw += national_labor_exchange(raw, log)
        mark("National Labor Exchange")
    jobs = [tag(j) for j in dedupe(raw)]
    today = dt.date.today().isoformat()
    wages = json.loads(WAGES.read_text()) if WAGES.exists() and not args.fixture else {}
    wages.update(WAGE_TABLE)
    if not args.fixture:  # BLS averages fill in occupations QualityInfo's listings didn't cover tonight
        try:
            import reference
            for soc, w in reference.oews_wages(log).items():
                wages.setdefault(soc, w)
        except Exception as e:  # noqa: BLE001
            log.append(f"BLS wages not added: {type(e).__name__}: {e}")
    if not args.fixture:
        WAGES.write_text(json.dumps(wages, sort_keys=True), encoding="utf-8")
        fetcher = direct.Fetcher()
        auto_name_domains(jobs, fetcher, today)
        jobs = [tag(j) for j in pull_direct(jobs, fetcher, today)]
        mark("Employer hiring sites")
        read_oed_pages(jobs, fetcher, today, log)
        read_posting_pages(jobs, fetcher, today, log)
        mark("Posting pages (pay, details)")
    add_details(jobs, wages)
    log.extend(ADD_DETAILS_LOG)
    jobs = drop_out_of_area(jobs, log)
    tag_barriers(jobs, log, offline=bool(args.fixture))
    mark("Barrier tags")
    dead_dropped = 0
    if not args.fixture:
        jobs, dead_dropped = drop_dead_links(jobs, log)
        mark("Dead-link check")
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    live_ids = set()
    for j in jobs:
        jid = job_id(j)
        live_ids.add(jid)
        rec = state.get(jid, {"first_seen": today})
        rec.update(last_seen=today, misses=0, title=j["title"], employer=j["employer"], city=j["city"], soc=j["soc"],
                   type=j.get("type", ""), posted_pay=bool(j.get("pay")), route=j.get("route", ""),
                   source=j.get("source", ""))
        state[jid] = rec
        j["id"] = jid
        j["first_seen"] = rec["first_seen"]
        j["dated"] = j.get("days") is not None
        if j["dated"] and "posted" not in rec:  # the employer's posting date, for the dashboard's longest-open list
            rec["posted"] = (dt.date.fromisoformat(today) - dt.timedelta(days=int(j["days"]))).isoformat()
        if not j["dated"]:  # hiring system gives no posting date: count from the night we first saw it
            j["days"] = (dt.date.fromisoformat(today) - dt.date.fromisoformat(rec["first_seen"])).days
    # Trust signals: a job whose employer, title and town were listed before under another posting (30+ days
    # earlier) is marked as reposted; "Was this job still open?" answers show when more said yes than no.
    earliest = {}
    for jid, rec in state.items():
        k = ((rec.get("employer") or "").lower(), (rec.get("title") or "").lower(), rec.get("city", ""))
        if k[0] and rec.get("first_seen") and (k not in earliest or rec["first_seen"] < earliest[k][0]):
            earliest[k] = (rec["first_seen"], jid)
    feedback = json.loads(FEEDBACK.read_text()) if FEEDBACK.exists() else {}
    for j in jobs:
        k = ((j.get("employer") or "").lower(), j["title"].lower(), j["city"])
        first = earliest.get(k)
        if first and first[1] != j["id"] and (dt.date.fromisoformat(today) - dt.date.fromisoformat(first[0])).days >= 30:
            j["reposted_since"] = first[0]
        fb = feedback.get(j["id"], {})
        if fb.get("yes", 0) >= 1 and fb.get("yes", 0) > fb.get("no", 0):
            j["said_open"] = fb["yes"]
    for jid, rec in state.items():
        if jid not in live_ids:
            rec["misses"] = rec.get("misses", 0) + 1
            if rec["misses"] >= MISSES_TO_CLOSE and "closed" not in rec:
                rec["closed"] = today

    def shown(j):
        host = re.sub(r"^https?://([^/]+).*$", r"\1", j["url"] or "").lower()
        if any(host == h or host.endswith("." + h) for h in SKIP_HOSTS):
            return False
        if j["days"] <= SHOW_DAYS:
            return True
        # Older postings stay up while the employer's hiring system still lists them or the link still checks
        # out as open; job-board reposts keep the shorter limit.
        checked = j.get("verified") and (dt.date.fromisoformat(today) - dt.date.fromisoformat(j["verified"])).days <= CHECKED_WITHIN
        return bool(checked) and j["days"] <= SHOW_DAYS_CHECKED and j.get("route") != "Reposted by a job board"

    show = sorted((j for j in jobs if shown(j)), key=lambda j: j["days"])
    out = {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "source": "QualityInfo Job Finder, Oregon Employment Department",
        "area": "Lane County, Oregon",
        "window_days": DAYS,
        "reported_total": total,
        "count": len(show),
        "pulled": len(jobs),
        "show_days": SHOW_DAYS, "show_days_checked": SHOW_DAYS_CHECKED,
        "dead_links_dropped": dead_dropped,
        "jobs": [{k: j.get(k, "") for k in ("id", "title", "city", "employer", "type", "workplaces", "hours", "pay",
                                            "typical_pay", "apply_via", "eases", "remote", "verified", "reposted_since", "said_open", "industries", "rural", "priority", "route", "title_full",
                                            "source", "days", "dated", "first_seen", "soc", "occupation", "url")}
                 | {"snippet": j["snippet"][:160]} for j in show],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    write_occupations(show)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    PULLED.write_text(json.dumps([{k: j.get(k) for k in ("id", "title", "city", "employer", "url", "days", "soc", "route")}
                                  for j in jobs], ensure_ascii=False, indent=0), encoding="utf-8")
    n_emp = update_employers(jobs, today)
    if not args.fixture:
        try:
            trace_employers(jobs, today, log)
        except Exception as e:  # noqa: BLE001  never stops the job list from publishing
            log.append(f"Employers to trace failed: {type(e).__name__}: {e}")
    print(f"Employers on record: {n_emp}.")
    if not args.fixture:
        try:
            row = dashboard.update(out, json.loads(EMPLOYERS.read_text()),
                                   json.loads(SOURCES.read_text()) if SOURCES.exists() else {}, state=state)
            log.append(f"Dashboard: {row['employers_hiring']} employers hiring, {row['employer_sources_searched']} sources.")
        except Exception as e:  # noqa: BLE001  the dashboard never stops the job list from publishing
            log.append(f"Dashboard update failed: {type(e).__name__}: {e}")
        import archive  # every posting pulled tonight, kept for later analysis (data/archive/)
        archive.save(jobs, today, employers=json.loads(EMPLOYERS.read_text()))
        log.append(f"Widget: {len(show)} shown of {len(jobs)} postings.")
        mark("Dashboard and archive")
        write_run_log({"date": run_date, "ok": True, "notes": log, "steps": minutes()})
    print(f"Widget shows {len(show)} (up to {SHOW_DAYS} days old, {SHOW_DAYS_CHECKED} when checked open).")
    print(f"QualityInfo reported {total}; parsed {len(raw)}; kept {len(jobs)} after duplicates; "
          f"{sum(1 for r in state.values() if 'closed' in r)} closed to date.")


if __name__ == "__main__":
    main()
