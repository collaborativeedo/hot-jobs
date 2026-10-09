"""Tagging rules for the Lane County Hot Jobs index.

Type of work comes from each posting's federal occupation code (SOC).
Industry and employer come from words in the posting itself: QualityInfo
does not provide either as a field. Every employer rule below was checked
by hand against a real Lane County posting in October 2026. Edit freely.
"""
import re

# ---- Type of work (from SOC code) -------------------------------------------
SOC_EXACT = {"119021":"Construction & trades","471011":"Construction & trades","172051":"Construction & trades","499021":"Construction & trades","399011":"Childcare & education","434081":"Hospitality & leisure","372012":"Hospitality & leisure","393031":"Hospitality & leisure","399032":"Hospitality & leisure","119051":"Hospitality & leisure","191032":"Natural resources","191031":"Natural resources","194071":"Natural resources","192041":"Natural resources","119111":"Healthcare & human services","119179":"Healthcare & human services","113031":"Finance & accounting","413031":"Finance & accounting","434141":"Finance & accounting","112021":"Creative & media","272022":"Other"}
SOC_PREFIX = [("29","Healthcare & human services"),("31","Healthcare & human services"),("21","Healthcare & human services"),("47","Construction & trades"),("49","Construction & trades"),("53","Transportation & logistics"),("51","Manufacturing"),("35","Hospitality & leisure"),("15","Technology"),("17","Engineering & science"),("19","Engineering & science"),("25","Childcare & education"),("27","Creative & media"),("41","Retail & sales"),("132","Finance & accounting"),("433","Finance & accounting"),("43","Office & customer service"),("13","Management & business"),("11","Management & business")]

def type_of_work(soc):
    if soc in SOC_EXACT:
        return SOC_EXACT[soc]
    for prefix, name in SOC_PREFIX:
        if soc.startswith(prefix):
            return name
    return "Other"

# ---- Industry (from words in the posting) -----------------------------------
INDUSTRY_RULES = [
    ("Wood products & forestry", r"plywood|log mills|lumber|sawmill|veneer|forester|silvicultur|forestry"),
    ("Food & beverage", r"post consumer brands|glorybee|franz|united states bakery|frozen treats"),
    ("Bioscience", r"biotech|bioscience|life science|pharmaceutical"),
    ("Public sector", r"city of eugene|lane county|school district|lane community college|lane education|bureau of land|direct hire authority|oregon hazards lab|air traffic control|home telehealth|junction city oregon health|governmentjobs\.com|schooljobs\.com|usajobs|federalgovernmentjobs"),
    ("Nonprofit", r"peacehealth|pacificsource|looking for a (meaningful way to make a difference in the lives of|way to make an impact and help people join)|salvation army|looking glass|white bird|arboretum|bushnell"),
]
INDUSTRY_RULES = [(n, re.compile(p, re.I)) for n, p in INDUSTRY_RULES]
INDUSTRY_NOT = re.compile(r"morrison healthcare", re.I)

def industries(text):
    if INDUSTRY_NOT.search(text):
        return []
    return [name for name, rx in INDUSTRY_RULES if rx.search(text)]

PRIORITY = {"Healthcare & human services","Construction & trades","Transportation & logistics","Manufacturing","Technology","Hospitality & leisure","Childcare & education","Creative & media","Wood products & forestry","Food & beverage","Bioscience"}

