"""Members of the Eugene and Springfield chambers of commerce, checked against the Employer Registry.

    python scripts/chambers.py            # read both directories -> data/chamber-members.json and data/chamber-summary.json

Both directories are public and drawn in the browser, so they are read with a real browser engine, page by page.
Eugene (web.eugenechamber.com) is read category by category; each listing shows the member's website.
Springfield (business.springfield-chamber.org) is read A to Z; each member's own page gives its website.
A member is "new" the first night it appears. Members whose website the registry has not searched are queued by
scripts/discover.py --build, which looks for a careers page or hiring system the same way it does for the
QualityInfo employer database.
"""
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT, SUMMARY = DATA / "chamber-members.json", DATA / "chamber-summary.json"
TODAY = dt.date.today().isoformat()
UA = "LaneCountyHotJobs/1.0 (+https://collaborativeedo.github.io/hot-jobs/; job listings for Lane Workforce Partnership)"
EUG, SPR = "https://web.eugenechamber.com", "https://business.springfield-chamber.org"
BUDGET = 100 * 60  # stop reading after 100 minutes and save what was found


def domain(web):
    w = (web or "").strip().lower()
    if not w:
        return ""
    if not re.match(r"https?://", w):
        w = "http://" + w
    host = urlparse(w).netloc.split(":")[0]
    return host[4:] if host.startswith("www.") else host


def city_of(address):
    """The Lane County town in an address, or "" (outside Lane County or not stated)."""
    import direct
    return direct.lane_city(address or "") or ""


EUG_CARDS = """() => [...document.querySelectorAll('p-card')].map(c => {
  const a = c.querySelector('a[href*="/atlas/directory/category/"]');
  const n = c.querySelector('.listing-header__name');
  const ad = c.querySelector('.address-line');
  const w = c.querySelector('a.above-card[href^="http"]');
  return {href: a ? a.getAttribute('href') : '', name: n ? n.innerText.trim() : '',
          address: ad ? ad.innerText.trim() : '', web: w ? w.getAttribute('href') : ''};
}).filter(x => x.href)"""


def read_eugene(page, log, deadline):
    page.goto(f"{EUG}/business/allcategories", wait_until="networkidle", timeout=60000)
    cats = sorted({h for h in page.eval_on_selector_all("a[href]", "els => els.map(a => a.href)")
                   if re.match(rf"{re.escape(EUG)}/business/[^/?#]+$", h)
                   and not re.search(r"/business/(search|advancedsearch|allcategories|results)$", h, re.I)})
    log.append(f"Eugene: {len(cats)} categories.")
    found = {}
    for k, cat in enumerate(cats):
        if time.time() > deadline:
            log.append(f"Eugene: time limit reached after {k} of {len(cats)} categories.")
            break
        label = re.sub(r"-", " ", cat.rsplit("/", 1)[1])
        try:
            page.goto(cat, wait_until="networkidle", timeout=45000)
            try:
                page.wait_for_selector("p-card", timeout=8000)
            except Exception:  # noqa: BLE001 - empty category
                continue
            for _ in range(40):  # pages of results
                for c in page.evaluate(EUG_CARDS):
                    m = re.search(r"-(\d+)$", c["href"])
                    key = "eug:" + (m.group(1) if m else c["href"])
                    rec = found.setdefault(key, {"chamber": "Eugene", "name": c["name"], "web": c["web"],
                                                 "address": c["address"], "city": city_of(c["address"]),
                                                 "profile": EUG + c["href"], "categories": []})
                    if label not in rec["categories"]:
                        rec["categories"].append(label)
                nxt = page.query_selector("button.p-paginator-next:not(.p-disabled):not([disabled])")
                if not nxt:
                    break
                first = page.evaluate("() => (document.querySelector('.listing-header__name')||{}).innerText")
                nxt.click()
                page.wait_for_function("f => (document.querySelector('.listing-header__name')||{}).innerText !== f",
                                       arg=first, timeout=10000)
        except Exception as e:  # noqa: BLE001
            log.append(f"Eugene: {label}: {type(e).__name__}")
        if k % 50 == 0:
            print(f"Eugene {k}/{len(cats)}: {len(found)} members", flush=True)
    log.append(f"Eugene: {len(found)} member listings.")
    return found


