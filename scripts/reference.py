"""Reference data for two job-seeker filters: "Near an LTD bus stop" and "No degree required".

soc_education(log)   6-digit SOC (no dash) -> BLS "typical education needed for entry", from the
                     BLS Employment Projections education table (Table 5.4). Cached in
                     data/soc-education.json and re-read at most every 120 days.
transit_tags(jobs, log)
                     Sets j["near_bus"] True/False when the employer's Lane County address(es) can be
                     found in the QualityInfo employer database (data/empdb-lane.json) and geocoded;
                     leaves it out when unknown. Uses LTD's public GTFS stops (data/ltd-stops.json,
                     refreshed weekly) and the US Census batch geocoder (data/geocode-cache.json).

Both functions never raise: on any failure they fall back to the cached data (or do nothing) and
add a one-line note to the run log.

CLI (run by .github/workflows/reference.yml):
    python scripts/reference.py --refresh [--geocode-all]
"""
import csv
import io
import json
import math
import re
import sys
import time
import zipfile
import datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SOC_CACHE = DATA / "soc-education.json"
STOPS_CACHE = DATA / "ltd-stops.json"
GEO_CACHE = DATA / "geocode-cache.json"
EMPDB = DATA / "empdb-lane.json"

UA = "LaneCountyHotJobs/1.0 (matts@collaborativeedo.org)"

# BLS Employment Projections: every education table in one workbook; Table 5.4 is
# "Education and training assignments by detailed occupation".
BLS_EDUCATION_URL = "https://www.bls.gov/emp/ind-occ-matrix/education.xlsx"
SOC_MAX_AGE_DAYS = 120

# LTD's own GTFS feed (producer URL listed by the Mobility Database, feed mdb-131), then the
# Mobility Database's mirror of the latest copy it fetched.
LTD_GTFS_URLS = [
    "https://www.ltd.org/files/library/ltdgtfs.zip",
    "https://files.mobilitydatabase.org/mdb-131/latest.zip",
]
STOPS_MAX_AGE_DAYS = 7

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
CENSUS_BENCHMARK = "Public_AR_Current"
GEOCODE_NIGHTLY_CAP = 3000     # new addresses geocoded per nightly run
GEOCODE_NIGHTLY_CHUNK = 1000   # rows per request during the nightly run (progress is saved per chunk)
GEOCODE_NIGHTLY_SECONDS = 150  # stop starting new geocoding requests after this long
GEOCODE_ALL_CHUNK = 10000      # Census batch limit, used by --geocode-all
MISS_RETRY_DAYS = 60

NEAR_METERS = 400.0
NO_DEGREE_LEVELS = {"No formal educational credential", "High school diploma or equivalent"}

# Rough box around Lane County, to drop stray stops (bad coordinates, out-of-area park-and-rides).
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 43.3, 44.5, -124.3, -121.7


def _say(log, msg):
    if isinstance(log, list):
        log.append(msg)
    else:
        print(msg)


def _today():
    return dt.date.today()


def _age_days(iso):
    try:
        return (_today() - dt.date.fromisoformat(str(iso)[:10])).days
    except (TypeError, ValueError):
        return 10 ** 6


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"})
    return s


