"""Offline tests for scripts/reference.py. Run: python -m pytest tests/test_reference.py"""
import io
import json
import sys
import zipfile
import datetime as dt
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reference as R  # noqa: E402


# --- fixtures ---------------------------------------------------------------------------------

def make_xlsx(sheets):
    """Minimal xlsx built with the standard library. sheets: {name: [[cell, ...], ...]}.
    Strings go to the shared-string table, except those starting with '!' (written inline)."""
    shared, sheet_xml = [], []
    for rows in sheets.values():
        out = []
        for r, row in enumerate(rows, 1):
            cells = []
            for c, val in enumerate(row):
                ref = f"{chr(65 + c)}{r}"
                if val is None:
                    continue
                if isinstance(val, (int, float)):
                    cells.append(f'<c r="{ref}"><v>{val}</v></c>')
                elif val.startswith("!"):
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{val[1:]}</t></is></c>')
                else:
                    shared.append(val)
                    cells.append(f'<c r="{ref}" t="s"><v>{len(shared) - 1}</v></c>')
            out.append(f'<row r="{r}">{"".join(cells)}</row>')
        sheet_xml.append('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                         f'<sheetData>{"".join(out)}</sheetData></worksheet>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' \
         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    wb = f'<?xml version="1.0"?><workbook {ns}><sheets>' + "".join(
        f'<sheet name="{n}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, n in enumerate(sheets)) + "</sheets></workbook>"
    rels = '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
        f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets))) + "</Relationships>"
    sst = '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + "".join(
        f"<si><t>{s.replace('&', '&amp;')}</t></si>" for s in shared) + "</sst>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/sharedStrings.xml", sst)
        for i, x in enumerate(sheet_xml):
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", x)
    return buf.getvalue()


EDU_SHEETS = {
    "Table 5.1": [["Summary table"], ["Typical education needed for entry", "Employment"], ["Bachelor's degree", 100]],
    "Table 5.4": [
        ["Table 5.4 Education and training assignments by detailed occupation, 2024"],
        ["2024 National Employment Matrix title", "2024 National Employment Matrix code",
         "Typical education needed for entry", "Work experience in a related occupation",
         "Typical on-the-job training needed to attain competency in the occupation"],
        ["Total, all occupations", "00-0000", "—", "—", "—"],
        ["Registered nurses", "29-1141", "Bachelor's degree", "None", "None"],
        ["Cashiers", "41-2011", "No formal educational credential", "None", "Short-term on-the-job training"],
        ["Customer service representatives", "43-4051", "!High school diploma or equivalent", "None", "Short-term"],
        ["Medical assistants", "31-9092", "Postsecondary nondegree award", "None", "None"],
        ["Software developers", "15-1252", "Bachelor's degree(1)", "None", "None"],
        ["Software quality assurance analysts", "15-1253", "Bachelor's degree", "None", "None"],
        [],
        ["Footnotes:", None, None],
    ],
}


