"""Direct pulls from employers' own hiring systems.

The nightly run learns which hiring system each employer uses from the
QualityInfo postings it sees (a Workday, Oracle or UKG link reveals it). Every
employer learned that way is saved to data/sources.json and, from then on, its
Lane County openings are pulled straight from its hiring system each night, so
the widget can link to the employer's own posting. Nobody has to add or approve
a source: the list grows by itself.

Every request first checks the site's robots.txt and skips the site if
automated access is not allowed. A source that fails is logged and skipped;
it never stops the run.
"""
import html
import json
import re
import time
import urllib.robotparser
from datetime import date, datetime
from urllib.parse import urlparse

import requests

UA = "LaneCountyHotJobs/0.2 (nonprofit workforce pilot; Collaborative Economic Development Oregon)"
PAUSE = 1.0
MAX_DETAILS = 80  # per source per night

LANE_CITIES = ["Eugene", "Springfield", "Florence", "Cottage Grove", "Junction City", "Creswell", "Veneta",
               "Oakridge", "Coburg", "Lowell", "Dexter", "Pleasant Hill", "Mapleton", "Blue River", "Marcola",
               "Elmira", "Walterville", "Westfir", "Dunes City", "Noti", "Lorane", "Leaburg", "Vida",
               "Swisshome", "Deadwood", "Fall Creek", "Crow", "Cheshire", "Alvadore", "Glenwood"]
SEARCH_CITIES = ["Eugene", "Springfield", "Florence", "Cottage Grove", "Junction City", "Creswell", "Veneta",
                 "Oakridge", "Coburg"]
_CITY_RX = re.compile(r"\b(" + "|".join(LANE_CITIES) + r")\b[ ,]*(OR\b|Oregon\b)", re.I)


def lane_city(text):
    """Lane County city named in a location string ('Eugene, OR 97401'), else ''."""
    m = _CITY_RX.search(text or "")
    return next((c for c in LANE_CITIES if c.lower() == m.group(1).lower()), "") if m else ""


def plain(s, n=300):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    return re.sub(r"\s+", " ", s).strip()[:n]


def days_since(iso):
    try:
        return max(0, (date.today() - datetime.fromisoformat(iso[:10]).date()).days)
    except (TypeError, ValueError):
        return None


class Fetcher:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        self.robots = {}
        self.robots_text = {}
        self.calls = 0

    def allowed(self, url):
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.s.get(root + "/robots.txt", timeout=20)
                if r.status_code in (401, 403):
                    rp.disallow_all = True
                elif r.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(r.text.splitlines())
                    self.robots_text[root] = r.text
            except requests.RequestException:
                rp.disallow_all = True  # cannot check, so do not crawl
            self.robots[root] = rp
        if not self.robots[root].can_fetch(UA, url):
            return False
        # robots.txt paths are case-sensitive, but some hiring sites ignore case; treat a case-insensitive
        # Disallow match as a "no" so we never pull a site its owner asked crawlers to skip.
        path = (p.path or "/").lower()
        for line in self.robots_text.get(root, "").splitlines():
            m = re.match(r"\s*disallow:\s*(\S+)", line, re.I)
            if m and m.group(1) != "/" and path.startswith(m.group(1).lower()):
                return False
        return True

    def get(self, url, **kw):
        return self._go("GET", url, **kw)

    def post(self, url, **kw):
        return self._go("POST", url, **kw)

    def _go(self, method, url, **kw):
        if not self.allowed(url):
            raise PermissionError(f"robots.txt does not allow {url}")
        time.sleep(PAUSE)
        self.calls += 1
        r = self.s.request(method, url, timeout=40, **kw)
        r.raise_for_status()
        return r


# ---- Learning sources from posting links -------------------------------------

