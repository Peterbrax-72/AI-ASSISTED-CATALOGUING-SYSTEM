from flask import Flask, jsonify, request, send_from_directory, abort, Response
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import copy
import os
import re
import time

import requests

import classifier

BASE = Path(__file__).resolve().parent

# Only these files may be fetched under /static/. The project folder also holds
# server.py and classifier.py, which must never be served to browsers.
STATIC_FILES = {"app.js", "style.css", "theme.css"}

app = Flask(__name__, static_folder=None)

# =========================================================
# CONFIGURATION
# =========================================================

HEADERS = {
    "User-Agent": "UniversalCatalogingAssistant/6.1 (educational library cataloging prototype)",
    "Accept": "application/json",
}

CACHE_TTL = 900  # 15 minutes
MAX_RESULTS_PER_SOURCE = 8
MAX_RESULTS_RETURNED = 20

session = requests.Session()
session.trust_env = False
session.headers.update(HEADERS)

_cache = {}
_cache_lock = Lock()


def cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        if time.time() - item["time"] > CACHE_TTL:
            _cache.pop(key, None)
            return None
        return copy.deepcopy(item["value"])


def cache_set(key, value):
    with _cache_lock:
        _cache[key] = {"time": time.time(), "value": copy.deepcopy(value)}


# =========================================================
# ERRORS: a failed API call is never a "zero results" search
# =========================================================

class SourceError(Exception):
    """kind: timeout | network | quota | auth | http_error | invalid_response"""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def request_json(url, params=None, timeout=8):
    try:
        response = session.get(url, params=params or {}, timeout=timeout)
    except requests.Timeout as exc:
        raise SourceError("timeout", f"Request timed out after {timeout}s") from exc
    except requests.RequestException as exc:
        raise SourceError("network", f"Network error: {exc.__class__.__name__}") from exc

    code = response.status_code
    if code == 429:
        raise SourceError("quota", "Quota or rate limit reached (HTTP 429)")
    if code in (401, 403):
        raise SourceError("auth", f"Authentication/authorisation refused (HTTP {code})")
    if code >= 400:
        raise SourceError("http_error", f"HTTP {code}")
    try:
        return response.json()
    except ValueError as exc:
        raise SourceError("invalid_response", "Response was not valid JSON") from exc


def expect_dict(raw):
    if not isinstance(raw, dict):
        raise SourceError("invalid_response", "Unexpected response structure")
    return raw


# =========================================================
# HELPERS
# =========================================================

def normalize_query(q):
    return re.sub(r"[^a-z0-9 ]+", " ", str(q or "").lower()).strip()


def collapse(q):
    return re.sub(r"\s+", " ", normalize_query(q))


def text_of(value):
    """Flatten strings / {'value': ...} / lists into one clean string."""
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value") or value.get("label")
    if isinstance(value, list):
        return text_of(value[0] if value else None)
    value = re.sub(r"<[^>]+>", " ", str(value or ""))  # Crossref abstracts are JATS XML
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if x not in (None, "")]
    return [str(value)]


def unique(values):
    seen, result = set(), []
    for value in values:
        value = str(value).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return result


def unique_names(values):
    """Dedupe author names ignoring case, spacing and initials punctuation ("J. E. Webb" = "J.E. Webb")."""
    seen, result = set(), []
    for value in values:
        value = str(value).strip()
        key = re.sub(r"[^a-z]", "", value.lower())
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def first_value(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


# ---- ISBN ------------------------------------------------------------------

def clean_isbn(value):
    s = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return s if len(s) in (10, 13) else None


def to_isbn13(value):
    s = clean_isbn(value)
    if not s:
        return None
    if len(s) == 13:
        return s
    core = "978" + s[:9]
    if not core.isdigit():
        return None
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(core))
    return core + str((10 - total % 10) % 10)


def is_isbn_query(q):
    s = re.sub(r"[\s-]", "", str(q or ""))
    return bool(re.fullmatch(r"(?:\d{9}[\dXx]|\d{13})", s))