# ---- Employer (first rule that matches wins) ----------------------------------
EMPLOYER_RULES = [
(r'morrison healthcare','Morrison Healthcare','Hospitality & leisure'),
(r'federal express','FedEx','Transportation & logistics'),
(r'work closely with wholesale and retail|essential to the success of our retail stores|sherwin-williams','Sherwin-Williams','Retail'),
(r'looking for a (meaningful way to make a difference in the lives of|way to make an impact and help people join)|pacificsource','PacificSource','Healthcare'),
(r'models and delivers a distinctive and delightful|walgreens|pharmacy customer service associate address','Walgreens','Retail'),
(r'vca delta oaks','VCA Delta Oaks Animal Hospital','Healthcare'),
(r'select your language preference|hcmportal\.wd5|helper coordinator ups','UPS','Transportation & logistics'),
(r'r256\d{3}|uhaul\.wd1|trailer/sri','U-Haul','Transportation & logistics'),
(r'globus medical','Globus Medical','Bioscience & medical devices'),
(r'oregon hazards lab|uoregon|communications officer apply','University of Oregon','Public sector'),
(r'our values start with our people|ross stores|rossstores','Ross Stores','Retail'),
(r'nabisco','Mondelez International (Nabisco)','Food & beverage'),
(r'post consumer brands|postholdings|headquartered in lakeville','Post Consumer Brands','Food & beverage'),
(r'kroger|e-commerce/clerk|fred meyer','Kroger (Fred Meyer)','Retail'),
(r'independent franchisee and not mcdonald','McDonald\'s franchisee','Hospitality & leisure'),
(r'dealership:|lithia|eugene apc|springfield toyota|southwest finance center','Lithia Motors','Retail'),
(r"lowe's|lowes\.wd5|pick, stage, inspect",'Lowe\'s','Retail'),
(r'sephora','Sephora','Retail'),
(r'vitamin shoppe','The Vitamin Shoppe','Retail'),
(r'insight global','Insight Global (staffing)','Staffing agency'),
(r'home depot|position purpose:|lot associates assist|merchandising execution associates|department supervisors lead|sales specialists help customers bring','The Home Depot','Retail'),
(r'job title: (maintenance technician|leasing consultant) salary','Avenue5 Residential','Real estate'),
(r'glorybee|1680 irving','GloryBee','Food & beverage'),
(r"eaton's",'Eaton','Manufacturing'),
(r'dungarvin','Dungarvin','Human services'),
(r'senior wealth advisor','Columbia Bank','Finance'),
(r'clorox','The Clorox Company','Manufacturing'),
(r'cinemark','Cinemark','Hospitality & leisure'),
(r'camping world|campingworld','Camping World','Retail'),
(r'company overview check out this video','CDM Smith','Engineering services'),
(r'outfitter|basspro','Bass Pro Shops','Retail'),
(r'step into a leadership role where your impact','RDO Equipment Co.','Retail'),
(r'saloncentric','SalonCentric','Retail'),
(r'shape the future of shopping experiences','Advantage Solutions','Retail'),
(r'albertsons','Albertsons','Retail'),
(r'whole foods|wholefoods|prepared foods team','Whole Foods Market','Retail'),
(r'frontier dermatology','Frontier Dermatology','Healthcare'),
(r'inner parish','Inner Parish Security','Security services'),
(r'stone works international','Stone Works International','Construction & trades'),
(r'bpas','BPAS','Finance'),
(r'ultimate staffing','Ultimate Staffing Services','Staffing agency'),
(r'register-guard|gannett','Gannett (The Register-Guard)','Creative & media'),
(r'didlakecareers','Didlake','Other'),
(r'work in team with cove','Cove Church','Nonprofit'),
(r'traxler','The Traxler Group','Hospitality & leisure'),
(r'baker tilly','Baker Tilly','Finance'),
(r'recruiting opportunity closes: 10\.02','The Salvation Army','Nonprofit'),
(r'unifi','Unifi Aviation','Transportation & logistics'),
(r'lane commun','Lane Community College','Public sector'),
(r'requisition number: 236945','Cintas','Other'),
(r'jp morgan|forestry field office internship','J.P. Morgan Asset Management (timberland)','Wood products & forestry'),
(r'senior home lending advisor','JPMorgan Chase','Finance'),
(r'dialysis|fmcna','Fresenius Kidney Care','Healthcare'),
(r'autozone','AutoZone','Retail'),
(r'everus|oeg, inc','OEG (Everus)','Construction & trades'),
(r'travelcenters of america','TravelCenters of America','Transportation & logistics'),
(r'wells fargo','Wells Fargo','Finance'),
(r'johnson crushers','Johnson Crushers International','Manufacturing'),
(r'cbre','CBRE','Other'),
(r'servicemaster','ServiceMaster Clean','Other'),
(r'old spaghetti factory','The Old Spaghetti Factory','Hospitality & leisure'),
(r'broad river retail','Broad River Retail','Retail'),
(r'schulte hospitality','Schulte Hospitality Group','Hospitality & leisure'),
(r'trinity services','Trinity Services Group','Other'),
(r'mckenzie-willamette|qhc1000qhcs','McKenzie-Willamette Medical Center','Healthcare'),
(r'coquille indian tribe','Coquille Indian Tribe','Public sector'),
(r'done right trucking','Done Right Trucking (Redgo)','Transportation & logistics'),
(r'survey\.com','Survey.com','Retail'),
(r'bi-mart','Bi-Mart','Retail'),
(r'marquiscompanies','Marquis Companies','Healthcare'),
(r'at gaf','GAF','Manufacturing'),
(r'hayward inn','Hayward Inn','Hospitality & leisure'),
(r'peacehealth|peace harbor','PeaceHealth','Healthcare'),
(r'nw industrial staffing','NW Industrial Staffing','Staffing agency'),
(r'aggregate resource industries','Aggregate Resource Industries','Construction & trades'),
(r'school district 4j|churchill high','Eugene School District 4J','Public sector'),
(r'lane educ','Lane Education Service District','Public sector'),
(r'oregon\.wd5|junction city oregon health','State of Oregon','Public sector'),
(r'circana','Circana','Other'),
(r'lane county','Lane County','Public sector'),
(r'prism biotech','Prism Biotech','Bioscience & medical devices'),
(r'oxford global','Oxford Global Resources','Staffing agency'),
(r'bureau of land','Bureau of Land Management','Public sector'),
(r'us foods','US Foods','Food & beverage'),
(r'peopleready','PeopleReady','Staffing agency'),
(r'may trucking','May Trucking','Transportation & logistics'),
(r'crete is hiring','Crete Carrier','Transportation & logistics'),
(r'farmers insurance','Farmers Insurance (Tony Core agency)','Finance'),
(r'allenmediabroadcasting','Allen Media Broadcasting','Creative & media'),
(r'jet industries','Jet Industries','Construction & trades'),
(r'sweetbriar villa','Sweetbriar Villa','Healthcare'),
(r'worldwide techservices|worldwidetechservices','Worldwide TechServices','Technology'),
(r'umbrella properties','Umbrella Properties','Real estate'),
(r'piercing pagoda','Piercing Pagoda','Retail'),
(r'mountain rose herbs','Mountain Rose Herbs','Manufacturing'),
(r'waterhouse ridge','Waterhouse Ridge Memory Care','Healthcare'),
(r'wingstop','Wingstop','Hospitality & leisure'),
(r'ingersoll rand','Ingersoll Rand','Manufacturing'),
(r'eugene eyewear|vsp vision','VSP Vision (Eugene Eyewear)','Healthcare'),
(r'allied universal','Allied Universal','Security services'),
(r'little sprouts','Little Sprouts','Childcare'),
(r'franz|united states bakery','Franz Family Bakeries','Food & beverage'),
(r'hillside heights','Hillside Heights Rehabilitation Center','Healthcare'),
(r'keiperspine','KeiperSpine','Healthcare'),
(r'linguava','Linguava','Other'),
(r'pacific crest bus','Pacific Crest Bus Lines','Transportation & logistics'),
(r'bushnell','Bushnell University','Nonprofit'),
(r'gentle dental','Gentle Dental','Healthcare'),
(r'hoban associates','Hoban Associates','Real estate'),
(r'guardianpharmacy','Guardian Pharmacy','Healthcare'),
(r'city of eugene','City of Eugene','Public sector'),
(r'merete','Merete Hotel Management (Residence Inn)','Hospitality & leisure'),
(r'proactive global','Proactive Global','Other'),
(r'reveille foundation','The Reveille Foundation','Nonprofit'),
(r'cornerstone associates','Cornerstone Associates','Other'),
(r'abc supply','ABC Supply','Construction & trades'),
(r'american traveler','American Traveler','Staffing agency'),
(r'valley river inn','Columbia Hospitality (Valley River Inn)','Hospitality & leisure'),
(r'signify health','Signify Health','Healthcare'),
(r"brink's land improvement",'Brink\'s Land Improvement','Construction & trades'),
(r'timber pointe','Timber Pointe Senior Living','Healthcare'),
(r'lululemon','lululemon','Retail'),
(r'mount pisgah arboretum','Mount Pisgah Arboretum','Nonprofit'),
(r'zip o log mills','Zip-O-Log Mills','Wood products & forestry'),
(r'beauty bar salon','Beauty Bar Salon','Other'),
(r'benson health','Benson Health Clinic','Healthcare'),
(r'northwest premier','Northwest Premier','Human services'),
(r'alive integrative','Alive Integrative Medicine','Healthcare'),
(r'central willamette credit union','Central Willamette Credit Union','Finance'),
(r'willamette valley cancer','Willamette Valley Cancer Institute','Healthcare'),
(r'looking glass','Looking Glass Community Services','Nonprofit'),
(r'staszak','Staszak Physical Therapy','Healthcare'),
(r'dollar tree','Dollar Tree','Retail'),
(r'interstate group','Interstate Group','Other'),
(r'swanson','Swanson Group (Springfield Plywood)','Wood products & forestry'),
(r"dick's sporting",'DICK\'S Sporting Goods','Retail'),
(r'castle megastore','Castle Megastore Group','Retail'),
(r'oregon flight','Oregon Flight','Other'),
(r'jaj enterprises','JAJ Enterprises','Other'),
(r'white bird','White Bird Clinic','Nonprofit'),
(r'careers\.ulta\.com','Ulta Beauty','Retail'),
(r'air traffic control','Federal Aviation Administration','Public sector'),
(r'gordon, aylworth','Gordon, Aylworth & Tami','Other'),
(r'abts inc','ABTS Inc','Finance'),
(r'aacpnw','AACPNW (office-based dental anesthesia)','Healthcare'),
(r'early autism services','Early Autism Services','Human services'),
(r'redgo','Done Right Trucking (Redgo)','Transportation & logistics'),
]
EMPLOYER_RULES = [(re.compile(p, re.I), name, ind) for p, name, ind in EMPLOYER_RULES]

