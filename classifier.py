"""Evidence-based DDC classification for the Universal Cataloging Assistant.

Single source of truth for classification (the browser no longer keeps its own
rule list).  Design goals taken from the project handover document:

* A source-supplied DDC is validated, kept, and labelled as such.  It is never
  mixed with an unrelated locally inferred subject or shelf.
* Shelf and subject for a source DDC are derived from the number itself
  (class -> division -> section captions), so they cannot contradict it.
* Inference weighs title/subject evidence far above description evidence,
  counts distinct terms (not repetitions), supports exclusions, and prefers a
  specific subdivision over its broader parent when the evidence supports it.
* Nothing defaults to 000; no evidence means "needs review".
* Everything inferred is flagged ``review_required``.

DDC numbers below are classification *directions* and must be verified against
an authorised DDC edition before cataloguing.
"""

import re
from collections import Counter

# ---------------------------------------------------------------------------
# DDC STRUCTURE
# ---------------------------------------------------------------------------

CLASS_RANGES = [
    (0, 99, "000–099", "Computer science, information & general works"),
    (100, 199, "100–199", "Philosophy & psychology"),
    (200, 299, "200–299", "Religion"),
    (300, 399, "300–399", "Social sciences"),
    (400, 499, "400–499", "Language"),
    (500, 599, "500–599", "Science"),
    (600, 699, "600–699", "Technology"),
    (700, 799, "700–799", "Arts & recreation"),
    (800, 899, "800–899", "Literature"),
    (900, 999, "900–999", "History & geography"),
]

# Divisions (tens), then selected sections/subdivisions.  Lookup walks from the
# full number down to the division, so unknown decimals fall back to the
# nearest broader caption rather than inventing one.
CAPTIONS = {
    # 000
    "000": "Computer science, knowledge & systems", "001": "Knowledge",
    "002": "The book", "003": "Systems", "004": "Computer science",
    "005": "Computer programming, programs & data",
    "006": "Special computer methods", "010": "Bibliography",
    "020": "Library & information sciences", "021": "Library relationships",
    "022": "Administration of the physical plant",
    "023": "Personnel administration (library staff)",
    "025": "Library operations", "026": "Libraries for specific subjects",
    "027": "General libraries", "028": "Reading & use of other information media",
    "030": "Encyclopedias & books of facts", "040": "(Unassigned)",
    "050": "Magazines, journals & serials", "060": "Associations, organizations & museums",
    "069": "Museum science", "070": "News media, journalism & publishing",
    "080": "Quotations & general collections", "090": "Manuscripts & rare books",
    "004.6": "Interfacing & communications (networks)", "004.678": "Internet",
    "005.1": "Programming", "005.133": "Specific programming languages",
    "005.43": "Operating systems", "005.74": "Data files & databases",
    "005.8": "Data security", "006.3": "Artificial intelligence",
    "006.31": "Machine learning", "006.7": "Multimedia systems & web design",
    "025.1": "Library administration", "025.3": "Bibliographic analysis & control (cataloguing)",
    "025.4": "Subject analysis & classification systems", "025.5": "Services to users",
    "027.4": "Public libraries", "027.7": "Academic libraries", "027.8": "School libraries",
    "070.4": "Journalism", "070.5": "Publishing",
    # 100
    "100": "Philosophy", "110": "Metaphysics", "120": "Epistemology",
    "130": "Parapsychology & occultism", "140": "Philosophical schools",
    "150": "Psychology", "153": "Conscious mental processes & intelligence",
    "155": "Differential & developmental psychology", "155.4": "Child psychology",
    "158": "Applied psychology", "158.1": "Personal improvement & analysis",
    "160": "Logic", "170": "Ethics", "180": "Ancient, medieval & eastern philosophy",
    "190": "Modern western philosophy",
    # 200
    "200": "Religion", "210": "Philosophy & theory of religion", "220": "Bible",
    "230": "Christianity & Christian theology", "240": "Christian practice & observance",
    "248": "Christian life & practice", "250": "Christian pastoral practice & orders",
    "260": "Christian organization, social work & worship",
    "270": "History of Christianity", "280": "Christian denominations",
    "290": "Other religions", "294": "Religions of Indic origin",
    "296": "Judaism", "297": "Islam",
    # 300
    "300": "Social sciences", "301": "Sociology & anthropology", "310": "Statistics (general)",
    "320": "Political science", "330": "Economics", "332": "Financial economics",
    "340": "Law", "350": "Public administration & military science",
    "360": "Social problems & services", "370": "Education",
    "370.15": "Educational psychology", "374": "Adult education", "380": "Commerce, communications & transportation",
    "390": "Customs, etiquette & folklore",
    # 400
    "400": "Language", "410": "Linguistics", "420": "English & Old English",
    "430": "German", "440": "French", "450": "Italian & Romanian",
    "460": "Spanish & Portuguese", "470": "Latin", "480": "Classical & modern Greek",
    "490": "Other languages", "496": "African languages", "496.392": "Swahili",
    # 500
    "500": "Science", "510": "Mathematics", "519.5": "Statistics (mathematical)",
    "520": "Astronomy", "530": "Physics", "540": "Chemistry",
    "540.76": "Chemistry — problems, exercises", "550": "Earth sciences & geology",
    "560": "Fossils & prehistoric life", "570": "Biology", "580": "Plants (botany)",
    "579.5": "Fungi", "582.16": "Trees", "590": "Animals (zoology)", "595.7": "Insects",
    "597": "Fishes", "597.8": "Amphibians", "597.9": "Reptiles", "598": "Birds", "599": "Mammals",
    # 600
    "600": "Technology", "610": "Medicine & health", "620": "Engineering",
    "630": "Agriculture", "640": "Home & family management", "641.5": "Cooking",
    "650": "Management & public relations", "657": "Accounting",
    "658": "General management", "658.8": "Marketing", "660": "Chemical engineering",
    "670": "Manufacturing", "680": "Manufacture for specific uses",
    "690": "Construction of buildings",
    # 700
    "700": "Arts", "709": "Art history", "710": "Landscaping & area planning",
    "720": "Architecture", "730": "Sculpture, ceramics & metalwork",
    "740": "Graphic arts & decorative arts", "750": "Painting",
    "760": "Printmaking & prints", "770": "Photography, computer art, film & video",
    "780": "Music", "790": "Sports, games & entertainment", "796": "Athletic & outdoor sports",
    # 800
    "800": "Literature", "810": "American literature in English",
    "820": "English & Old English literatures", "830": "German literature",
    "840": "French literature", "850": "Italian & Romanian literature",
    "860": "Spanish & Portuguese literature", "870": "Latin literature",
    "880": "Classical & modern Greek literature", "890": "Other literatures",
    # 900
    "900": "History", "910": "Geography & travel", "920": "Biography & genealogy",
    "930": "History of the ancient world", "940": "History of Europe",
    "950": "History of Asia", "960": "History of Africa",
    "967.6": "East Africa", "967.62": "Kenya", "970": "History of North America",
    "973": "United States", "980": "History of South America",
    "990": "History of other areas",
}