# ---------------------------------------------------------------------------------------------
# No degree required: BLS typical education needed for entry
# ---------------------------------------------------------------------------------------------

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _col_index(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xlsx_sheets(data):
    """Yield (sheet name, rows) for every sheet of an xlsx file, using only the standard library.
    Each row is a list of cell strings (empty string for blank cells)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))
    rels = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
            target = r.get("Target", "")
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            rels[r.get("Id")] = target
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    for sh in wb.findall("m:sheets/m:sheet", _NS):
        path = rels.get(sh.get(_REL))
        if not path or path not in names:
            continue
        rows = []
        for row in ET.fromstring(z.read(path)).iter("{%s}row" % _NS["m"]):
            cells = {}
            for i, c in enumerate(row.findall("m:c", _NS)):
                ref = c.get("r")
                col = _col_index(ref) if ref else i
                t = c.get("t")
                if t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % _NS["m"]))
                else:
                    v = c.find("m:v", _NS)
                    val = v.text if v is not None and v.text is not None else ""
                    if t == "s" and val != "":
                        val = shared[int(val)]
                cells[col] = val
            rows.append([cells.get(k, "") for k in range(max(cells) + 1)] if cells else [])
        yield sh.get("name", ""), rows


def _clean_level(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    return re.sub(r"\s*\(\d+\)$", "", s)  # footnote markers like "Bachelor's degree(1)"


def parse_education_xlsx(data):
    """SOC (6 digits, no dash) -> typical education needed for entry, from the BLS education workbook.

    Finds the sheet whose header row has an occupation-code column and a "typical education needed
    for entry" column (Table 5.4), so it survives the projection year changing in the headers."""
    best = {}
    for _name, rows in _xlsx_sheets(data):
        code_col = edu_col = None
        out = {}
        for row in rows:
            low = [str(c).strip().lower() for c in row]
            if code_col is None:
                cc = next((i for i, c in enumerate(low) if "code" in c and ("matrix" in c or "occupation" in c or "soc" in c)), None)
                ec = next((i for i, c in enumerate(low) if "education" in c and "entry" in c), None)
                if cc is not None and ec is not None:
                    code_col, edu_col = cc, ec
                continue
            if max(code_col, edu_col) >= len(row):
                continue
            code = str(row[code_col]).strip()
            if re.fullmatch(r"\d{2}-\d{4}", code):
                level = _clean_level(row[edu_col])
                if level:
                    out[code.replace("-", "")] = level
        if len(out) > len(best):
            best = out
    return best


def soc_education(log=None, force=False):
    """SOC (6 digits, no dash) -> BLS typical education needed for entry. Never raises."""
    cache = _read_json(SOC_CACHE, {})
    levels = cache.get("levels") or {}
    if levels and not force and _age_days(cache.get("fetched")) < SOC_MAX_AGE_DAYS:
        return levels
    try:
        r = _session().get(BLS_EDUCATION_URL, timeout=60)
        r.raise_for_status()
        fresh = parse_education_xlsx(r.content)
        if len(fresh) < 300:
            raise ValueError(f"only {len(fresh)} occupations parsed")
        _write_json(SOC_CACHE, {"fetched": _today().isoformat(), "source": BLS_EDUCATION_URL, "levels": fresh})
        _say(log, f"BLS education levels: read {len(fresh)} occupations.")
        return fresh
    except Exception as e:  # noqa: BLE001
        _say(log, f"BLS education levels: refresh failed ({type(e).__name__}: {str(e)[:150]}); "
                  f"using cached table ({len(levels)} occupations).")
        return levels


OEWS_URL = "https://www.bls.gov/oes/current/oes_21660.htm"   # Eugene-Springfield metro area = Lane County
# BLS moves the "current" page between releases; the dated pages stay put. Newest first.
OEWS_URLS = [OEWS_URL] + [f"https://www.bls.gov/oes/{y}/may/oes_21660.htm" for y in range(2026, 2021, -1)]
OEWS_CACHE = DATA / "oews-lane.json"


def parse_oews_html(html):
    """{soc: {"lane_hourly", "lane_annual", "year"}} from BLS's OEWS page for one metro area."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    year = ""
    m = re.search(r"May (20\d\d)", soup.get_text(" ")[:3000])
    if m:
        year = m.group(1)
    out = {}
    for table in soup.find_all("table"):
        heads = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if not any("occupation code" in h for h in heads):
            continue
        cols = [h for h in heads][:12]
        try:
            i_code = next(i for i, h in enumerate(cols) if "occupation code" in h)
            i_hour = next(i for i, h in enumerate(cols) if "mean hourly" in h)
            i_year = next(i for i, h in enumerate(cols) if "annual mean" in h)
        except StopIteration:
            continue
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) <= max(i_code, i_hour, i_year) or not re.fullmatch(r"\d\d-\d{4}", cells[i_code]):
                continue
            num = lambda t: float(re.sub(r"[^0-9.]", "", t)) if re.search(r"\d", t) else None  # noqa: E731
            h, a = num(cells[i_hour]), num(cells[i_year])
            if h or a:
                out[cells[i_code].replace("-", "")] = {"lane_hourly": h, "lane_annual": a, "year": year, "source": "BLS OEWS"}
    return out


def oews_wages(log=None, force=False):
    """Average wages for every occupation in the Eugene-Springfield (Lane County) metro area, from BLS. Never raises."""
    cache = _read_json(OEWS_CACHE, {})
    wages = cache.get("wages") or {}
    if wages and not force and _age_days(cache.get("fetched")) < SOC_MAX_AGE_DAYS:
        return wages
    try:
        sess, fresh, r, used = _session(), {}, None, OEWS_URL
        for used in OEWS_URLS:
            r = sess.get(used, timeout=60)
            if r.status_code == 200:
                fresh = parse_oews_html(r.text)
                if len(fresh) >= 200:
                    break
        if len(fresh) < 200:
            import re as _re
            txt = _re.sub(r"\s+", " ", r.text)
            raise ValueError(f"only {len(fresh)} occupations parsed; status {r.status_code}, {len(r.text)} chars; "
                             f"title {(_re.search(r'<title>(.*?)</title>', txt) or [None, ''])[1][:80]!r}; "
                             f"th sample {_re.findall(r'<th[^>]*>(.*?)</th>', txt)[:6]!r}")
        _write_json(OEWS_CACHE, {"fetched": _today().isoformat(), "source": used, "wages": fresh})
        _say(log, f"BLS wages (Eugene-Springfield): read {len(fresh)} occupations.")
        return fresh
    except Exception as e:  # noqa: BLE001
        _say(log, f"BLS wages: refresh failed ({type(e).__name__}: {str(e)[:600]}); using cached table ({len(wages)}).")
        return wages


def education_level(soc, levels):
    """Education level for a SOC code; falls back to the detailed codes in the same broad group when
    they all agree (posting SOC codes are sometimes a broad-group code like 151250)."""
    soc = re.sub(r"\D", "", str(soc or ""))
    if len(soc) != 6:
        return ""
    if soc in levels:
        return levels[soc]
    same = {v for k, v in levels.items() if k[:5] == soc[:5]}
    return same.pop() if len(same) == 1 else ""


def no_degree(soc, levels):
    """True / False, or None when the occupation's level is unknown."""
    lv = education_level(soc, levels)
    return (lv in NO_DEGREE_LEVELS) if lv else None


# ---------------------------------------------------------------------------------------------
# Near an LTD bus stop
# ---------------------------------------------------------------------------------------------

def parse_gtfs_stops(data):
    """[{name, lat, lon}] for boardable stops in a GTFS zip, limited to stops with scheduled service
    when stop_times.txt is present."""
    z = zipfile.ZipFile(io.BytesIO(data))
    names = {n.rsplit("/", 1)[-1]: n for n in z.namelist()}
    served = None
    if "stop_times.txt" in names:
        served = set()
        with z.open(names["stop_times.txt"]) as f:
            for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline="")):
                served.add((row.get("stop_id") or "").strip())
    stops = []
    with z.open(names["stops.txt"]) as f:
        for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", newline="")):
            if (row.get("location_type") or "0").strip() not in ("", "0"):
                continue
            sid = (row.get("stop_id") or "").strip()
            if served is not None and served and sid not in served:
                continue
            try:
                lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
                stops.append({"name": (row.get("stop_name") or "").strip(), "lat": round(lat, 6), "lon": round(lon, 6)})
    return stops