def employer(text):
    for rx, name, ind in EMPLOYER_RULES:
        if rx.search(text):
            return name
    return ""

# ---- Employer from the posting link -----------------------------------------
# Employers' own careers domains. Checked against real Lane County postings, October 2026.
DOMAIN_EMPLOYERS = {
    "jobs.tacobell.com": "Taco Bell", "www.kendallcareers.com": "Kendall Auto Group",
    "jobs.familyresourcehomecare.com": "Family Resource Home Care", "weyerhaeuser.taleo.net": "Weyerhaeuser",
    "www.atriacareers.com": "Atria Senior Living", "wendys-careers.com": "Wendy's", "careers.petco.com": "Petco",
    "careers.lovisa.com": "Lovisa", "careers.guitarcenter.com": "Guitar Center", "careers.nike.com": "Nike",
    "careers.cintas.com": "Cintas", "careers.kbs-services.com": "KBS (Kellermeyer Bergensons Services)",
    "careers.thespringsliving.com": "The Springs Living", "jobs.sportclips.com": "Sport Clips",
    "jobs.danaher.com": "Danaher", "corporate.target.com": "Target", "careers.vetcor.com": "VetCor",
    "www.procaretherapy.com": "ProCare Therapy", "careers.onemedical.com": "One Medical",
    "careers.essilorluxottica.com": "EssilorLuxottica", "www.judge.com": "The Judge Group",
    "workwithus.circlek.com": "Circle K", "jobs.heartland.com": "Heartland Dental",
    "careers.unitedhealthgroup.com": "UnitedHealth Group", "www.gapinc.com": "Gap Inc.",
    "careers.maximhealthcare.com": "Maxim Healthcare", "careers.tradesmeninternational.com": "Tradesmen International",
    "careers.bankofamerica.com": "Bank of America", "careers.montenidoaffiliates.com": "Monte Nido",
    "www.spi-ind.com": "Sierra Pacific Industries", "jobs.retirement.org": "Pacific Retirement Services",
    "www.spencersandspiritjobs.com": "Spencer's and Spirit Halloween", "workatbest.com": "BEST Crowd Management",
    "www.kcecareers.com": "KinderCare", "www.usajobs.gov": "Federal government (USAJOBS)",
    "careers.peacehealth.org": "PeaceHealth", "jobs.lanecc.edu": "Lane Community College",
    "careers.uoregon.edu": "University of Oregon", "jobs.walgreens.com": "Walgreens",
}
TENANT_NAMES = {"sunsrce": "SunSource", "boxlunch": "BoxLunch", "bannerbank": "Banner Bank", "wireless-vision": "Wireless Vision",
                "leaf-home": "Leaf Home", "clairesstores": "Claire's", "celsius": "Celsius", "rwcgroup": "RWC Group",
                "lithia": "Lithia Motors", "tti": "Techtronic Industries (TTI)", "hcmportal": "UPS", "lowes": "Lowe's",
                "basspro": "Bass Pro Shops", "campingworld": "Camping World", "dickssportinggoods": "DICK'S Sporting Goods",
                "guardianpharmacy": "Guardian Pharmacy", "oregon": "State of Oregon", "uhaul": "U-Haul",
                "petersonholding": "Peterson Cat", "oreillyauto": "O'Reilly Auto Parts", "columbiabank": "Umpqua Bank (Columbia Banking System)",
                "usbank": "U.S. Bank", "genpt": "NAPA Auto Parts (Genuine Parts Company)", "hdsupply": "HD Supply",
                "firststudent": "First Student", "vfc": "Vans (VF Corporation)", "davita": "DaVita",
                "equitylifestyleproperties": "Equity LifeStyle Properties", "sunrisegroup": "Sunrise Group",
                "greystar": "Greystar", "bridgestone": "Bridgestone", "medtronic": "Medtronic"}