def extract_ddc_candidates(*values):
    out = []
    for value in values:
        for item in as_list(value):
            ddc = classifier.normalize_ddc(item)
            if ddc:
                out.append(ddc)
    return unique(out)


# =========================================================
# RECORD CONSTRUCTION AND MERGING
# =========================================================

def make_doc(source, **fields):
    """Build a normalized record. Provenance is attached per source."""
    ddcs = fields.pop("ddc", [])
    call_number = fields.pop("call_number", None)
    lcc = fields.pop("lc_classifications", [])
    doc = {
        "key": None, "title": "Untitled", "author_name": [], "first_publish_year": None,
        "subject": [], "scholarly_subjects": [], "isbn": [], "publisher": [], "language": [],
        "description": None, "first_sentence": [], "number_of_pages": None,
        "cover_i": None, "doi": None, "url": None,
    }
    doc.update(fields)
    doc["source"] = source
    doc["sources"] = [source]
    doc["ddc"] = ddcs
    doc["source_ddcs"] = [{"number": n, "source": source} for n in ddcs]
    doc["classification_candidates"] = ddcs
    doc["lcc"] = [{"number": n, "source": source} for n in lcc]
    doc["source_call_numbers"] = (
        [{"value": call_number, "source": source}] if call_number else []
    )
    doc["call_number"] = call_number
    doc["call_number_source"] = source if call_number else None
    return doc


def _surname(name):
    name = str(name or "").strip()
    if "," in name:
        name = name.split(",", 1)[0]
    else:
        parts = name.split()
        name = parts[-1] if parts else ""
    return normalize_query(name)


def _main_title(title):
    t = re.split(r"\s[:–—-]\s|:", str(title or ""), maxsplit=1)[0]
    return collapse(t)


def _year(book):
    m = re.match(r"\d{4}", str(book.get("first_publish_year") or ""))
    return int(m.group(0)) if m else None


def _identifiers(book):
    ids = set()
    for i in as_list(book.get("isbn")):
        n = to_isbn13(i)
        if n:
            ids.add("isbn:" + n)
    if book.get("doi"):
        ids.add("doi:" + str(book["doi"]).lower())
    return ids


def _title_key(book):
    t = _main_title(book.get("title"))
    authors = book.get("author_name") or []
    a = _surname(authors[0]) if authors else ""
    return (t, a) if t and a else None


def _articleish(book):
    t = str(book.get("type") or "").lower()
    return (book.get("metadata_type") == "scholarly_bibliographic_record"
            and (not t or t in SCHOLARLY_ARTICLE_TYPES or "chapter" in t))


def _compatible(a, b):
    """Same work? Identifiers decide; otherwise main title + author + non-conflicting year."""
    if _identifiers(a) & _identifiers(b):
        return True
    # A journal article / book chapter is not the book, even with a similar title and author.
    if _articleish(a) != _articleish(b):
        return False
    ka, kb = _title_key(a), _title_key(b)
    if not ka or ka != kb:
        return False
    ya, yb = _year(a), _year(b)
    return ya is None or yb is None or ya == yb


