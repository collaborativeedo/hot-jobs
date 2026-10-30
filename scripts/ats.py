"""More hiring systems, plus a browser-based reader for careers pages that need JavaScript.

Used for employers found by name (data/employer-sites.json) as well as those learned from posting links.
Each connector returns rows: {title, city, url, days, snippet, org, info}.

The browser reader loads a careers page the way a person's browser would (it runs the page's JavaScript),
identifies itself honestly, and stops if the site refuses automated visitors (401/403/429) or shows a
challenge page. It never logs in or fills in forms.
"""
import json
import re
from urllib.parse import urljoin, urlparse

from direct import (LANE_CITIES, NOT_LANE, UA, days_since, lane_city, plain)

LOCAL_OK = re.compile(r"\b(OR|Oregon|Lane County|Remote)\b", re.I)


def keep_city(location, local, home=""):
    """Lane County town for a posting, or None to skip it.

    National employers: keep only postings that name a Lane County town.
    Lane County employers: also keep postings with no location, or an Oregon one that is not clearly elsewhere.
    """
    c = lane_city(location or "") or lane_city(f"{location or ''}, OR" if location and "," not in location else "")
    if c:
        return c
    if not local:
        return None
    loc = location or ""
    if NOT_LANE.search(loc) or re.search(r"[A-Za-z]\s*,\s*(?:[A-Z]{2}|Oregon)\b", loc):
        return None  # names some other town ("Welches, OR", "Boise, ID")
    return home or "Lane County"


# ---- Recognizing hiring systems from a careers page address -----------------------------------------

def source_from_url(url):
    u = (url or "").strip()
    pats = [
        (r"https?://(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)", "Greenhouse", "token"),
        (r"https?://boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", "Greenhouse", "token"),
        (r"https?://jobs\.lever\.co/([A-Za-z0-9_-]+)", "Lever", "token"),
        (r"https?://(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", "SmartRecruiters", "token"),
        (r"https?://([a-z0-9-]+)\.breezy\.hr", "Breezy HR", "token"),
        (r"https?://apply\.workable\.com/([A-Za-z0-9_-]+)", "Workable", "token"),
        (r"https?://([a-z0-9-]+)\.bamboohr\.com", "BambooHR", "token"),
        (r"https?://recruiting\.paylocity\.com/recruiting/jobs/(?:All|Details/\d+)/([0-9a-f-]{36})", "Paylocity", "token"),
        (r"https?://([a-z0-9-]+)\.applytojob\.com", "JazzHR", "token"),
        (r"https?://([a-z0-9-]+)\.pinpointhq\.com", "Pinpoint", "token"),
        (r"https?://(?:www\.)?amazon\.jobs()", "Amazon", "token"),
        (r"https?://ats\.rippling\.com/(?:[a-z-]+/)?([A-Za-z0-9_-]+)/jobs", "Rippling", "token"),
        (r"https?://workforcenow\.adp\.com/.*[?&]cid=([0-9a-f-]{36})", "ADP Workforce Now", "token"),
    ]
    for rx, plat, field in pats:
        m = re.match(rx, u, re.I)
        if m and m.group(1).lower() not in ("www", "api", "jobs", "careers", "embed"):
            tok = m.group(1)
            src = {"platform": plat, field: tok, "host": urlparse(u).netloc.lower()}
            if plat == "ADP Workforce Now":
                cc = re.search(r"[?&]ccId=([^&]+)", u)
                src["ccid"] = cc.group(1) if cc else "19000101_000001"
            return f"{plat.lower().split()[0]}:{tok.lower()}", src
    return None


# ---- Connectors for hiring systems with public job feeds ---------------------------------------------

_SOCIAL = re.compile(r"^(bluesky|facebook|instagram|linkedin|twitter|x|youtube|tiktok|nextdoor|pinterest|yelp|resumes?|"
                     r"create a job alert|job market outlook|career areas|.* careers|ai/ml roles.*|how to apply|"
                     r"freshman .*|benefits (&|and) perks|careers blog|join our talent community|chair for rent|"
                     r"clinical|corporate|behavioral health operations|working at .*|federal benefits|"
                     r"general application.*|talent (community|network)|career (opportunities|fairs?)|our culture)$", re.I)
