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
    # Job-site summaries: "Buckle - 3.6 Eugene, OR", "Avenue5 Residential, LLC - 3.0 Eugene, OR"
    re.compile(_NAME + r"(?:,? (?:LLC|Inc\.?|L\.L\.C\.))?\s+-\s+\d\.\d\s+[A-Z][a-z]+(?: [A-Z][a-z]+)?,\s+OR\b"),
    re.compile(r"\b(?:Description|Summary|Overview)\s+" + _NAME + r"\s+is\s+(?:seeking|hiring|recruiting|looking|immediately)\b"),
    re.compile(r"\b[Ff]rom\s+" + _NAME + r"\s+is\s+partnering\b"),
    re.compile(r"\b[Ee]xplore (?:opportunities|careers) (?:with|at)\s+" + _NAME + r"(?=[,.\s])"),
    re.compile(r"(?:^|[.!?]\s+)" + _NAME + r"\s+is\s+(?:recruiting|immediately hiring)\b"),
]


_LEAD_JUNK = re.compile(r"^(?:(?:click here|eeoc? statement|equal employment opportunity|job description|"
                        r"talentmatch|about us|company overview|who we are)\s+)+", re.I)
_TRAIL_JUNK = {"Sales", "Associates", "Associate", "Corporation", "Corp", "Inc", "LLC", "Ltd", "Co", "Company", "This", "The"}
_BAD_NAMES = {"Inc", "LLC", "Posted", "Schools", "Workplace", "Click", "EEO", "EEOC", "Equal", "Job", "Company", "Corporation"}


def _tidy_name(name):
    name = re.split(r"(?<=\w{3})\. ", name)[0]
    name = _LEAD_JUNK.sub("", name.strip(" .,'’-"))
    words = name.replace(",", "").split()
    caps = 0
    while caps < len(words) and words[caps].isupper() and len(words[caps]) > 1:
        caps += 1
    if 2 <= caps < len(words):
        words = words[caps:]   # a heading run: "ABOUT SHELTERCARE ShelterCare" -> "ShelterCare"
    half = len(words) // 2
    if half and len(words) % 2 == 0 and words[:half] == words[half:]:
        words = words[:half]   # "AIC Insurance Agency AIC Insurance Agency"
    while len(words) > 1 and words[-1].strip(".") in _TRAIL_JUNK:
        words.pop()
    return " ".join(words).strip(" .,'’-")


# ---- Final check on every employer name, whatever produced it -------------------------------------

_WRAP_LEAD = re.compile(r"^(?:(?i:careers? at|open jobs at|jobs at|work at|working at|join|learn about)|Us)\s+")
_WRAP_TRAIL = re.compile(r"\s+(?:(?i:and explore our.*|careers?|jobs|job openings)|We|Us)$")
_BAD_FIRST = {"We", "You", "Our", "Your", "This", "These", "Who", "What", "Apply", "Click", "Position", "Job", "Where",
              "Seeking", "Join", "About"}
_HEADING = re.compile(r"\b(?:DESCRIPTION|TITLE|EOE|STATEMENT|SUMMARY|POSITION|OVERVIEW|REQUIREMENTS)\b")
_CODE = re.compile(r"[A-Za-z]\d{3,}|\d{3,}[A-Za-z]")          # hiring-system tenant codes: "Mcm1001Mcmen"
_ROLE = re.compile(r"\b(?:wanted|representative|caregiver|dispatcher|driver|technician|assistant|specialist|"
                   r"coordinator|manager|nurse|housekeeper|cashier|clerk)s?\b", re.I)
_NOT_EMPLOYERS = {n.lower() for n in """Adoption Client Clients Collaboration Others Other They Weekends Sponsors Policy
Florence Eugene Springfield Oregon Finance Research Workplace Dayforce GetHired.com Ghr Prt Sparinc Myoccu
Indeed SimplyHired ZipRecruiter LinkedIn Glassdoor Monster Workday Paylocity Paychex iCIMS UKG""".split()} | {
    "worksource oregon", "oregon employment department", "national labor exchange",
    "finance and administration", "research administration", "workplace type", "human resources", "talent acquisition",
    "who we are", "about us", "our company", "equal opportunity employer"}


