from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path
import requests
import re
import time
from threading import Lock

BASE = Path(__file__).resolve().parent

app = Flask(
    __name__,
    static_folder=str(BASE),
    static_url_path="/static"
)

# =========================================================
# V6 CONFIGURATION
# =========================================================

HEADERS = {
    "User-Agent": "UniversalCatalogingAssistant/6.0 (educational library cataloging prototype)",
    "Accept": "application/json",
}

CACHE_TTL = 900  # 15 minutes
MAX_RESULTS_PER_SOURCE = 8

session = requests.Session()
session.trust_env = False
session.headers.update(HEADERS)

_cache = {}
_cache_lock = Lock()


# =========================================================
# CACHE
# =========================================================

def cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        if time.time() - item["time"] > CACHE_TTL:
            _cache.pop(key, None)
            return None
        return item["value"]


def cache_set(key, value):
    with _cache_lock:
        _cache[key] = {
            "time": time.time(),
            "value": value,
        }


# =========================================================
# HELPERS
# =========================================================

def normalize_query(q):
    return re.sub(r"[^a-z0-9 ]+", " ", str(q or "").lower()).strip()


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x) for x in value if x not in (None, "")]
    return [str(value)]


def unique(values):
    seen = set()
    result = []
    for value in values:
        value = str(value).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return result