def _merge_into(base, other):
    base["author_name"] = unique_names(as_list(base.get("author_name")) + as_list(other.get("author_name")))
    for field in ("subject", "scholarly_subjects", "isbn", "publisher", "language", "first_sentence"):
        base[field] = unique(as_list(base.get(field)) + as_list(other.get(field)))
    for field in ("first_publish_year", "number_of_pages", "cover_i", "doi", "url", "type",
                  "container_title", "volume", "issue", "page", "metadata_type"):
        if base.get(field) in (None, "", []) and other.get(field) not in (None, "", []):
            base[field] = other[field]
    if not base.get("description") and other.get("description"):
        base["description"] = other["description"]
    for field, key in (("source_ddcs", ("number", "source")), ("lcc", ("number", "source")),
                       ("source_call_numbers", ("value", "source"))):
        seen = {tuple(x.get(k) for k in key) for x in base.get(field, [])}
        for x in other.get(field, []):
            sig = tuple(x.get(k) for k in key)
            if sig not in seen:
                base.setdefault(field, []).append(x)
                seen.add(sig)
    base["sources"] = unique(base.get("sources", []) + other.get("sources", []))
    base["source"] = " + ".join(base["sources"])
    base["ddc"] = unique([x["number"] for x in base.get("source_ddcs", [])])
    base["classification_candidates"] = base["ddc"]
    cns = base.get("source_call_numbers", [])
    base["call_number"] = cns[0]["value"] if cns else None
    base["call_number_source"] = cns[0]["source"] if cns else None
    base["merged_from"] = base.get("merged_from", 1) + other.get("merged_from", 1)
    return base


def merge_docs(groups):
    """Merge compatible records from all sources, keeping every source's data."""
    clusters = []
    for group in groups:
        for book in group:
            book = copy.deepcopy(book)
            book.setdefault("merged_from", 1)
            for cluster in clusters:
                if _compatible(cluster, book):
                    _merge_into(cluster, book)
                    break
            else:
                clusters.append(book)
    return clusters


def source_result(name, status="ok", count=0, error=None, kind=None):
    item = {"name": name, "status": status, "count": count}
    if error:
        item["error"] = str(error)
    if kind:
        item["error_kind"] = kind
    return item


# =========================================================
# LOCAL FALLBACK (search text only, clearly synthetic)
# =========================================================

def local_record(query):
    title = query.strip() or "Untitled"
    return {
        "key": "local:" + normalize_query(query).replace(" ", "-"),
        "title": title, "author_name": [], "first_publish_year": None,
        "subject": [], "isbn": [], "publisher": [], "language": [],
        "description": None, "first_sentence": [], "number_of_pages": None,
        "cover_i": None, "source": "Local classification fallback",
        "sources": ["Local classification fallback"],
        "ddc": [], "source_ddcs": [], "classification_candidates": [],
        "lcc": [], "source_call_numbers": [], "call_number": None,
        "call_number_source": None, "synthetic": True,
        "classification_provenance": "inferred_from_query",
    }


# =========================================================
# SOURCES
# =========================================================

def open_library_search(q):
    cache_key = "openlibrary:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    raw = expect_dict(request_json(
        "https://openlibrary.org/search.json",
        params={
            "q": q, "limit": MAX_RESULTS_PER_SOURCE,
            "fields": ("key,title,author_name,first_publish_year,subject,ddc,isbn,publisher,"
                       "language,first_sentence,number_of_pages_median,cover_i,lc_classifications"),
        },
        timeout=7,
    ))
    if not isinstance(raw.get("docs", []), list):
        raise SourceError("invalid_response", "Unexpected 'docs' structure")

    docs = []
    for book in raw.get("docs", []):
        docs.append(make_doc(
            "Open Library",
            key=book.get("key"),
            title=book.get("title") or "Untitled",
            author_name=as_list(book.get("author_name")),
            first_publish_year=book.get("first_publish_year"),
            subject=as_list(book.get("subject")),
            ddc=extract_ddc_candidates(book.get("ddc")),
            isbn=as_list(book.get("isbn"))[:20],
            publisher=as_list(book.get("publisher"))[:10],
            language=as_list(book.get("language")),
            description=text_of(book.get("description")),
            first_sentence=as_list(book.get("first_sentence")),
            number_of_pages=book.get("number_of_pages_median"),
            cover_i=book.get("cover_i"),
            lc_classifications=as_list(book.get("lc_classifications")),
        ))
    result = {"numFound": raw.get("numFound", len(docs)), "docs": docs}
    cache_set(cache_key, result)
    return result