def read_springfield(page, log, deadline):
    found = {}
    for letter in list("abcdefghijklmnopqrstuvwxyz") + ["0-9"]:
        page.goto(f"{SPR}/list/searchalpha/{letter}", wait_until="networkidle", timeout=60000)
        rows = page.evaluate("""() => [...document.querySelectorAll('a[href*="/list/member/"]')].map(a => {
            const card = a.closest('.gz-list-card-wrapper, .card, li, .gz-card') || a.parentElement;
            const ad = card ? card.querySelector('a[href*="google.com/maps"]') : null;
            return {href: a.href, name: a.innerText.trim(), address: ad ? ad.innerText.replace(/\\s+/g, ' ').trim() : ''};
        })""")
        for r in rows:
            m = re.search(r"/list/member/[^/?#]*?-(\d+)$", r["href"])
            if not m:
                continue
            rec = found.setdefault("spr:" + m.group(1), {"chamber": "Springfield", "name": "", "web": "", "address": "",
                                                          "city": "", "profile": r["href"], "categories": []})
            rec["name"] = rec["name"] or r["name"]
            if r["address"] and not rec["address"]:
                rec["address"], rec["city"] = r["address"], city_of(r["address"])
    log.append(f"Springfield: {len(found)} members listed A to Z.")
    for k, rec in enumerate(found.values()):
        if time.time() > deadline:
            log.append(f"Springfield: time limit reached after {k} member pages.")
            break
        try:
            page.goto(rec["profile"], wait_until="domcontentloaded", timeout=30000)
            web = page.evaluate("""() => { const a = [...document.querySelectorAll('a[href^="http"]')].find(a =>
                /visit website/i.test(a.innerText) || (a.closest('[class*="website"]') && !/springfield-chamber|growthzone/.test(a.href)));
                return a ? a.href : ''; }""")
            cats = page.evaluate("""() => [...document.querySelectorAll('a[href*="/list/ql/"], .gz-member-cats a, [class*="category"] a')]
                .map(a => a.innerText.trim()).filter(Boolean)""")
            rec["web"] = web
            rec["categories"] = sorted(set(cats))[:6]
        except Exception as e:  # noqa: BLE001
            rec["error"] = type(e).__name__
        if k % 100 == 0:
            print(f"Springfield {k}/{len(found)} member pages", flush=True)
    return found


def compare(members):
    """Which members the registry already knows (by website or name)."""
    import discover
    import enrich
    covered = discover.covered_domains()
    db = json.loads(discover.EMPDB.read_text()) if discover.EMPDB.exists() else {}
    db_domains = {domain(v.get("web")) for v in db.values() if v.get("web")}
    done = json.loads(discover.DONE.read_text()) if discover.DONE.exists() else {}
    names = set()
    for f in (DATA / "employers.json", DATA / "employer-sites.json"):
        if f.exists():
            d = json.loads(f.read_text())
            names |= {k for k in d} if isinstance(d, dict) else {x.get("employer", "") for x in d}
    norm = lambda t: re.sub(r"[^a-z0-9]", "", re.sub(r"\b(inc|llc|co|corp|company|the|of|and|pc|ltd)\b", "", (t or "").lower()))  # noqa: E731
    names = {norm(n) for n in names if n}
    for rec in members.values():
        d = domain(rec.get("web"))
        if discover.NOT_EMPLOYER_SITES.search(d or "x.invalid"):
            d = ""
        rec["domain"] = d
        if d and (d in covered or any(d.endswith("." + c) for c in covered if c)):
            rec["status"] = "already searched for jobs"
        elif norm(enrich.clean_employer(rec["name"]) or rec["name"]) in names:
            rec["status"] = "already an employer on record"
        elif d and d in done:
            rec["status"] = f"website checked {done[d]['checked']}: {done[d]['outcome']}"
        elif d and d in db_domains:
            rec["status"] = "in QualityInfo employer database, queued there"
        elif d:
            rec["status"] = "new: website to check for jobs"
        else:
            rec["status"] = "new: no website listed"


def main():
    from playwright.sync_api import sync_playwright
    log, start = [], time.time()
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    members = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_context(user_agent=UA).new_page()
        page.set_default_timeout(30000)
        for reader, share in ((read_eugene, 0.55), (read_springfield, 1.0)):
            try:
                members.update(reader(page, log, start + BUDGET * share))
            except Exception as e:  # noqa: BLE001
                log.append(f"{reader.__name__} failed: {type(e).__name__}: {str(e)[:200]}")
        b.close()
    for k, rec in members.items():
        rec["first_seen"] = old.get(k, {}).get("first_seen", TODAY)
        rec["last_seen"] = TODAY
        if not rec.get("web") and old.get(k, {}).get("web"):
            rec["web"] = old[k]["web"]
    for k, rec in old.items():  # keep members not read tonight (time limit, page error) so nothing is lost
        members.setdefault(k, rec)
    compare(members)
    OUT.write_text(json.dumps(members, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    from collections import Counter
    seen_now = [r for r in members.values() if r.get("last_seen") == TODAY]
    summary = {"date": TODAY, "log": log, "members": len(seen_now),
               "by_chamber": dict(Counter(r["chamber"] for r in seen_now)),
               "status": dict(Counter(r["status"].split(":")[0] if r["status"].startswith(("new", "website")) else r["status"] for r in seen_now)),
               "new_this_run": sorted(r["name"] for r in seen_now if r["first_seen"] == TODAY and old)}
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1)[:3000])


if __name__ == "__main__":
    main()