def class_info(number):
    m = re.match(r"\d{3}", str(number or ""))
    if not m:
        return None
    n = int(m.group(0))
    for lo, hi, rng, name in CLASS_RANGES:
        if lo <= n <= hi:
            return {"range": rng, "name": name}
    return None


def caption_for(number):
    """Return (caption, exact) walking from the full number to the division."""
    num = str(number or "")
    if not re.fullmatch(r"\d{3}(\.\d+)?", num):
        return None, False
    probe = num
    while True:
        if probe in CAPTIONS:
            return CAPTIONS[probe], probe == num
        if "." in probe:
            probe = probe[:-1]
            if probe.endswith("."):
                probe = probe[:-1]
            continue
        break
    division = num[:2] + "0"
    if division in CAPTIONS:
        return CAPTIONS[division], False
    hundred = num[0] + "00"
    return CAPTIONS.get(hundred), False


def shelf_for(number):
    """Shelf description derived only from the number, so it cannot conflict."""
    info = class_info(number)
    if not info:
        return "Librarian review required"
    text = f"{info['range']} • {info['name']}"
    division = str(number)[:2] + "0"
    if division in CAPTIONS and division[0] + "00" != division:
        text += f" › {CAPTIONS[division]} ({division})"
    elif division in CAPTIONS and division == str(number)[0] + "00":
        pass
    return text


# ---------------------------------------------------------------------------
# DDC VALIDATION
# ---------------------------------------------------------------------------

def normalize_ddc(value):
    """Return a valid DDC number or None.

    Strict: the whole token must be a DDC number.  Segmentation marks
    ("023/.9"), brackets and a juvenile "j" prefix are removed.  Embedded digits
    from LC call numbers (e.g. HF5549.5) are never accepted.
    """
    if value is None:
        return None
    for token in str(value).split():
        tok = re.sub(r"[\[\]]", "", token).replace("/", "").strip(".")
        tok = re.sub(r"^[jJcC](?=\d)", "", tok)
        if re.fullmatch(r"\d{3}(\.\d+)?", tok):
            return tok
    return None


def _stem(number):
    """Number without trailing zeros, used to test broader/narrower relations."""
    base = str(number).replace(".", "")
    return base.rstrip("0")


def related(a, b):
    """True when one number is the same as, or broader than, the other."""
    sa, sb = _stem(a), _stem(b)
    if not sa or not sb:
        return False
    return sa.startswith(sb) or sb.startswith(sa)


