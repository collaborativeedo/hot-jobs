"""One-off cleanup of already-published data with the location rules in ats._rows (used Oct 29, 2026).

    python scripts/out_of_area.py     # drops out-of-area and non-job rows read from employer hiring sites

The nightly run applies the same rules as it reads each source; this only fixes data published before a rule
change, then recomputes the staff dashboard for the day.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive  # noqa: E402
import ats  # noqa: E402
import dashboard  # noqa: E402
from direct import lane_city  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"


def host(u):
    return re.sub(r"^https?://([^/]+).*$", r"\1", u or "").lower()


def bad_keys(rows, trusted=frozenset()):
    """URLs to drop among rows read from employer hiring sites (title and url only; locations are not kept).
    Employers in `trusted` (hand-checked Lane County employers) lose only rows that name another place."""
    by = defaultdict(list)
    for r in rows:
        by[host(r["url"])].append(r)
    drop = set()
    for h, rs in by.items():
        named = sum(1 for r in rs if lane_city(r["title"]))
        away = sum(1 for r in rs if not lane_city(r["title"]) and ats._NOT_HERE.search(r["title"]))
        national = (away >= 3 or away > named) and not any((r.get("employer") or "") in trusted for r in rs)
        for r in rs:
            t = r["title"].strip()
            if ats._SOCIAL.match(t) or (not lane_city(t) and (ats._NOT_HERE.search(t) or national)):
                drop.add(r["url"])
    return drop


def main():
    direct_route = "Employer's hiring site"
    doc = json.loads((ROOT / "docs" / "jobs.json").read_text())
    pulled = json.loads((D / "pulled.json").read_text())
    rows = [r for r in pulled if r.get("route") == direct_route] + \
           [j for j in doc["jobs"] if j.get("source") == "Employer direct"]
    sites = json.loads((D / "employer-sites.json").read_text())
    auto = {x["employer"] for x in sites if x.get("list") and x.get("list") != "Eugene tech (Matt)"}
    trusted = {r.get("employer") or "" for r in rows} - auto
    drop = bad_keys(rows, frozenset(trusted))
    n_show, n_pull = len(doc["jobs"]), len(pulled)
    doc["jobs"] = [j for j in doc["jobs"] if j["url"] not in drop]
    pulled = [r for r in pulled if r["url"] not in drop]
    doc["count"], doc["pulled"] = len(doc["jobs"]), len(pulled)
    state = json.loads((D / "state.json").read_text())
    n_state = len(state)
    state = {k: v for k, v in state.items() if not (v.get("route") == direct_route and v.get("first_seen", "") >= "2026-10-29"
                                                    and (ats._SOCIAL.match(v.get("title", "").strip())
                                                         or (not lane_city(v.get("title", "")) and ats._NOT_HERE.search(v.get("title", "")))))}
    emps = json.loads((D / "employers.json").read_text())
    live = defaultdict(int)
    for r in pulled:
        live[r.get("employer") or ""] += 1
    for name, e in emps.items():
        if e.get("open_now") and live.get(name, 0) < e["open_now"]:
            e["open_now"] = live.get(name, 0)
            if not e["open_now"]:
                e["cities_now"] = []
    (ROOT / "docs" / "jobs.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (D / "pulled.json").write_text(json.dumps(pulled, ensure_ascii=False, indent=0), encoding="utf-8")
    (D / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    (D / "employers.json").write_text(json.dumps(emps, ensure_ascii=False, indent=1), encoding="utf-8")
    day = doc["updated"][:10]
    for d in {day, "2026-10-29"}:
        a = archive.load(d)
        if a:
            archive.save([j for j in a["jobs"] if j.get("url") not in drop], d, employers=emps)
    row = dashboard.update(doc, emps, json.loads((D / "sources.json").read_text()), state=state)
    print(f"Shown {n_show} -> {len(doc['jobs'])}; pulled {n_pull} -> {len(pulled)}; history {n_state} -> {len(state)}; "
          f"dashboard openings {row['openings']}, employers hiring {row['employers_hiring']}.")


if __name__ == "__main__":
    main()
