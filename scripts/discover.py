"""Find employers' own job listings from the websites in QualityInfo's Employer Database.

    python scripts/discover.py --build            # queue websites not already searched (data/discover-queue.json)
    python scripts/discover.py --shard 3 --of 15  # visit one slice of the queue (data/discover-out/shard-3.json)
    python scripts/discover.py --merge            # add employers with job listings to data/employer-sites.json

Only employers whose site shows a hiring system or a careers page are added. Sites that do not load, show a
human-verification check, or have no careers page are recorded in data/discover-done.json and not retried for 90 days.
"""
import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ats  # noqa: E402
import direct  # noqa: E402
import enrich  # noqa: E402
import rules  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EMPDB, QUEUE, DONE = DATA / "empdb-lane.json", DATA / "discover-queue.json", DATA / "discover-done.json"
OUTDIR, SITES, SOURCES = DATA / "discover-out", DATA / "employer-sites.json", DATA / "sources.json"
SUMMARY = DATA / "discover-summary.json"
TODAY = dt.date.today().isoformat()

NOT_EMPLOYER_SITES = re.compile(r"(^|\.)(facebook|instagram|twitter|x|linkedin|yelp|youtube|google|tiktok|pinterest|"
                                r"nextdoor|yellowpages|bbb|mapquest|tripadvisor|indeed|craigslist|etsy|amazon|ebay|"
                                r"blogspot|wordpress|weebly)\.(com|org|net)$", re.I)
NO_OPENINGS = re.compile(r"no (current )?(job )?(openings|open positions|positions (are )?(currently )?available|vacancies)|"
                         r"not (currently )?hiring|nothing right now|check back (later|soon)|no positions", re.I)
JOB_SIGNAL = re.compile(r"\bapply\b|open positions|current openings|job openings|now hiring|we'?re hiring|"
                        r"job description|full[- ]time|part[- ]time|\$\d", re.I)


def domain(web):
    w = (web or "").strip().lower()
    if not w:
        return ""
    if not re.match(r"https?://", w):
        w = "http://" + w
    host = urlparse(w).netloc.split(":")[0]
    return host[4:] if host.startswith("www.") else host


def covered_domains():
    hosts = set()
    if SOURCES.exists():
        for s in json.loads(SOURCES.read_text()).values():
            for u in (s.get("url"), s.get("host")):
                if u:
                    hosts.add(domain(u))
    if SITES.exists():
        hosts |= {domain(s.get("careers_url")) for s in json.loads(SITES.read_text())}
    hosts |= {d.lower().removeprefix("www.") for d in getattr(rules, "DOMAIN_EMPLOYERS", {})}
    return {h for h in hosts if h}


def build():
    db = json.loads(EMPDB.read_text())
    done = json.loads(DONE.read_text()) if DONE.exists() else {}
    covered = covered_domains()
    counts = Counter(domain(v.get("web")) for v in db.values() if v.get("web"))
    queue, seen, skipped = [], set(), Counter()
    for uid, v in sorted(db.items(), key=lambda kv: kv[1].get("name", "")):
        d = domain(v.get("web"))
        if not d:
            skipped["no website listed"] += 1
            continue
        if d in seen:
            continue
        seen.add(d)
        if NOT_EMPLOYER_SITES.search(d):
            skipped["social or directory page"] += 1
        elif d in covered or any(d.endswith("." + c) for c in covered):
            skipped["already searched"] += 1
        elif d in done and (dt.date.fromisoformat(TODAY) - dt.date.fromisoformat(done[d]["checked"])).days < 90:
            skipped["checked in the last 90 days"] += 1
        else:
            queue.append({"domain": d, "employer": v.get("name", ""), "city": v.get("city", ""),
                          "business": v.get("business", ""), "naics": v.get("naics", ""), "locations": counts[d]})
    QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(db)} employers; {len(seen)} distinct websites; queued {len(queue)}; skipped {dict(skipped)}")


def classify(item, results):
    """Turn probe results for one website into a decision."""
    first = results[0] if results else {}
    if first.get("error") or not first.get("status") or first["status"] >= 400:
        title = (first.get("title") or "") + " " + (first.get("text") or "")[:300]
        if re.search(r"just a moment|verify you are human|security verification|attention required", title, re.I):
            return {"outcome": "blocked (human-verification check)"}
        return {"outcome": "site did not load", "detail": first.get("error") or first.get("status")}
    for r in results:
        for link in r.get("system_links", []):
            found = direct.source_from_url(link) or ats.source_from_url(link)
            if found:
                return {"outcome": "hiring system", "careers_url": link, "system": found[1]["platform"]}
    site = domain(first.get("final") or "")
    careers = [r for r in results[1:] if not r.get("error") and (r.get("status") or 0) < 400
               and domain(r.get("final") or "").endswith(site)
               and re.search(r"career|job|employ|hiring|join|work-with|opportunit", r.get("final") or "", re.I)]
    if not careers:
        return {"outcome": "no careers page found"}
    page = careers[0]
    text = page.get("text") or ""
    if NO_OPENINGS.search(text):
        return {"outcome": "careers page, no openings today", "careers_url": page["final"]}
    if JOB_SIGNAL.search(text):
        return {"outcome": "careers page with openings", "careers_url": page["final"]}
    return {"outcome": "careers page, unclear", "careers_url": page["final"]}