_TENANT_RX = [
    r"^https?://jobs\.lever\.co/([^/?#]+)", r"fountain\.com/apply/([^/?#]+)", r"saashr\.com/ta/([A-Za-z0-9]+)\.careers",
    r"apply\.workable\.com/([^/?#]+)", r"careers\.hireology\.com/([^/?#]+)", r"^https?://([^./]+)\.(?:applytojob\.com|breezy\.hr|workbrightats\.com)",
    r"^https?://([^./]+)\.taleo\.net", r"^https?://([^./]+)\.wd\d+\.myworkdayjobs\.com", r"^https?://([^./]+)\.jobs\.hr\.cloud\.sap",
]
_TENANT_RX = [re.compile(p, re.I) for p in _TENANT_RX]


def _tenant_name(slug):
    s = slug.lower()
    if s in TENANT_NAMES:
        return TENANT_NAMES[s]
    if s in ("phe", "www", "jobs", "careers", "search", "external"):
        return ""
    return re.sub(r"[-_]+", " ", slug).title()


def employer_from_url(url):
    """Employer named by the posting link itself: a known careers domain or a hiring-platform account name."""
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url or "").lower()
    if host in DOMAIN_EMPLOYERS:
        return DOMAIN_EMPLOYERS[host]
    for rx in _TENANT_RX:
        m = rx.search(url or "")
        if m:
            return _tenant_name(m.group(1))
    return ""