def choose_source_ddc(candidates):
    """Pick the best source DDC from [{'number','source'}...] or plain strings."""
    cleaned = []
    for item in candidates or []:
        raw = item.get("number") if isinstance(item, dict) else item
        src = item.get("source") if isinstance(item, dict) else None
        num = normalize_ddc(raw)
        if num:
            cleaned.append({"number": num, "source": src})
    if not cleaned:
        return None, []
    groups = {}
    order = []
    for c in cleaned:
        g = c["number"][:3]
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(c)
    best = max(order, key=lambda g: (len({x["source"] for x in groups[g]}), len(groups[g])))
    counts = Counter(x["number"] for x in groups[best])
    number = max(counts, key=lambda n: (counts[n], len(n)))
    chosen = next(x for x in groups[best] if x["number"] == number)
    return chosen, cleaned


# ---------------------------------------------------------------------------
# INFERENCE RULES
# ---------------------------------------------------------------------------

def R(number, subject, lcsh, any_=None, all_=None, exclude=None, note=None):
    return {
        "number": number, "subject": subject, "lcsh": lcsh,
        "any": [re.compile(p, re.I) for p in (any_ or [])],
        "all": [re.compile(p, re.I) for p in (all_ or [])],
        "exclude": [re.compile(p, re.I) for p in (exclude or [])],
        "note": note,
    }


LIB = r"\blibrar(?:y|ies|ian|ians|ianship)\b"
HIST = r"\b(?:history|historical|politics|political|colonial\w*|independence|empire|war)\b"