def ltd_stops(log=None, force=False):
    """LTD bus stops, refreshed weekly from the GTFS feed. Never raises."""
    cache = _read_json(STOPS_CACHE, {})
    stops = cache.get("stops") or []
    if stops and not force and _age_days(cache.get("fetched")) < STOPS_MAX_AGE_DAYS:
        return stops
    errors = []
    s = _session()
    for url in LTD_GTFS_URLS:
        try:
            r = s.get(url, timeout=90)
            r.raise_for_status()
            fresh = parse_gtfs_stops(r.content)
            if len(fresh) < 200:
                raise ValueError(f"only {len(fresh)} stops")
            _write_json(STOPS_CACHE, {"fetched": _today().isoformat(), "source": url, "stops": fresh})
            _say(log, f"LTD stops: read {len(fresh)} stops from {url}.")
            return fresh
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url}: {type(e).__name__}: {str(e)[:100]}")
    _say(log, f"LTD stops: refresh failed ({'; '.join(errors)}); using cached list ({len(stops)} stops).")
    return stops


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, a)))


class StopGrid:
    """Stops bucketed in 0.01-degree cells (about 1.1 km north-south, 0.8 km east-west in Lane County),
    so a 400 m search only looks at the 3x3 cells around a point."""
    CELL = 0.01

    def __init__(self, stops):
        self.cells = {}
        for s in stops:
            self.cells.setdefault(self._key(s["lat"], s["lon"]), []).append((s["lat"], s["lon"]))

    def _key(self, lat, lon):
        return (math.floor(lat / self.CELL), math.floor(lon / self.CELL))

    def nearest_m(self, lat, lon):
        """Distance in meters to the nearest stop within one cell, or None."""
        ky, kx = self._key(lat, lon)
        best = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for slat, slon in self.cells.get((ky + dy, kx + dx), ()):
                    d = haversine_m(lat, lon, slat, slon)
                    if best is None or d < best:
                        best = d
        return best

    def near(self, lat, lon, meters=NEAR_METERS):
        d = self.nearest_m(lat, lon)
        return d is not None and d <= meters


