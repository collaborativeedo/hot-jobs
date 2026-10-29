"""Nightly numbers for the staff dashboard (docs/dashboard/).

Each run appends one row per day to docs/dashboard/history.json and writes today's detail to
docs/dashboard/today.json. The dashboard page reads both; the job seeker widget never does.

Backfill earlier days from the repository's own history:
    python scripts/dashboard.py --backfill
"""
import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH = ROOT / "docs" / "dashboard"
HISTORY = DASH / "history.json"
TODAY = DASH / "today.json"


def _share(n, d):
    return round(100 * n / d, 1) if d else None


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


def update(jobs_doc, employers, sources, pulled=None):
    DASH.mkdir(parents=True, exist_ok=True)
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else []
    row = metrics(jobs_doc, employers, sources, pulled)
    history = [h for h in history if h["date"] != row["date"]] + [row]
    history.sort(key=lambda h: h["date"])
    HISTORY.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    TODAY.write_text(json.dumps(today_detail(jobs_doc, employers, sources, history), ensure_ascii=False,
                                separators=(",", ":")), encoding="utf-8")
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