def clean_employer(name):
    """Return a usable employer name, or "" when the text is a fragment, heading, code or job title."""
    name = re.sub(r"\s+", " ", (name or "")).strip(" ,;:'’-")
    if not name:
        return ""
    for _ in range(2):
        name = _WRAP_TRAIL.sub("", _WRAP_LEAD.sub("", name)).strip(" ,;:'’-")
    words = name.split()
    words = [w for i, w in enumerate(words) if i == 0 or w.lower() != words[i - 1].lower()]   # "Bethel Bethel Schools"
    name = " ".join(words)
    if (len(name) < 3 or name.lower() in _NOT_EMPLOYERS or _HEADING.search(name) or _CODE.search(name)
            or (_ROLE.search(name) and not re.search(r"\b(?:inc|llc|group|company|services|staffing)\b", name, re.I))
            or len(words) > 7 or words[0] in _BAD_FIRST):
        return ""
    return name


_KNOWN_RX = None


def employer_from_known(text, names):
    """An employer from our registry named word for word in the posting text (case-sensitive, longest first)."""
    global _KNOWN_RX
    if _KNOWN_RX is None:
        good = {n for n in (clean_employer(x) for x in names)
                if n and len(n) >= 5 and n not in _BAD_NAMES and n.split()[0] not in _STOP
                and (len(n.split()) > 1 or len(n) >= 6) and n.lower() not in _COMMON_WORDS}
        _KNOWN_RX = re.compile(r"(?<![\w&'-])(" + "|".join(re.escape(n) for n in sorted(good, key=len, reverse=True))
                               + r")(?![\w&'-])") if good else re.compile(r"(?!)")
    m = _KNOWN_RX.search(text or "")
    return m.group(1) if m else ""


_COMMON_WORDS = {"afscme", "seiu", "teamsters", "oregon nurses association", "general", "services", "service", "health", "careers", "community", "medical", "industries",
                 "solutions", "partners", "systems", "management", "construction", "academy", "options", "pathways"}


def employer_from_text(text, title=""):
    tw = {w[:5] for w in re.findall(r"[a-z]+", (title or "").lower()) if len(w) > 2}
    for rx in _PATTERNS:
        for m in rx.finditer(text or ""):
            name = _tidy_name(m.group(1))
            words = name.split()
            while len(words) > 1 and words[0].lower()[:5] in tw:   # "Kiosk Operator Lane Forest Products"
                words = words[1:]
            name = " ".join(words)
            name = re.sub(r"^.*?\b(?:Road|Rd|Street|St|Avenue|Ave|Highway|Hwy|Blvd)\s+(?=[A-Z])", "", name)  # "Airport Road Astec"
            name = re.sub(r"\s+(of|and|&|the)$", "", name)
            if not name:
                continue
            first = name.split()[0]
            if ((first in _STOP and not (first in ("Lane", "Eugene", "Springfield", "Oregon") and len(name.split()) >= 3))
                    or name in _BAD_NAMES or name.upper() == name or len(name) < 3
                    or len(name.split()) > 6):
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


# Lane County technology employers (hand-checked): software, games, cybersecurity, IT services, semiconductors.
TECH_EMPLOYERS = {"pipeworks studios", "pipeworks", "zynga", "palo alto software", "sheerid", "lone wolf technologies",
                  "lone wolf technologies (idx broker)", "idx broker", "frontsteps", "air-weigh", "cbt nuggets",
                  "avant assessment", "trifoia", "ksana health", "cognitopia", "ieq technology", "twenty ideas",
                  "emberex", "stepup it services", "sentinelone", "intel", "strata information group",
                  "technology integration group", "mld technologies"}


def workplaces(employer, employer_industry, text_industries):
    """Kinds of workplace for a posting, from its employer and the posting text. Empty when unknown."""
    out = ["Technology"] if (employer or "").strip().lower() in TECH_EMPLOYERS else []
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


# ---- Occupation code for a job title, from titles QualityInfo has already coded -------------------------