# --- employer names ---------------------------------------------------------------------------

_DROP = {"inc", "llc", "co", "corp", "corporation", "company", "the", "ltd", "lp", "llp", "pc", "pllc",
         "incorporated", "and", "dba"}
_PLACE_WORDS = {"lane", "county", "city", "of", "oregon", "or", "state", "north", "south", "east", "west",
                "eugene", "springfield", "florence", "cottage", "grove", "junction", "creswell", "veneta",
                "oakridge", "coburg", "lowell", "dexter", "pleasant", "hill", "mapleton", "blue", "river",
                "marcola", "elmira", "walterville", "westfir", "noti", "mckenzie", "bridge", "willamette", "valley"}


_ABBR = {"nw": "northwest", "ne": "northeast", "sw": "southwest", "se": "southeast", "inst": "institute",
         "univ": "university", "svc": "services", "svcs": "services", "service": "services", "ctr": "center",
         "cntr": "center", "clnc": "clinic", "hosp": "hospital", "assn": "association", "dept": "department",
         "dist": "district", "intl": "international", "mgmt": "management", "natl": "national",
         "mfg": "manufacturing", "hlth": "health", "med": "medical", "grp": "group", "bd": "board",
         "elec": "electric", "st": "saint", "mt": "mount"}


def norm_tokens(name):
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"\bu\.\s?s\.", "us ", s)  # U.S. Bank -> us bank
    s = re.sub(r"['’`]", "", s)          # domino's -> dominos
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return tuple(_ABBR.get(t, t) for t in s.split() if t not in _DROP)


def name_variants(name):
    """Normalized token tuples to try for a posting's employer name: the name without any
    parenthetical, and the parenthetical itself ("EWEB (Eugene Water & Electric Board)")."""
    out = []
    outer = re.sub(r"\([^)]*\)", " ", name or "")
    for part in [outer] + re.findall(r"\(([^)]*)\)", name or ""):
        t = norm_tokens(part)
        if t and t not in out:
            out.append(t)
    return out


def _prefix_ok(tokens):
    """Prefix matching is only safe for names with something distinctive in them: "Lane County" would
    otherwise match "Lane County Glass"."""
    if all(t in _PLACE_WORDS for t in tokens):
        return False
    return len(tokens) >= 2 or len(tokens[0]) >= 5


def _addr_key(street, city, zip_):
    street = re.sub(r"\s*(#|\bste\b|\bsuite\b|\bunit\b|\bapt\b|\bspc\b|\bbldg\b).*$", "", street or "", flags=re.I)
    street = re.sub(r"\s+", " ", street).strip().lower()
    return f"{street}|{(city or '').strip().lower()}|{re.sub(r'[^0-9]', '', zip_ or '')[:5]}"


def _geocodable(street):
    s = (street or "").strip().lower()
    return bool(re.match(r"^\d+[a-z]?\s+\S", s)) and not re.match(r"^(po|p o|p\.o\.)\s*box", s)