# ---- Type of work from the job title (for postings without an occupation code) ----
TITLE_TYPES = [
    ("Healthcare & human services", r"\bnurs|\brn\b|\blpn\b|\bcna\b|medical|clinic|physician|therap|pharm|dental|hygien|caregiver|patient|health|counsel|social work|lab ass|phlebot|radiolog|surg|behavioral|psych"),
    ("Childcare & education", r"teacher|teach|school|child ?care|preschool|tutor|instruct|educat|paraeducator|coach"),
    ("Construction & trades", r"electric|plumb|carpent|hvac|construct|mechanic|technician|install|weld|maintenance|millwright|laborer|roof|paint"),
    ("Transportation & logistics", r"driver|cdl|truck|deliver|warehouse|forklift|logistic|dispatch|freight|porter"),
    ("Hospitality & leisure", r"cook|chef|server|bartend|barista|dishwash|host|housekeep|restaurant|kitchen|crew member|food|hotel|event staff"),
    ("Retail & sales", r"sales|cashier|retail|store|merchandis|stocker|associate|clerk|shopper"),
    ("Finance & accounting", r"account|bookkeep|payroll|finance|banker|teller|loan|underwrit|auditor|controller"),
    ("Technology", r"software|developer|it support|desktop support|network|data|systems admin|cyber|\bit\b"),
    ("Engineering & science", r"engineer|scientist|chemist|biolog|environmental|lab tech"),
    ("Manufacturing", r"production|machin|assembl|manufactur|operator|fabricat"),
    ("Office & customer service", r"receptionist|customer service|administrative|office|clerical|coordinator|call center|front desk"),
    ("Management & business", r"manager|director|supervisor|lead\b|analyst|specialist"),
]
TITLE_TYPES = [(n, re.compile(p, re.I)) for n, p in TITLE_TYPES]


def type_from_title(title):
    for name, rx in TITLE_TYPES:
        if rx.search(title or ""):
            return name
    return "Other"