def shard(i, n):
    import signal

    import probe
    from playwright.sync_api import sync_playwright
    queue = json.loads(QUEUE.read_text())[i::n]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    path = OUTDIR / f"shard-{i}.json"
    out = []

    def too_slow(*_):
        raise TimeoutError("site took over a minute")

    signal.signal(signal.SIGALRM, too_slow)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(user_agent=probe.UA)
        ctx.set_default_timeout(20000)
        for k, item in enumerate(queue):
            signal.alarm(60)  # hard limit per website, whatever the page does
            try:
                results = [probe.look(ctx, f"https://{item['domain']}/")]
                if results[0].get("error") and "ERR_" in results[0]["error"]:
                    results = [probe.look(ctx, f"http://www.{item['domain']}/")]
                if not results[0].get("system_links"):
                    for nxt in results[0].get("careers_links", [])[:2]:
                        results.append(probe.look(ctx, nxt))
                dec = classify(item, results)
            except TimeoutError:
                dec = {"outcome": "site did not load", "detail": "over a minute"}
                try:  # start fresh in case the page is wedged
                    ctx.close()
                except Exception:  # noqa: BLE001
                    pass
                ctx = b.new_context(user_agent=probe.UA)
                ctx.set_default_timeout(20000)
            finally:
                signal.alarm(0)
            out.append(dict(item, **dec))
            if k % 10 == 0:  # save as we go, so a timed-out worker keeps what it found
                path.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
                print(f"shard {i}: {k}/{len(queue)}", flush=True)
        b.close()
    path.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")


ACCEPT = {"hiring system": False, "careers page with openings": False, "careers page, unclear": True,
          "careers page, no openings today": True}   # value: check weekly instead of nightly


GIVEN = set("""matt scot scott patricia stephanie bruce danielle noni monique sean richard gary kelly robert keith william
candice jeremy dmitriy chuck nicholas loren jerry dave david john james michael mary susan linda karen lisa nancy jennifer
sarah emily jessica amanda brian kevin mark paul steven stephen thomas daniel joseph charles christopher anthony donald
margaret barbara elizabeth patrick peter laura julie amy anne ann jean carol deborah sandra donna ruth sharon cynthia
kathleen helen andrea rachel heather nicole melissa michelle rebecca timothy jason jeffrey ryan eric jacob gregory frank
larry dennis jerry tyler aaron jose adam henry douglas nathan zachary kyle walter harold carl arthur roger joe terry
preet parisa bryan""".split())
CRED = re.compile(r"\b(MD|DMD|DDS|DO|ATY|AGT|LO|OD|DC|LCSW|LPC|PhD|CPA PC)\b\.?$")
FRANCHISE = re.compile(r"state farm|farmers insurance|allstate|edward jones|american income life|new york life|primerica|"
                       r"northwestern mutual|mary kay|shaklee|watkins products|liberty tax|nationwide insurance|aflac", re.I)
JUNK = re.compile(r"&$|^(?![A-Z]{2,5}$)[A-Za-z]{1,4}$|^good$|complaint line|worksource|employment division|fish & wildlife|^buy \d|science library|"
                  r"master gardeners|portraits$", re.I)


def not_an_employer(name):
    """Why a QualityInfo listing should not be searched as an employer, or "" if it should."""
    w = name.replace(",", "").split()
    if JUNK.search(name):
        return "fragment or not an employer"
    if CRED.search(name):
        return "individual practitioner"
    if FRANCHISE.search(name):
        return "franchise agent (careers page is the national company)"
    if 2 <= len(w) <= 4 and w[0] not in ("St", "Saint") and w[1].lower() in GIVEN and w[0][0].isupper() and all(len(x) <= 2 or x.isalpha() for x in w):
        return "a person's name"
    return ""


def merge():
    rows = []
    for f in sorted(OUTDIR.glob("shard-*.json")):
        rows += json.loads(f.read_text())
    done = json.loads(DONE.read_text()) if DONE.exists() else {}
    sites = json.loads(SITES.read_text()) if SITES.exists() else []
    have = {(s.get("careers_url") or "").lower().rstrip("/") for s in sites} | {s["employer"].lower() for s in sites}
    added = []
    for r in rows:
        done[r["domain"]] = {"checked": TODAY, "outcome": r["outcome"], "employer": r["employer"]}
        if r["outcome"] not in ACCEPT or not r.get("careers_url"):
            continue
        name = enrich.clean_employer(enrich._tidy_name(r["employer"])) or r["employer"]
        if not_an_employer(name):
            done[r["domain"]]["outcome"] += f" (not added: {not_an_employer(name)})"
            continue
        if r["careers_url"].lower().rstrip("/") in have or name.lower() in have:
            continue
        chain = r.get("locations", 1) >= 3
        sites.append({"employer": name, "careers_url": r["careers_url"], "local": not chain,
                      "home": "" if chain else r.get("city", ""), "found": TODAY,
                      "list": "QualityInfo employer database", "weekly": ACCEPT[r["outcome"]]})
        have |= {r["careers_url"].lower().rstrip("/"), name.lower()}
        added.append(name)
    SITES.write_text(json.dumps(sites, ensure_ascii=False, indent=1), encoding="utf-8")
    DONE.write_text(json.dumps(done, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    summary = {"date": TODAY, "visited": len(rows), "outcomes": dict(Counter(r["outcome"] for r in rows)),
               "added": len(added), "added_names": sorted(added)}
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "added_names"}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--shard", type=int)
    ap.add_argument("--of", type=int, default=1)
    ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    if a.shard is not None:
        shard(a.shard, a.of)
    if a.merge:
        merge()
    return 0


if __name__ == "__main__":
    sys.exit(main())