RULES = [
    # ---- 000 -------------------------------------------------------------
    R("004", "Computer science", ["Computer science"],
      any_=[r"\bcomputer science\b", r"\bcomputing\b", r"\bcomputer systems?\b",
            r"\bcomputer architecture\b", r"\binformation technology\b", r"\bict\b",
            r"\bcomputer hardware\b"]),
    R("004.6", "Computer networks", ["Computer networks"],
      any_=[r"\bcomputer networks?\b", r"\bnetworking\b"]),
    R("004.678", "Internet", ["Internet"], any_=[r"\binternet\b", r"\bworld wide web\b"]),
    R("005.1", "Computer programming", ["Computer programming"],
      any_=[r"\bcomputer programming\b", r"\bprogramming\b", r"\bsoftware (?:engineering|development)\b",
            r"\bweb development\b", r"\bcoding\b", r"\balgorithms?\b"]),
    R("005.133", "Programming languages", ["Programming languages (Electronic computers)"],
      any_=[r"\bpython\b", r"\bjavascript\b", r"\bjava\b", r"c\+\+", r"\bphp\b",
            r"\bprogramming languages?\b"],
      exclude=[r"\bsnakes?\b", r"\breptiles?\b", r"\bmonty python\b", r"\bisland\b", r"\bcoffee\b"]),
    R("005.43", "Operating systems", ["Operating systems (Computers)"],
      any_=[r"\boperating systems?\b", r"\blinux\b", r"\bunix\b"]),
    R("005.74", "Databases", ["Databases"], any_=[r"\bdata ?bases?\b", r"\bsql\b", r"\bdata management\b"]),
    R("005.8", "Computer security", ["Computer security"],
      any_=[r"\bcyber ?security\b", r"\bcomputer security\b", r"\binformation security\b"]),
    R("006.3", "Artificial intelligence", ["Artificial intelligence"],
      any_=[r"\bartificial intelligence\b", r"\bneural networks?\b"]),
    R("006.31", "Machine learning", ["Machine learning"], any_=[r"\bmachine learning\b", r"\bdeep learning\b"]),
    R("006.7", "Web design & multimedia", ["Web site development", "Multimedia systems"],
      any_=[r"\bweb design\b", r"\bmultimedia\b", r"\bhtml\b", r"\bcss\b"]),
    R("010", "Bibliography", ["Bibliography"], any_=[r"\bbibliograph(?:y|ies)\b"]),
    R("020", "Library & information science", ["Library science", "Information science"],
      any_=[r"\blibrary science\b", r"\blibrary and information science\b", r"\binformation science\b",
            r"\blibrarianship\b", LIB]),
    R("023", "Library personnel administration", ["Library personnel management"],
      all_=[LIB, r"\b(?:staff|personnel|employees|motivat\w*|hiring|recruit\w*|training)\b"]),
    R("025.1", "Library administration", ["Library administration"],
      all_=[LIB, r"\b(?:management|administration|budget\w*|strategic planning)\b"]),
    R("025.3", "Cataloguing", ["Cataloging", "Descriptive cataloging"],
      any_=[r"\bcatalog(?:u)?ing\b", r"\baacr2?\b", r"\brda\b", r"\bmarc\b", r"\bmetadata\b",
            r"\bbibliographic (?:control|description)\b"]),
    R("025.4", "Subject analysis & classification systems", ["Classification—Books", "Subject headings"],
      any_=[r"\bdewey\b", r"\blibrary of congress classification\b", r"\bsubject headings?\b",
            r"\bclassification systems?\b", r"\bindexing\b", r"\bthesaur(?:us|i)\b"]),
    R("025.5", "Library user services", ["Reference services (Libraries)", "Information literacy"],
      any_=[r"\breference services?\b", r"\breference (?:work|librarian)\b", r"\binformation literacy\b",
            r"\breaders'? advisory\b"]),
    R("027.4", "Public libraries", ["Public libraries"], any_=[r"\bpublic librar(?:y|ies)\b"]),
    R("027.7", "Academic libraries", ["Academic libraries"],
      any_=[r"\bacademic librar(?:y|ies)\b", r"\buniversity librar(?:y|ies)\b"]),
    R("027.8", "School libraries", ["School libraries"], any_=[r"\bschool librar(?:y|ies)\b", r"\bschool media\b"]),
    R("030", "Encyclopedias & books of facts", ["Encyclopedias and dictionaries"],
      any_=[r"\bencyclop(?:a)?edias?\b", r"\balmanacs?\b", r"\bbooks of facts\b"]),
    R("050", "Serial publications", ["Serial publications"],
      any_=[r"\bperiodicals?\b", r"\bserial publications?\b"]),
    R("069", "Museum science", ["Museums"], any_=[r"\bmuseums?\b", r"\bmuseology\b"]),
    R("070.4", "Journalism", ["Journalism"],
      any_=[r"\bjournalis[mt]s?\b", r"\bnews ?papers?\b", r"\bnews media\b", r"\binvestigative reporting\b"]),
    R("070.5", "Publishing", ["Publishers and publishing"], any_=[r"\bpublishing\b"]),
    R("080", "Quotations & general collections", ["Quotations"], any_=[r"\bquotations\b"]),
    R("090", "Manuscripts & rare books", ["Manuscripts", "Rare books"],
      any_=[r"\bmanuscripts?\b", r"\brare books?\b", r"\bincunabula\b"]),
    # ---- 100 -------------------------------------------------------------
    R("100", "Philosophy", ["Philosophy"], any_=[r"\bphilosoph(?:y|ical)\b"]),
    R("130", "Parapsychology & occultism", ["Occultism", "Parapsychology"],
      any_=[r"\boccult\b", r"\bastrology\b", r"\bparanormal\b", r"\bparapsychology\b"]),
    R("150", "Psychology", ["Psychology"],
      any_=[r"\bpsycholog(?:y|ical)\b", r"\bpersonality\b", r"\bbehaviou?r\b", r"\bmental health\b",
            r"\bcognitive\b", r"\bcognition\b"]),
    R("155.4", "Child psychology", ["Child psychology"],
      any_=[r"\bchild psychology\b", r"\bchild development\b", r"\bdevelopmental psychology\b"]),
    R("158.1", "Self-help & personal development", ["Self-help techniques", "Self-realization", "Success"],
      any_=[r"\bself-?help\b", r"\bpersonal (?:development|growth)\b", r"\bself-?improvement\b",
            r"\bself-?mastery\b", r"\bself-?sabotage\b", r"\bmindset\b", r"\bpersonal transformation\b",
            r"\bself-?realization\b"]),
    R("160", "Logic", ["Logic"], any_=[r"\blogic\b"], exclude=[r"\bdigital logic\b", r"\blogic circuits?\b"]),
    R("170", "Ethics", ["Ethics"], any_=[r"\bethics\b", r"\bmoral philosophy\b", r"\bmorality\b"]),
    # ---- 200 -------------------------------------------------------------
    R("200", "Religion", ["Religion"], any_=[r"\breligio(?:n|us)\b"]),
    R("220", "Bible", ["Bible"], any_=[r"\bbible\b", r"\bscriptures?\b"]),
    R("230", "Christianity", ["Christianity", "Theology"],
      any_=[r"\bchristian(?:ity)?\b", r"\btheology\b", r"\bchurch\b"]),
    R("248", "Christian life", ["Christian life", "Spiritual life"],
      any_=[r"\bchristian life\b", r"\bspiritual growth\b", r"\bdiscipleship\b", r"\bdevotional\b", r"\bprayer\b"]),
    R("250", "Pastoral practice", ["Pastoral theology", "Preaching"],
      any_=[r"\bpastoral\b", r"\bpreaching\b", r"\bsermons?\b", r"\bministry\b"]),
    R("294", "Religions of Indic origin", ["Hinduism", "Buddhism"], any_=[r"\bhindu(?:ism)?\b", r"\bbuddh\w+\b"]),
    R("296", "Judaism", ["Judaism"], any_=[r"\bjudaism\b", r"\bjewish\b", r"\btorah\b"]),
    R("297", "Islam", ["Islam"], any_=[r"\bislam\w*\b", r"\bmuslims?\b", r"\bqur'?an\b"]),
    # ---- 300 -------------------------------------------------------------
    R("300", "Social sciences", ["Social sciences"], any_=[r"\bsocial sciences?\b"]),
    R("301", "Sociology", ["Sociology"], any_=[r"\bsociolog(?:y|ical)\b", r"\banthropology\b"]),
    R("320", "Political science", ["Political science"],
      any_=[r"\bpolitic(?:s|al)\b", r"\bdemocracy\b", r"\bgovernment\b"]),
    R("330", "Economics", ["Economics"], any_=[r"\beconomics\b", r"\beconom(?:y|ic)\b"]),
    R("332", "Finance", ["Finance"], any_=[r"\bfinance\b", r"\bbanking\b", r"\binvest(?:ing|ment|ments)\b"]),
    R("340", "Law", ["Law"], any_=[r"\blaw\b", r"\blegal\b", r"\bconstitution\w*\b"],
      exclude=[r"\blaw of attraction\b"]),
    R("360", "Social problems & services", ["Social service"],
      any_=[r"\bsocial work\b", r"\bpoverty\b", r"\bwelfare\b"]),
    R("370", "Education", ["Education"],
      any_=[r"\beducation\b", r"\bteaching\b", r"\bteachers?\b", r"\bpedagog\w*\b", r"\bcurriculum\b"]),
    R("370.15", "Educational psychology", ["Educational psychology"],
      any_=[r"\beducational psychology\b", r"\bpsychology of (?:education|learning)\b"]),
    R("374", "Adult education", ["Adult education"],
      any_=[r"\badult education\b", r"\badult learning\b", r"\bcontinuing education\b",
            r"\blifelong learning\b", r"\badult literacy\b"]),
    R("390", "Customs & folklore", ["Folklore", "Manners and customs"],
      any_=[r"\bfolklore\b", r"\bcustoms\b", r"\betiquette\b"]),
    R("658", "Business management", ["Management", "Business"],
      any_=[r"\bbusiness\b", r"\bmanagement\b", r"\bleadership\b", r"\bentrepreneur\w*\b"]),
    R("658.8", "Marketing", ["Marketing"], any_=[r"\bmarketing\b"]),
    R("657", "Accounting", ["Accounting"], any_=[r"\baccounting\b"]),
    # ---- 400 -------------------------------------------------------------
    R("400", "Language", ["Language and languages"], any_=[r"\blanguages?\b"],
      exclude=[r"\bprogramming languages?\b"]),
    R("410", "Linguistics", ["Linguistics"], any_=[r"\blinguistics\b", r"\bphonetics\b", r"\bsyntax\b"]),
    R("420", "English language", ["English language"],
      any_=[r"\benglish (?:language|grammar)\b"]),
    R("496.392", "Swahili language", ["Swahili language"], any_=[r"\bswahili\b", r"\bkiswahili\b"]),
    # ---- 500 -------------------------------------------------------------
    R("500", "Science", ["Science"], any_=[r"\bscience\b", r"\bscientific\b"],
      exclude=[r"\b(?:computer|political|library|information|social|data) science\b", r"\bscience fiction\b"]),
    R("510", "Mathematics", ["Mathematics"],
      any_=[r"\bmathematics\b", r"\balgebra\b", r"\bcalculus\b", r"\bgeometry\b", r"\barithmetic\b"]),
    R("519.5", "Statistics", ["Mathematical statistics"], any_=[r"\bstatistics\b"]),
    R("520", "Astronomy", ["Astronomy"], any_=[r"\bastronomy\b", r"\bastrophysics\b"]),
    R("530", "Physics", ["Physics"],
      any_=[r"\bphysics\b", r"\bthermodynamics\b", r"\bquantum\b"]),
    R("540", "Chemistry", ["Chemistry"], any_=[r"\bchemistry\b", r"\bchemical\b"]),
    R("540.76", "Chemistry — problems & exercises", ["Chemistry—Problems, exercises, etc."],
      all_=[r"\bchemistry\b",
            r"\b(?:problems?|exercises?|questions?|calculations?|workbook|practice)\b"]),
    R("550", "Earth sciences & geology", ["Geology"], any_=[r"\bgeology\b", r"\bearth science\w*\b"]),
    R("570", "Biology", ["Biology"], any_=[r"\bbiology\b", r"\bgenetics\b", r"\bevolution\b"]),
    R("580", "Botany", ["Botany"], any_=[r"\bbotany\b"]),
    R("579.5", "Fungi", ["Fungi", "Mushrooms"], any_=[r"\bfungi\b", r"\bmushrooms?\b", r"\bmycology\b"]),
    R("582.16", "Trees", ["Trees"], any_=[r"\btrees\b", r"\bdendrology\b"]),
    R("590", "Zoology", ["Zoology", "Animals"],
      any_=[r"\bzoology\b", r"\bwildlife\b", r"\banimals\b", r"\bfauna\b"]),
    R("595.7", "Insects", ["Insects"], any_=[r"\binsects?\b", r"\bbutterfl(?:y|ies)\b", r"\bbeetles?\b", r"\bentomology\b"]),
    R("597", "Fishes", ["Fishes"], any_=[r"\bfish(?:es)?\b", r"\bichthyology\b"],
      exclude=[r"\bfishing\b", r"\bfish ?and ?chips\b"]),
    R("597.8", "Amphibians", ["Amphibians"],
      any_=[r"\bamphibians?\b", r"\bfrogs?\b", r"\btoads?\b", r"\bsalamanders?\b", r"\bnewts?\b", r"\bherpetology\b"]),
    R("597.9", "Reptiles", ["Reptiles"],
      any_=[r"\breptiles?\b", r"\bsnakes?\b", r"\blizards?\b", r"\bturtles?\b", r"\bcrocodil\w+\b"]),
    R("598", "Birds", ["Birds"], any_=[r"\bbirds?\b", r"\bornithology\b", r"\bbirding\b"]),
    R("599", "Mammals", ["Mammals"], any_=[r"\bmammals?\b", r"\bprimates?\b", r"\belephants?\b"]),
    # ---- 600 -------------------------------------------------------------
    R("610", "Medicine & health", ["Medicine", "Health"],
      any_=[r"\bmedicine\b", r"\bmedical\b", r"\bnursing\b", r"\bdiseases?\b", r"\bclinical\b",
            r"\banatomy\b", r"\bpublic health\b", r"\bhealth ?care\b", r"\bnutrition\b"]),
    R("620", "Engineering", ["Engineering"],
      any_=[r"\bengineering\b", r"\bmechanical\b", r"\belectrical\b"],
      exclude=[r"\bsoftware engineering\b"]),
    R("630", "Agriculture", ["Agriculture"],
      any_=[r"\bagriculture\b", r"\bfarming\b", r"\bcrops?\b", r"\blivestock\b", r"\bhorticulture\b"]),
    R("641.5", "Cooking", ["Cooking"], any_=[r"\bcook(?:ing|books?)\b", r"\brecipes?\b"]),
    R("690", "Building construction", ["Building"], any_=[r"\bbuilding construction\b", r"\bcarpentry\b"]),
    # ---- 700 -------------------------------------------------------------
    R("709", "Art history", ["Art"], any_=[r"\bfine arts\b", r"\bart history\b", r"\bvisual arts\b"]),
    R("720", "Architecture", ["Architecture"], any_=[r"\barchitecture\b"],
      exclude=[r"\b(?:computer|software|information) architecture\b"]),
    R("750", "Painting", ["Painting"], any_=[r"\bpainting\b"]),
    R("770", "Photography & film", ["Photography", "Motion pictures"],
      any_=[r"\bphotograph(?:y|s)\b", r"\bfilm ?making\b", r"\bcinematography\b"]),
    R("780", "Music", ["Music"], any_=[r"\bmusic\b", r"\bsongs?\b", r"\bguitar\b", r"\bpiano\b"]),
    R("796", "Sports", ["Sports"],
      any_=[r"\bsports?\b", r"\bfootball\b", r"\bsoccer\b", r"\bathletics\b", r"\bbasketball\b"]),
    # ---- 800 -------------------------------------------------------------
    R("800", "Literature (fiction, poetry, drama)", ["Literature", "Fiction"],
      any_=[r"\bfiction\b", r"\bnovels?\b", r"\bshort stories\b", r"\bpoetry\b", r"\bpoems?\b",
            r"\bliterature\b", r"\bliterary\b", r"\bdrama\b"],
      note="Literature is classed by language and period (e.g. 813, 823, 896); "
           "confirm the author's language before assigning a specific number."),
    # ---- 900 -------------------------------------------------------------
    R("900", "History", ["History"],
      any_=[r"\bhistory\b", r"\bhistorical\b", r"\bcivilization\b", r"\bcolonial\w*\b"]),
    R("910", "Geography & travel", ["Geography", "Voyages and travels"],
      any_=[r"\bgeography\b", r"\btravel\b", r"\batlas\b"]),
    R("920", "Biography", ["Biography"],
      any_=[r"\bbiograph(?:y|ies)\b", r"\bautobiograph\w+\b", r"\bmemoirs?\b"]),
    R("930", "Ancient history", ["History, Ancient"],
      any_=[r"\bancient (?:history|rome|greece|egypt)\b"]),
    # Place names alone do NOT make a history number ("Adult education in Kenya" is education);
    # they must be paired with a historical/political word.
    R("940", "History of Europe", ["Europe—History"], all_=[r"\beurope(?:an)?\b", HIST]),
    R("960", "History of Africa", ["Africa—History"], all_=[r"\bafrica(?:n)?\b", HIST]),
    R("967.6", "East Africa", ["Africa, East—History"], all_=[r"\beast africa\w*\b", HIST]),
    R("967.61", "Uganda", ["Uganda—History"], all_=[r"\bugand\w+\b", HIST]),
    R("967.62", "Kenya", ["Kenya—History"], all_=[r"\bkenya\w*\b", HIST]),
    R("973", "United States history", ["United States—History"],
      any_=[r"\bamerican history\b"], all_=None),
    R("973", "United States history", ["United States—History"], all_=[r"\bunited states\b", HIST]),
]