def gtfs_zip(stops, stop_times=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("stops.txt", "﻿stop_id,stop_name,stop_lat,stop_lon,location_type\n" +
                   "".join(f"{s[0]},{s[1]},{s[2]},{s[3]},{s[4] if len(s) > 4 else ''}\n" for s in stops))
        if stop_times is not None:
            z.writestr("stop_times.txt", "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n" +
                       "".join(f"t1,08:00:00,08:00:00,{sid},{i}\n" for i, sid in enumerate(stop_times)))
    return buf.getvalue()


@pytest.fixture
def tmpdata(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "SOC_CACHE", tmp_path / "soc-education.json")
    monkeypatch.setattr(R, "STOPS_CACHE", tmp_path / "ltd-stops.json")
    monkeypatch.setattr(R, "GEO_CACHE", tmp_path / "geocode-cache.json")
    monkeypatch.setattr(R, "EMPDB", tmp_path / "empdb-lane.json")
    return tmp_path


class Boom(Exception):
    pass


def no_network(monkeypatch):
    def fail(*a, **k):
        raise Boom("network blocked")
    monkeypatch.setattr(R.requests.Session, "get", fail)
    monkeypatch.setattr(R.requests, "post", fail)
    monkeypatch.setattr(R.requests, "get", fail)


# --- education table --------------------------------------------------------------------------

def test_parse_education_xlsx():
    levels = R.parse_education_xlsx(make_xlsx(EDU_SHEETS))
    assert levels["291141"] == "Bachelor's degree"
    assert levels["412031" if False else "412011"] == "No formal educational credential"
    assert levels["434051"] == "High school diploma or equivalent"  # inline string cell
    assert levels["319092"] == "Postsecondary nondegree award"
    assert levels["151252"] == "Bachelor's degree"                  # footnote marker stripped
    assert "000000" in levels and len(levels) == 7


def test_parse_education_xlsx_with_openpyxl():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Table 5.4"
    for row in EDU_SHEETS["Table 5.4"]:
        ws.append([v.lstrip("!") if isinstance(v, str) else v for v in row])
    buf = io.BytesIO()
    wb.save(buf)
    levels = R.parse_education_xlsx(buf.getvalue())
    assert levels["412011"] == "No formal educational credential" and len(levels) == 7


def test_no_degree_levels_and_lookup():
    assert R.NO_DEGREE_LEVELS == {"No formal educational credential", "High school diploma or equivalent"}
    levels = R.parse_education_xlsx(make_xlsx(EDU_SHEETS))
    assert R.no_degree("412011", levels) is True
    assert R.no_degree("434051", levels) is True
    assert R.no_degree("319092", levels) is False      # certificate: not "no degree"
    assert R.no_degree("291141", levels) is False
    assert R.no_degree("", levels) is None
    assert R.no_degree("999999", levels) is None
    assert R.education_level("151250", levels) == "Bachelor's degree"  # broad code, detailed codes agree


def test_soc_education_cache_and_failure(tmpdata, monkeypatch):
    no_network(monkeypatch)
    assert R.soc_education(log := []) == {} and "failed" in log[0]
    # stale cache is returned when the refresh fails
    R._write_json(R.SOC_CACHE, {"fetched": "2020-01-01", "levels": {"412011": "No formal educational credential"}})
    assert R.soc_education([]) == {"412011": "No formal educational credential"}


def test_soc_education_fresh_cache_skips_network(tmpdata, monkeypatch):
    no_network(monkeypatch)
    R._write_json(R.SOC_CACHE, {"fetched": dt.date.today().isoformat(), "levels": {"1": "x"}})
    log = []
    assert R.soc_education(log) == {"1": "x"} and log == []


def test_soc_education_refresh(tmpdata, monkeypatch):
    rows = [["Title", "2024 National Employment Matrix code", "Typical education needed for entry"]]
    rows += [[f"Occ {i}", f"{11 + i // 10000:02d}-{i % 10000:04d}", "High school diploma or equivalent"] for i in range(400)]
    data = make_xlsx({"Table 5.4": rows})

    class Resp:
        content = data
        def raise_for_status(self): pass

    seen = {}
    def get(self, url, **k):
        seen["ua"] = self.headers["User-Agent"]
        return Resp()
    monkeypatch.setattr(R.requests.Session, "get", get)
    levels = R.soc_education([])
    assert len(levels) == 400 and "matts@collaborativeedo.org" in seen["ua"]
    assert json.loads(R.SOC_CACHE.read_text())["fetched"] == dt.date.today().isoformat()


# --- names ------------------------------------------------------------------------------------

def test_norm_tokens():
    assert R.norm_tokens("The Glorybee Co., Inc.") == ("glorybee",)
    assert R.norm_tokens("Domino's") == ("dominos",)
    assert R.norm_tokens("Willamalane Park & Recreation") == ("willamalane", "park", "recreation")
    assert R.norm_tokens("U.S. Bank") == ("us", "bank")
    assert R.norm_tokens("NW Industrial Staffing Corp") == ("northwest", "industrial", "staffing")
    assert R.name_variants("EWEB (Eugene Water & Electric Board)") == [("eweb",), ("eugene", "water", "electric", "board")]


EMPDB = {
    "1": {"name": "Albertsons", "address": "1675 W 18th Ave", "city": "Eugene", "zip": "97402"},
    "2": {"name": "Albertsons", "address": "4740 Royal Ave", "city": "Eugene", "zip": "97402"},
    "3": {"name": "Albertsons", "address": "2000 Marcola Rd", "city": "Springfield", "zip": "97477"},
    "4": {"name": "Key Bank", "address": "1380 Coburg Rd", "city": "Eugene", "zip": "97401"},
    "5": {"name": "Securitas Inc", "address": "911 Country Club Rd # 350", "city": "Eugene", "zip": "97401"},
    "6": {"name": "Lane County Glass Inc", "address": "1369 W 6th Ave # 100", "city": "Eugene", "zip": "97402"},
    "7": {"name": "Willamalane Park & Recreation", "address": "200 S Mill St", "city": "Springfield", "zip": "97477"},
    "8": {"name": "Eugene Water & Electric Board", "address": "4200 Roosevelt Blvd", "city": "Eugene", "zip": "97402"},
    "9": {"name": "Peacehealth Sacred Heart Med", "address": "3333 Riverbend Dr", "city": "Springfield", "zip": "97477"},
    "10": {"name": "Peacehealth Medical Group", "address": "3311 Riverbend Dr", "city": "Springfield", "zip": "97477"},
    "11": {"name": "University of Oregon", "address": "130 Hendricks Hall", "city": "Eugene", "zip": "97403"},
    "12": {"name": "Sample Shop", "address": "PO Box 12", "city": "Eugene", "zip": "97440"},
}


def street_of(addrs):
    return sorted(v[0] for v in addrs.values())


def test_employer_matching():
    ix = R.EmployerIndex(EMPDB)
    assert street_of(ix.addresses("Albertsons", "Eugene")) == ["1675 W 18th Ave", "4740 Royal Ave"]
    assert street_of(ix.addresses("Albertsons", "Springfield")) == ["2000 Marcola Rd"]
    assert ix.addresses("Albertsons", "Florence") == {}                      # same city required
    assert street_of(ix.addresses("KeyBank", "Eugene")) == ["1380 Coburg Rd"]  # spaces ignored
    assert street_of(ix.addresses("Securitas Security Services", "eugene")) == ["911 Country Club Rd # 350"]
    assert street_of(ix.addresses("EWEB (Eugene Water & Electric Board)", "Eugene")) == ["4200 Roosevelt Blvd"]
    assert street_of(ix.addresses("Willamalane Park and Recreation District", "Springfield")) == ["200 S Mill St"]
    assert len(ix.addresses("PeaceHealth", "Springfield")) == 2               # name prefix
    assert ix.addresses("Lane County", "Eugene") == {}                        # no "Lane County Glass"
    assert street_of(ix.addresses("University of Oregon", "Eugene")) == ["130 Hendricks Hall"]  # geocoder decides
    assert ix.addresses("", "Eugene") == {} and ix.addresses("Sample Shop", "Eugene") == {}


def test_addr_key():
    assert R._addr_key("911 Country Club Rd # 350", "Eugene", "97401-1234") == "911 country club rd|eugene|97401"
    assert R._addr_key("1200 Hilyard St Ste 300", "Eugene", "") == "1200 hilyard st|eugene|"


# --- distance ---------------------------------------------------------------------------------

def test_haversine():
    # 0.001 degree of latitude is about 111 m
    assert abs(R.haversine_m(44.05, -123.09, 44.051, -123.09) - 111.2) < 1
    assert R.haversine_m(44.05, -123.09, 44.05, -123.09) == 0


def test_grid_nearest_and_cell_edges():
    stops = [{"name": "A", "lat": 44.0500, "lon": -123.0900}, {"name": "B", "lat": 44.1000, "lon": -123.2000}]
    g = R.StopGrid(stops)
    assert g.near(44.0530, -123.0900)            # ~334 m
    assert not g.near(44.0540, -123.0900)        # ~445 m
    assert g.nearest_m(44.3, -122.5) is None
    # neighbor cell: point just across a cell boundary from the stop
    g2 = R.StopGrid([{"name": "C", "lat": 44.0099, "lon": -123.0001}])
    assert g2.near(44.0101, -122.9999)
    # brute force agrees with the grid on a sweep of points
    pts = [(44.04 + i * 0.0007, -123.10 + k * 0.0009) for i in range(30) for k in range(30)]
    for lat, lon in pts:
        brute = min(R.haversine_m(lat, lon, s["lat"], s["lon"]) for s in stops)
        assert g.near(lat, lon) == (brute <= 400)


def test_parse_gtfs_stops_service_filter():
    data = gtfs_zip([("1", "5th & Pearl", 44.0521, -123.0868), ("2", "Unused", 44.06, -123.08),
                     ("3", "Station", 44.05, -123.09, 1), ("4", "Far away", 45.5, -122.6)], stop_times=["1", "4"])
    assert [s["name"] for s in R.parse_gtfs_stops(data)] == ["5th & Pearl"]
    data = gtfs_zip([("1", "A", 44.05, -123.08), ("2", "B", 44.06, -123.08)])
    assert len(R.parse_gtfs_stops(data)) == 2  # no stop_times.txt: keep all boardable stops


def test_parse_census_response():
    text = ('"0","1675 W 18th Ave, Eugene, OR, 97402","Match","Exact","1675 W 18TH AVE, EUGENE, OR, 97402",'
            '"-123.11653,44.03829","123","L"\n"1","1 Nowhere, Eugene, OR, 97402","No_Match"\n'
            '"2","2 Tie St, Eugene, OR","Tie"\n')
    assert R.parse_census_response(text) == {"0": (44.03829, -123.11653), "1": None, "2": None}


# --- near_bus rule ----------------------------------------------------------------------------

def test_near_bus_status_all_none_mixed():
    g = R.StopGrid([{"name": "S", "lat": 44.05, "lon": -123.09}])
    near, far = [44.0505, -123.09], [44.10, -123.09]
    cache = {"a": near, "b": near, "c": far, "d": far, "miss": "2026-10-01"}
    assert R.near_bus_status(["a", "b"], cache, g) is True
    assert R.near_bus_status(["c", "d"], cache, g) is False
    assert R.near_bus_status(["a", "c"], cache, g) is None
    assert R.near_bus_status(["a", "miss"], cache, g) is True    # unplaceable address ignored
    assert R.near_bus_status(["miss"], cache, g) is None
    assert R.near_bus_status(["a", "untried"], cache, g) is None  # not geocoded yet: unknown


def setup_world(tmpdata):
    R._write_json(R.EMPDB, EMPDB)
    R._write_json(R.STOPS_CACHE, {"fetched": dt.date.today().isoformat(),
                                  "stops": [{"name": "W 18th", "lat": 44.0385, "lon": -123.1165},
                                            {"name": "Mill", "lat": 44.0450, "lon": -123.0200}]})


def jobs_fixture():
    return [{"employer": "Albertsons", "city": "Eugene"},           # two stores: one near, one far -> unknown
            {"employer": "Albertsons", "city": "Springfield"},      # one store, far -> False
            {"employer": "Willamalane Park & Recreation", "city": "Springfield"},  # near -> True
            {"employer": "Nobody Known", "city": "Eugene"},         # no match -> unknown
            {"employer": "", "city": "Eugene"}]


COORDS = {"1675 w 18th ave|eugene|97402": (44.0383, -123.1165), "4740 royal ave|eugene|97402": (44.07, -123.17),
          "2000 marcola rd|springfield|97477": (44.07, -122.99), "200 s mill st|springfield|97477": (44.0452, -123.0201)}


def test_transit_tags_end_to_end(tmpdata, monkeypatch):
    setup_world(tmpdata)
    calls = []

    def fake_batch(rows, timeout=None):
        calls.append(len(rows))
        out = {}
        for rid, street, city, zip_ in rows:
            out[str(rid)] = COORDS.get(R._addr_key(street, city, zip_))
        return out
    monkeypatch.setattr(R, "census_batch", fake_batch)
    jobs = jobs_fixture()
    log = []
    R.transit_tags(jobs, log)
    assert [j.get("near_bus") for j in jobs] == [None, False, True, None, None]
    assert "near_bus" not in jobs[0] and len(log) == 1 and log[0].startswith("Bus-stop tags: 1 near, 1 not near")
    assert calls == [4]
    # warm cache: no new geocoding, same answers
    jobs = jobs_fixture()
    R.transit_tags(jobs, [])
    assert calls == [4] and [j.get("near_bus") for j in jobs] == [None, False, True, None, None]


def test_transit_tags_network_down(tmpdata, monkeypatch):
    no_network(monkeypatch)
    R._write_json(R.EMPDB, EMPDB)
    jobs = jobs_fixture()
    log = []
    R.transit_tags(jobs, log)  # no stop cache, no network
    assert all("near_bus" not in j for j in jobs) and "no LTD stop list" in log[-1]
    # stops cached but geocoder down: nothing tagged, nothing raised
    setup_world(tmpdata)
    log = []
    R.transit_tags(jobs, log)
    assert all("near_bus" not in j for j in jobs)
    assert any("Census geocoder failed" in m for m in log)


def test_transit_tags_never_raises(tmpdata, monkeypatch, capsys):
    setup_world(tmpdata)
    monkeypatch.setattr(R, "EmployerIndex", lambda *_: (_ for _ in ()).throw(RuntimeError("bad")))
    jobs = jobs_fixture()
    R.transit_tags(jobs)  # log=None prints instead
    assert all("near_bus" not in j for j in jobs)
    assert "Bus-stop tags failed" in capsys.readouterr().out


def test_ltd_stops_falls_back_to_second_url(tmpdata, monkeypatch):
    data = gtfs_zip([(str(i), f"S{i}", 44.0 + i * 0.0001, -123.1) for i in range(250)])

    class Resp:
        def __init__(self, ok):
            self.ok, self.content = ok, data
        def raise_for_status(self):
            if not self.ok:
                raise Boom("404")
    monkeypatch.setattr(R.requests.Session, "get", lambda self, url, **k: Resp(url == R.LTD_GTFS_URLS[1]))
    log = []
    assert len(R.ltd_stops(log)) == 250
    assert json.loads(R.STOPS_CACHE.read_text())["source"] == R.LTD_GTFS_URLS[1]


def test_geocode_miss_retry_and_cap(tmpdata):
    old = (dt.date.today() - dt.timedelta(days=61)).isoformat()
    recent = dt.date.today().isoformat()
    cache = {"a|eugene|": old, "b|eugene|": recent, "c|eugene|": [44.0, -123.0]}
    addrs = {k: (k.split("|")[0], "Eugene", "") for k in ["a|eugene|", "b|eugene|", "c|eugene|", "d|eugene|", "e|eugene|"]}
    sent = []

    def batch(rows, timeout=None):
        sent.extend(r[1] for r in rows)
        return {str(r[0]): None for r in rows}
    tried, matched = R.geocode(addrs, cache, [], cap=2, chunk=1, batch=batch)
    assert sent == ["a", "d"] and tried == 2 and matched == 0      # old miss retried, recent miss skipped, cap 2
    assert cache["a|eugene|"] == recent and "e|eugene|" not in cache
