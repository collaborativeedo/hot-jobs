"""Record the four short Hot Jobs training clips on the live Lane Workforce Partnership page.

    python scripts/record_tour.py [out_dir]      # writes clip-1.webm ... clip-4.webm, step screenshots, cues.json

Run from GitHub Actions (the probe workflow); the widget's anonymous counter is switched off for the recording
(Do Not Track, and requests to it are blocked) so the clips don't add fake traffic. Nothing is submitted: the
problem report is opened and cancelled, and no link is copied.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGE = "https://laneworkforce.org/hot-jobs/"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "data/debug/rec")
W, H = 1280, 720

OVERLAY = r"""
(() => {
  if (window.__tour) return;
  const css = document.createElement('style');
  css.textContent = `
  #tour-cap{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);max-width:1000px;z-index:2147483646;
    background:rgba(17,24,39,.92);color:#fff;font:600 24px/1.35 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    padding:14px 24px;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.3);opacity:0;transition:opacity .35s;text-align:center}
  #tour-cap.on{opacity:1}
  #tour-cur{position:fixed;left:0;top:0;width:26px;height:26px;margin:-13px 0 0 -13px;border-radius:50%;
    background:rgba(234,88,12,.35);border:3px solid #ea580c;z-index:2147483647;pointer-events:none;
    transition:transform .7s cubic-bezier(.4,0,.2,1);transform:translate(640px,360px)}
  #tour-cur.tap{animation:tourTap .4s}
  @keyframes tourTap{0%{box-shadow:0 0 0 0 rgba(234,88,12,.6)}100%{box-shadow:0 0 0 22px rgba(234,88,12,0)}}
  .tour-ring{outline:4px solid #ea580c !important;outline-offset:3px !important;box-shadow:0 0 0 9px rgba(234,88,12,.22) !important;border-radius:8px}
  #tour-card{position:fixed;inset:0;z-index:2147483647;display:flex;flex-direction:column;align-items:center;justify-content:center;
    background:linear-gradient(135deg,#0f3d5e,#155e75);color:#fff;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    opacity:0;transition:opacity .5s;pointer-events:none;text-align:center;padding:40px}
  #tour-card.on{opacity:1}
  #tour-card .k{font:600 22px/1.2 inherit;letter-spacing:.08em;text-transform:uppercase;opacity:.85}
  #tour-card .t{font:800 56px/1.15 inherit;margin:14px 0}
  #tour-card .s{font:500 26px/1.4 inherit;opacity:.92;max-width:900px}`;
  document.head.appendChild(css);
  const cap = Object.assign(document.createElement('div'), {id: 'tour-cap'});
  const cur = Object.assign(document.createElement('div'), {id: 'tour-cur'});
  const card = Object.assign(document.createElement('div'), {id: 'tour-card'});
  document.body.append(cap, cur, card);
  window.__tour = {
    cap(t) { cap.classList.remove('on'); setTimeout(() => { cap.textContent = t; if (t) cap.classList.add('on'); }, t ? 180 : 0); },
    move(x, y) { cur.style.transform = `translate(${x}px,${y}px)`; },
    tap() { cur.classList.remove('tap'); void cur.offsetWidth; cur.classList.add('tap'); },
    ring(sel, i) { document.querySelectorAll('.tour-ring').forEach(e => e.classList.remove('tour-ring'));
      if (sel) { const e = document.querySelectorAll(sel)[i || 0]; if (e) e.classList.add('tour-ring'); } },
    card(k, t, s) { if (!t) { card.classList.remove('on'); return; }
      card.innerHTML = `<div class="k">${k}</div><div class="t">${t}</div><div class="s">${s || ''}</div>`; card.classList.add('on'); },
  };
})();
"""


class Clip:
    def __init__(self, page, n, log):
        self.p, self.n, self.log, self.step = page, n, log, 0

    def wait(self, ms):
        self.p.wait_for_timeout(ms)

    def cap(self, text, ms=3200):
        self.p.evaluate("t => __tour.cap(t)", text)
        self.step += 1
        self.wait(600)
        self.p.screenshot(path=str(OUT / f"clip-{self.n}-step-{self.step:02d}.png"))
        self.log.append({"clip": self.n, "step": self.step, "caption": text})
        self.wait(max(ms - 600, 300))

    def card(self, kicker, title, sub="", ms=3000):
        self.p.evaluate("([k,t,s]) => __tour.card(k,t,s)", [kicker, title, sub])
        self.wait(ms)
        self.p.evaluate("() => __tour.card('', '')")
        self.wait(500)

    def ring(self, sel, i=0):
        self.p.evaluate("([s,i]) => __tour.ring(s,i)", [sel, i])

    def scroll_to(self, sel, i=0, offset=230):
        self.p.evaluate("""([s,i,o]) => { const e = document.querySelectorAll(s)[i]; if (!e) return;
            window.scrollTo({top: e.getBoundingClientRect().top + window.scrollY - o, behavior: 'smooth'}); }""", [sel, i, offset])
        self.wait(900)

    def point(self, loc):
        loc.scroll_into_view_if_needed()
        b = loc.bounding_box()
        if b:
            self.p.evaluate("([x,y]) => __tour.move(x,y)", [b["x"] + b["width"] / 2, b["y"] + b["height"] / 2])
            self.wait(800)

    def click(self, loc):
        self.point(loc)
        self.p.evaluate("() => __tour.tap()")
        loc.click()
        self.wait(700)


def chip(page, group, label):
    return page.locator(f'.lchj-chip[data-g="{group}"]', has_text=label).first


def open_page(browser, n):
    ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(OUT / f"raw-{n}"),
                              record_video_size={"width": W, "height": H})
    ctx.add_init_script("Object.defineProperty(navigator, 'doNotTrack', {get: () => '1'});")
    ctx.route("**/*workers.dev/**", lambda r: r.abort())
    page = ctx.new_page()
    page.goto(PAGE, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector(".lchj-jobs li", state="attached", timeout=60000)
    page.wait_for_timeout(1500)
    # The page may hold more than one copy of the widget (one hidden, for another screen size): keep the one shown.
    info = page.evaluate("""() => { const roots = [...document.querySelectorAll('.lchj')];
        const vis = roots.filter(r => r.getClientRects().length && r.getBoundingClientRect().height > 50);
        roots.filter(r => !vis.includes(r)).forEach(r => r.remove());
        if (vis[0]) vis[0].scrollIntoView();
        return {roots: roots.length, visible: vis.length,
                frames: [...document.querySelectorAll('iframe')].map(f => f.src).slice(0, 5)}; }""")
    print("page", n, info, flush=True)
    if not info["visible"]:
        page.screenshot(path=str(OUT / f"clip-{n}-page.png"), full_page=True)
        raise RuntimeError(f"no visible widget on the page: {info}")
    for txt in ("Decline", "Reject", "Deny", "Necessary only", "Close"):  # privacy-preserving choice on any banner
        b = page.get_by_role("button", name=txt)
        if b.count():
            try:
                b.first.click(timeout=1500)
            except Exception:
                pass
    page.evaluate(OVERLAY)
    # The LWP site keeps its menu bar on screen: leave room for it when scrolling.
    page.evaluate("() => { document.documentElement.style.scrollPaddingTop = '120px'; const r = document.querySelector('.lchj'); if (r) window.scrollTo({top: r.getBoundingClientRect().top + window.scrollY - 100}); }")
    page.wait_for_timeout(800)
    return ctx, page


def clip1(c, page):
    c.card("Hot Jobs tutorial · 1 of 4", "Search and filters", "Find the right openings in a few clicks")
    c.cap("Search by job title, skill or employer.", 1200)
    q = page.locator(".lchj-q")
    c.click(q)
    q.type("nurse", delay=140)
    c.wait(1200)
    c.ring(".lchj-count")
    c.cap("The count at the top updates as you go.")
    c.ring("")
    town = page.locator(".lchj-city")
    c.point(town)
    town.select_option("Eugene")
    c.wait(600)
    c.cap("Pick a town to stay close to home.")
    c.scroll_to('.lchj-chips[data-g="hours"]')
    full = chip(page, "hours", "Full-time")
    if full.count() and full.is_enabled():
        c.click(full)
        c.cap("Filters combine: here, full-time nursing jobs in Eugene.")
    c.scroll_to('.lchj-chips[data-g="type"]')
    c.ring('.lchj-chips[data-g="type"]')
    c.cap("Each button shows how many openings it would add.")
    c.ring("")
    clear = page.locator(".lchj-active .lchj-clear")
    if clear.count():
        c.scroll_to(".lchj-active")
        c.click(clear)
        c.cap("Clear all filters to start over.", 2500)
    c.cap("")
    c.card("Try it", "laneworkforce.org/hot-jobs", "Next: Fewer barriers", 2800)


def clip2(c, page):
    c.card("Hot Jobs tutorial · 2 of 4", "Fewer barriers", "Match clients to jobs they can reach and qualify for")
    c.scroll_to('.lchj-chips[data-g="ease"]', offset=260)
    c.ring('.lchj-chips[data-g="ease"]')
    c.cap("Fewer barriers filters narrow the list together.")
    c.ring("")
    bus = chip(page, "ease", "Near an LTD bus stop")
    c.click(bus)
    c.cap("Near an LTD bus stop: the workplace is about a quarter mile or less from a stop.")
    deg = chip(page, "ease", "No degree needed")
    if deg.count() and deg.is_enabled():
        c.click(deg)
        c.cap("Add No degree needed: now jobs must match both.")
    c.scroll_to(".lchj-jobs li")
    c.ring(".lchj-jobs li")
    c.cap("Every job shown is near transit and open to people without a degree.")
    c.ring("")
    clear = page.locator(".lchj-active .lchj-clear")
    if clear.count():
        c.scroll_to(".lchj-active")
        c.click(clear)
    c.scroll_to('.lchj-chips[data-g="ease"]', offset=260)
    fc = chip(page, "ease", "Fair-chance employer")
    if fc.count() and fc.is_enabled():
        c.click(fc)
        c.cap("Fair-chance employer: a confirmed fair-chance policy, or a posting that says a record won't rule you out.", 4200)
    tr = chip(page, "ease", "Training provided")
    c.point(tr)
    c.cap("Training provided: paid or on-the-job training, or an apprenticeship.", 3600)
    c.cap("")
    c.card("Try it", "laneworkforce.org/hot-jobs", "Next: Reading a listing", 2800)


def clip3(c, page):
    c.card("Hot Jobs tutorial · 3 of 4", "Reading a listing", "What each line tells you")
    find_posted = """() => { const li = [...document.querySelectorAll('.lchj-jobs li')].find(li =>
        li.querySelector('.lchj-pay:not(.typ)') && li.querySelector('.lchj-trust') && li.querySelector('.lchj-via'));
        return li ? li.dataset.id : null; }"""
    pid = page.evaluate(find_posted)
    for _ in range(6):  # look further down the list if needed
        if pid:
            break
        page.locator(".lchj-more").click()
        page.wait_for_timeout(500)
        pid = page.evaluate(find_posted)
    tid = page.evaluate("""() => { const li = [...document.querySelectorAll('.lchj-jobs li')].find(li =>
        li.querySelector('.lchj-pay.typ')); return li ? li.dataset.id : null; }""")
    card = f'.lchj-jobs li[data-id="{pid}"]'
    c.scroll_to(card)
    c.ring(card)
    c.cap("Each listing shows the job, the employer, the town and the hours.", 3600)
    c.ring(card + " .lchj-pay")
    c.cap('"Pay:" means the employer posted this pay.')
    if tid:
        tcard = f'.lchj-jobs li[data-id="{tid}"]'
        c.scroll_to(tcard)
        c.ring(tcard + " .lchj-pay")
        c.cap('"Pay not listed" shows the Lane County average for that kind of job, clearly marked.', 4200)
        c.scroll_to(card)
    c.ring(card + " .lchj-trust")
    c.cap('"Link checked" means we opened the posting and it was still up.', 3800)
    c.ring(card + " .lchj-act")
    c.cap("View and apply opens the original posting. The note says where the application goes.", 4200)
    c.ring(card + " .lchj-when")
    c.cap("And this shows how long ago the job was posted.")
    c.ring("")
    c.cap("")
    c.card("Try it", "laneworkforce.org/hot-jobs", "Next: Share a list, report a problem", 2800)


def clip4(c, page):
    c.card("Hot Jobs tutorial · 4 of 4", "Share a list, report a problem", "Hand a client their own short list")
    make = page.locator(".lchj-make")
    c.click(make)
    c.cap("Make a list for someone: pick up to 12 jobs for a client.")
    picks = page.locator(".lchj-pick input")
    for k in range(min(3, picks.count())):
        c.click(picks.nth(k))
    c.scroll_to(".lchj-tray", offset=300)
    c.ring(".lchj-tray")
    c.cap("Copy a link, show a QR code, or print a one-page list.")
    qr = page.locator('[data-tray="qr"]')
    if qr.count():
        c.click(qr)
        c.cap("The QR code opens the same list on a phone.", 3200)
    c.ring("")
    done = page.locator('[data-tray="done"]')
    if done.count():
        c.click(done)
    rep = page.locator('[data-report="open"]')
    c.scroll_to(".lchj-foot", offset=300)
    c.cap('Something wrong with a listing? Choose "Let us know".', 2600)
    c.click(rep)
    c.scroll_to(".lchj-report", offset=200)
    c.ring(".lchj-report")
    c.cap("Pick the job and what's wrong. We fix or remove listings that are wrong.", 3800)
    c.ring("")
    cancel = page.locator(".lchj-report button", has_text="Cancel")
    if cancel.count():
        c.click(cancel)
    c.cap("")
    c.card("That's it", "laneworkforce.org/hot-jobs", "Free, updated every night, built with Lane Workforce Partnership", 3200)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for n, fn in enumerate((clip1, clip2, clip3, clip4), start=1):
            ctx, page = open_page(browser, n)
            try:
                fn(Clip(page, n, log), page)
            except Exception as e:  # keep the other clips
                log.append({"clip": n, "error": f"{type(e).__name__}: {str(e)[:300]}"})
                page.screenshot(path=str(OUT / f"clip-{n}-error.png"))
            video = page.video
            ctx.close()
            src = Path(video.path())
            src.rename(OUT / f"clip-{n}.webm")
        browser.close()
    (OUT / "cues.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