_JOB_WORD = re.compile(r"\b(manager|manger|assistant|associate|technician|tech|specialist|coordinator|director|engineer|nurse|"
                       r"driver|operator|officer|clerk|cleaner|custodian|janitor|coach|teacher|instructor|faculty|professor|"
                       r"designer|developer|analyst|consultant|supervisor|lead|foreman|superintendent|cook|chef|server|"
                       r"cashier|stylist|barber|therapist|counselor|aide|worker|laborer|attendant|representative|rep|agent|"
                       r"advisor|adviser|planner|scientist|mlt|mls|medic|deputy|guard|security|leader|intern|apprentice|"
                       r"orthodontist|dentist|hygienist|physician|surgeon|pharmacist|accountant|bookkeeper|recruiter|"
                       r"receptionist|mechanic|electrician|plumber|carpenter|painter|welder|machinist|installer|inspector|"
                       r"estimator|buyer|police|firefighter|paramedic|emt|trainer|caregiver|housekeeper|dishwasher|"
                       r"bartender|barista|host|hostess|valet|porter|courier|loader|handler|picker|packer|stocker|"
                       r"merchandiser|teller|banker|underwriter|adjuster|administrator|executive|president|officer|"
                       r"head|chief|crew|staff|member|helper|apprentice|journeyman|journeyworker|lineman|operator|"
                       r"veterinarian|groomer|kennel|lifeguard|librarian|paralegal|attorney|lawyer|editor|writer|"
                       r"producer|photographer|artist|architect|surveyor|drafter|programmer|administrator|navigator|"
                       r"educator|tutor|interpreter|translator|dispatcher|scheduler|estimator|controller|auditor|"
                       r"para|paraeducator|substitute|nanny|provider|clinician|psychologist|social worker|"
                       r"phlebotomist|radiologic|sonographer|respiratory|cna|lpn|rn|np|pa-c|dds|dmd|md|pathologist|childcare|"
                       r"crewmember|teammate|entry level|folder|feeder|assessor|archaeologist|biologist|chemist|technologist|"
                       r"interpreter|provider|producer|maker|shopper|reviewer|scholar|postdoc|in charge|baker|butcher|"
                       r"professional|nutritionist|dietitian|\w+ologist)s?\b", re.I)
_NOT_JOB = re.compile(r"^#|\(\d+\)|^(here|click here|learn more|apply|apply now|load more|view all|see all|"
                      r"full job posting|saved jobs?|job areas|our locations|locations|who we are|equal opportunity|"
                      r"job scams?|military|veterans|students|university programs|launch your career|start a career|"
                      r"explore .*|search .*|career map|benefits( (and|&) (perks|career development))?|life at .*|.* careers?)\.?$|"
                      r"\btips\b|\bsign up\b", re.I)


def looks_like_job(title):
    """True when a link's text reads like a job title rather than a menu item, heading or article."""
    t = (title or "").strip()
    if not t or _NOT_JOB.search(t) or _SOCIAL.match(t) or len(t.split()) > 14:
        return False
    if _JOB_WORD.search(t):
        return True
    import enrich  # a title the occupation rules recognize ("Server", "Welder") is a job too
    return bool(enrich.soc_for_title(t, {}))


