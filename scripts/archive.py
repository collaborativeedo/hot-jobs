"""Nightly archive of every posting the run pulled, kept for analysis we have not thought of yet.

The published files (docs/jobs.json, data/state.json) keep only what the widget and dashboard need today:
jobs.json holds postings up to 14 days old and a fixed set of fields, and state.json keeps one small record per
posting. The archive keeps the whole night: every posting pulled, with every field the run had for it (snippet,
pay, occupation code, route, source, dates ...), plus a compact snapshot of the employer record. Over months
this supports questions such as how pay statements change, how long particular occupations take to fill, or
which employers post seasonally, without having to have planned for them.

Format: one gzip-compressed JSON file per night at data/archive/YYYY/MM/YYYY-MM-DD.json.gz:

    {"date": "2026-10-29", "archived": "<UTC time>", "count": 2571,
     "jobs": [ {...every field of each posting...}, ... ],
     "employers": {"<name>": {"open_now": 3, "industry": "", "platform": "Workday", "first_seen": "2026-10-28"}}}

"employers" is present only when the caller passes the employer record. A re-run on the same day replaces that
day's file. Read one back with load("2026-10-29").

Size: first planned at 100-200 KB per night; measured on Oct 29, 2026 data it is closer to 250-400 KB per night
compressed for ~2,500 postings (the 799 postings shown that day alone compress to ~97 KB), so roughly 100-150 MB
a year. We keep everything; prune() does nothing unless it is given a number of days.
"""
import datetime as dt
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "data" / "archive"


def path_for(day):
    return ARCHIVE / day[:4] / day[5:7] / f"{day}.json.gz"


def save(jobs, today, employers=None):
    """Write tonight's archive file. Never raises: on any problem prints one line and returns None."""
    try:
        day = dt.date.fromisoformat(str(today)[:10]).isoformat()
        doc = {"date": day, "archived": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
               "count": len(jobs), "jobs": [dict(j) for j in jobs]}
        if employers:
            doc["employers"] = {name: {"open_now": e.get("open_now", 0), "industry": e.get("industry", ""),
                                       "platform": e.get("platform", ""), "first_seen": e.get("first_seen", "")}
                                for name, e in employers.items()}
        out = path_for(day)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        data = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        with gzip.open(tmp, "wb", compresslevel=9) as f:
            f.write(data)
        tmp.replace(out)
        return out
    except Exception as e:  # noqa: BLE001  the archive never stops the nightly run
        print(f"Archive not saved: {type(e).__name__}: {e}")
        return None


def load(day):
    """Read one night's archive back (None if there is no file for that day)."""
    p = path_for(str(day)[:10])
    if not p.exists():
        return None
    with gzip.open(p, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def prune(keep_days=None):
    """Delete archive files older than keep_days. By default (None) does nothing: we keep everything."""
    if not keep_days:
        return 0
    cutoff = dt.date.today() - dt.timedelta(days=int(keep_days))
    n = 0
    for p in ARCHIVE.glob("*/*/*.json.gz"):
        try:
            if dt.date.fromisoformat(p.name[:10]) < cutoff:
                p.unlink()
                n += 1
        except ValueError:
            continue
    return n