# ---- How a posting is reached -----------------------------------------------
JOB_BOARDS = {"simplyhired.com","indeed.com","gr8jobs.net","disabledperson.com","joblinkapply.com","employeebenefitsjobs.com","dejobs.org","diversityjobs.com","healthecareers.com","careersinaudit.com","eugenejobs.net","academiccareers.com","planning.org","apwa.org","awwa.org","globaltalentpartners.com","madison.com","netimpact.org","federalgovernmentjobs.us","jobmonkeyjobs.com","equest.com","conbio.org","careerarc.com","healthjobsnationwide.com","fairygodboss.com","jobit.com","jobtarget.com","chronicle.com","idealist.org","themuse.com","schoolspring.com","womensjoblist.com","conservationjobboard.com","dice.com","efinancialcareers.com","salesheads.com","constructionjobs.com","blazerjobs.com","partnersindiversity.org","gopromotive.com","nwppa.org"}

def route(url):
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url).lower()
    if "emp.state.or.us" in host:
        return "WorkSource Oregon listing"
    if any(host == b or host.endswith("." + b) for b in JOB_BOARDS):
        return "Reposted by a job board"
    return "Employer's hiring site"

METRO = {"Eugene", "Springfield"}

# ---- Hiring platform and careers page (from a posting's link) ----------------
PLATFORMS = [
    (r"myworkdayjobs\.com", "Workday"), (r"ultipro\.com|rec\.pro\.ukg\.net", "UKG (UltiPro)"),
    (r"adp\.com", "ADP"), (r"oraclecloud\.com", "Oracle Recruiting"), (r"paycomonline", "Paycom"),
    (r"paylocity", "Paylocity"), (r"paychex", "Paychex"), (r"hirebridge", "Hirebridge"),
    (r"greenhouse\.io", "Greenhouse"), (r"dayforcehcm", "Dayforce"), (r"icims\.com", "iCIMS"),
    (r"successfactors", "SAP SuccessFactors"), (r"smartrecruiters", "SmartRecruiters"),
    (r"trakstar", "Trakstar Hire"), (r"careerplug", "CareerPlug"), (r"hrmdirect", "HRM Direct"),
    (r"governmentjobs\.com|schooljobs\.com", "NEOGOV (GovernmentJobs)"),
    (r"taleo\.net", "Taleo"), (r"lever\.co", "Lever"), (r"fountain\.com", "Fountain"),
    (r"saashr\.com", "UKG Ready"), (r"applitrack\.com", "Frontline (AppliTrack)"), (r"brassring\.com", "BrassRing"),
    (r"breezy\.hr", "Breezy HR"), (r"workable\.com", "Workable"), (r"hireology\.com", "Hireology"),
    (r"workbrightats\.com", "WorkBright"), (r"applytojob\.com", "JazzHR"), (r"hr\.cloud\.sap", "SAP SuccessFactors"),
    (r"brt\.mv", "BrightMove"), (r"careers\.peacehealth\.org", "PeaceHealth careers site"),
]
PLATFORMS = [(re.compile(p, re.I), n) for p, n in PLATFORMS]


def platform(url):
    """Hiring platform behind a posting link, 'Employer website', or '' for OED and job boards."""
    r = route(url)
    if r != "Employer's hiring site":
        return ""
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url).lower()
    for rx, name in PLATFORMS:
        if rx.search(host):
            return name
    return "Employer website"


def careers_page(url, plat):
    """Best guess at the employer's careers page from one posting link."""
    url = url.replace("http://", "https://")
    base = re.sub(r"^(https://[^/]+).*$", r"\1", url)
    if plat == "Workday":
        return url.split("/job/")[0]
    if plat == "UKG (UltiPro)":
        m = re.match(r"(https://[^/]+/[^/]+/jobboard/[^/?]+)", url, re.I)
        return m.group(1) if m else base
    if plat == "Greenhouse":
        m = re.match(r"(https://[^/]+/[^/?]+)", url)
        return m.group(1) if m else base
    if plat == "Oracle Recruiting":
        return re.split(r"/job/", url, flags=re.I)[0]
    if plat == "ADP":
        m = re.match(r"(https://myjobs\.adp\.com/[^/]+)", url)
        return m.group(1) + "/cx" if m else ""
    if plat == "Dayforce":
        return url.split("/jobs/")[0]
    if plat == "iCIMS":
        return base + "/jobs"
    if plat == "Paycom":
        m = re.match(r"(https://[^?]+/portal/[A-Za-z0-9]+)", url)
        return m.group(1) if m else ""
    if plat == "Employer website":
        return base
    return ""


def employer_industry(name):
    for rx, n, ind in EMPLOYER_RULES:
        if n == name:
            return ind
    return ""