_TITLE_NOISE = re.compile(r"\([^)]*\)|\[[^\]]*\]|\s[-|–—:]\s.*$|\b(part[- ]?time|full[- ]?time|per[- ]?diem|prn|temporary|temp|"
                          r"seasonal|remote|hybrid|on[- ]?call|w/.*|with .*bonus|sign[- ]?on.*|\$[\d,.]+.*|"
                          r"i{1,3}|iv|1|2|3)\b", re.I)


def norm_title(t):
    t = _TITLE_NOISE.sub(" ", (t or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# High-confidence title words -> 2018 SOC code. Checked in order; first match wins. Used only when coded titles miss.
_TITLE_SOC = [(re.compile(p, re.I), c) for p, c in [
    (r"\bprep cook|food prep", "352021"), (r"\b(line |grill |kitchen )?cook\b", "352014"), (r"dishwasher", "359021"),
    (r"bartender", "353011"), (r"\bbarista|crew member|team member.*(restaurant|cafe)|counter (staff|worker)", "353023"),
    (r"^(?!.*\b(sql|data|web|network|systems?|it|cloud|windows|linux|application)\b).*\bserver\b|waitstaff|waitress|waiter", "353031"),
    (r"^(?!.*\b(web|server|sql|cloud|network)\b).*\bhost(ess)?\b", "359031"),
    (r"cashier", "412011"), (r"(retail )?sales associate|sales floor", "412031"), (r"stocker|stock associate|overnight stock", "537065"),
    (r"housekeep", "372012"), (r"janitor|custodian|custodial", "372011"), (r"groundskeep|landscap", "373011"),
    (r"\b(cna|certified nursing assistant|nursing assistant)\b", "311131"),
    (r"caregiver|home care aide|personal care (aide|assistant)|direct support professional|\bdsp\b", "311122"),
    (r"\b(registered nurse|rn)\b", "291141"), (r"\b(lpn|licensed practical nurse)\b", "292061"),
    (r"medical assistant", "319092"), (r"dental hygienist", "292021"), (r"dental assistant", "319091"),
    (r"pharmacy tech", "292052"), (r"community health worker|\bchw\b", "211094"),
    (r"behavioral health clinician|mental health (therapist|counselor|clinician)|\b(lpc|lcsw|qmhp)\b", "211018"),
    (r"patient (support|access|services) (specialist|representative)|medical receptionist|front desk|receptionist", "434171"),
    (r"customer service (rep|representative|associate|specialist)|call center", "434051"),
    (r"administrative assistant|office assistant", "436014"), (r"bookkeep", "433031"), (r"\baccountant\b", "132011"),
    (r"software (engineer|developer)|web developer|full[- ]stack", "151252"), (r"help ?desk|it support|desktop support", "151232"),
    (r"security (officer|guard)", "339032"), (r"\bcdl\b|truck driver|tractor[- ]trailer", "533032"),
    (r"delivery driver|courier", "533033"), (r"forklift", "537051"),
    (r"warehouse (associate|worker)|material handler|order picker|picker|packer", "537062"),
    (r"welder|welding", "514121"), (r"electrician", "472111"), (r"plumber", "472152"), (r"\bhvac", "499021"),
    (r"diesel (tech|mechanic)", "493031"), (r"auto(motive)? (tech|technician|mechanic)|lube tech", "493023"),
    (r"carpenter", "472031"), (r"construction laborer|general laborer", "472061"),
    (r"maintenance (tech|technician|worker|mechanic)", "499071"),
    (r"paraeducator|instructional assistant|teaching assistant|educational assistant", "259042"),
    (r"preschool teacher", "252011"), (r"child ?care (worker|provider|teacher|assistant)|daycare", "399011"),
    # Titles common on employers' own hiring sites (added Oct 29, 2026)
    (r"\b(nurse practitioner|np|fnp|pmhnp|arnp)\b", "291171"), (r"physician assistant|\bpa-?c\b", "291071"),
    (r"family (medicine|practice) physician|primary care physician", "291215"), (r"\bphysician\b|\bhospitalist\b", "291229"),
    (r"physical therapist assistant", "312021"), (r"physical therapist", "291123"),
    (r"occupational therapist", "291122"), (r"speech[- ]language|speech therapist", "291127"),
    (r"\bpharmacist\b", "291051"), (r"phlebotom", "319097"), (r"\bmls\b|medical laboratory scientist|medical technologist", "292011"),
    (r"\bmlt\b|medical laboratory technician|lab(oratory)? (assistant|technician)", "292012"),
    (r"veterinary technician|vet tech", "292056"), (r"veterinary assistant|kennel", "319096"),
    (r"(clinical|licensed|mental health|behavioral health|family|addiction|substance use) (therapist|counselor)|\btherapist\b", "211018"),
    (r"case manager|care coordinator|peer support|resource navigator", "211093"),
    (r"\b(licensed )?(registered )?nurse\b(?!.*(practitioner|assistant|aide))", "291141"),
    (r"superintendent|construction manager", "119021"), (r"foreman|forewoman|foreperson|crew (lead|leader|supervisor)", "471011"),
    (r"estimator", "131051"), (r"project engineer|civil engineer", "172051"), (r"mechanical engineer", "172141"),
    (r"electrical engineer", "172071"), (r"journeyman.*electric|electrical apprentice|inside wireman", "472111"),
    (r"pest control|home services technician|termite", "372021"),
    (r"personal trainer|fitness (instructor|coach)|group exercise|water fitness|swim instructor|tumbling|yoga instructor", "399031"),
    (r"lifeguard", "339092"), (r"\bcoach\b", "272022"),
    (r"activity leader|program leader|recreation (leader|aide|assistant)|youth (program|activity)", "399032"),
    (r"assistant teacher|teacher'?s? (aide|assistant)", "259042"), (r"childcare|child care", "399011"),
    (r"\b(adjunct|instructor pool|faculty)\b", "251199"),
    (r"(assistant )?store manager|shift (lead|leader|supervisor)|retail (supervisor|manager)", "411011"),
    (r"\bgeneral manager\b", "111021"),
    (r"logistics manager|warehouse manager|distribution manager", "113071"), (r"\bbuyer\b|purchasing (agent|specialist)", "131023"),
    (r"sourcing manager|purchasing manager|procurement manager", "113061"),
    (r"receiving supervisor|warehouse supervisor|shipping supervisor", "531047"),
    (r"business development|account (manager|executive)|sales (representative|rep|consultant|development)|outside sales|inside sales", "414012"),
    (r"accounts (receivable|payable)|billing (specialist|clerk)|payroll", "433031"),
    (r"(office|administrative|facilities) (coordinator|manager)|office manager", "431011"),
    (r"client success|customer success|customer support", "434051"),
    (r"marketing (manager|director)|director.*marketing", "112021"), (r"marketing (coordinator|specialist)", "131161"),
    (r"human resources (manager|director)|\bhr (manager|director)", "113121"),
    (r"human resources|\bhr (generalist|specialist|coordinator|assistant)|recruiter", "131071"),
    (r"\bui\b|\bux\b|user experience|user interface|interaction designer|product designer", "151255"),
    (r"game (designer|developer|producer|artist)|level designer|technical artist", "151255"),
    (r"project manager", "131082"), (r"data analyst|business analyst", "152051"),
    (r"machine operator|production (worker|associate|operator)|blending operator|assembler", "519199"),
    (r"industrial clean|cleaning tech", "372019"), (r"\blaborer\b", "472061"),
]]


def soc_for_title(title, title_soc):
    """Exact title match first, then the same title without schedule/bonus/level words, then the longest coded title
    contained in this one ("Medical Assistant - Pediatrics" -> Medical Assistant)."""
    t = (title or "").lower()
    if t in title_soc:
        return title_soc[t]
    idx = getattr(soc_for_title, "_idx", None)
    if idx is None or idx[0] is not title_soc:
        norm = {}
        for k, v in title_soc.items():
            n = norm_title(k)
            if n:
                norm.setdefault(n, v)
        idx = soc_for_title._idx = (title_soc, norm, sorted((k for k in norm if len(k.split()) >= 2), key=len, reverse=True))
    n = norm_title(title)
    if n in idx[1]:
        return idx[1][n]
    padded = f" {n} "
    for k in idx[2]:
        if f" {k} " in padded:
            return idx[1][k]
    # This title inside longer coded ones ("medical assistant" in "certified medical assistant"): take the most
    # common code among them, if it clearly leads.
    if len(n.split()) >= 2:
        from collections import Counter
        votes = Counter(v for k, v in idx[1].items() if f" {n} " in f" {k} ")
        if votes:
            (code, top), total = votes.most_common(1)[0], sum(votes.values())
            if top >= 2 and top / total >= 0.6:
                return code
    for rx, code in _TITLE_SOC:
        if rx.search(title or ""):
            return code
    return ""


# ---- Fewer barriers: no degree needed, paid training, fair-chance employer ---------------------------------

_DEGREE_REQUIRED = re.compile(r"\b(bachelor'?s|master'?s|doctoral|doctorate|associate'?s|ph\.?d|b\.?s\.?n|b\.?a\.?/b\.?s|"
                              r"\bba\b|\bbs\b|\bmba\b|\bmsw\b|\blcsw\b)\b[^.;]{0,60}\b(degree|required|in)\b|"
                              r"\bdegree (is )?required\b|\brequires? an? [a-z' ]{0,20}degree\b|"
                              r"\bmust (have|hold|possess) an? [a-z' ]{0,25}degree\b", re.I)
_DEGREE_PREFERRED = re.compile(r"degree[^.;]{0,30}\b(preferred|a plus|helpful|desired|not required|optional)\b", re.I)
_NO_DEGREE = re.compile(r"\bno (college )?degree (is )?(required|needed|necessary)\b|\bdegree not required\b|"
                        r"\bhigh school diploma\b|\b(ged|hse)\b|\bno experience (is )?(required|necessary|needed)\b|"
                        r"\bentry[- ]level\b", re.I)
_TRAINING = re.compile(r"\bpaid training\b|\btraining (is )?(provided|available|included)\b|\bwe (will|'ll) train\b|"
                       r"\bwill train\b|\bon[- ]the[- ]job training\b|\bapprentice(ship)?s?\b|\bearn while you learn\b|"
                       r"\bfull training\b|\btrain you\b", re.I)
_FAIR_CHANCE = re.compile(r"\bfair[- ]chance\b|\bsecond[- ]chance (employer|hiring|program|friendly)\b|"
                          r"\bbackground[- ]friendly\b|\bfelony[- ]friendly\b|\bjustice[- ]involved\b|"
                          r"\bre-?entry (program|friendly|candidates|population)\b|"
                          r"\bcriminal (history|record|background)[^.;]{0,40}\bnot (an )?(automatic|automatically)[^.;]{0,20}disqualif|"
                          r"\bconviction[^.;]{0,40}\bnot (an )?(automatic|automatically)[^.;]{0,20}(bar|disqualif)", re.I)


def text_flags(text):
    """What a posting's own words say: degree required or not, training provided, fair-chance hiring."""
    t = text or ""
    req = bool(_DEGREE_REQUIRED.search(t)) and not _DEGREE_PREFERRED.search(t)
    return {"degree_required": req, "no_degree": (not req) and bool(_NO_DEGREE.search(t)),
            "training": bool(_TRAINING.search(t)), "fair_chance": bool(_FAIR_CHANCE.search(t))}


def eases(text, occ_no_degree=None, page_flags=None, near_bus=None):
    """Labels for the widget's "Fewer barriers" filters.

    no_degree: the posting says so, or (when it doesn't ask for a degree) the occupation usually needs no more
    than a high school diploma, per the Bureau of Labor Statistics (occ_no_degree). A degree requirement in the
    text always wins.
    """
    f = text_flags(text)
    if page_flags:  # words from the employer's own posting page, read once and cached
        for k in ("degree_required", "no_degree", "training", "fair_chance"):
            f[k] = f[k] or bool(page_flags.get(k))
        if f["degree_required"]:
            f["no_degree"] = False
    out = []
    if near_bus:
        out.append("bus")
    if not f["degree_required"] and (f["no_degree"] or occ_no_degree is True):
        out.append("no_degree")
    if f["training"]:
        out.append("training")
    if f["fair_chance"]:
        out.append("fair_chance")
    return out