_NOT_HERE = re.compile(r"\b(remote|portland|seattle|boise|sacramento|san francisco|los angeles|new york|chicago|denver|"
                        r"phoenix|dallas|houston|atlanta|boston|calgary|winnipeg|vancouver|toronto|montreal|edmonton|"
                        r"ottawa|bend|medford|salem|corvallis|albany|beaverton|hillsboro|tigard|gresham)\b|"
                        r"\b[A-Z][a-z]+,\s*(?-i:(?:AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|"
                        r"NH|NJ|NM|NY|NC|ND|OH|OK|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|AB|BC|MB|ON|QC|SK))\b|"
                        r"\b(idaho|california|nevada|utah|arizona|montana|wyoming|colorado|texas|alaska|hawaii|"
                        r"new mexico|florida|georgia|ohio|michigan|minnesota|wisconsin|illinois|indiana|missouri|"
                        r"alberta|british columbia|manitoba|ontario|quebec|saskatchewan|pocatello|twin falls|"
                        r"idaho falls|coeur d'alene|spokane|tacoma|olympia|reno|las vegas|tucson|wood river valley|"
                        r"roseburg|grants pass|coos bay|north bend|newport|lebanon|klamath falls|ashland|astoria|"
                        r"the dalles|pendleton|hermiston|redmond|mcminnville|woodburn|keizer|sweet home|brownsville|"
                        r"harrisburg|reedsport|sutherlin|philomath|monmouth|lincoln city|tillamook|"
                        r"salt lake city|st\.? petersburg|minneapolis|st\.? louis|kansas city|san diego|san jose|oakland|"
                        r"nashville|charlotte|orlando|miami|tampa|pittsburgh|philadelphia|detroit|indianapolis|"
                        r"cincinnati|cleveland|baltimore|omaha|albuquerque|oklahoma city|louisville|memphis|milwaukee|"
                        r"raleigh|honolulu|anchorage|everett|bellevue|yakima|eureka|redding|chico|fresno|bakersfield|"
                        r"(?:linn|benton|douglas|coos|lincoln|marion|polk|deschutes|jackson|josephine|klamath|multnomah|"
                        r"clackamas|yamhill|curry|crook|jefferson|hood river|wasco|umatilla|malheur|clatsop|tillamook|"
                        r"columbia) county)\b|"
                        r",\s*washington\b", re.I)


_REMOTE = re.compile(r"\b(remote|work from home|wfh|telecommute|virtual)\b", re.I)
_NOT_REMOTE = re.compile(r"\b(not remote|no remote|non-remote|on-?site only)\b", re.I)
# A remote posting can also name the country or a region; these do not make it "somewhere else".
_REMOTE_AREA = re.compile(r"^\W*(remote|work from home|virtual)\W*(\(?\s*(us|usa|u\.s\.|united states|north america|"
                          r"pacific northwest|pnw|oregon|or|anywhere|nationwide|pst|pacific time)\s*\)?)?\W*$", re.I)


def is_remote(title, loc):
    t = f"{title or ''} {loc or ''}"
    return bool(_REMOTE.search(t)) and not _NOT_REMOTE.search(t)


def _rows(items, local, home, remote_ok=False):
    """Postings in Lane County. local=True: a Lane County employer (hand-checked), whose postings with no location
    are kept. local="maybe": found automatically (employer database, chamber directories); its postings with no
    location are kept only when the employer looks local: a handful of postings and none naming another place.
    Otherwise only postings that name a Lane County town are kept."""
    items = [it for it in items if it.get("title") and it.get("url") and not _SOCIAL.match(plain(it["title"], 200).strip())]
    named = sum(1 for it in items if lane_city(it.get("loc", "") or ""))
    elsewhere = sum(1 for it in items if not lane_city(it.get("loc", "") or "")
                    and (_NOT_HERE.search(it.get("loc", "") or "") or _NOT_HERE.search(it.get("title") or "")))
    if local == "maybe" and (elsewhere >= 3 or elsewhere > named):
        local = False  # a regional or national employer: only postings that name a Lane County town
    if local == "maybe" and (len(items) - named > 8):
        local = False  # too many unplaced postings for a one-site local employer
    out = []
    for it in items:
        loc = it.get("loc", "") or ""
        if remote_ok and is_remote(it.get("title"), loc) and not lane_city(loc) and (
                not loc.strip() or _REMOTE_AREA.match(loc) or not _NOT_HERE.search(re.sub(_REMOTE, "", loc))):
            # A remote job with an employer that has a Lane County presence (hand-checked): kept, marked remote.
            out.append({"title": plain(it["title"], 200), "city": "Remote", "remote": True, "url": it["url"],
                        "days": it.get("days"), "snippet": plain(it.get("snippet", ""), 300), "org": "",
                        "info": it.get("info", "")})
            continue
        if not lane_city(it.get("loc", "") or "") and not lane_city(it.get("title") or "") and (
                _NOT_HERE.search(it.get("title") or "") or _NOT_HERE.search(it.get("loc", "") or "")):
            continue  # names some other place
        c = keep_city(it.get("loc", ""), local, home)
        if c:
            out.append({"title": plain(it["title"], 200), "city": c, "remote": is_remote(it.get("title"), loc),
                        "url": it["url"], "days": it.get("days"),
                        "snippet": plain(it.get("snippet", ""), 300), "org": "", "info": it.get("info", "")})
    return out


