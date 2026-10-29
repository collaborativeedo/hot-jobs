"""Harvest Lane County employers (name, town, industry, website) from QualityInfo's Employer Database.

QualityInfo licenses this list from Data Axle. Contact names and phone numbers are not kept.
Resumable: data/empdb-lane.json keeps what has been read, so a run that stops early picks up where it left off.

    python scripts/empdb.py --list            # read the list pages (IDs, names, towns, business type)
    python scripts/empdb.py --details 6000    # read up to N employer detail records (websites)
"""
import argparse
import json
import re
import sys
import time
from html import unescape
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "empdb-lane.json"
PAGE = "https://www.qualityinfo.org/empdb"
RES = (PAGE + "?p_p_id=QiDatatoolEmpdb_INSTANCE_MOvhE5SqO3XC&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view"
       "&p_p_cacheability=cacheLevelPage&p_p_resource_id=")
UA = "LaneCountyHotJobs/1.0 (+https://collaborativeedo.github.io/hot-jobs/; job listings for Lane Workforce Partnership)"
LIST = dict(rpth="0", em_empdbState="41", em_empdbStateDesc="Oregon", em_empdbAreacode="4104000039",
            em_empdbAreacodeDesc="Lane County", em_SearchType="0", em_SearchTerm="", em_Indcode="", em_Indname="",
            em_Address="", em_City="", em_Zipcode="", em_SortField="name", em_SortOrder="asc")
KEEP = {"Employer Name": "name", "Address": "address", "City": "city", "Zipcode": "zip", "Web Address": "web",
        "Business Type": "business", "NAICS Code": "naics"}


def text(html):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def post(s, rid, data, tries=4):
    for i in range(tries):
        try:
            r = s.post(RES + rid, data=data, timeout=40)
            if r.status_code == 200 and r.text.strip():
                return r.text
        except requests.RequestException:
            pass
        time.sleep(3 * (i + 1))
    return ""


def read_list(s, db):
    start, total = 1, None
    while total is None or start <= total:
        html = post(s, "getReportHtml", dict(LIST, em_StartRec=str(start)))
        if not html:
            print(f"list page at {start} failed; stopping")
            break
        if total is None:
            m = re.search(r'id="empdbtotal"[^>]*value="(\d+)"|value="(\d+)"[^>]*id="empdbtotal"', html)
            total = int(next(g for g in m.groups() if g)) if m else 0
            print(f"QualityInfo lists {total} Lane County employers")
        for row in re.split(r"<tr[^>]*>", html):
            m = re.search(r'id="empuniqueid(\d+)"', row)
            if not m:
                continue
            cells = [text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)][:5]
            rec = db.setdefault(m.group(1), {})
            rec.update({k: v for k, v in zip(("name", "address", "city", "zip", "business"), cells) if v})
        start += 25
        time.sleep(0.4)
    return total


def read_details(s, db, limit):
    todo = [k for k, v in db.items() if "web" not in v and not v.get("detail_failed")]
    print(f"{len(todo)} employers still need detail records; reading up to {limit}")
    done = 0
    for uid in todo[:limit]:
        html = post(s, "getReportDetail", {"rpth": "1", "uniqueid": uid})
        rec = db[uid]
        if not html:
            rec["detail_failed"] = True
            continue
        t = text(html)
        labels = "|".join(map(re.escape, ["Employer Name", "Address", "City", "State", "Zipcode", "Web Address",
                                          "Business Type", "NAICS Code", "Contact", "Telephone", "Close"]))
        for lab, val in re.findall(rf"({labels}):\s*(.*?)(?=\s(?:{labels}):|\sClose\b|$)", t):
            if lab in KEEP and val:
                rec[KEEP[lab]] = val.strip()
        rec.setdefault("web", "")
        done += 1
        if done % 500 == 0:
            save(db)
            print(f"  {done} read")
        time.sleep(0.25)
    return done


def save(db):
    OUT.write_text(json.dumps(db, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--details", type=int, default=0)
    a = ap.parse_args()
    db = json.loads(OUT.read_text()) if OUT.exists() else {}
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    s.get(PAGE, timeout=40)  # session cookie
    if a.list:
        read_list(s, db)
        save(db)
    if a.details:
        read_details(s, db, a.details)
        save(db)
    have = sum(1 for v in db.values() if "web" in v)
    print(f"{len(db)} employers on file; {have} with detail read; {sum(1 for v in db.values() if v.get('web'))} list a website")
    return 0


if __name__ == "__main__":
    sys.exit(main())