def source_from_url(url):
    """(key, source dict) for a posting link on a hiring system we can pull directly, else None."""
    u = (url or "").replace("http://", "https://")
    m = re.match(r"https://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[a-z]{2}/)?([^/?#]+)", u, re.I)
    if m:
        tenant, site = m.group(1).lower(), m.group(3)
        host = f"{tenant}.{m.group(2).lower()}.myworkdayjobs.com"
        return f"workday:{tenant}/{site.lower()}", {"platform": "Workday", "host": host, "tenant": tenant, "site": site}
    m = re.match(r"https://([a-z0-9.-]+\.oraclecloud\.com)/hcmui/candidateexperience/[a-z-]+/sites/([^/?#]+)", u, re.I)
    if m:
        host, site = m.group(1).lower(), m.group(2)
        return f"oracle:{host}/{site.lower()}", {"platform": "Oracle Recruiting", "host": host, "site": site}
    m = re.match(r"https://(recruiting\d*\.ultipro\.com)/([a-z0-9]+)/jobboard/([0-9a-f-]{36})", u, re.I)
    if m:
        host, tenant, board = m.group(1).lower(), m.group(2), m.group(3).lower()
        return f"ukg:{tenant.lower()}/{board}", {"platform": "UKG (UltiPro)", "host": host, "tenant": tenant, "board": board}
    if re.match(r"https://careers\.peacehealth\.org/", u, re.I):
        return "peacehealth", {"platform": "PeaceHealth careers site", "host": "careers.peacehealth.org"}
    return None


def posting_key(url):
    """Identity of one posting across links (lets a direct posting replace its QualityInfo copy)."""
    u = (url or "").lower().replace("http://", "https://").split("#")[0]
    m = re.search(r"([a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com/.*/job/.*_([a-z0-9-]+)(?:[/?]|$)", u)
    if m:
        return f"workday:{m.group(1)}:{m.group(2)}"
    m = re.search(r"([a-z0-9.-]+\.oraclecloud\.com)/.*/job/(\d+)", u)
    if m:
        return f"oracle:{m.group(1)}:{m.group(2)}"
    m = re.search(r"ultipro\.com/([a-z0-9]+)/jobboard/.*opportunityid=([0-9a-f-]{36})", u)
    if m:
        return f"ukg:{m.group(1)}:{m.group(2)}"
    m = re.search(r"careers\.peacehealth\.org/jobs/(\d+)", u)
    if m:
        return f"peacehealth:{m.group(1)}"
    return u.split("?")[0].rstrip("/")


# ---- Connectors ----------------------------------------------------------------

def _workday_days(posted_on):
    t = (posted_on or "").lower()
    if "today" in t:
        return 0
    if "yesterday" in t:
        return 1
    m = re.search(r"(\d+)\+? days", t)
    return int(m.group(1)) if m else None


def _workday_lane_facets(facets):
    """(facetParameter, id) pairs for location facet values that name a Lane County city."""
    out = []
    def walk(items, param):
        for it in items or []:
            p = it.get("facetParameter", param)
            if it.get("values"):
                walk(it["values"], p)
            desc = it.get("descriptor", "")
            if it.get("id") and p and "loc" in p.lower() and lane_city(desc):
                out.append((p, it["id"]))
    walk(facets, None)
    return out


def pull_workday(f, src):
    base = f"https://{src['host']}"
    api = f"{base}/wday/cxs/{src['tenant']}/{src['site']}"
    if not f.allowed(f"{base}/{src['site']}/"):
        # Some employers' robots.txt block their careers site even though the data service is open; honor the intent.
        raise PermissionError(f"robots.txt does not allow {base}/{src['site']}/")
    first = f.post(api + "/jobs", json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}).json()
    pairs = _workday_lane_facets(first.get("facets"))
    searches = []
    if pairs:
        applied = {}
        for p, i in pairs:
            applied.setdefault(p, []).append(i)
        for p, ids in applied.items():  # one search per facet type, since facet types combine with AND
            searches.append(({p: ids}, ""))
    else:
        searches = [({}, c) for c in SEARCH_CITIES]
    found = {}
    for facets, text in searches:
        for offset in range(0, 400, 20):
            posts = f.post(api + "/jobs", json={"appliedFacets": facets, "limit": 20, "offset": offset,
                                                 "searchText": text}).json().get("jobPostings") or []
            for p in posts:
                if p.get("externalPath"):
                    found.setdefault(p["externalPath"], p)
            if len(posts) < 20:
                break
    jobs, details = [], 0
    for path, p in found.items():
        loc = p.get("locationsText", "")
        city = lane_city(loc)
        if not city and re.search(r"\d+ Locations", loc) and details < MAX_DETAILS:
            details += 1
            info = f.get(api + path, headers={"Accept": "application/json"}).json().get("jobPostingInfo") or {}
            locs = [info.get("location", "")] + list(info.get("additionalLocations") or [])
            city = next((c for c in map(lane_city, locs) if c), "")
        if city:
            jobs.append({"title": p.get("title", ""), "city": city, "url": f"{base}/{src['site']}{path}",
                         "days": _workday_days(p.get("postedOn")), "snippet": "", "org": ""})
    return jobs