def loc_search(q):
    cache_key = "loc:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    raw = expect_dict(request_json(
        "https://www.loc.gov/books/",
        params={"q": q, "fo": "json", "c": MAX_RESULTS_PER_SOURCE},
        timeout=8,
    ))
    items = raw.get("results", [])
    if not isinstance(items, list):
        raise SourceError("invalid_response", "Unexpected 'results' structure")

    docs = []
    for item in items[:MAX_RESULTS_PER_SOURCE]:
        if not isinstance(item, dict):
            continue
        title = first_value(item.get("title")) or item.get("title_s") or "Untitled"
        authors = as_list(item.get("contributor_names") or item.get("contributor"))
        date_value = first_value(item.get("date")) or first_value(item.get("date_s"))
        subjects = as_list(item.get("subject")) + as_list(item.get("subject_headings"))
        ddc = extract_ddc_candidates(item.get("ddc"), item.get("dewey_decimal_classification"),
                                     item.get("082"))
        call_number = None
        for value in (item.get("call_number"), item.get("callNumber"),
                      item.get("lc_call_number"), item.get("lc_callnumber")):
            value = text_of(value)
            if value:
                call_number = value
                break
        docs.append(make_doc(
            "Library of Congress",
            key=item.get("id") or ("loc:" + normalize_query(str(title))),
            title=str(title),
            author_name=unique(authors),
            first_publish_year=str(date_value)[:4] if date_value else None,
            subject=unique(subjects),
            ddc=ddc,
            isbn=as_list(item.get("isbn")),
            publisher=as_list(item.get("publisher")),
            language=as_list(item.get("language")),
            description=text_of(item.get("description")),
            call_number=call_number,
            url=item.get("url") or item.get("id"),
        ))
    result = {"numFound": (raw.get("pagination") or {}).get("total", len(docs)), "docs": docs}
    cache_set(cache_key, result)
    return result


def openalex_search(q):
    cache_key = "openalex:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    raw = expect_dict(request_json(
        "https://api.openalex.org/works",
        params={
            "search": q, "per-page": MAX_RESULTS_PER_SOURCE,
            "select": "id,display_name,publication_year,authorships,topics,keywords,type,doi",
        },
        timeout=8,
    ))
    docs = []
    for item in raw.get("results", []) or []:
        authors = [(a.get("author") or {}).get("display_name") for a in item.get("authorships", []) or []]
        subjects = [t.get("display_name") for t in item.get("topics", []) or []]
        subjects += [k.get("display_name") for k in item.get("keywords", []) or []]
        doi = item.get("doi")
        if doi:
            doi = re.sub(r"^https?://doi.org/", "", doi)
        docs.append(make_doc(
            "OpenAlex",
            key=item.get("id") or ("openalex:" + normalize_query(item.get("display_name", ""))),
            title=item.get("display_name") or "Untitled",
            author_name=unique([a for a in authors if a]),
            first_publish_year=item.get("publication_year"),
            scholarly_subjects=unique([s for s in subjects if s]),
            doi=doi, type=item.get("type"),
            metadata_type="scholarly_bibliographic_record",
        ))
    result = {"numFound": (raw.get("meta") or {}).get("count", len(docs)), "docs": docs}
    cache_set(cache_key, result)
    return result


