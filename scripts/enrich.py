"""Details job seekers asked for: who is hiring, pay, full or part time, and the kind of workplace.

Everything here is read from the postings themselves or from public wage data; nothing is guessed
without a source. When a detail is not stated, it is left blank so the widget can say so.
"""
import html as _html
import json
import re

from bs4 import BeautifulSoup


def _clean(s):
    return re.sub(r"\s+", " ", _html.unescape(s or "")).strip()


# ---- Typical pay by occupation (from the wage boxes on QualityInfo's own result pages) ----------

def parse_wage_boxes(soup):
    """{soc: {"lane_hourly", "lane_annual", "or_hourly", "or_annual", "year"}} from QualityInfo's wage pop-ups."""
    out = {}
    for box in soup.select('[id^="wage"]'):
        soc = box.get("id", "")[4:]
        if not re.fullmatch(r"\d{6}", soc):
            continue
        rec = {}
        title = _clean(box.get_text(" "))
        m = re.search(r"\b(20\d\d) Wage", title)
        if m:
            rec["year"] = m.group(1)
        for tr in box.select("tr"):
            cells = [_clean(td.get_text()) for td in tr.find_all(["td", "th"])]
            if len(cells) < 3 or cells[0] not in ("Lane", "Oregon"):
                continue
            key = "lane" if cells[0] == "Lane" else "or"
            hourly = re.sub(r"[^\d.]", "", cells[1])
            annual = re.sub(r"[^\d.]", "", cells[2])
            if hourly:
                rec[f"{key}_hourly"] = float(hourly)
            if annual:
                rec[f"{key}_annual"] = float(annual)
        if rec.get("lane_hourly") or rec.get("lane_annual") or rec.get("or_hourly") or rec.get("or_annual"):
            out[soc] = rec
    return out


def typical_pay(soc, wages):
    """Text like 'Average for this occupation in Lane County: $28.54 an hour', or ''."""
    w = wages.get(soc or "")
    if not w:
        return ""
    for key, where in (("lane", "Lane County"), ("or", "Oregon")):
        h, a = w.get(f"{key}_hourly"), w.get(f"{key}_annual")
        if h:
            return f"Average for this occupation in {where}: ${h:,.2f} an hour"
        if a:
            return f"Average for this occupation in {where}: ${a:,.0f} a year"
    return ""


# ---- Pay stated in the posting ----------------------------------------------------------------

_MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?\s*([kK])?"
_PAY = re.compile(_MONEY + r"(?:\s*(?:-|–|—|to)\s*" + _MONEY + r")?"
                  r"(?:\s*(?:per|an|a|/)\s*(hour|hr|year|yr|annually|annual|month|mo|week)\b|\s*(hourly|annually|yearly|monthly)\b)?",
                  re.I)
_NOT_PAY = re.compile(r"bonus|sign[- ]?on|tuition|reimburse|stipend|referral|allowance|401|deductible|budget|revenue|"
                      r"sales of|million|billion|fee\b|deposit|award", re.I)


def _num(whole, cents, k):
    v = float(whole.replace(",", "") + ("." + cents if cents else ""))
    return v * 1000 if k else v


def posted_pay(text):
    """Pay range stated in a posting, as 'From $18.00 to $22.00 an hour' style text, or ''."""
    for m in _PAY.finditer(text or ""):
        around = text[max(0, m.start() - 30): m.end() + 12]
        if _NOT_PAY.search(around):
            continue
        lo = _num(m.group(1), m.group(2), m.group(3))
        hi = _num(m.group(4), m.group(5), m.group(6)) if m.group(4) else None
        unit = (m.group(7) or m.group(8) or "").lower()
        if not unit:
            if not re.search(r"pay|wage|salary|compensation|rate|earn", around, re.I):
                continue
            unit = "hour" if lo < 200 else ("year" if lo >= 20000 else "")
        unit = {"hr": "hour", "hourly": "hour", "yr": "year", "annually": "year", "annual": "year", "yearly": "year",
                "mo": "month", "monthly": "month"}.get(unit, unit)
        if not unit or lo <= 0:
            continue
        if unit == "hour" and not 7 <= lo <= 300:
            continue
        if unit == "year" and not 10000 <= lo <= 1000000:
            continue
        fmt = (lambda v: f"${v:,.2f}") if unit in ("hour",) else (lambda v: f"${v:,.0f}")
        if hi and hi > lo:
            return f"{fmt(lo)} to {fmt(hi)} a{'n' if unit == 'hour' else ''} {unit}"
        return f"{fmt(lo)} a{'n' if unit == 'hour' else ''} {unit}"
    return ""


# ---- Full time or part time -------------------------------------------------------------------