def pull_oracle(f, src):
    base = f"https://{src['host']}"
    found = {}
    for city in SEARCH_CITIES:
        for offset in range(0, 200, 25):
            finder = (f"findReqs;siteNumber={src['site']},limit=25,offset={offset},"
                      f'keyword="{city}",sortBy=POSTING_DATES_DESC')
            r = f.get(base + "/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
                      params={"onlyData": "true", "expand": "requisitionList.secondaryLocations", "finder": finder},
                      headers={"Accept": "application/json"})
            items = (r.json().get("items") or [{}])[0]
            reqs = items.get("requisitionList") or []
            for q in reqs:
                locs = [q.get("PrimaryLocation", "")] + [s.get("Name", "") for s in q.get("secondaryLocations") or []]
                c = next((x for x in map(lane_city, locs) if x), "")
                if c:
                    found.setdefault(q["Id"], (q, c))
            if len(reqs) < 25:
                break
    return [{"title": q.get("Title", ""), "city": c,
             "url": f"{base}/hcmUI/CandidateExperience/en/sites/{src['site']}/job/{q['Id']}",
             "days": days_since(q.get("PostedDate")), "snippet": plain(q.get("ShortDescriptionStr")), "org": ""}
            for q, c in found.values()]


def pull_ukg(f, src):
    base = f"https://{src['host']}/{src['tenant']}/JobBoard/{src['board']}"
    jobs, skip = [], 0
    while skip < 1000:
        body = {"opportunitySearch": {"Top": 50, "Skip": skip, "QueryString": "",
                                      "OrderBy": [{"Value": "postedDateDesc", "PropertyName": "PostedDate", "Ascending": False}],
                                      "Filters": []},
                "matchCriteria": {"PreferredJobs": [], "Educations": [], "LicenseAndCertifications": [], "Skills": [],
                                  "hasNoLicenses": False, "SkippedSkills": []}}
        r = f.post(base + "/JobBoardView/LoadSearchResults", json=body, headers={"Accept": "application/json"})
        data = r.json()
        opps = data.get("opportunities") or []
        for o in opps:
            locs = []
            for l in o.get("Locations") or []:
                a = l.get("Address") or {}
                st = (a.get("State") or {}).get("Code", "")
                locs.append(f"{a.get('City', '')}, {st} {l.get('LocalizedDescription', '')}")
            c = next((x for x in map(lane_city, locs) if x), "")
            if c:
                jobs.append({"title": o.get("Title", ""), "city": c,
                             "url": f"{base}/OpportunityDetail?opportunityId={o['Id']}",
                             "days": days_since(o.get("PostedDate")), "snippet": plain(o.get("BriefDescription")), "org": ""})
        skip += 50
        if len(opps) < 50 or skip >= (data.get("totalCount") or 0):
            break
    return jobs


_PH = re.compile(r'\{"id":"(\d+)","title":"((?:[^"\\]|\\.)*)","permalink":"([^"]*)"(?:[^{}]|\{[^{}]*\})*?"location_string":"((?:[^"\\]|\\.)*)"')


def pull_peacehealth(f, src):
    jobs, seen = [], set()
    for page in range(1, 80):
        h = f.get(f"https://{src['host']}/jobs", params={"page": page}).text
        rows = _PH.findall(h)
        new = [r for r in rows if r[0] not in seen]
        if not new:
            break
        for jid, title, slug, loc in new:
            seen.add(jid)
            c = lane_city(json.loads(f'"{loc}"'))
            if c:
                jobs.append({"title": json.loads(f'"{title}"'), "city": c,
                             "url": f"https://{src['host']}/jobs/{jid}-{slug}", "days": None, "snippet": "", "org": ""})
    return jobs


CONNECTORS = {"Workday": pull_workday, "Oracle Recruiting": pull_oracle, "UKG (UltiPro)": pull_ukg,
              "PeaceHealth careers site": pull_peacehealth}
