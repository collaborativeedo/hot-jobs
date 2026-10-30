"""Nightly numbers for the staff dashboard (docs/dashboard/).

Each run appends one row per day to docs/dashboard/history.json and writes today's detail to
docs/dashboard/today.json. The dashboard page reads both; the job seeker widget never does.

Backfill earlier days from the repository's own history:
    python scripts/dashboard.py --backfill

Three measures read the posting record (data/state.json: posting id -> first_seen, last_seen, closed, ...):
  * days open: how long postings closed in the last 30 days stayed open, and how old open postings are now;
  * postings added and removed by employer over the last 7 days, with flagged employers worth a call;
  * share of today's postings that state pay, by type of work (from docs/jobs.json).
Dates in the record are the nights the run first saw or stopped seeing a posting; the run began Oct 6, 2026.
"""
import argparse
import datetime as dt
import json
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH = ROOT / "docs" / "dashboard"
HISTORY = DASH / "history.json"
TODAY = DASH / "today.json"


def _share(n, d):
    return round(100 * n / d, 1) if d else None


def _date(s):
    try:
        return dt.date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def _median(xs):
    return float(round(statistics.median(xs), 1)) if xs else None


def _type_of(rec):
    """Type of work for a posting record. Records written before Oct 30, 2026 carry no "type": derive it
    the same way the nightly run does (occupation code, else job title); "Other" if that is not possible."""
    if rec.get("type"):
        return rec["type"]
    try:
        import rules
        return rules.type_of_work(rec["soc"]) if rec.get("soc") else rules.type_from_title(rec.get("title", ""))
    except Exception:  # noqa: BLE001
        return "Other"


def _skip_employer(name):
    return not (name or "").strip() or name.startswith("Unnamed")


def _is_open(rec, day):
    """True when the posting was open on `day`: first seen on or before it and not closed by then."""
    fs, cl = _date(rec.get("first_seen")), _date(rec.get("closed"))
    return fs is not None and fs <= day and (cl is None or cl > day)


def days_open(state, today, longest=20):
    """How long postings stay open.

    Closed in the last 30 days: days open = closed - first_seen. Median overall and by type of work
    (types with at least 5 such postings). Open now: median age (today - first_seen) by type, and the
    `longest` oldest open postings.
    """
    today = _date(today) if isinstance(today, str) else today
    since = today - dt.timedelta(days=30)
    closed, by_type = [], defaultdict(list)
    ages, open_rows = defaultdict(list), []
    for rec in state.values():
        fs, cl = _date(rec.get("first_seen")), _date(rec.get("closed"))
        if fs is None:
            continue
        t = _type_of(rec)
        if cl is not None:
            if since < cl <= today:
                d = max(0, (cl - fs).days)
                closed.append(d)
                by_type[t].append(d)
        elif fs <= today:
            age = (today - fs).days
            ages[t].append(age)
            open_rows.append({"title": rec.get("title", ""), "employer": rec.get("employer", ""),
                              "city": rec.get("city", ""), "type": t, "first_seen": rec.get("first_seen", ""),
                              "days_open": age})
    open_rows.sort(key=lambda r: (-r["days_open"], r["title"].lower()))
    return {
        "closed_30d": len(closed),
        "median_days_open_30d": _median(closed),
        "by_type": sorted(({"type": t, "closed": len(v), "median_days": _median(v)} for t, v in by_type.items()
                           if len(v) >= 5), key=lambda r: (-r["median_days"], r["type"])),
        "open_now": sum(len(v) for v in ages.values()),
        "open_age_by_type": sorted(({"type": t, "open": len(v), "median_age": _median(v)} for t, v in ages.items()),
                                   key=lambda r: (-r["median_age"], -r["open"], r["type"])),
        "longest_open": open_rows[:longest],
        "open_at_longest": sum(1 for r in open_rows if r["days_open"] == open_rows[0]["days_open"]) if open_rows else 0,
    }


def weekly_flow(state, today):
    """Postings added (first seen) and removed (closed) in the 7 days ending `today`, all employers."""
    today = _date(today) if isinstance(today, str) else today
    start = today - dt.timedelta(days=7)
    added = sum(1 for r in state.values() if (d := _date(r.get("first_seen"))) and start < d <= today)
    removed = sum(1 for r in state.values() if (d := _date(r.get("closed"))) and start < d <= today)
    return added, removed