def job_hours(*texts):
    """'Full-time', 'Part-time', 'Temporary or seasonal', or '' when the posting does not say."""
    t = " ".join(x for x in texts if x)
    if re.search(r"\b(seasonal|temporary|temp\b|summer (job|help|position)|holiday help|limited duration|short[- ]term)", t, re.I):
        return "Temporary or seasonal"
    ft = re.search(r"\bfull[- ]?time\b|\bFT\b", t, re.I)
    pt = re.search(r"\bpart[- ]?time\b|\bPT\b|\bper diem\b|\bPRN\b|\bon[- ]call\b|\bcasual\b", t, re.I)
    if ft and not pt:
        return "Full-time"
    if pt and not ft:
        return "Part-time"
    if ft and pt:
        return "Full-time" if ft.start() < pt.start() else "Part-time"
    return ""


# ---- Employer named in the posting text -------------------------------------------------------

_STOP = set("""This The Our We You Your Position Job Company Candidate Candidates Applicant Applicants Successful
Individual It That These Those Each All Must Duties Responsibilities Summary Description Employer Location Eugene
Springfield Oregon Lane Full Part Seasonal Hiring Now Are Do If As In For With Apply Pay Benefits Shift Hours
Training Experience Requirements Qualifications Paid New Every Work Team Staff Employees Here There Who What Why
How When Where Join Help Looking Seeking Must Please Note Additional Starting Salary Wage Compensation Schedule
Overview About Purpose Essential Primary General Under Under Today Monday Tuesday Wednesday Thursday Friday
Saturday Sunday Day Night Store Location Department Program Project Role Opportunity Opening Openings
Entry Senior Junior School Local District Public Private Retail Health Care Lead Manager Supervisor Associate Specialist Technician Assistant Coordinator Director""".split())
_NAME = r"([A-Z][A-Za-z0-9&'’.\-]+(?:\s+(?:[A-Z][A-Za-z0-9&'’.\-]+|of|and|&|the)){0,5})"
_PATTERNS = [
    re.compile(r"(?:^|[.!?]\s+|\n)(?:About\s+)?" + _NAME + r"\s+(?:is|has|was|are|provides|offers|operates|serves|specializes)\s+"
               r"(?:a|an|the|one|seeking|hiring|looking|currently|proud|committed|dedicated|now|decades|over|more|been)\b"),
    re.compile(r"\b[Jj]oin\s+(?:the\s+)?" + _NAME + r"\s+(?:team|family)\b"),
    re.compile(r"\b[Aa]t\s+" + _NAME + r",\s+(?:we|our)\b"),
    re.compile(_NAME + r"\s+is an?\s+(?:equal opportunity|EEO|drug[- ]free)"),
]


def employer_from_text(text):
    for rx in _PATTERNS:
        for m in rx.finditer(text or ""):
            name = m.group(1).strip(" .,'’-")
            name = re.sub(r"\s+(of|and|&|the)$", "", name)
            first = name.split()[0]
            if first in _STOP or name.upper() == name or len(name) < 3 or len(name.split()) > 6:
                continue
            return name
    return ""


# ---- Where you'd work (the kind of workplace) ----------------------------------------------------

WORKPLACES = ["Healthcare", "Education & childcare", "Government", "Retail", "Restaurants & hospitality",
              "Banking & finance", "Manufacturing", "Construction & trades", "Transportation & logistics",
              "Automotive", "Wood products & forestry", "Food & beverage", "Bioscience", "Nonprofit & social services",
              "Technology", "Real estate & property", "Engineering & professional services", "Staffing agency"]

_FROM_RULES = {"Retail": "Retail", "Healthcare": "Healthcare", "Hospitality & leisure": "Restaurants & hospitality",
               "Transportation & logistics": "Transportation & logistics", "Public sector": "Government",
               "Finance": "Banking & finance", "Nonprofit": "Nonprofit & social services",
               "Staffing agency": "Staffing agency", "Manufacturing": "Manufacturing",
               "Construction & trades": "Construction & trades", "Food & beverage": "Food & beverage",
               "Real estate": "Real estate & property", "Human services": "Nonprofit & social services",
               "Wood products & forestry": "Wood products & forestry", "Bioscience & medical devices": "Bioscience",
               "Engineering services": "Engineering & professional services", "Technology": "Technology",
               "Childcare": "Education & childcare"}
_FROM_TEXT = {"Public sector": "Government", "Nonprofit": "Nonprofit & social services", "Bioscience": "Bioscience",
              "Wood products & forestry": "Wood products & forestry", "Food & beverage": "Food & beverage"}