def pull_greenhouse(f, src):
    data = f.get(f"https://boards-api.greenhouse.io/v1/boards/{src['token']}/jobs", params={"content": "true"}).json()
    return _rows([{"title": j.get("title"), "loc": (j.get("location") or {}).get("name", ""), "url": j.get("absolute_url"),
                   "days": days_since(j.get("updated_at")), "snippet": j.get("content", "")}
                  for j in data.get("jobs", [])], src.get("local"), src.get("home", ""), src.get("remote_ok"))


def pull_lever(f, src):
    data = f.get(f"https://api.lever.co/v0/postings/{src['token']}", params={"mode": "json"}).json()
    rows = []
    for j in data if isinstance(data, list) else []:
        cat = j.get("categories") or {}
        created = j.get("createdAt")
        rows.append({"title": j.get("text"), "loc": cat.get("location", ""), "url": j.get("hostedUrl"),
                     "days": None if not created else days_since(__import__("datetime").datetime.utcfromtimestamp(created / 1000).isoformat()),
                     "snippet": j.get("descriptionPlain", ""), "info": cat.get("commitment", "")})
    return _rows(rows, src.get("local"), src.get("home", ""), src.get("remote_ok"))


def pull_smartrecruiters(f, src):
    rows, offset = [], 0
    while offset < 1000:
        data = f.get(f"https://api.smartrecruiters.com/v1/companies/{src['token']}/postings",
                     params={"limit": 100, "offset": offset, "country": "us", "region": "OR"}).json()
        content = data.get("content") or []
        for j in content:
            loc = j.get("location") or {}
            rows.append({"title": j.get("name"), "loc": f"{loc.get('city', '')}, {loc.get('region', '')}",
                         "url": f"https://jobs.smartrecruiters.com/{src['token']}/{j.get('id')}",
                         "days": days_since(j.get("releasedDate")), "info": (j.get("typeOfEmployment") or {}).get("label", "")})
        offset += 100
        if len(content) < 100:
            break
    return _rows(rows, src.get("local"), src.get("home", ""), src.get("remote_ok"))


def pull_breezy(f, src):
    data = f.get(f"https://{src['token']}.breezy.hr/json").json()
    return _rows([{"title": j.get("name"), "url": j.get("url"),
                   "loc": f"{(j.get('location') or {}).get('city', '')}, {((j.get('location') or {}).get('state') or {}).get('id', '')}",
                   "days": days_since(j.get("published_date")), "info": f"{(j.get('type') or {}).get('name', '')} {j.get('salary') or ''}"}
                  for j in data if isinstance(j, dict)], src.get("local"), src.get("home", ""), src.get("remote_ok"))


def pull_workable(f, src):
    data = f.get(f"https://apply.workable.com/api/v1/widget/accounts/{src['token']}").json()
    return _rows([{"title": j.get("title"), "url": j.get("url") or j.get("application_url"),
                   "loc": f"{j.get('city', '')}, {j.get('state', '')}", "days": days_since(j.get("created_at") or j.get("published_on")),
                   "info": j.get("employment_type", "")} for j in data.get("jobs", [])], src.get("local"), src.get("home", ""), src.get("remote_ok"))


def pull_bamboohr(f, src):
    base = f"https://{src['token']}.bamboohr.com"
    data = f.get(f"{base}/careers/list", headers={"Accept": "application/json"}).json()
    return _rows([{"title": j.get("jobOpeningName"), "url": f"{base}/careers/{j.get('id')}",
                   "loc": f"{(j.get('location') or {}).get('city') or ''}, {(j.get('location') or {}).get('state') or ''}",
                   "info": j.get("employmentStatusLabel", "")} for j in data.get("result", [])], src.get("local"), src.get("home", ""), src.get("remote_ok"))