def first_value(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def merge_docs(groups):
    seen = set()
    merged = []

    for group in groups:
        for book in group:
            title = book.get("title", "")
            authors = book.get("author_name", [])
            author_text = " ".join(as_list(authors))

            key = (
                book.get("isbn", [None])[0]
                if book.get("isbn")
                else None
            )

            if not key:
                key = (
                    normalize_query(title)
                    + "|"
                    + normalize_query(author_text)
                )

            if key in seen:
                continue

            seen.add(key)
            merged.append(book)

    return merged


def request_json(url, params=None, timeout=8):
    response = session.get(
        url,
        params=params or {},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json(), response


def source_result(name, status="ok", count=0, error=None):
    item = {
        "name": name,
        "status": status,
        "count": count,
    }
    if error:
        item["error"] = str(error)
    return item


# =========================================================
# LOCAL CLASSIFICATION FALLBACK
# =========================================================

RULES = [
    (
        re.compile(r"library|cataloging|cataloguing|librarianship|information science", re.I),
        {
            "subject": "Library & Information Science",
            "ddc": ["020"],
            "lcsh": ["Libraries", "Library science", "Information science"],
            "shelf": "000–099 • General Works / Library & Information Science",
        },
    ),
    (
        re.compile(r"computer|programming|software|information technology|ict|python|javascript|coding|web development", re.I),
        {
            "subject": "Computer Science & Information Technology",
            "ddc": ["004–006"],
            "lcsh": ["Computer science", "Information technology"],
            "shelf": "000–099 • General Works / Computing",
        },
    ),
    (
        re.compile(r"economics|finance|banking|business|accounting|entrepreneur|marketing|management", re.I),
        {
            "subject": "Economics / Business",
            "ddc": ["330"],
            "lcsh": ["Economics", "Finance", "Business"],
            "shelf": "300–399 • Social Sciences",
        },
    ),
    (
        re.compile(r"education|teaching|teacher|school|learning|curriculum", re.I),
        {
            "subject": "Education",
            "ddc": ["370"],
            "lcsh": ["Education", "Teaching"],
            "shelf": "300–399 • Social Sciences",
        },
    ),
    (
        re.compile(r"psychology|behavior|behaviour|personality|mindset|mental", re.I),
        {
            "subject": "Psychology",
            "ddc": ["150"],
            "lcsh": ["Psychology", "Behavior"],
            "shelf": "100–199 • Philosophy & Psychology",
        },
    ),
    (
        re.compile(r"self-help|success|motivation|personal development|leadership|achievement|confidence|habits", re.I),
        {
            "subject": "Self-help / Personal Development",
            "ddc": ["158.1"],
            "lcsh": ["Self-help techniques", "Success", "Personal development"],
            "shelf": "100–199 • Philosophy & Psychology",
        },
    ),
    (
        re.compile(r"fiction|novel|poetry|poems|short stories|literature", re.I),
        {
            "subject": "Literature / Fiction",
            "ddc": ["800"],
            "lcsh": ["Literature", "Fiction"],
            "shelf": "800–899 • Literature",
        },
    ),
    (
        re.compile(r"history|civilization|war|colonial|independence|historical", re.I),
        {
            "subject": "History",
            "ddc": ["900"],
            "lcsh": ["History", "Civilization"],
            "shelf": "900–999 • History & Geography",
        },
    ),
    (
        re.compile(r"africa|kenya|kenyan|east africa|ethiopia|uganda|tanzania", re.I),
        {
            "subject": "Africa / Regional Studies",
            "ddc": ["960"],
            "lcsh": ["Africa", "Africa—History"],
            "shelf": "900–999 • History & Geography",
        },
    ),
    (
        re.compile(r"religion|christian|church|bible|theology|islam|muslim", re.I),
        {
            "subject": "Religion",
            "ddc": ["200"],
            "lcsh": ["Religion", "Christianity"],
            "shelf": "200–299 • Religion",
        },
    ),
    (
        re.compile(r"science|physics|chemistry|biology|astronomy|geology", re.I),
        {
            "subject": "Science",
            "ddc": ["500"],
            "lcsh": ["Science"],
            "shelf": "500–599 • Science",
        },
    ),
    (
        re.compile(r"medicine|medical|health|nursing|disease|clinical", re.I),
        {
            "subject": "Medicine / Health",
            "ddc": ["610"],
            "lcsh": ["Medicine", "Health"],
            "shelf": "600–699 • Technology / Medicine",
        },
    ),
    (
        re.compile(r"engineering|mechanical|electrical|civil engineering|construction", re.I),
        {
            "subject": "Engineering & Technology",
            "ddc": ["620"],
            "lcsh": ["Engineering", "Technology"],
            "shelf": "600–699 • Technology",
        },
    ),
]


def infer_local(text):
    text = str(text or "")
    scores = []

    for pattern, data in RULES:
        matches = pattern.findall(text)
        if matches:
            scores.append((len(matches), data))

    if not scores:
        return {
            "subject": "General / needs review",
            "ddc": [],
            "lcsh": [],
            "shelf": "Librarian review required",
        }

    scores.sort(key=lambda x: x[0], reverse=True)
    return scores[0][1]


def local_record(query):
    inferred = infer_local(query)

    author = ""
    words = query.strip().split()
    if len(words) >= 2 and any(x.lower() in query.lower() for x in ["by", "author"]):
        pass

    return {
        "key": "local:" + normalize_query(query).replace(" ", "-"),
        "title": query.strip() or "Untitled",
        "author_name": [],
        "first_publish_year": None,
        "subject": inferred["lcsh"] or [inferred["subject"]],
        "ddc": inferred["ddc"],
        "isbn": [],
        "publisher": [],
        "language": [],
        "description": "Generated by the V6 local classification fallback. This is not an authoritative bibliographic record.",
        "first_sentence": [],
        "number_of_pages": None,
        "cover_i": None,
        "source": "Local classification fallback",
        "synthetic": True,
        "suggested_subject": inferred["subject"],
        "suggested_shelf": inferred["shelf"],
    }


# =========================================================
# OPEN LIBRARY
# =========================================================

def open_library_search(q):
    cache_key = "openlibrary:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    raw, _ = request_json(
        "https://openlibrary.org/search.json",
        params={
            "q": q,
            "limit": MAX_RESULTS_PER_SOURCE,
            "fields": (
                "key,title,author_name,first_publish_year,subject,ddc,"
                "isbn,publisher,language,description,first_sentence,"
                "number_of_pages_median,cover_i"
            ),
        },
        timeout=7,
    )

    docs = []

    for book in raw.get("docs", []):
        docs.append({
            "key": book.get("key"),
            "title": book.get("title") or "Untitled",
            "author_name": as_list(book.get("author_name")),
            "first_publish_year": book.get("first_publish_year"),
            "subject": as_list(book.get("subject")),
            "ddc": as_list(book.get("ddc")),
            "isbn": as_list(book.get("isbn")),
            "publisher": as_list(book.get("publisher")),
            "language": as_list(book.get("language")),
            "description": book.get("description"),
            "first_sentence": as_list(book.get("first_sentence")),
            "number_of_pages": book.get("number_of_pages_median"),
            "cover_i": book.get("cover_i"),
            "source": "Open Library",
        })

    result = {
        "numFound": raw.get("numFound", len(docs)),
        "docs": docs,
    }
    cache_set(cache_key, result)
    return result


# =========================================================
# LIBRARY OF CONGRESS
# =========================================================

def loc_search(q):
    cache_key = "loc:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    raw, _ = request_json(
        "https://www.loc.gov/books/",
        params={
            "q": q,
            "fo": "json",
            "c": MAX_RESULTS_PER_SOURCE,
        },
        timeout=8,
    )

    docs = []

    for item in raw.get("results", [])[:MAX_RESULTS_PER_SOURCE]:
        title = first_value(item.get("title")) or item.get("title_s") or "Untitled"

        creators = item.get("contributor_names") or item.get("contributor")
        authors = as_list(creators)

        date_value = (
            first_value(item.get("date"))
            or first_value(item.get("date_s"))
            or None
        )

        subjects = (
            as_list(item.get("subject"))
            + as_list(item.get("subject_headings"))
        )

        docs.append({
            "key": item.get("id") or ("loc:" + normalize_query(str(title))),
            "title": str(title),
            "author_name": unique(authors),
            "first_publish_year": str(date_value)[:4] if date_value else None,
            "subject": unique(subjects),
            "ddc": as_list(item.get("ddc")),
            "isbn": as_list(item.get("isbn")),
            "publisher": as_list(item.get("publisher")),
            "language": as_list(item.get("language")),
            "description": first_value(item.get("description")),
            "first_sentence": [],
            "number_of_pages": None,
            "cover_i": None,
            "source": "Library of Congress",
        })

    result = {
        "numFound": raw.get("pagination", {}).get("total", len(docs)),
        "docs": docs,
    }
    cache_set(cache_key, result)
    return result