def employer_flow(state, today):
    """Postings added and removed by employer over the 7 days ending `today`, with two flagged lists.

    Both lists use net change (open now minus open a week ago), so big employers that simply turn postings over
    are not flagged. Possible expansion: net +3 or more, and open postings up by at least half (or from none).
    Watch list: net -3 or more, and open postings down by at least half (or to none).
    Employers with a blank name or an "Unnamed ..." placeholder are left out. These are signals worth a call,
    not conclusions: postings close for many reasons, including positions being filled.
    """
    today = _date(today) if isinstance(today, str) else today
    start = today - dt.timedelta(days=7)
    emp = defaultdict(lambda: {"added": 0, "removed": 0, "open_week_ago": 0, "open_now": 0})
    for rec in state.values():
        name = (rec.get("employer") or "").strip()
        if _skip_employer(name):
            continue
        fs, cl = _date(rec.get("first_seen")), _date(rec.get("closed"))
        if fs is None or fs > today:
            continue
        e = emp[name]
        if start < fs:
            e["added"] += 1
        if cl is not None and start < cl <= today:
            e["removed"] += 1
        if _is_open(rec, start):
            e["open_week_ago"] += 1
        if _is_open(rec, today):
            e["open_now"] += 1
    rows = [{"employer": k} | v for k, v in emp.items() if v["added"] or v["removed"]]

    def net(r):
        return r["open_now"] - r["open_week_ago"]

    def expansion(r):
        return net(r) >= 3 and (r["open_week_ago"] == 0 or r["open_now"] >= 1.5 * r["open_week_ago"])

    def watch(r):
        return net(r) <= -3 and (r["open_now"] == 0 or r["open_now"] <= 0.5 * r["open_week_ago"])

    key = lambda r: r["employer"].lower()  # noqa: E731
    return {
        "added_7d": sum(r["added"] for r in rows),
        "removed_7d": sum(r["removed"] for r in rows),
        "employers_adding": sum(1 for r in rows if r["added"]),
        "employers_removing": sum(1 for r in rows if r["removed"]),
        "expansion": sorted((r for r in rows if expansion(r)), key=lambda r: (-net(r), key(r))),
        "watch": sorted((r for r in rows if watch(r)), key=lambda r: (net(r), key(r))),
        "movers": sorted(rows, key=lambda r: (-(r["added"] + r["removed"]), key(r)))[:40],
    }


def pay_by_type(jobs):
    """Share of postings shown today whose employer stated pay ("pay"; "typical_pay" is an occupation
    average and does not count), by type of work."""
    n, k = Counter(), Counter()
    for j in jobs:
        t = j.get("type") or "Other"
        n[t] += 1
        if (j.get("pay") or "").strip():
            k[t] += 1
    return sorted(({"type": t, "shown": n[t], "posted_pay": k[t], "share": _share(k[t], n[t])} for t in n),
                  key=lambda r: (r["type"] == "Other", -(r["share"] or 0), -r["shown"], r["type"]))


def state_metrics(state, day):
    """History-row fields that come from the posting record for one day (None when there is no record)."""
    d = _date(day)
    if not state or d is None:
        return {"added_7d": None, "removed_7d": None, "median_days_open_30d": None, "closed_30d": None}
    added, removed = weekly_flow(state, d)
    do = days_open(state, d, longest=0)
    return {"added_7d": added, "removed_7d": removed, "median_days_open_30d": do["median_days_open_30d"],
            "closed_30d": do["closed_30d"]}


def metrics(jobs_doc, employers, sources, pulled=None):
    """One day's figures from the published jobs, the employer record and the direct sources."""
    jobs = jobs_doc.get("jobs", [])
    n = len(jobs)
    hiring = {k: v for k, v in employers.items() if v.get("open_now")}
    ok = [s for s in sources.values() if s.get("status") == "ok"]
    day = (jobs_doc.get("updated") or "")[:10]
    return {
        "date": day,
        "openings": n,
        # Remote roles from employers with a Lane County presence are listed but kept out of the Lane County count.
        "openings_lane": sum(1 for j in jobs if not (j.get("remote") or j.get("city") == "Remote")),
        "openings_remote": sum(1 for j in jobs if j.get("remote") or j.get("city") == "Remote"),
        "postings_pulled": jobs_doc.get("pulled") or (len(pulled) if pulled else None),
        "employers_hiring": len(hiring),
        "employers_on_record": len(employers),
        "employer_sources_searched": len(sources),
        "employer_sources_ok": len(ok),
        "employer_sites_by_name": sum(1 for s in sources.values() if s.get("named")),
        "direct_openings": sum(s.get("lane_openings", 0) for s in ok),
        "share_direct_to_employer": _share(sum(1 for j in jobs if j.get("route") == "Employer's hiring site"), n),
        "share_employer_named": _share(sum(1 for j in jobs if j.get("employer")), n),
        "share_with_pay": _share(sum(1 for j in jobs if j.get("pay") or j.get("typical_pay")), n) if n and "typical_pay" in jobs[0] else None,
        "share_posted_pay": _share(sum(1 for j in jobs if j.get("pay")), n) if n and "pay" in jobs[0] else None,
        "by_type": dict(Counter(j.get("type") or "Other" for j in jobs)),
        "by_workplace": dict(Counter(w for j in jobs for w in (j.get("workplaces") or []))),
        "by_city": dict(Counter(j.get("city") or "Lane County" for j in jobs)),
        "by_hours": dict(Counter(j.get("hours") or "Not stated" for j in jobs)) if n and "hours" in jobs[0] else {},
        "by_route": dict(Counter(j.get("route") or "" for j in jobs)),
        "by_type_posted_pay": dict(Counter(j.get("type") or "Other" for j in jobs if (j.get("pay") or "").strip())),
        "dead_links_dropped": jobs_doc.get("dead_links_dropped"),
    }