def pull_paylocity(f, src):
    """Paylocity boards embed their full job list in the page (window.pageData)."""
    page = f.get(f"https://recruiting.paylocity.com/Recruiting/Jobs/All/{src['token']}").text
    i = page.find("pageData")
    j = page.find("{", i) if i >= 0 else -1
    data = json.JSONDecoder().raw_decode(page[j:])[0] if j >= 0 else {}
    rows = []
    for job in data.get("Jobs") or []:
        loc = job.get("JobLocation") or {}
        where = f"{loc.get('City', '')}, {loc.get('State', '')}"
        if (loc.get("County") or "").upper() == "LANE" and not lane_city(where):
            where = "Lane County, OR"
        rows.append({"title": job.get("JobTitle"), "loc": where, "days": days_since(job.get("PublishedDate")),
                     "url": f"https://recruiting.paylocity.com/Recruiting/Jobs/Details/{job.get('JobId')}",
                     "snippet": job.get("Description", "")})
    return _rows(rows, src.get("local"), src.get("home", ""), src.get("remote_ok"))


def pull_jazzhr(f, src):
    from bs4 import BeautifulSoup
    base = f"https://{src['token']}.applytojob.com"
    soup = BeautifulSoup(f.get(f"{base}/apply").text, "html.parser")
    rows = []
    for li in soup.select("li.list-group-item"):
        a = li.select_one("a[href]")
        if not a:
            continue
        rows.append({"title": a.get_text(" ", strip=True), "url": urljoin(base + "/", a["href"]),
                     "loc": plain(li.get_text(" "), 300).replace(a.get_text(" ", strip=True), "")})
    return _rows(rows, src.get("local"), src.get("home", ""), src.get("remote_ok"))


# ---- Browser reader for careers pages without a known hiring system ---------------------------------------

_NAV = re.compile(r"^(careers?|jobs?|job search|search( jobs)?|apply( now)?|home|about( us)?|benefits|login|log in|sign in|"
                  r"view (all|more|details|job)|learn more|read more|more|next|previous|back|contact( us)?|privacy|"
                  r"terms|current openings|open positions|see (all )?(openings|jobs)|join (our|the) team|"
                  r"employment( opportunities)?|why work (here|with us)|students?|internships?|culture|faq|news|blog|"
                  r"skip to( main)? content|general application|apply anytime|find a job|job shadows?.*|"
                  r"work at .*|applying for a job.*|view (open )?positions|all jobs|job openings|open jobs|"
                  r"english|español|espanol|français|deutsch|italiano|português|中文|日本語|한국어|tiếng việt|русский|العربية)$", re.I)
_JUNK = re.compile(r"notify me|privacy|cookie|personal information|subscribe|newsletter|polski|português|portugues|"
                   r"nederlands|svenska|türkçe|accessibility|sitemap|donate|do not sell|terms of use|"
                   r"^(job |digital |online |general )?applications?$|(internal|external) jobs?|jobs? openings$|"
                   r"^job title$|^view\b|^start\b.*application|^apply\b|^click here|\bclosed\b|accepting applications|"
                   r"^all categories$|^listing information$|\bvolunteer\b|^(all|show( me)? all|find|see all|browse|view all)\b.*\b(jobs|positions|openings)\b|"
                   r"positions near me|job descriptions|^admin$|^events?$|^job details$|^more info$|^details$|accepted anytime|^apply anytime", re.I)
_FILTER_QUERY = re.compile(r"(^|&)(department|dept|category|categories|catid|cat|filter|team|location|type)=", re.I)
_ELSEWHERE = re.compile(r"\b(Portland|Bend|Hillsboro|Medford|Beaverton|Tigard|Gresham|Redmond|Klamath Falls|Grants Pass|"
                        r"Coos Bay|Astoria|Seaside|Tillamook|Roseburg|Salem|Corvallis|Albany|Lake Oswego|Wilsonville|"
                        r"Vancouver|Seattle|Boise)\b")
_LOCATION_ONLY = re.compile(r"^[A-Za-z .'-]+,\s*(OR|Oregon)\b[\s\d-]*$")
_BAD_PATH = re.compile(r"/(category|categories|tag|department|departments|location|locations|search|login|benefits)(/|$)|"
                       r"^/(es|fr|de|it|pt|zh|ja|ko|vi|ru|ar)(/|$)", re.I)


