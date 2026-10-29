"""Nightly traffic numbers for the staff traffic page (docs/traffic/).

Reads the counter's Cloudflare D1 database through the Cloudflare API and writes docs/traffic/data.json.
Needs CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in the environment; does nothing without them.

Daily unique-visitor counts are kept in data/traffic-uniques.json because the counter deletes its
anonymous visitor keys after about five weeks.
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "traffic" / "data.json"
UNIQUES = ROOT / "data" / "traffic-uniques.json"
CONFIG = ROOT / "data" / "analytics.json"
FEEDBACK = ROOT / "data" / "listing-feedback.json"  # per-listing "still open?" answers, read by the nightly refresh
CORE = {"load", "view", "apply"}
TEST_HOSTS = {"selftest.invalid"}


def query(sql, token, account, db):
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{db}/query",
        data=json.dumps({"sql": sql}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        doc = json.load(r)
    if not doc.get("success"):
        raise RuntimeError(f"D1 query failed: {doc.get('errors')}")
    return doc["result"][0]["results"]


def build(daily, uniq_rows, kept):
    """daily: rows of day/host/event/label/n. uniq_rows: day/host/event/u from D1. kept: earlier uniques."""
    # Merge visitor counts: what D1 still holds wins; older days come from the saved file.
    uniq = {(r["day"], r["host"], r["event"]): r["u"] for r in kept}
    for r in uniq_rows:
        uniq[(r["day"], r["host"], r["event"])] = r["u"]
    uniq = {k: v for k, v in uniq.items() if k[1] not in TEST_HOSTS and k[2] in CORE}
    rows = [r for r in daily if r["host"] not in TEST_HOSTS]
    daily = [r for r in rows if r["event"] in CORE]
    feedback, quality = listing_feedback(rows)

    days = sorted({r["day"] for r in daily} | {k[0] for k in uniq})
    by_day = {d: {"date": d, "loads": 0, "views": 0, "applies": 0, "visitors": 0, "sites": 0} for d in days}
    sites = defaultdict(lambda: {"loads": 0, "views": 0, "applies": 0, "visitor_days": 0, "days_active": set(),
                                 "first_seen": None, "last_seen": None, "loads_30": 0, "views_30": 0,
                                 "applies_30": 0, "visitors_30": 0})
    employers, types = defaultdict(int), defaultdict(int)
    employers_30, types_30 = defaultdict(int), defaultdict(int)
    last = days[-1] if days else ""
    cut = (dt.date.fromisoformat(last) - dt.timedelta(days=29)).isoformat() if last else ""
    key = {"load": "loads", "view": "views", "apply": "applies"}

    for r in daily:
        k, n, s = key[r["event"]], r["n"], sites[r["host"]]
        by_day[r["day"]][k] += n
        s[k] += n
        s["days_active"].add(r["day"])
        s["first_seen"] = min(filter(None, [s["first_seen"], r["day"]]))
        s["last_seen"] = max(filter(None, [s["last_seen"], r["day"]]))
        recent = r["day"] >= cut
        if recent:
            s[k + "_30"] += n
        if r["event"] == "apply":
            emp, _, typ = (r["label"] or "|").partition("|")
            employers[emp or "Employer not named"] += n
            types[typ or "Other"] += n
            if recent:
                employers_30[emp or "Employer not named"] += n
                types_30[typ or "Other"] += n

    per = defaultdict(lambda: {"loads": 0, "views": 0, "applies": 0, "visitors": 0})
    for r in daily:
        per[(r["day"], r["host"])][key[r["event"]]] += r["n"]
    for (day, host, event), u in uniq.items():
        if event != "load":
            continue
        if host != "*":
            per[(day, host)]["visitors"] = u
        if host == "*":
            by_day[day]["visitors"] = u
        else:
            sites[host]["visitor_days"] += u
            if day >= cut:
                sites[host]["visitors_30"] += u
    for d in days:
        by_day[d]["sites"] = len({r["host"] for r in daily if r["day"] == d and r["event"] == "load"})

    site_rows = []
    for host, s in sites.items():
        active = len(s.pop("days_active"))
        s.update(host=host, days_active=active,
                 avg_daily_visitors=round(s["visitor_days"] / active, 1) if active else 0,
                 view_rate=round(100 * s["views"] / s["loads"], 1) if s["loads"] else None,
                 apply_rate=round(100 * s["applies"] / s["views"], 1) if s["views"] else None)
        site_rows.append(s)
    site_rows.sort(key=lambda s: (-s["loads_30"], -s["loads"], s["host"]))

    top = lambda d, n: [{"name": k, "clicks": v} for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]
    totals = {k: sum(r[k] for r in by_day.values()) for k in ("loads", "views", "applies")}
    totals["visitor_days"] = sum(r["visitors"] for r in by_day.values())
    totals["sites"] = len(site_rows)
    return {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "first_day": days[0] if days else None, "last_day": last or None,
        "totals": totals, "by_day": [by_day[d] for d in days], "sites": site_rows,
        "site_days": [dict(date=d, host=h, **v) for (d, h), v in sorted(per.items())],
        "apply_by_employer": top(employers, 40), "apply_by_type": top(types, 30),
        "apply_by_employer_30": top(employers_30, 40), "apply_by_type_30": top(types_30, 30),
        **quality,
    }, feedback, [{"day": d, "host": h, "event": e, "u": u} for (d, h, e), u in sorted(uniq.items())]


def listing_feedback(rows):
    """Per-listing answers to "Was this job still open?", quick returns, and case-manager list use."""
    per = defaultdict(lambda: {"yes": 0, "no": 0, "quick": 0, "last": "", "employer": ""})
    lists = defaultdict(lambda: defaultdict(int))
    for r in rows:
        ev, label, n, day = r["event"], r["label"] or "", r["n"], r["day"]
        if ev == "stillopen":
            ans, _, rest = label.partition("|")
            jid, _, emp = rest.partition("|")
            if jid:
                rec = per[jid]
                rec["yes" if ans == "yes" else "no"] += n
                rec["employer"] = rec["employer"] or emp
                rec["last"] = max(rec["last"], day)
        elif ev == "quickreturn" and label:
            per[label]["quick"] += n
            per[label]["last"] = max(per[label]["last"], day)
        elif ev == "shortlist":
            act = label.partition("|")[0] or "other"
            lists[day][act] += n
    feedback = {k: v for k, v in per.items()}
    flagged = sorted(({"id": k, **v} for k, v in per.items() if v["no"] > v["yes"]),
                     key=lambda r: (-r["no"], r["id"]))[:50]
    quality = {
        "still_open": {"yes": sum(v["yes"] for v in per.values()), "no": sum(v["no"] for v in per.values()),
                       "quick_returns": sum(v["quick"] for v in per.values())},
        "flagged_listings": flagged,
        "shortlists_by_day": [{"date": d, **dict(v)} for d, v in sorted(lists.items())],
    }
    return feedback, quality


def main():
    token, account = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    db = (json.loads(CONFIG.read_text()) if CONFIG.exists() else {}).get("database_id")
    if not (token and account and db):
        print("Traffic: Cloudflare settings missing; skipped.")
        return 0
    daily = query("SELECT day, host, event, label, n FROM daily", token, account, db)
    uniq_rows = query("SELECT day, host, event, COUNT(*) AS u FROM visitors GROUP BY day, host, event", token, account, db)
    kept = json.loads(UNIQUES.read_text()) if UNIQUES.exists() else []
    doc, feedback, uniq = build(daily, uniq_rows, kept)
    FEEDBACK.write_text(json.dumps(feedback, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    UNIQUES.write_text(json.dumps(uniq, separators=(",", ":")), encoding="utf-8")
    t = doc["totals"]
    print(f"Traffic: {t['sites']} sites, {t['loads']} loads, {t['views']} views, {t['applies']} apply clicks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
