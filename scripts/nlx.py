"""Lane County postings from the National Labor Exchange (usnlx.com), with links to the employer's own posting.

NLx is the public, ad-free job bank run by the National Association of State Workforce Agencies and the
DirectEmployers Association. Its search pages are drawn in the browser, so they are read with a real browser
engine, page by page, the same way a visitor sees them. Each job's "Apply Now" button is a public redirect
(nlx.jobsyn.org) to the employer's own posting; that redirect is followed once per job and remembered.

    python scripts/nlx.py --snapshot     # write data/nlx-lane.json (all postings and companies) and print a summary
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import direct  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "nlx-cache.json"      # job id -> employer posting address (or "" if it never resolved)
SNAPSHOT = ROOT / "data" / "nlx-lane.json"
SITE = "https://usnlx.com"
UA = "LaneCountyHotJobs/1.0 (+https://collaborativeedo.github.io/hot-jobs/; job listings for Lane Workforce Partnership)"
# Lane County towns NLx may have a location page for. Towns with no page are skipped quickly.
TOWNS = ["eugene", "springfield", "cottage-grove", "florence", "junction-city", "creswell", "veneta", "oakridge",
         "coburg", "lowell", "pleasant-hill", "dexter", "elmira", "marcola", "mapleton", "blue-river", "vida",
         "westfir", "walterville", "noti", "leaburg", "dunes-city", "fall-creek", "swisshome", "deadwood"]
MAX_PAGES = 80        # 15 postings a page; Eugene alone is ~40 pages
PAGE_WAIT_MS = 2500


def _days(text):
    t = (text or "").lower()
    if "today" in t or "hour" in t:
        return 0
    if "yesterday" in t:
        return 1
    m = re.search(r"(\d+)\+?\s*days?", t)
    return int(m.group(1)) if m else None


def _parse_cards(cards):
    """cards: [{href, text}] from one results page -> postings (title, employer, place, days, id)."""
    out = []
    for c in cards:
        href, lines = c.get("href", ""), [x.strip() for x in (c.get("text") or "").split("\n") if x.strip()]
        m = re.search(r"/([0-9A-F]{32})/job/?$", href, re.I)
        if not m or not lines:
            continue
        title, employer, place, posted = lines[0], "", "", ""
        for ln in lines[1:]:
            if ln.lower().startswith("posted"):
                posted = ln
            elif not employer and " - " in ln:
                employer, place = ln.rsplit(" - ", 1)
        out.append({"id": m.group(1).upper(), "title": title, "employer": employer.strip(), "place": place.strip(),
                    "days": _days(posted), "page": SITE + href if href.startswith("/") else href})
    return out


def read_listings(log, max_pages=MAX_PAGES):
    """Every Lane County posting NLx lists, read from its location pages."""
    from playwright.sync_api import sync_playwright
    found, seen = [], set()
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(user_agent=UA)
        page = ctx.new_page()
        for town in TOWNS:
            for n in range(1, max_pages + 1):
                url = f"{SITE}/locations/{town}-or/jobs/" + (f"?page={n}" if n > 1 else "")
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    if resp is not None and resp.status in (401, 403, 429):
                        log.append(f"NLx: {town} page {n} refused ({resp.status}); stopped.")
                        b.close()
                        return found
                    try:
                        page.wait_for_selector('a[href$="/job/"]', timeout=12000)
                    except Exception:  # noqa: BLE001 - no results on this page
                        break
                    page.wait_for_timeout(300)
                    cards = page.eval_on_selector_all('a[href$="/job/"]', "els => els.map(a => ({href: a.getAttribute('href'), text: a.innerText}))")
                except Exception as e:  # noqa: BLE001
                    log.append(f"NLx: {town} page {n}: {type(e).__name__}")
                    break
                rows = [r for r in _parse_cards(cards) if r["id"] not in seen]
                if not rows:
                    break
                for r in rows:
                    seen.add(r["id"])
                    r["town_page"] = town
                found.extend(rows)
                time.sleep(0.5)
        b.close()
    return found


def _resolve(job_id):
    """Follow the public "Apply Now" redirect to the employer's posting. Returns the final address or ''."""
    import requests
    for url in (f"https://nlx.jobsyn.org/{job_id}1", f"https://nlx.jobsyn.org/{job_id}"):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=20, allow_redirects=True)
            final = r.url
            if "jobsyn.org" in urlparse(final).netloc or "usnlx.com" in urlparse(final).netloc:
                m = (re.search(r'http-equiv=["\']refresh["\'][^>]*url=([^"\'>]+)', r.text, re.I) or
                     re.search(r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)', r.text))
                final = m.group(1) if m else ""
            if final and r.status_code < 400:
                return final
        except Exception:  # noqa: BLE001
            continue
    return ""


def pull(log, limit_new=1500):
    """Lane County NLx postings ready to merge with the QualityInfo list (same fields)."""
    rows = read_listings(log)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [r["id"] for r in rows if r["id"] not in cache][:limit_new]
    if todo:
        with ThreadPoolExecutor(max_workers=16) as pool:
            for jid, final in zip(todo, pool.map(_resolve, todo)):
                cache[jid] = final
    live = {r["id"] for r in rows}
    cache = {k: v for k, v in cache.items() if k in live}
    CACHE.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    out, no_city, unresolved = [], 0, 0
    for r in rows:
        city = direct.lane_city(r["place"]) if r["place"] else None
        if not city:
            no_city += 1
            continue
        url = cache.get(r["id"]) or r["page"]
        unresolved += 0 if cache.get(r["id"]) else 1
        out.append({"title": r["title"], "city": city, "url": url, "source": "National Labor Exchange",
                    "days": r["days"] if r["days"] is not None else 0, "soc": "", "occupation": "", "snippet": "",
                    "employer": r["employer"], "nlx_id": r["id"]})
    log.append(f"NLx: {len(rows)} postings read, {len(out)} in Lane County towns, {len(todo)} new links followed, "
               f"{unresolved} still pointing at NLx, {no_city} outside Lane County.")
    return out


def snapshot():
    log = []
    jobs = pull(log)
    by_emp = {}
    for j in jobs:
        by_emp[j["employer"]] = by_emp.get(j["employer"], 0) + 1
    doc = {"date": dt.date.today().isoformat(), "count": len(jobs),
           "companies": sorted(({"employer": k, "postings": v} for k, v in by_emp.items()), key=lambda r: -r["postings"]),
           "jobs": jobs, "log": log}
    SNAPSHOT.write_text(json.dumps(doc, ensure_ascii=False, indent=0), encoding="utf-8")
    print("\n".join(log))
    print(f"{len(jobs)} Lane County postings from {len(by_emp)} companies.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true")
    if ap.parse_args().snapshot:
        snapshot()
