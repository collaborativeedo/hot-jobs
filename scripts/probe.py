"""Find careers pages for employers we know only by name and website.

Reads data/probe.json: [{"employer": "...", "urls": ["https://...", ...]}]. For each, opens the URLs in a
real browser, follows the most likely careers link one step, and records where postings live (hiring-system
links found, careers links, final address, page title). Writes data/probe-results.json.

Run from the "Find careers pages" workflow; it does not change what the nightly run searches.
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
IN, OUT = ROOT / "data" / "probe.json", ROOT / "data" / "probe-results.json"
UA = "LaneCountyHotJobs/1.0 (+https://collaborativeedo.github.io/hot-jobs/; job listings for Lane Workforce Partnership)"
SYSTEMS = re.compile(r"greenhouse\.io|lever\.co|bamboohr\.com|applytojob\.com|jazzhr|paylocity\.com|myworkdayjobs|"
                     r"ultipro\.com|ukg\.net|adp\.com|breezy\.hr|workable\.com|smartrecruiters\.com|rippling|ashbyhq|"
                     r"jobvite|icims\.com|dayforcehcm|paycomonline|recruitee|governmentjobs\.com|schooljobs\.com|"
                     r"paychex|isolvedhire|hrmdirect|wellfound|teamtailor|pinpointhq|workforcenow|taleo|oraclecloud|"
                     r"successfactors|careerplug|hiringthing|gusto\.com|indeed\.com/cmp|linkedin\.com/company/[^/]+/jobs", re.I)
CAREERS = re.compile(r"career|jobs?\b|employment|join.?(our|the)?.?team|work.?with.?us|openings|opportunit|hiring", re.I)


def look(page, url):
    r = {"url": url}
    try:
        resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
        r["status"] = resp.status if resp else None
        r["final"] = page.url
        r["title"] = (page.title() or "")[:120]
        links = page.eval_on_selector_all("a[href], iframe[src], script[src]", """els => els.map(e => ({
            h: e.href || e.src || "", t: (e.innerText || e.title || "").trim().slice(0, 60)}))""")
        html = page.content()
        r["systems"] = sorted({m.group(0).lower() for m in SYSTEMS.finditer(html)})
        r["system_links"] = list(dict.fromkeys(l["h"] for l in links if SYSTEMS.search(l["h"])))[:8]
        r["careers_links"] = list(dict.fromkeys(l["h"] for l in links
                                                if l["h"].startswith("http") and (CAREERS.search(l["t"]) or
                                                CAREERS.search(l["h"].split("?")[0].rsplit("/", 1)[-1] or ""))))[:8]
        r["text"] = re.sub(r"\s+", " ", page.inner_text("body"))[:600]
    except Exception as e:  # noqa: BLE001 - report every failure as data
        r["error"] = str(e).splitlines()[0][:200]
    return r


def main():
    todo = json.loads(IN.read_text())
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(user_agent=UA)
        page = ctx.new_page()
        for item in todo:
            seen, results = set(), []
            for url in item["urls"]:
                res = look(page, url)
                results.append(res)
                seen.add(url)
                # Follow the first careers link once, if the page itself doesn't show a hiring system.
                if not res.get("system_links"):
                    for nxt in res.get("careers_links", [])[:2]:
                        if nxt not in seen:
                            seen.add(nxt)
                            results.append(look(page, nxt))
            out.append({"employer": item["employer"], "results": results})
            print(item["employer"], [(r.get("status"), r.get("final"), r.get("systems")) for r in results])
        b.close()
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