_NAME_RULES = [
    ("Healthcare", r"hospital|medical|health|clinic|dental|dentist|pharmac|care center|rehab|hospice|physical therapy|"
                   r"oncology|cancer|surgery|surgical|orthop|pediatric|nursing|senior living|assisted living|memory care|"
                   r"retirement|davita|peacehealth|mckenzie|kaiser|optum|unitedhealth|one medical|vision|eye care|"
                   r"veterinar|animal hospital|vetcor"),
    ("Education & childcare", r"school|college|university|academy|kindercare|learning|child ?care|preschool|head start|"
                              r"\b4j\b|education"),
    ("Government", r"^city of|county|^state of|federal|usajobs|utility board|water (&|and) electric|\beweb\b|"
                   r"\bltd\b|lane transit|district|authority|department of|police|fire (and|&) rescue|government"),
    ("Banking & finance", r"bank|credit union|financial|insurance|progressive|umpqua|mortgage|tax|accounting|cpa|baker tilly"),
    ("Restaurants & hospitality", r"restaurant|pizza|coffee|grill|taco|wendy|domino|burger|cafe|café|\bbar\b|hotel|"
                                  r"\binn\b|resort|casino|starbucks|mcdonald|subway|dutch bros|chipotle|kitchen|brewpub"),
    ("Automotive", r"\bauto|motors|tire|nissan|toyota|honda|ford|chevrolet|lithia|kendall|o'?reilly|napa|autozone|"
                   r"car wash|les schwab|collision|body shop"),
    ("Staffing agency", r"staffing|labor ready|express employment|robert half|judge group|manpower|adecco|kelly services|"
                        r"randstad|tradesmen international|procare therapy|maxim"),
    ("Food & beverage", r"\bfoods?\b|bakery|brewing|brewery|beverage|winery|farms?\b|creamery|dairy"),
    ("Wood products & forestry", r"lumber|\bwood|forest|timber|plywood|\bmill\b|sierra pacific|weyerhaeuser|seneca|roseburg"),
    ("Construction & trades", r"construction|builders|electric\b|electrical|plumbing|roofing|hvac|contractor|excavat|"
                              r"paving|asplundh|peterson cat|rdo equipment"),
    ("Transportation & logistics", r"trucking|freight|logistics|transport|\bups\b|fedex|u-haul|airport|airline|"
                                   r"first student|moving|courier|unifi"),
    ("Retail", r"store|market|mart\b|walgreens|target|safeway|albertsons|fred meyer|kroger|winco|home depot|lowe'?s|"
               r"bi-mart|petco|guitar center|dick'?s|bass pro|camping world|gap inc|h&m|boxlunch|claire'?s|"
               r"spencer|lovisa|duluth|circle k|wireless|t-mobile|verizon|cvs|rite aid|costco|walmart|ross|tj ?maxx"),
    ("Technology", r"software|technolog|\btech\b|data|digital|networks?|systems\b|cyber"),
    ("Real estate & property", r"properties|property|realty|apartments|greystar|real estate|housing"),
    ("Engineering & professional services", r"engineer|consult|\bllp\b|law|legal|architect|dowl|cdm smith|"
                                            r"planning|surveying"),
    ("Nonprofit & social services", r"nonprofit|foundation|ministr|church|salvation army|goodwill|st\.? vincent|"
                                    r"united way|ymca|boys (&|and) girls|services for|catholic|clarvida|looking glass"),
]
_NAME_RULES = [(n, re.compile(p, re.I)) for n, p in _NAME_RULES]


def workplaces(employer, employer_industry, text_industries):
    """Kinds of workplace for a posting, from its employer and the posting text. Empty when unknown."""
    out = []
    if employer_industry in _FROM_RULES:
        out.append(_FROM_RULES[employer_industry])
    if employer and not out:
        for name, rx in _NAME_RULES:
            if rx.search(employer):
                out.append(name)
                break
    for i in text_industries or []:
        w = _FROM_TEXT.get(i)
        if w and w not in out:
            out.append(w)
    return out


# ---- WorkSource Oregon listing pages ------------------------------------------------------------

def oed_ord(url):
    m = re.search(r"[?&]ord=(\d+)", url or "")
    return m.group(1) if m else ""


def parse_oed_page(page_html):
    """Fields shown on a WorkSource Oregon listing before its contact-information question."""
    soup = BeautifulSoup(page_html, "html.parser")
    text = soup.get_text("\n")
    text = re.sub(r"[ \t]+", " ", text)

    def field(label):
        m = re.search(label + r"\s*:?\s*\n?\s*([^\n]+)", text, re.I)
        return _clean(m.group(1)) if m else ""

    desc = ""
    i = text.find("Job Summary")
    if i >= 0:
        j = text.find("Access our Statewide", i)
        desc = _clean(text[i + len("Job Summary"): j if j > 0 else i + 6000])
    return {"duration": field(r"Duration of Job"), "hours_week": field(r"Hours Worked Per Week"),
            "wage": field(r"(?:Wage|Salary|Pay Rate|Rate of Pay)(?: Range)?"), "description": desc[:5000]}


def oed_hours(rec):
    d = (rec.get("duration") or "").lower()
    if "full" in d:
        return "Full-time"
    if "part" in d:
        return "Part-time"
    if "temp" in d or "season" in d or "less than" in d:
        return "Temporary or seasonal"
    try:
        h = float(re.sub(r"[^\d.]", "", rec.get("hours_week") or "") or 0)
    except ValueError:
        h = 0
    if h >= 35:
        return "Full-time"
    if 0 < h < 30:
        return "Part-time"
    return ""
