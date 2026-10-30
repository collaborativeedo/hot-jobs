"""Tests for the staff dashboard measures (scripts/dashboard.py) and the nightly archive (scripts/archive.py).

Run: python -m pytest tests/test_dashboard.py -q
"""
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import archive  # noqa: E402
import dashboard  # noqa: E402

TODAY = "2026-11-20"


def rec(first, closed=None, employer="Acme", type_="Healthcare & human services", title="Nurse", **kw):
    r = {"first_seen": first, "last_seen": closed or TODAY, "misses": 3 if closed else 0, "title": title,
         "employer": employer, "city": "Eugene", "soc": ""}
    if type_ is not None:
        r["type"] = type_
    if closed:
        r["closed"] = closed
    r.update(kw)
    return r


# ---- days open ----------------------------------------------------------------------------------------

def test_days_open_no_closed_postings():
    state = {"a": rec("2026-11-01"), "b": rec("2026-11-10", type_="Retail & sales", employer="Beta")}
    d = dashboard.days_open(state, TODAY)
    assert d["closed_30d"] == 0
    assert d["median_days_open_30d"] is None
    assert d["by_type"] == []
    assert d["open_now"] == 2
    assert [r["days_open"] for r in d["longest_open"]] == [19, 10]
    ages = {r["type"]: r["median_age"] for r in d["open_age_by_type"]}
    assert ages == {"Healthcare & human services": 19, "Retail & sales": 10}


def test_days_open_medians_window_and_type_threshold():
    state = {}
    for i, n in enumerate([2, 4, 6, 8, 10]):  # 5 healthcare closures -> reported; median 6
        state[f"h{i}"] = rec("2026-11-01", closed=f"2026-11-{1 + n:02d}")
    for i in range(4):  # 4 retail closures -> below the 5-posting threshold, but in the overall median
        state[f"r{i}"] = rec("2026-11-10", closed="2026-11-11", type_="Retail & sales")
    state["old"] = rec("2026-09-01", closed="2026-10-01")  # closed more than 30 days ago: excluded
    d = dashboard.days_open(state, TODAY)
    assert d["closed_30d"] == 9
    assert d["median_days_open_30d"] == 2.0  # [1,1,1,1,2,4,6,8,10]
    assert d["by_type"] == [{"type": "Healthcare & human services", "closed": 5, "median_days": 6.0}]
    assert d["open_now"] == 0 and d["longest_open"] == []


def test_missing_type_falls_back_to_occupation_code_or_title():
    state = {"a": rec("2026-11-01", type_=None, soc="291141"),  # registered nurses -> healthcare
             "b": rec("2026-11-01", type_=None, title="Zzzz", soc=""),  # nothing to go on -> Other
             "c": {"first_seen": "2026-11-05"}}  # bare old record
    d = dashboard.days_open(state, TODAY)
    types = {r["type"] for r in d["open_age_by_type"]}
    assert "Healthcare & human services" in types and "Other" in types
    assert d["open_now"] == 3


def test_longest_open_limited_to_20():
    state = {str(i): rec(f"2026-10-{i + 1:02d}", employer=f"E{i}") for i in range(30)}
    d = dashboard.days_open(state, TODAY)
    assert len(d["longest_open"]) == 20
    assert d["longest_open"][0]["days_open"] == 50


def test_longest_open_uses_posting_dates_and_caps_each_employer():
    state = {"a": rec("2026-11-01", posted="2026-01-01"), "b": rec("2026-11-01", posted="2026-02-01"),
             "c": rec("2026-11-01", posted="2026-03-01"), "d": rec("2026-11-01", employer="Beta", posted="2026-10-01"),
             "e": rec("2026-10-01", employer="Gamma")}  # no posting date: age unknown, left out
    d = dashboard.days_open(state, TODAY)
    assert [(r["employer"], r["days_open"]) for r in d["longest_open"]] == [("Acme", 323), ("Acme", 292), ("Beta", 50)]
    assert d["open_age_unknown"] == 1


# ---- added / removed by employer ----------------------------------------------------------------------