class EmployerIndex:
    """QualityInfo employer records indexed by city and normalized name."""

    def __init__(self, empdb):
        self.by_city = {}
        self.squashed = {}
        for rec in empdb.values():
            if not isinstance(rec, dict):
                continue
            street = rec.get("address") or ""
            if not _geocodable(street):
                continue
            toks = norm_tokens(rec.get("name"))
            if not toks:
                continue
            city = (rec.get("city") or "").strip().lower()
            key = _addr_key(street, rec.get("city"), rec.get("zip"))
            item = (toks, key, street, rec.get("city"), rec.get("zip"))
            self.by_city.setdefault(city, {}).setdefault(toks[0], []).append(item)
            self.squashed.setdefault(city, {}).setdefault("".join(toks), []).append(item)

    def addresses(self, employer, city):
        """{addr_key: (street, city, zip)} for the employer's records in that city, or {}."""
        city_key = (city or "").strip().lower()
        idx = self.by_city.get(city_key)
        if not idx or not employer:
            return {}
        variants = name_variants(employer)
        # 1. same name exactly, or the same once spaces are ignored ("KeyBank" / "Key Bank")
        for v in variants:
            hit = {k: (s, c, z) for toks, k, s, c, z in idx.get(v[0], ()) if toks == v}
            if hit:
                return hit
        sq = self.squashed.get(city_key, {})
        hit = {k: (s, c, z) for v in variants for toks, k, s, c, z in sq.get("".join(v), ())}
        if hit:
            return hit
        # 2. a record whose whole name begins the posting's name ("Securitas" for "Securitas Security Services")
        for v in variants:
            hit = {k: (s, c, z) for toks, k, s, c, z in idx.get(v[0], ())
                   if len(toks) < len(v) and v[:len(toks)] == toks and _prefix_ok(toks)}
            if hit:
                return hit
        # 3. names that start with the whole name, then with its first 3, then first 2 words
        for v in variants:
            for n in sorted({len(v), min(3, len(v)), min(2, len(v))}, reverse=True):
                p = v[:n]
                if not _prefix_ok(p):
                    continue
                hit = {k: (s, c, z) for toks, k, s, c, z in idx.get(p[0], ()) if toks[:n] == p}
                if hit:
                    return hit
        return {}


# --- geocoding --------------------------------------------------------------------------------

def census_batch(rows, timeout=600):
    """Geocode [(id, street, city, zip)] with the Census batch geocoder.
    Returns {id: (lat, lon) or None for no match}. Raises on HTTP errors."""
    buf = io.StringIO()
    w = csv.writer(buf)
    for rid, street, city, zip_ in rows:
        w.writerow([rid, street, city, "OR", re.sub(r"[^0-9]", "", zip_ or "")[:5]])
    r = requests.post(CENSUS_BATCH_URL, data={"benchmark": CENSUS_BENCHMARK},
                      files={"addressFile": ("addresses.csv", buf.getvalue(), "text/csv")},
                      headers={"User-Agent": UA}, timeout=(30, timeout))
    r.raise_for_status()
    return parse_census_response(r.text)


def parse_census_response(text):
    out = {}
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        rid = row[0].strip()
        ll = None
        if len(row) >= 6 and row[2].strip() == "Match":
            try:
                lon, lat = (float(x) for x in row[5].split(","))
                ll = (round(lat, 6), round(lon, 6))
            except ValueError:
                ll = None
        out[rid] = ll
    return out


def _needs_geocode(cache, key):
    v = cache.get(key)
    if isinstance(v, list):
        return False
    if isinstance(v, str):  # date of a miss
        return _age_days(v) >= MISS_RETRY_DAYS
    return True


def geocode(addresses, cache, log=None, cap=GEOCODE_NIGHTLY_CAP, chunk=GEOCODE_NIGHTLY_CHUNK,
            seconds=GEOCODE_NIGHTLY_SECONDS, timeout=300, batch=None):
    """Geocode {key: (street, city, zip)} not yet in the cache, up to `cap` of them, saving the cache
    after each chunk. Hits are stored as [lat, lon]; misses as the ISO date they were tried.
    Returns (tried, matched). Never raises."""
    batch = batch or census_batch
    todo = [k for k in sorted(addresses) if _needs_geocode(cache, k)][:cap]
    tried = matched = 0
    start = time.monotonic()
    for i in range(0, len(todo), chunk):
        if seconds is not None and time.monotonic() - start > seconds:
            break
        part = todo[i:i + chunk]
        ids = {str(n): k for n, k in enumerate(part)}
        try:
            res = batch([(n, *addresses[k]) for n, k in ids.items()], timeout=timeout)
        except Exception as e:  # noqa: BLE001
            _say(log, f"Census geocoder failed ({type(e).__name__}: {str(e)[:120]}); {len(todo) - tried} addresses left for later.")
            break
        today = _today().isoformat()
        for n, k in ids.items():
            ll = res.get(n)
            if ll:
                cache[k] = [ll[0], ll[1]]
                matched += 1
            elif n in res:
                cache[k] = today
            # ids missing from the answer stay untried
        tried += len(part)
        try:
            _write_json(GEO_CACHE, cache)
        except Exception:  # noqa: BLE001
            pass
    return tried, matched


