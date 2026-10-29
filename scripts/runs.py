"""Nightly-process health for the staff dashboard: recent runs of every automated workflow, how long they took,
and whether they finished cleanly, plus the step timings and warnings the nightly refresh recorded.

Writes docs/dashboard/runs.json. Runs inside GitHub Actions (needs GITHUB_TOKEN and GITHUB_REPOSITORY); never fails
the workflow.
"""
import datetime as dt
import json
import os
import re
import statistics
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "dashboard" / "runs.json"
RUNLOG = ROOT / "data" / "run-log.json"
WARN = re.compile(r"fail|error|refused|timed? ?out|skipp|stopped|not saved|unavailable|challenge|using the last good", re.I)
ZERO = re.compile(r"\b0 (failed|errors?|refused|skipped|stopped)", re.I)  # "0 failed" is not a warning
# Plain-English names for each workflow and what it does.
ABOUT = {
    "Refresh and publish": "Nightly: pulls every Lane County posting, checks links, publishes the widget and dashboards",
    "Deploy traffic counter": "Updates the anonymous widget counter (runs when its code changes)",
    "Read National Labor Exchange (Lane County)": "Snapshot of NLx postings (by hand; the nightly run reads NLx itself)",
    "Refresh reference data (education levels, LTD stops, geocodes)": "Education levels, LTD bus stops and employer addresses",
    "Discover employer job pages": "Looks for careers pages of employers in the QualityInfo database",
    "Find careers pages": "Looks for careers pages of named employers",
    "Read QualityInfo employer database": "Reads the QualityInfo employer database",
}


def _t(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def _pacific(t):
    # Pacific time without a tz database: daylight time from the 2nd Sunday in March to the 1st Sunday in November.
    y = t.year
    start = dt.datetime(y, 3, 8 + (6 - dt.date(y, 3, 8).weekday()) % 7, 10, tzinfo=dt.timezone.utc)
    end = dt.datetime(y, 11, 1 + (6 - dt.date(y, 11, 1).weekday()) % 7, 9, tzinfo=dt.timezone.utc)
    return (t + dt.timedelta(hours=-7 if start <= t < end else -8)).strftime("%Y-%m-%d %H:%M")


def runs_by_workflow(rows, keep=10):
    """rows: GitHub workflow runs (newest first) -> per-workflow summary and recent runs."""
    now = dt.datetime.now(dt.timezone.utc)
    by = {}
    for r in rows:
        name = r.get("name") or "?"
        start, end = _t(r.get("run_started_at") or r.get("created_at")), _t(r.get("updated_at"))
        running = r.get("status") != "completed"
        mins = round(((now if running else end) - start).total_seconds() / 60, 1) if start and end else None
        result = "running" if running else (r.get("conclusion") or "unknown")
        by.setdefault(name, []).append({"started": _pacific(start) if start else "", "minutes": mins, "result": result,
                                        "trigger": {"schedule": "nightly", "workflow_dispatch": "by hand",
                                                    "push": "code change"}.get(r.get("event"), r.get("event")),
                                        "url": r.get("html_url", "")})
    out = []
    for name, rs in by.items():
        rs = rs[:keep]
        done = [x for x in rs if x["result"] not in ("running", "cancelled", "skipped")]
        mins = [x["minutes"] for x in done if x["result"] == "success" and x["minutes"] is not None]
        out.append({"workflow": name, "about": ABOUT.get(name, ""), "last": rs[0],
                    "failures": sum(1 for x in done if x["result"] != "success"), "finished": len(done),
                    "median_minutes": round(statistics.median(mins), 1) if mins else None, "runs": rs})
    out.sort(key=lambda w: w["last"]["started"], reverse=True)
    out.sort(key=lambda w: w["workflow"] != "Refresh and publish")  # nightly refresh first, then most recent
    return out


def nightly_notes(runlog):
    """Step timings and warnings from the nightly refresh's own log (data/run-log.json)."""
    out = []
    for e in reversed(runlog[-10:]):
        out.append({"date": _pacific(_t(e["date"])) if e.get("date") else "", "ok": e.get("ok", True),
                    "steps": e.get("steps", []),
                    "warnings": [n for n in e.get("notes", []) if WARN.search(ZERO.sub("", n))][:15]})
    return out


def main():
    doc = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "workflows": [], "nightly": []}
    try:
        doc["nightly"] = nightly_notes(json.loads(RUNLOG.read_text())) if RUNLOG.exists() else []
    except Exception as e:  # noqa: BLE001
        doc["error_log"] = f"{type(e).__name__}: {e}"
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if repo and token:
        try:
            r = requests.get(f"https://api.github.com/repos/{repo}/actions/runs", params={"per_page": 100},
                             headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                             timeout=30)
            r.raise_for_status()
            doc["workflows"] = runs_by_workflow(r.json().get("workflow_runs", []))
        except Exception as e:  # noqa: BLE001
            doc["error_github"] = f"{type(e).__name__}: {str(e)[:200]}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Nightly processes: {len(doc['workflows'])} workflows, {len(doc['nightly'])} nightly logs.")


if __name__ == "__main__":
    main()