# =========================================================
# OPENALEX
# =========================================================

def openalex_search(q):
    cache_key = "openalex:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    raw, _ = request_json(
        "https://api.openalex.org/works",
        params={
            "search": q,
            "per-page": MAX_RESULTS_PER_SOURCE,
            "select": (
                "id,display_name,publication_year,authorships,"
                "topics,keywords,type,primary_location"
            ),
        },
        timeout=8,
    )

    docs = []

    for item in raw.get("results", []):
        authors = []
        for author in item.get("authorships", []) or []:
            name = (author.get("author") or {}).get("display_name")
            if name:
                authors.append(name)

        subjects = []

        for topic in item.get("topics", []) or []:
            name = topic.get("display_name")
            if name:
                subjects.append(name)

        for keyword in item.get("keywords", []) or []:
            name = keyword.get("display_name")
            if name:
                subjects.append(name)

        docs.append({
            "key": item.get("id") or ("openalex:" + normalize_query(item.get("display_name", ""))),
            "title": item.get("display_name") or "Untitled",
            "author_name": unique(authors),
            "first_publish_year": item.get("publication_year"),
            "subject": unique(subjects),
            "ddc": [],
            "isbn": [],
            "publisher": [],
            "language": [],
            "description": None,
            "first_sentence": [],
            "number_of_pages": None,
            "cover_i": None,
            "source": "OpenAlex",
        })

    result = {
        "numFound": raw.get("meta", {}).get("count", len(docs)),
        "docs": docs,
    }
    cache_set(cache_key, result)
    return result