# --- tagging ----------------------------------------------------------------------------------

def near_bus_status(keys, cache, grid):
    """True if every geocoded address is near a stop, False if none is, None if mixed or unknown.
    Addresses the geocoder could not place are ignored; any address not tried yet makes it unknown."""
    flags = []
    for k in keys:
        v = cache.get(k)
        if isinstance(v, list):
            flags.append(grid.near(v[0], v[1]))
        elif v is None:
            return None
    if not flags:
        return None
    if all(flags):
        return True
    if not any(flags):
        return False
    return None


def transit_tags(jobs, log=None, geocode_cap=GEOCODE_NIGHTLY_CAP):
    """Set j["near_bus"] True/False where it can be told; leave it absent when unknown. Never raises."""
    try:
        t0 = time.monotonic()
        for j in jobs:
            j.pop("near_bus", None)
        stops = ltd_stops(log)
        if not stops:
            _say(log, "Bus-stop tags: no LTD stop list available; skipped.")
            return
        grid = StopGrid(stops)
        index = EmployerIndex(_read_json(EMPDB, {}))
        cache = _read_json(GEO_CACHE, {})
        if not isinstance(cache, dict):
            cache = {}
        plans, needed, unmatched = [], {}, 0
        memo = {}
        for j in jobs:
            mk = (j.get("employer") or "", j.get("city") or "")
            if mk not in memo:
                memo[mk] = index.addresses(*mk)
            addrs = memo[mk]
            if not addrs:
                unmatched += 1
                continue
            plans.append((j, list(addrs)))
            needed.update(addrs)
        tried, matched = geocode(needed, cache, log, cap=geocode_cap) if needed else (0, 0)
        yes = no = 0
        for j, keys in plans:
            st = near_bus_status(keys, cache, grid)
            if st is not None:
                j["near_bus"] = st
                yes += st
                no += not st
        _say(log, f"Bus-stop tags: {yes} near, {no} not near, {len(jobs) - yes - no} unknown "
                  f"({unmatched} without an employer address); geocoded {matched}/{tried} new addresses; "
                  f"{len(stops)} LTD stops; {time.monotonic() - t0:.0f}s.")
    except Exception as e:  # noqa: BLE001
        for j in jobs:
            j.pop("near_bus", None)
        _say(log, f"Bus-stop tags failed: {type(e).__name__}: {str(e)[:200]}")


# ---------------------------------------------------------------------------------------------

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true", help="re-read the BLS table and the LTD stops now")
    ap.add_argument("--geocode-all", action="store_true", help="geocode every employer address in data/empdb-lane.json")
    args = ap.parse_args(argv)
    log = []
    levels = soc_education(log, force=args.refresh)
    stops = ltd_stops(log, force=args.refresh)
    wages = oews_wages(log, force=args.refresh)
    print(f"Wages: {len(wages)} occupations.")
    for line in log:
        print(line)
    print(f"Education levels: {len(levels)} occupations "
          f"({sum(v in NO_DEGREE_LEVELS for v in levels.values())} need no degree).")
    print(f"LTD stops: {len(stops)}.")
    if args.geocode_all:
        index = EmployerIndex(_read_json(EMPDB, {}))
        addrs = {}
        for by_tok in index.by_city.values():
            for recs in by_tok.values():
                for _toks, k, s, c, z in recs:
                    addrs[k] = (s, c, z)
        cache = _read_json(GEO_CACHE, {})
        glog = []
        tried, matched = geocode(addrs, cache, glog, cap=len(addrs), chunk=GEOCODE_ALL_CHUNK, seconds=None, timeout=1500)
        for line in glog:
            print(line)
        hits = sum(isinstance(v, list) for v in cache.values())
        print(f"Geocoded {matched}/{tried} new addresses; cache has {hits} located of {len(cache)} "
              f"({len(addrs)} distinct employer addresses).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