def crossref_search(q):
    cache_key = "crossref:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    # No field restriction: Crossref returns abstract, URL, container title, etc.
    raw = expect_dict(request_json(
        "https://api.crossref.org/v1/works",
        params={"query.bibliographic": q, "rows": MAX_RESULTS_PER_SOURCE},
        timeout=8,
    ))
    message = expect_dict(raw.get("message", {}))
    docs = []
    for item in message.get("items", []) or []:
        titles = as_list(item.get("title"))
        title = titles[0] if titles else "Untitled"
        authors = []
        for author in item.get("author", []) or []:
            name = " ".join(str(x).strip() for x in (author.get("given"), author.get("family")) if x).strip()
            name = name or str(author.get("name") or "").strip()
            if name:
                authors.append(name)
        published = (item.get("published-print") or item.get("published-online")
                     or item.get("published") or item.get("issued") or {})
        parts = published.get("date-parts") or []
        year = parts[0][0] if parts and parts[0] else None
        doi = item.get("DOI")
        doc = make_doc(
            "Crossref",
            key=doi or ("crossref:" + normalize_query(title)),
            title=title, author_name=unique(authors), first_publish_year=year,
            scholarly_subjects=unique(as_list(item.get("subject"))),
            isbn=unique(as_list(item.get("ISBN"))),
            publisher=as_list(item.get("publisher")),
            language=as_list(item.get("language")),
            description=text_of(item.get("abstract")),
            doi=doi, url=item.get("URL") or ("https://doi.org/" + doi if doi else None),
            type=item.get("type"),
            container_title=as_list(item.get("container-title")),
            volume=item.get("volume"), issue=item.get("issue"), page=item.get("page"),
            metadata_type="scholarly_bibliographic_record",
        )
        doc["classification_provenance"] = "not_available_from_crossref"
        doc["call_number_provenance"] = "not_available_from_crossref"
        docs.append(doc)
    result = {"numFound": message.get("total-results", len(docs)), "docs": docs}
    cache_set(cache_key, result)
    return result


def google_books_search(q):
    cache_key = "googlebooks:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    raw = expect_dict(request_json(
        "https://www.googleapis.com/books/v1/volumes",
        params={"q": q, "maxResults": MAX_RESULTS_PER_SOURCE},
        timeout=8,
    ))
    docs = []
    for item in raw.get("items", []) or []:
        volume = item.get("volumeInfo", {}) or {}
        isbn = [x.get("identifier") for x in (volume.get("industryIdentifiers") or [])
                if x.get("identifier") and str(x.get("type", "")).startswith("ISBN")]
        published = volume.get("publishedDate") or ""
        docs.append(make_doc(
            "Google Books",
            key=item.get("id"),
            title=" : ".join(x for x in (volume.get("title"), volume.get("subtitle")) if x) or "Untitled",
            author_name=as_list(volume.get("authors")),
            first_publish_year=published[:4] if published else None,
            subject=as_list(volume.get("categories")),
            isbn=isbn, publisher=as_list(volume.get("publisher")),
            language=as_list(volume.get("language")),
            description=text_of(volume.get("description")),
            number_of_pages=volume.get("pageCount"),
        ))
    result = {"numFound": raw.get("totalItems", len(docs)), "docs": docs}
    cache_set(cache_key, result)
    return result


# =========================================================
# QUERY VARIANTS AND RANKING
# =========================================================

def query_variants(name, q):
    original = str(q or "").strip()
    normalized = collapse(original)
    if is_isbn_query(original):
        isbn = re.sub(r"[\s-]", "", original)
        return [f"isbn:{isbn}"] if name in ("Open Library", "Google Books") else [isbn]

    variants = [original]
    if normalized and normalized.lower() != original.lower():
        variants.append(normalized)
    if " by " in normalized:
        title_part = normalized.split(" by ", 1)[0].strip()
        if title_part:
            variants.append(title_part)
    if name == "Open Library" and len(normalized.split()) >= 3:
        variants.append("title:" + " ".join(normalized.split()[:8]))  # only Open Library understands this
    return unique(variants)[:4]


SCHOLARLY_ARTICLE_TYPES = {
    "article", "journal-article", "proceedings-article", "posted-content", "dissertation",
    "peer-review", "preprint", "review", "report", "dataset", "paratext", "editorial", "letter",
}