# =========================================================
# CROSSREF BACKUP
# =========================================================

def crossref_search(q):
    cache_key = "crossref:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    raw, _ = request_json(
        "https://api.crossref.org/v1/works",
        params={
            "query.bibliographic": q,
            "rows": MAX_RESULTS_PER_SOURCE,
            "select": (
                "DOI,title,author,published-print,published,"
                "publisher,ISBN,subject,type"
            ),
        },
        timeout=8,
    )

    docs = []

    for item in raw.get("message", {}).get("items", []):
        titles = as_list(item.get("title"))
        title = titles[0] if titles else "Untitled"

        authors = []
        for author in item.get("author", []) or []:
            name = " ".join(
                x for x in [
                    author.get("given"),
                    author.get("family"),
                ]
                if x
            ).strip()
            if name:
                authors.append(name)

        published = item.get("published-print") or item.get("published") or {}
        date_parts = published.get("date-parts", [])
        year = None
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

        docs.append({
            "key": item.get("DOI") or ("crossref:" + normalize_query(title)),
            "title": title,
            "author_name": unique(authors),
            "first_publish_year": year,
            "subject": as_list(item.get("subject")),
            "ddc": [],
            "isbn": as_list(item.get("ISBN")),
            "publisher": as_list(item.get("publisher")),
            "language": [],
            "description": None,
            "first_sentence": [],
            "number_of_pages": None,
            "cover_i": None,
            "source": "Crossref",
            "doi": item.get("DOI"),
        })

    result = {
        "numFound": raw.get("message", {}).get("total-results", len(docs)),
        "docs": docs,
    }
    cache_set(cache_key, result)
    return result


# =========================================================
# GOOGLE BOOKS
# =========================================================

def google_books_search(q):
    cache_key = "googlebooks:" + normalize_query(q)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    response = session.get(
        "https://www.googleapis.com/books/v1/volumes",
        params={
            "q": q,
            "maxResults": MAX_RESULTS_PER_SOURCE,
        },
        timeout=8,
    )

    if response.status_code == 429:
        raise RuntimeError(
            "Google Books quota/rate limit reached (HTTP 429). "
            "V6 skipped retries and continued with other sources."
        )

    response.raise_for_status()
    raw = response.json()

    docs = []

    for item in raw.get("items", []):
        volume = item.get("volumeInfo", {})
        identifiers = volume.get("industryIdentifiers") or []

        isbn = [
            x.get("identifier")
            for x in identifiers
            if x.get("identifier")
        ]

        published = volume.get("publishedDate") or ""

        docs.append({
            "key": item.get("id"),
            "title": volume.get("title") or "Untitled",
            "author_name": as_list(volume.get("authors")),
            "first_publish_year": published[:4] if published else None,
            "subject": as_list(volume.get("categories")),
            "ddc": [],
            "isbn": isbn,
            "publisher": as_list(volume.get("publisher")),
            "language": as_list(volume.get("language")),
            "description": volume.get("description"),
            "first_sentence": [],
            "number_of_pages": volume.get("pageCount"),
            "cover_i": None,
            "source": "Google Books",
        })

    result = {
        "numFound": raw.get("totalItems", len(docs)),
        "docs": docs,
    }
    cache_set(cache_key, result)
    return result


# =========================================================
# QUERY VARIANTS
# =========================================================

def query_variants(q):
    original = str(q or "").strip()
    normalized = normalize_query(original)

    variants = []
    for value in [original, normalized]:
        if value and value.lower() not in [x.lower() for x in variants]:
            variants.append(value)

    words = normalized.split()

    if len(words) >= 3:
        variants.append("title:" + " ".join(words[:8]))

    if " by " in normalized:
        title_part = normalized.split(" by ", 1)[0].strip()
        if title_part:
            variants.append(title_part)

    return variants[:4]