def test_employer_flow_flags_and_blank_names():
    state = {}
    # Big adder: 6 new this week -> expansion.
    for i in range(6):
        state[f"big{i}"] = rec("2026-11-18", employer="Big Co")
    # Small adder: 1 open before, 3 new -> net +3 and up by half or more -> expansion.
    state["s0"] = rec("2026-11-01", employer="Small Co")
    for i in range(3):
        state[f"s{i + 1}"] = rec("2026-11-19", employer="Small Co")
    # Modest adder: 8 open before, 3 new -> net +3 but up less than half -> not flagged.
    for i in range(8):
        state[f"m{i}"] = rec("2026-11-01", employer="Modest Co")
    for i in range(3):
        state[f"mn{i}"] = rec("2026-11-19", employer="Modest Co")
    # Gone quiet: 3 open a week ago, all closed this week -> watch.
    for i in range(3):
        state[f"q{i}"] = rec("2026-11-01", closed="2026-11-17", employer="Quiet Co")
    # Half closed: 6 open a week ago, 3 closed -> watch.
    for i in range(6):
        state[f"h{i}"] = rec("2026-11-01", closed="2026-11-16" if i < 3 else None, employer="Half Co")
    # Ten open, 3 closed -> not flagged.
    for i in range(10):
        state[f"t{i}"] = rec("2026-11-01", closed="2026-11-16" if i < 3 else None, employer="Ten Co")
    # Turnover: 10 open, 6 closed and 6 new this week -> net 0 -> on neither list.
    for i in range(10):
        state[f"to{i}"] = rec("2026-11-01", closed="2026-11-16" if i < 6 else None, employer="Turnover Co")
    for i in range(6):
        state[f"tn{i}"] = rec("2026-11-19", employer="Turnover Co")
    # Blank and placeholder employers never appear.
    for i in range(8):
        state[f"b{i}"] = rec("2026-11-18", employer="")
        state[f"u{i}"] = rec("2026-11-18", employer="Unnamed employer (Workday)")
        state[f"n{i}"] = rec("2026-11-18", employer=None)
    f = dashboard.employer_flow(state, TODAY)
    exp = {r["employer"] for r in f["expansion"]}
    watch = {r["employer"] for r in f["watch"]}
    assert exp == {"Big Co", "Small Co"}
    assert watch == {"Quiet Co", "Half Co"}
    names = {r["employer"] for r in f["movers"]}
    assert not any(n == "" or n.startswith("Unnamed") for n in names)
    assert f["added_7d"] == 6 + 3 + 3 + 6
    assert f["removed_7d"] == 3 + 3 + 3 + 6
    quiet = next(r for r in f["watch"] if r["employer"] == "Quiet Co")
    assert quiet == {"employer": "Quiet Co", "added": 0, "removed": 3, "open_week_ago": 3, "open_now": 0}


def test_employer_flow_empty_state():
    f = dashboard.employer_flow({}, TODAY)
    assert f["added_7d"] == 0 and f["removed_7d"] == 0 and f["expansion"] == [] and f["watch"] == []


def test_weekly_flow_window_edges():
    state = {"in": rec("2026-11-14"), "edge": rec("2026-11-13"), "c": rec("2026-11-01", closed="2026-11-20"),
             "blank": rec("2026-11-19", employer="")}
    # window is the 7 days ending today: Nov 14..Nov 20; blank employers still count in the overall totals
    assert dashboard.weekly_flow(state, TODAY) == (2, 1)


# ---- pay by type --------------------------------------------------------------------------------------

def test_pay_by_type_ignores_typical_pay_and_missing_type():
    jobs = [{"type": "Retail & sales", "pay": "$18 an hour", "typical_pay": ""},
            {"type": "Retail & sales", "pay": "", "typical_pay": "$17 an hour typical"},
            {"type": "Retail & sales", "pay": "  "},
            {"pay": "$20 an hour"},  # no type -> Other
            {"type": "", "pay": ""}]
    rows = {r["type"]: r for r in dashboard.pay_by_type(jobs)}
    assert rows["Retail & sales"] == {"type": "Retail & sales", "shown": 3, "posted_pay": 1, "share": 33.3}
    assert rows["Other"]["shown"] == 2 and rows["Other"]["posted_pay"] == 1
    assert dashboard.pay_by_type([]) == []
    assert dashboard.pay_by_type(jobs)[-1]["type"] == "Other"  # Other always last


# ---- update(): history and today.json -----------------------------------------------------------------