def search_relevance(book, query):
    q = collapse(query)
    words = set(q.split())
    title = collapse(book.get("title"))
    authors = collapse(" ".join(as_list(book.get("author_name"))))
    subjects = collapse(" ".join(as_list(book.get("subject"))))
    score = 0

    if is_isbn_query(query):
        target = to_isbn13(query)
        if target and target in {to_isbn13(i) for i in as_list(book.get("isbn"))}:
            score += 20000

    main_title = _main_title(book.get("title"))
    if q and (title == q or main_title == q):
        score += 5000
    elif q and q in title:
        score += 3000

    title_words = set(title.split())
    overlap = len(words & title_words)
    score += overlap * 250
    if words:
        score += int((overlap / len(words)) * 1000)

    if q and q in authors:
        score += 1500
    score += len(words & set(authors.split())) * 80
    if q and q in subjects:
        score += 250
    score += len(words & set(subjects.split())) * 20

    # Journal articles only share words with a book title; keep them below books.
    if str(book.get("type") or "").lower() in SCHOLARLY_ARTICLE_TYPES and title != q:
        score -= 1500
    # Records carrying real cataloguing data are more useful to a cataloguer.
    if book.get("source_ddcs"):
        score += 120
    if book.get("isbn"):
        score += 40
    score += 10 * (len(book.get("sources", [])) - 1)

    source_bonus = {"library of congress": 40, "open library": 35, "google books": 30,
                    "crossref": 10, "openalex": 5}
    primary = str((book.get("sources") or [book.get("source", "")])[0]).lower()
    score += source_bonus.get(primary, 0)
    return score


# =========================================================
# SEARCH API
# =========================================================

SERVICES = [
    ("Open Library", open_library_search),
    ("Library of Congress", loc_search),
    ("OpenAlex", openalex_search),
    ("Crossref", crossref_search),
    ("Google Books", google_books_search),
]
SKIP_FOR_ISBN = {"OpenAlex", "Crossref"}


def run_service(name, function, query):
    """Run one source. Returns (docs, status_dict, error_text)."""
    if is_isbn_query(query) and name in SKIP_FOR_ISBN:
        return [], source_result(name, "skipped", 0, "Scholarly source not used for ISBN searches"), None

    docs, failure = [], None
    for variant in query_variants(name, query):
        try:
            result = function(variant)
        except SourceError as exc:
            failure = exc
            break  # do not keep hammering a failing source
        except Exception as exc:  # defensive: unexpected parsing problem
            failure = SourceError("invalid_response", f"Could not read response: {exc.__class__.__name__}")
            break
        found = result.get("docs", [])
        if found:
            docs.extend(found)
            break

    if docs:
        docs = merge_docs([docs])
        return docs, source_result(name, "ok", len(docs)), None
    if failure:
        return [], source_result(name, "failed", 0, failure, failure.kind), f"{name}: {failure}"
    return [], source_result(name, "no_results", 0), None


@app.get("/api/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"numFound": 0, "docs": [], "sources": [], "errors": [], "fallback": False,
                        "message": "Enter a title, author, ISBN, or topic."})

    with ThreadPoolExecutor(max_workers=len(SERVICES)) as pool:
        futures = [(name, pool.submit(run_service, name, fn, query)) for name, fn in SERVICES]
        outcomes = [(name, f.result()) for name, f in futures]

    groups, sources, errors = [], [], []
    for _, (docs, status, error) in outcomes:
        sources.append(status)
        if docs:
            groups.append(docs)
        if error:
            errors.append(error)

    docs = merge_docs(groups)
    docs.sort(key=lambda b: search_relevance(b, query), reverse=True)
    docs = docs[:MAX_RESULTS_RETURNED]

    attempted = [s for s in sources if s["status"] != "skipped"]
    all_failed = bool(attempted) and all(s["status"] == "failed" for s in attempted)
    some_failed = any(s["status"] == "failed" for s in sources)

    if not docs:
        if all_failed:
            message = ("Every bibliographic source failed, so this is NOT an empty result. "
                       "Check the connection or source status below.")
        elif some_failed:
            message = ("No records were returned and some sources failed, so the search may be "
                       "incomplete. A query-based suggestion is shown instead.")
        else:
            message = "No external bibliographic record was found. A query-based suggestion is shown."
        return jsonify({
            "numFound": 1, "docs": [local_record(query)], "source": "Local classification fallback",
            "fallback": True, "all_sources_failed": all_failed, "message": message,
            "sources": sources, "errors": errors,
        })

    return jsonify({
        "numFound": len(docs), "docs": docs, "source": "Multi-source V6", "fallback": False,
        "all_sources_failed": False, "sources": sources, "errors": errors,
        "message": ("Some sources failed; results may be incomplete." if some_failed else None),
    })