# =========================================================
# SEARCH API — ALL SOURCES + FALLBACK
# =========================================================

@app.get("/api/search")
def search():
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({
            "numFound": 0,
            "docs": [],
            "sources": [],
            "message": "Enter a title, author, ISBN, or topic."
        })

    groups = []
    sources = []
    errors = []

    # Each service is independent. One failure never stops the others.
    services = [
        ("Open Library", open_library_search),
        ("Library of Congress", loc_search),
        ("OpenAlex", openalex_search),
        ("Crossref", crossref_search),
        ("Google Books", google_books_search),
    ]

    variants = query_variants(query)

    for name, function in services:
        service_docs = []

        # First try the original query, then useful variants if needed.
        for variant in variants:
            try:
                result = function(variant)
                docs = result.get("docs", [])

                if docs:
                    service_docs.extend(docs)
                    break

            except Exception as exc:
                errors.append(f"{name}: {exc}")
                # Do not keep hammering a failing source with variants.
                break

        service_docs = merge_docs([service_docs])

        if service_docs:
            groups.append(service_docs)
            sources.append(
                source_result(name, "ok", len(service_docs))
            )
        else:
            # A source may be reachable but have no matching records.
            sources.append(
                source_result(name, "no_results", 0)
            )

    docs = merge_docs(groups)

    # ---------------------------------------------------------
    # ALWAYS RETURN SOMETHING USEFUL
    # ---------------------------------------------------------
    if not docs:
        fallback = local_record(query)

        return jsonify({
            "numFound": 1,
            "docs": [fallback],
            "source": "Local classification fallback",
            "fallback": True,
            "message": (
                "No external bibliographic record was available. "
                "A local classification suggestion was generated."
            ),
            "sources": sources,
            "errors": errors,
        })

    return jsonify({
        "numFound": len(docs),
        "docs": docs,
        "source": "Multi-source V6",
        "fallback": False,
        "sources": sources,
        "errors": errors,
    })


# =========================================================
# LCSH AUTHORITY SEARCH
# =========================================================

@app.get("/api/lcsh")
def lcsh():
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({
            "query": "",
            "headings": [],
            "source": "Library of Congress",
        })

    try:
        response = session.get(
            "https://id.loc.gov/authorities/subjects/suggest/",
            params={
                "q": query,
                "count": 8,
            },
            timeout=8,
        )
        response.raise_for_status()
        raw = response.json()

        headings = []

        if isinstance(raw, dict):
            candidates = (
                raw.get("suggestions")
                or raw.get("results")
                or []
            )
        elif isinstance(raw, list):
            candidates = raw
        else:
            candidates = []

        for item in candidates:
            if isinstance(item, str):
                headings.append(item)
            elif isinstance(item, list) and item:
                headings.append(str(item[0]))
            elif isinstance(item, dict):
                value = (
                    item.get("label")
                    or item.get("term")
                    or item.get("title")
                )
                if value:
                    headings.append(str(value))

        return jsonify({
            "query": query,
            "headings": unique(headings)[:8],
            "source": "Library of Congress Linked Data Service",
        })

    except Exception as exc:
        return jsonify({
            "query": query,
            "headings": [],
            "source": "Library of Congress",
            "error": str(exc),
        })


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "6.0",
        "backend": "Flask",
        "search": "/api/search",
        "catalog_sources": [
            "Open Library",
            "Library of Congress",
            "OpenAlex",
            "Crossref",
            "Google Books",
            "Local classification fallback",
        ],
        "authority_source": "Library of Congress Linked Data Service",
        "cache_ttl_seconds": CACHE_TTL,
    })


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return send_from_directory(BASE, "index.html")


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
    )
