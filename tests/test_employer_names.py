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