# Area notations (DDC Table 2) used to build geographic numbers such as 374.96761
# (adult education, Uganda).  Applied only to plain 3-digit numbers in classes 100-799.
AREAS = [
    ("east africa", "East Africa", "676"), ("south africa", "South Africa", "68"),
    ("united states", "United States", "73"), ("uganda", "Uganda", "6761"),
    ("kenya", "Kenya", "6762"), ("tanzania", "Tanzania", "678"), ("nigeria", "Nigeria", "669"),
    ("ghana", "Ghana", "667"), ("india", "India", "54"), ("china", "China", "51"),
    ("africa", "Africa", "6"),
]


def detect_area(text):
    low = str(text or "").lower()
    for key, name, notation in AREAS:
        if re.search(r"\b" + key + r"\w*\b", low):
            return {"name": name, "notation": notation}
    return None


STRONG_WEIGHT = 10
WEAK_WEIGHT = 2
WEAK_CAP = 3
MIN_SCORE = 4


def _terms(patterns, text):
    found = set()
    for rx in patterns:
        for m in rx.finditer(text):
            found.add(m.group(0).lower())
    return found


def _score_rule(rule, strong, weak):
    both = f"{strong} {weak}"
    if any(rx.search(both) for rx in rule["exclude"]):
        return 0, []
    if rule["all"]:
        evidence = []
        score = 0
        for rx in rule["all"]:
            if rx.search(strong):
                score += STRONG_WEIGHT
                evidence.append(rx.search(strong).group(0).lower())
            elif rx.search(weak):
                score += WEAK_WEIGHT
                evidence.append(rx.search(weak).group(0).lower() + " (description)")
            else:
                return 0, []
        return score, evidence
    s_terms = _terms(rule["any"], strong)
    w_terms = _terms(rule["any"], weak) - s_terms
    score = STRONG_WEIGHT * len(s_terms) + WEAK_WEIGHT * min(WEAK_CAP, len(w_terms))
    return score, sorted(s_terms) + [t + " (description)" for t in sorted(w_terms)]