def pull_pinpoint(f, src):
    data = f.get(f"https://{src['token']}.pinpointhq.com/postings.json").json()
    rows = []
    for j in (data.get("data") if isinstance(data, dict) else data) or []:
        loc = j.get("location") or {}
        where = loc.get("name") or ", ".join(x for x in (loc.get("city"), loc.get("province")) if x) if isinstance(loc, dict) else str(loc)
        rows.append({"title": j.get("title"), "loc": where or "", "url": j.get("url") or j.get("path"),
                     "days": days_since(j.get("published_at") or j.get("created_at")),
                     "snippet": j.get("description") or "", "info": j.get("employment_type_text") or j.get("employment_type") or ""})
    return _rows(rows, src.get("local"), src.get("home", ""), src.get("remote_ok"))


def _amazon_days(text):
    from datetime import datetime
    try:
        return days_since(datetime.strptime((text or "").strip(), "%B %d, %Y").date().isoformat())
    except ValueError:
        return None


def pull_amazon(f, src):
    """amazon.jobs: postings within about 40 km of Eugene, plus (for remote-friendly listing) the newest US
    virtual/remote roles. Locations look like "US, OR, Eugene" or "US, Virtual"."""
    base = "https://www.amazon.jobs/en/search.json"
    rows, seen = [], set()
    queries = [{"loc_query": "Eugene, Oregon, United States", "latitude": "44.0521", "longitude": "-123.0868",
                "radius": "40km", "country": "USA"}]
    if src.get("remote_ok"):
        queries.append({"base_query": "virtual", "country": "USA"})
    for q in queries:
        for offset in range(0, 500, 100):
            data = f.get(base, params=dict(q, result_limit=100, offset=offset, sort="recent")).json()
            jobs = data.get("jobs") or []
            for j in jobs:
                path = j.get("job_path") or ""
                if not path or path in seen:
                    continue
                seen.add(path)
                parts = [p.strip() for p in (j.get("location") or "").split(",")]
                city = j.get("city") or (parts[2] if len(parts) > 2 else "")
                state = j.get("state") or (parts[1] if len(parts) > 1 else "")
                virtual = re.search(r"virtual|remote", f'{j.get("location", "")} {j.get("title", "")}', re.I)
                if virtual and (j.get("country_code") in (None, "", "USA", "US") or "US" in parts[:1]):
                    loc = "Remote (United States)"
                else:
                    loc = f"{city}, {state}" if city else (j.get("location") or "")
                rows.append({"title": j.get("title"), "loc": loc, "url": "https://www.amazon.jobs" + path,
                             "days": _amazon_days(j.get("posted_date")),
                             "snippet": j.get("description_short") or "", "info": j.get("job_schedule_type") or ""})
            if len(jobs) < 100 or q.get("base_query"):
                break  # remote: the newest 100 are plenty (the run keeps at most 15 per employer)
    return _rows(rows, src.get("local"), src.get("home", ""), src.get("remote_ok"))


def pull_rippling(f, src):
    data = f.get(f"https://api.rippling.com/platform/api/ats/v1/board/{src['token']}/jobs").json()
    rows = []
    for j in (data if isinstance(data, list) else data.get("items") or data.get("jobs") or []):
        locs = j.get("workLocations") or ([j["workLocation"]] if j.get("workLocation") else [])
        names = [(l.get("label") or l.get("name") or "") if isinstance(l, dict) else str(l) for l in locs]
        url = j.get("url") or f"https://ats.rippling.com/{src['token']}/jobs/{j.get('uuid') or j.get('id')}"
        for where in names or [""]:
            rows.append({"title": j.get("name") or j.get("title"), "loc": where, "url": url,
                         "info": (j.get("employmentType") or {}).get("label", "") if isinstance(j.get("employmentType"), dict) else ""})
    return _rows(rows, src.get("local"), src.get("home", ""), src.get("remote_ok"))


