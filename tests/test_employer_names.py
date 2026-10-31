import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import enrich  # noqa: E402


def test_job_site_summary():
    t = "Kiosk Operator Lane Forest Products - 3.9 Eugene, OR Job Details Full-time"
    assert enrich.employer_from_text(t, "Kiosk Operators") == "Lane Forest Products"
    t = "Document Control Specialist-Eugene Airport Road Astec Industries - 2.9 Eugene, OR Job"
    assert enrich.employer_from_text(t, "Document Control Specialists") == "Astec Industries"


def test_seeking_and_partnering():
    assert enrich.employer_from_text("Requisition Number: 1 Job Description Cintas is seeking a Route") == "Cintas"
    assert enrich.employer_from_text("Description Bridget Killen from Robert Half is partnering with") == "Robert Half"


def test_not_employers():
    assert enrich.clean_employer("WorkSource Oregon") == ""


def test_display_title_drops_reference_numbers():
    cases = {"{1823} Trailer Fabricator and Assembly": "Trailer Fabricator and Assembly",
             "842753 Field Laborer": "Field Laborer",
             "Wireless Retail Sales Associate - W3258": "Wireless Retail Sales Associate",
             "Residential Care Associate II-5858": "Residential Care Associate II",
             "Tire Technician - Eugene East #254": "Tire Technician - Eugene East",
             "barista - Store# 81322, HWY 101 & 20TH ST - FLORENCE": "barista - HWY 101 & 20TH ST - FLORENCE",
             "$19.90/HR Team Member Dave's Hot Chicken (1047)": "$19.90/HR Team Member Dave's Hot Chicken"}
    for raw, want in cases.items():
        assert enrich.display_title(raw) == want
    for keep in ["CNA - PT Nights- 8 Hours 1500-2300", "Survey Internship - Summer 2027",
                 "Food Service Assistant 1 Pool 2026-27", "911 Call-Taker/Dispatcher", "Pipe Fitter #2"]:
        assert enrich.display_title(keep) == keep


def test_fair_chance_wording():
    yes = ["People with lived experience with incarceration or the justice system are encouraged to apply.",
           "A criminal record does not automatically disqualify you.", "We are a fair chance employer.",
           "We will consider qualified applicants with criminal histories."]
    no = ["People with lived experience are encouraged to apply.",
          "We encourage people with lived experience of recovery to apply.", "Must pass a criminal background check."]
    assert all(enrich.text_flags(t)["fair_chance"] for t in yes)
    assert not any(enrich.text_flags(t)["fair_chance"] for t in no)


def test_onet_titles():
    if not enrich.onet().get("titles"):
        return  # data/onet.json not built in this checkout
    assert enrich.onet_soc("Dishwasher") == "359021"
    assert enrich.onet_soc("Certified Veterinary Technician") == "292056"
    assert enrich.onet_soc("Customer Service Associate") == ""
    assert enrich.rule_soc("Sterile Processing Tech") == "319093"
    assert enrich.onet_soc("Director") == ""
    assert enrich.onet_soc("Head Chef") == "351011"