def infer(strong_text, weak_text=""):
    """Return ranked inference candidates (best first)."""
    strong = str(strong_text or "")
    weak = str(weak_text or "")
    scored = []
    for order, rule in enumerate(RULES):
        score, evidence = _score_rule(rule, strong, weak)
        if score >= MIN_SCORE:
            scored.append({"rule": rule, "score": score, "evidence": evidence, "order": order})
    # A narrower number with real (title/subject) evidence replaces its broader parent.
    strong_children = [c for c in scored if c["score"] >= STRONG_WEIGHT]
    keep = []
    for c in scored:
        n = c["rule"]["number"]
        superseded = any(
            o is not c and o["rule"]["number"] != n
            and _stem(n) and _stem(o["rule"]["number"]).startswith(_stem(n))
            for o in strong_children
        )
        if not superseded:
            keep.append(c)
    keep.sort(key=lambda c: (-c["score"], -len(c["rule"]["number"]), c["order"]))
    return keep


# ---------------------------------------------------------------------------
# CALL NUMBER
# ---------------------------------------------------------------------------

_PARTICLES = {"van", "von", "de", "der", "den", "la", "le", "da", "di", "al", "el", "bin", "wa", "ibn"}


def author_mark(name):
    """Basic 3-letter author mark.  NOT a full Cutter number."""
    name = str(name or "").strip()
    if not name:
        return "XXX"
    if "," in name:
        surname = name.split(",", 1)[0]
    else:
        parts = [p for p in re.split(r"\s+", name) if p]
        parts = [p for p in parts if re.sub(r"[^A-Za-z]", "", p)]
        # drop trailing suffixes such as Jr./III
        while len(parts) > 1 and re.fullmatch(r"(?i)jr\.?|sr\.?|ii|iii|iv", parts[-1]):
            parts.pop()
        surname = parts[-1] if parts else ""
    cleaned = re.sub(r"[^A-Za-z]", "", surname)
    return (cleaned[:3] or "XXX").upper()