def today_detail(jobs_doc, employers, sources, history):
    """Lists for the dashboard tables: top hiring employers, newest employers, direct sources."""
    day = (jobs_doc.get("updated") or "")[:10]
    shown = Counter(j.get("employer") for j in jobs_doc.get("jobs", []) if j.get("employer"))
    top = [{"employer": k, "openings_shown": v, "industry": (employers.get(k) or {}).get("industry", ""),
            "first_seen": (employers.get(k) or {}).get("first_seen", "")} for k, v in shown.most_common(25)]
    from enrich import clean_employer
    new = sorted(({"employer": k, "first_seen": v.get("first_seen", ""), "open_now": v.get("open_now", 0),
                   "industry": v.get("industry", ""), "platform": v.get("platform", "")} for k, v in employers.items()
                  if not k.startswith("Unnamed") and v.get("open_now") and clean_employer(k) == k
                  and v.get("first_seen", "") >= _days_before(day, 7)),
                 key=lambda r: (-r["open_now"], r["employer"].lower()))
    src = sorted(({"employer": _clean_name(s.get("employer")) or ("Public employers (NEOGOV)" if s.get("multi") else k),
                   "system": s.get("platform", ""), "openings": s.get("lane_openings", 0), "status": s.get("status", ""),
                   "added_by_name": bool(s.get("named")), "first_seen": s.get("first_seen", "")}
                  for k, s in sources.items()), key=lambda r: (-r["openings"], r["employer"].lower()))
    return {"date": day, "updated": jobs_doc.get("updated"), "top_employers": top, "new_employers": new,
            "sources": src, "days_tracked": len(history)}


def _clean_name(name):
    import re
    name = re.sub(r"\s+(External|Candidate Experience page|US)$", "", name or "").replace("JPMC", "JPMorgan Chase")
    return "" if re.search(r"[A-Za-z]\d{3,}", name) else ("International Paper" if name == "IP Global" else name)


def _days_before(day, n):
    import datetime as dt
    try:
        return (dt.date.fromisoformat(day) - dt.timedelta(days=n)).isoformat()
    except ValueError:
        return ""


def _state_day(jobs_doc, state):
    day = (jobs_doc.get("updated") or "")[:10]
    if _date(day):
        return day
    seen = [r.get("last_seen", "") for r in (state or {}).values()]
    return max(seen) if seen else ""


def fill_history(history, state):
    """Add posting-record fields to earlier history rows that lack them, recomputed as of each row's date.
    Weekly figures are left empty for the first week the run was going, when every posting was new to it."""
    if not state:
        return history
    starts = [d for r in state.values() if (d := _date(r.get("first_seen")))]
    first = min(starts) if starts else None
    for h in history:
        if "added_7d" in h or not _date(h.get("date")):
            continue
        h.update(state_metrics(state, h["date"]))
        if first and _date(h["date"]) < first + dt.timedelta(days=7):
            h["added_7d"] = h["removed_7d"] = None
    return history


def update(jobs_doc, employers, sources, pulled=None, state=None):
    """Append today's row to history.json and rewrite today.json.

    state: the dict from data/state.json (posting id -> record). Optional: without it the days-open and
    added/removed measures are left out and everything else works as before.
    """
    DASH.mkdir(parents=True, exist_ok=True)
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    row = metrics(jobs_doc, employers, sources, pulled)
    if state:
        if not row["date"]:
            row["date"] = _state_day(jobs_doc, state)
        row.update(state_metrics(state, row["date"]))
    history = [h for h in history if h["date"] != row["date"]] + [row]
    history.sort(key=lambda h: h["date"])
    fill_history(history, state)
    detail = today_detail(jobs_doc, employers, sources, history)
    detail["pay_by_type"] = pay_by_type(jobs_doc.get("jobs", []))
    if state and _date(row["date"]):
        detail["days_open"] = days_open(state, row["date"])
        detail["employer_flow"] = employer_flow(state, row["date"])
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    TODAY.write_text(json.dumps(detail, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return row


def _git_show(rev, path):
    try:
        return json.loads(subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{path}"], capture_output=True,
                                         text=True, check=True).stdout)
    except (subprocess.CalledProcessError, ValueError):
        return None


def backfill():
    """Rebuild history from every earlier commit of docs/jobs.json (latest commit per day wins)."""
    revs = subprocess.run(["git", "-C", str(ROOT), "log", "--format=%H", "--", "docs/jobs.json"],
                          capture_output=True, text=True, check=True).stdout.split()
    rows = {}
    for rev in reversed(revs):
        doc = _git_show(rev, "docs/jobs.json")
        if not doc or not doc.get("jobs"):
            continue
        emps = _git_show(rev, "data/employers.json") or {}
        srcs = _git_show(rev, "data/sources.json") or {}
        row = metrics(doc, emps, srcs)
        if row["date"]:
            rows[row["date"]] = row
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    for h in history:
        rows[h["date"]] = h
    DASH.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(sorted(rows.values(), key=lambda h: h["date"]), ensure_ascii=False,
                                  separators=(",", ":")), encoding="utf-8")
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    a = ap.parse_args()
    if a.backfill:
        print(f"{backfill()} days in history")