def pull_adp(f, src):
    cid, cc = src["token"], src.get("ccid", "19000101_000001")
    base = "https://workforcenow.adp.com/mascsr/default"
    rows, skip = [], 0
    while skip < 500:
        data = f.get(f"{base}/careercenter/public/events/staffing/v1/job-requisitions",
                     params={"cid": cid, "ccId": cc, "lang": "en_US", "locale": "en_US", "timeStamp": "1",
                             "$top": 50, "$skip": skip}).json()
        reqs = data.get("jobRequisitions") or []
        for j in reqs:
            locs = []
            for l in j.get("requisitionLocations") or []:
                a = l.get("address") or {}
                st = (a.get("countrySubdivisionLevel1") or {}).get("codeValue", "")
                locs.append(f"{a.get('cityName', '')}, {st}".strip(", ") or (l.get("nameCode") or {}).get("shortName", ""))
            rows.append({"title": j.get("requisitionTitle"), "loc": locs[0] if locs else "",
                         "url": f"{base}/mdf/recruitment/recruitment.html?cid={cid}&ccId={cc}&jobId={j.get('itemID')}&lang=en_US",
                         "days": days_since(j.get("postDate")), "info": (j.get("workLevelCode") or {}).get("shortName", "")})
        skip += 50
        if len(reqs) < 50:
            break
    return _rows(rows, src.get("local"), src.get("home", ""), src.get("remote_ok"))


def _job_title(text, row):
    t = re.sub(r"^\{?\d{2,}\}?\s*", "", text).strip()
    if _LOCATION_ONLY.match(t):  # the link text is the location; the title is elsewhere in the row
        rest = row.replace(text, " ").strip()
        t = re.split(r"\s{2,}|\s[|•·]\s", rest)[0].strip() if rest else ""
    t = re.sub(r"\s*\{[^}]*\}.*$", "", t)                       # "Clerk {Springfield, OR} ..." -> "Clerk"
    t = re.split(r"\s+(?=(?:" + "|".join(LANE_CITIES) + r"),\s*OR)", t)[0]  # drop trailing "Eugene, OR..."
    return t.strip(" -|•·")
_JOBLINK = re.compile(r"/(jobs?|careers?|positions?|openings?|postings?|requisitions?|vacanc|opportunit|apply|job-details|jobdetail)"
                      r"|viewjob|job_?description|jobposting|/hire/|/employment/"
                      r"|^/j/[a-z0-9]{6,}/[^/]+/[^/]+/[^/]+", re.I)  # Workstream: /j/<account>/<brand>/<location>/<position>
_CHALLENGE = re.compile(r"verify you are (a )?human|are you a robot|access denied|captcha|attention required|unusual traffic", re.I)
_ATS_HOSTS = re.compile(r"greenhouse\.io|lever\.co|smartrecruiters\.com|breezy\.hr|workable\.com|bamboohr\.com|"
                        r"paylocity\.com|applytojob\.com|myworkdayjobs\.com|oraclecloud\.com|ultipro\.com|"
                        r"governmentjobs\.com|schooljobs\.com|icims\.com|paycomonline\.net|adp\.com", re.I)


class Browser:
    """One headless Chromium for the whole run, started only if a careers page needs it."""

    def __init__(self):
        self.pw = self.browser = None

    def page(self):
        if not self.browser:
            from playwright.sync_api import sync_playwright
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.launch()
        ctx = self.browser.new_context(user_agent=f"Mozilla/5.0 (compatible; {UA})", viewport={"width": 1280, "height": 1600})
        return ctx.new_page()

    def close(self):
        if self.browser:
            self.browser.close()
            self.pw.stop()


def _jsonld_jobs(html, base):
    rows = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if d.get("@type") == "JobPosting":
                    loc = d.get("jobLocation") or {}
                    loc = loc[0] if isinstance(loc, list) and loc else loc
                    addr = (loc.get("address") if isinstance(loc, dict) else {}) or {}
                    if isinstance(addr, str):
                        addr = {"addressLocality": addr}
                    pay = d.get("baseSalary") or {}
                    val = pay.get("value") if isinstance(pay, dict) else {}
                    pay_txt = ""
                    if isinstance(val, dict) and (val.get("minValue") or val.get("value")):
                        unit = (val.get("unitText") or "").lower()
                        lo, hi = val.get("minValue") or val.get("value"), val.get("maxValue")
                        pay_txt = f"${lo} to ${hi} per {unit}" if hi else f"${lo} per {unit}"
                    rows.append({"title": d.get("title"), "url": urljoin(base, d.get("url") or base),
                                 "loc": f"{addr.get('addressLocality', '')}, {addr.get('addressRegion', '')}",
                                 "days": days_since(d.get("datePosted")), "snippet": d.get("description", ""),
                                 "info": f"{d.get('employmentType', '')} {pay_txt}"})
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
            elif isinstance(d, list):
                stack.extend(d)
    return rows