def source_call_number(book):
    values = book.get("source_call_numbers") or []
    if values:
        first = values[0]
        if isinstance(first, dict):
            return first.get("value"), first.get("source")
        return str(first), book.get("call_number_source")
    cn = book.get("call_number")
    if isinstance(cn, dict):
        cn = cn.get("value")
    return (str(cn).strip(), book.get("call_number_source")) if cn else (None, None)


# ---------------------------------------------------------------------------
# MAIN ENTRY
# ---------------------------------------------------------------------------

def _subject_terms(book, limit=12):
    seen, out = set(), []
    for s in book.get("subject") or []:
        s = str(s).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
        if len(out) >= limit:
            break
    return out


def classify(book):
    book = book or {}
    terms = _subject_terms(book)
    strong_text = " ".join([str(book.get("title") or "")] + terms)
    weak_text = " ".join(
        [str(book.get("description") or "")] + [str(x) for x in (book.get("first_sentence") or [])]
    )
    ranked = infer(strong_text, weak_text)
    top = ranked[0] if ranked else None

    candidates = book.get("source_ddcs")
    if candidates is None:
        candidates = book.get("classification_candidates") or book.get("ddc") or []
    chosen, all_valid = choose_source_ddc(candidates)

    notes = []
    conflict = None
    alternatives = []

    def alt(c):
        return {"number": c["rule"]["number"], "subject": c["rule"]["subject"],
                "evidence": c["evidence"], "score": c["score"]}

    if chosen:
        number = chosen["number"]
        caption, exact = caption_for(number)
        classification = {
            "system": "DDC", "number": number, "provenance": "source_record",
            "source": chosen.get("source") or book.get("source"),
            "confidence": "source_supplied", "review_required": True,
            "evidence": ["DDC number supplied by the bibliographic source"],
        }
        subject = caption or "Subject requires librarian review"
        if caption and not exact:
            notes.append("Caption shown is the nearest broader DDC caption; the exact number "
                         "is a source subdivision to verify in the DDC schedule.")
        if len({c["number"] for c in all_valid}) > 1:
            notes.append("Sources supplied several DDC numbers: "
                         + ", ".join(sorted({c["number"] for c in all_valid})) + ".")
        # score >= STRONG_WEIGHT means at least one title/subject hit (description alone maxes at 6)
        if top and top["score"] >= STRONG_WEIGHT and not related(number, top["rule"]["number"]):
            conflict = {
                "message": "The record's subject evidence points to a different area than the "
                           "source DDC. The source number is kept; check the record.",
                "inferred_number": top["rule"]["number"],
                "inferred_subject": top["rule"]["subject"],
                "evidence": top["evidence"],
            }
        lcsh_terms = terms[:5]
        note = None
    elif top:
        rule = top["rule"]
        number = rule["number"]
        subject_text = rule["subject"]
        lcsh_list = list(rule["lcsh"])
        area = detect_area(strong_text)
        if area and re.fullmatch(r"[1-7]\d\d", number):
            number = number[:3] + ".9" + area["notation"]
            subject_text = f"{rule['subject']} — {area['name']}"
            lcsh_list = [f"{rule['lcsh'][0]} -- {area['name']}"] + lcsh_list
            notes.append(f"Geographic treatment: {area['name']} (area notation −{area['notation']}) was added "
                         f"to {rule['number']}. Verify against DDC standard subdivision −09 and Table 2.")
        margin = top["score"] - (ranked[1]["score"] if len(ranked) > 1 else 0)
        strong_hit = top["score"] >= STRONG_WEIGHT
        confidence = "medium" if (top["score"] >= 2 * STRONG_WEIGHT and margin >= STRONG_WEIGHT) else "low"
        if not strong_hit:
            notes.append("Evidence comes only from the description; treat as a weak suggestion.")
        classification = {
            "system": "DDC", "number": number, "provenance": "inferred",
            "source": "Local classification engine", "confidence": confidence,
            "review_required": True, "evidence": top["evidence"],
        }
        subject = subject_text
        alternatives = [alt(c) for c in ranked[1:4]]
        lcsh_terms = lcsh_list
        note = rule.get("note")
        if note:
            notes.append(note)
        notes.append("Inferred from title/subject keywords, not supplied by a source. Verify against DDC.")
    else:
        number = None
        classification = {
            "system": "DDC", "number": None, "provenance": "none", "source": None,
            "confidence": "none", "review_required": True, "evidence": [],
        }
        subject = "General / needs review"
        lcsh_terms = terms[:5]
        notes.append("No dominant subject could be established; no number was assumed.")

    cn_value, cn_source = source_call_number(book)
    first_author = (book.get("author_name") or [None])[0]
    suggested = None
    if number:
        suggested = {"value": f"{number} {author_mark(first_author)}", "type": "generated_suggestion",
                     "note": "Basic author mark; not a full Cutter number or a library-assigned call number."}

    rtype = str(book.get("type") or "")
    if book.get("metadata_type") == "scholarly_bibliographic_record" and rtype and "book" not in rtype:
        material = "Scholarly work (not a library holding record)"
    elif number and re.match(r"8\d\d", number):
        material = "Fiction / Literature"
    elif top and top["rule"]["number"] == "800" and not chosen:
        material = "Fiction / Literature"
    else:
        material = "Non-fiction"

    return {
        "classification": classification,
        "primary_subject": subject,
        "source_subject_terms": terms,
        "lcsh_terms": lcsh_terms,
        "shelf": shelf_for(number) if number else "Librarian review required",
        "alternatives": alternatives,
        "conflict": conflict,
        "notes": notes,
        "material_type": material,
        "call_number": {"value": cn_value, "source": cn_source,
                        "type": "source_record" if cn_value else "not_available"},
        "suggested_call_number": suggested,
        "lc_classifications": book.get("lcc") or [],
    }