# =========================================================
# CLASSIFICATION API (single source of truth)
# =========================================================

@app.post("/api/classify")
def classify_route():
    book = request.get_json(silent=True)
    if not isinstance(book, dict):
        return jsonify({"error": "Send a JSON record in the request body."}), 400
    return jsonify(classifier.classify(book))


# =========================================================
# LCSH AUTHORITY SEARCH
# =========================================================

def parse_lcsh(raw):
    """id.loc.gov suggest returns [query, [labels], [notes], [uris]] (OpenSearch)."""
    headings = []
    if isinstance(raw, list) and len(raw) >= 2 and isinstance(raw[1], list):
        uris = raw[3] if len(raw) >= 4 and isinstance(raw[3], list) else []
        for i, label in enumerate(raw[1]):
            headings.append({"label": str(label), "uri": uris[i] if i < len(uris) else None})
        return headings
    candidates = []
    if isinstance(raw, dict):
        candidates = raw.get("suggestions") or raw.get("results") or []
    elif isinstance(raw, list):
        candidates = raw
    for item in candidates:
        if isinstance(item, str):
            headings.append({"label": item, "uri": None})
        elif isinstance(item, dict):
            value = item.get("label") or item.get("term") or item.get("title")
            if value:
                headings.append({"label": str(value), "uri": item.get("uri")})
    return headings


@app.get("/api/lcsh")
def lcsh():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"query": "", "headings": [], "source": "Library of Congress"})
    try:
        raw = request_json("https://id.loc.gov/authorities/subjects/suggest/",
                           params={"q": query, "count": 8}, timeout=8)
        seen, headings = set(), []
        for h in parse_lcsh(raw):
            if h["label"].lower() not in seen:
                seen.add(h["label"].lower())
                headings.append(h)
        return jsonify({
            "query": query,
            "headings": [h["label"] for h in headings[:8]],
            "authority": headings[:8],
            "verification": "authority_candidate_unverified",
            "source": "Library of Congress Linked Data Service",
        })
    except SourceError as exc:
        return jsonify({"query": query, "headings": [], "source": "Library of Congress",
                        "error": str(exc), "error_kind": exc.kind})


# =========================================================
# HEALTH, STATIC, HOME
# =========================================================

@app.get("/health")
def health():
    return jsonify({
        "status": "ok", "version": "6.1", "build": "2026-11-14b", "backend": "Flask",
        "search": "/api/search", "classify": "/api/classify", "lcsh": "/api/lcsh",
        "catalog_sources": [n for n, _ in SERVICES] + ["Local classification fallback"],
        "authority_source": "Library of Congress Linked Data Service",
        "cache_ttl_seconds": CACHE_TTL,
    })


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/static/<path:name>")
def static_files(name):
    if name not in STATIC_FILES:
        abort(404)
    return send_from_directory(BASE, name)


@app.get("/favicon.ico")
def favicon():
    return Response(status=204)


@app.get("/")
def home():
    return send_from_directory(BASE, "index.html")


if __name__ == "__main__":
    # Local use only. Set UCA_DEBUG=1 for the debugger (never on a shared network)
    # and UCA_HOST=0.0.0.0 only if you deliberately want LAN access.
    app.run(
        host=os.environ.get("UCA_HOST", "127.0.0.1"),
        port=int(os.environ.get("UCA_PORT", "5000")),
        debug=os.environ.get("UCA_DEBUG") == "1",
    )