@pytest.fixture
def dash_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "DASH", tmp_path)
    monkeypatch.setattr(dashboard, "HISTORY", tmp_path / "history.json")
    monkeypatch.setattr(dashboard, "TODAY", tmp_path / "today.json")
    return tmp_path


def jobs_doc(**extra):
    return {"updated": TODAY + "T03:00+00:00", "pulled": 3,
            "jobs": [{"employer": "Acme", "type": "Retail & sales", "pay": "$18", "typical_pay": "", "route": ""},
                     {"employer": "Acme", "type": "Retail & sales", "pay": "", "typical_pay": "$17", "route": ""}],
            **extra}


def test_update_without_state_is_backward_compatible(dash_dir, monkeypatch):
    monkeypatch.setattr(dashboard, "today_detail", lambda *a: {"date": TODAY})
    row = dashboard.update(jobs_doc(), {}, {})
    assert row["share_posted_pay"] == 50.0
    assert row["dead_links_dropped"] is None
    assert "added_7d" not in row
    today = json.loads((dash_dir / "today.json").read_text())
    assert "days_open" not in today and "employer_flow" not in today
    assert today["pay_by_type"][0]["posted_pay"] == 1


def test_update_with_state_adds_fields_and_fills_history(dash_dir, monkeypatch):
    monkeypatch.setattr(dashboard, "today_detail", lambda *a: {"date": TODAY})
    (dash_dir / "history.json").write_text(json.dumps([{"date": "2026-11-05", "openings": 1},
                                                       {"date": "2026-11-15", "openings": 2}]))
    state = {"a": rec("2026-11-01", closed="2026-11-12"), "b": rec("2026-11-18"), "c": rec("2026-11-10")}
    row = dashboard.update(jobs_doc(dead_links_dropped=4), {}, {}, state=state)
    assert row["dead_links_dropped"] == 4
    assert row["added_7d"] == 1 and row["removed_7d"] == 0
    assert row["median_days_open_30d"] == 11.0
    hist = json.loads((dash_dir / "history.json").read_text())
    assert [h["date"] for h in hist] == ["2026-11-05", "2026-11-15", TODAY]
    assert hist[0]["added_7d"] is None  # first week of the record: left empty
    assert hist[1]["added_7d"] == 1 and hist[1]["removed_7d"] == 1
    today = json.loads((dash_dir / "today.json").read_text())
    assert today["days_open"]["open_now"] == 2
    assert today["employer_flow"]["added_7d"] == 1


# ---- archive ------------------------------------------------------------------------------------------

def test_archive_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "ARCHIVE", tmp_path)
    jobs = [{"id": "x1", "title": "Café cook", "snippet": "Señor", "extra": [1, 2]}]
    emps = {"Acme": {"open_now": 2, "industry": "Retail", "platform": "Workday", "first_seen": "2026-10-06",
                     "careers_page": "dropped"}}
    p = archive.save(jobs, "2026-11-20", emps)
    assert p == tmp_path / "2026" / "11" / "2026-11-20.json.gz"
    raw = gzip.decompress(p.read_bytes()).decode("utf-8")
    assert "Café" in raw  # ensure_ascii=False
    doc = archive.load("2026-11-20")
    assert doc["jobs"] == jobs and doc["count"] == 1
    assert doc["employers"] == {"Acme": {"open_now": 2, "industry": "Retail", "platform": "Workday",
                                         "first_seen": "2026-10-06"}}
    assert "employers" not in json.loads(gzip.decompress(archive.save(jobs, "2026-11-21").read_bytes()))


def test_archive_never_raises(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(archive, "ARCHIVE", tmp_path / "file")
    (tmp_path / "file").write_text("not a directory")
    assert archive.save([{"a": 1}], "2026-11-20") is None
    assert archive.save([{"a": 1}], "not a date") is None
    assert archive.save(None, "2026-11-20") is None
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 3 and all(line.startswith("Archive not saved") for line in out)


def test_archive_prune_keeps_everything_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "ARCHIVE", tmp_path)
    archive.save([{"a": 1}], "2020-01-01")
    assert archive.prune() == 0
    assert (tmp_path / "2020" / "01" / "2020-01-01.json.gz").exists()
    assert archive.prune(keep_days=30) == 1