def pull_careers_page(f, src, browser):
    """Read a careers page with a real browser engine; hand off to a hiring-system connector if it uses one."""
    url = src["url"]
    page = browser.page()
    try:
        resp = page.goto(url, wait_until="networkidle", timeout=45000)
        if resp is not None and resp.status in (401, 403, 429):
            raise PermissionError(f"site refused automated visitors ({resp.status})")
        page.wait_for_timeout(1500)
        html = page.content()
        if _CHALLENGE.search(page.title() or "") or _CHALLENGE.search(html[:5000]):
            raise PermissionError("site shows a human-verification challenge")
        links = page.eval_on_selector_all("a[href]", """els => els.map(a => {
            const row = a.closest('li,tr,article,.job,.posting,[class*=job],[class*=posting],[class*=opening]') || a.parentElement;
            return {href: a.href, text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g,' '),
                    row: ((row && row.innerText) || '').trim().replace(/\\s+/g,' ').slice(0, 300)};
        })""")
        frames = page.eval_on_selector_all("iframe[src]", "els => els.map(e => e.src)")
    finally:
        page.context.close()

    # A careers page that embeds or links to a known hiring system: use that system's own connector next time.
    for u in frames + [l["href"] for l in links]:
        if _ATS_HOSTS.search(u or ""):
            found = source_from_url(u)
            if found:
                return {"handoff": found}
            import direct
            found = direct.source_from_url(u)
            if found:
                return {"handoff": found}

    rows = _jsonld_jobs(html, url)
    if not rows:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        seen = set()
        for l in links:
            h, t = l["href"], l["text"]
            lh = (urlparse(h).hostname or "").lower().removeprefix("www.")
            pu = urlparse(h)
            if "#" in h and h.split("#")[0].rstrip("/") == url.split("#")[0].rstrip("/"):
                continue  # a link to a spot on the same page
            h = h.split("#")[0]
            if not t or h in seen or _NAV.match(t):
                continue
            if not (lh == host or lh.endswith("." + host) or host.endswith("." + lh) or _ATS_HOSTS.search(lh)):
                continue
            if (not _JOBLINK.search(pu.path) or _BAD_PATH.search(pu.path) or _FILTER_QUERY.search(pu.query)
                    or h.rstrip("/").lower() == url.split("#")[0].rstrip("/").lower()):
                continue
            t = _job_title(t, l["row"])
            t = re.sub(r"(?<=[a-z])(?:Full|Part)-time$", "", t or "").strip()  # "Shift LeadFull-time"
            if (not t or len(t) < 4 or len(t) > 120 or _NAV.match(t) or not re.search(r"[A-Za-z]{3}", t)
                    or _JUNK.search(t) or _ELSEWHERE.search(t)):
                continue
            if not looks_like_job(t):
                continue  # menu items, headings, articles ("Our Locations", "6 Tips for Writing a Resume")
            seen.add(h)
            rows.append({"title": t, "url": h, "loc": l["row"], "days": None})
            if len(rows) >= 60:
                break
    return _rows(rows, src.get("local", True), src.get("home", ""), src.get("remote_ok"))


CONNECTORS = {"Greenhouse": pull_greenhouse, "Lever": pull_lever, "SmartRecruiters": pull_smartrecruiters,
              "Breezy HR": pull_breezy, "Workable": pull_workable, "BambooHR": pull_bamboohr,
              "Paylocity": pull_paylocity, "JazzHR": pull_jazzhr, "Pinpoint": pull_pinpoint, "Amazon": pull_amazon,
              "Rippling": pull_rippling, "ADP Workforce Now": pull_adp}
