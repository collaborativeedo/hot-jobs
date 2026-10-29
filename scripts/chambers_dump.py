"""One-off: save rendered HTML of sample chamber directory pages so the harvester can be written against them."""
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(__file__).resolve().parent.parent / "data" / "chamber-dump"
OUT.mkdir(parents=True, exist_ok=True)
PAGES = {"spr-alpha-b": "https://business.springfield-chamber.org/list/searchalpha/b",
         "spr-cat": "https://business.springfield-chamber.org/list/ql/health-wellness-1026",
         "eug-cat": "https://web.eugenechamber.com/business/Banks",
         "eug-cat2": "https://web.eugenechamber.com/business/Plumbing-Contractors",
         "eug-search": "https://web.eugenechamber.com/atlas/directory/search"}
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    for k, u in PAGES.items():
        try:
            r = pg.goto(u, wait_until="networkidle", timeout=60000); pg.wait_for_timeout(3000)
            (OUT / f"{k}.html").write_text(f"<!-- {u} status {r.status if r else '?'} final {pg.url} -->\n" + pg.content())
            links = pg.eval_on_selector_all("a[href]", "els=>els.map(a=>a.href+' | '+a.innerText.trim().slice(0,60))")
            (OUT / f"{k}.links.txt").write_text("\n".join(links))
        except Exception as e:
            (OUT / f"{k}.err.txt").write_text(repr(e))
    b.close()
