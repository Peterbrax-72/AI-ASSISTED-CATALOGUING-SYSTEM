from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path
import requests
import re

BASE = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE), static_url_path="/static")
HEADERS = {"User-Agent": "UniversalCatalogingAssistant/5.0 (educational prototype)"}


def open_library_search(q):
    r = requests.get(
        "https://openlibrary.org/search.json",
        params={
            "q": q, "limit": 10,
            "fields": "key,title,author_name,first_publish_year,subject,ddc,isbn,publisher,language,description,first_sentence,number_of_pages_median,cover_i"
        }, headers=HEADERS, timeout=15)
    r.raise_for_status()
    raw = r.json()
    docs = []
    for b in raw.get("docs", []):
        docs.append({
            "key": b.get("key"), "title": b.get("title") or "Untitled",
            "author_name": b.get("author_name") or [],
            "first_publish_year": b.get("first_publish_year"),
            "subject": b.get("subject") or [], "ddc": b.get("ddc") or [],
            "isbn": b.get("isbn") or [], "publisher": b.get("publisher") or [],
            "language": b.get("language") or [], "description": b.get("description"),
            "first_sentence": b.get("first_sentence") or [],
            "number_of_pages": b.get("number_of_pages_median"),
            "cover_i": b.get("cover_i"), "source": "Open Library"
        })
    return {"numFound": raw.get("numFound", len(docs)), "docs": docs}

def normalize_query(q):
    import re
    return re.sub(r"[^a-z0-9 ]+", " ", q.lower()).strip()

def merge_docs(groups):
    seen = set(); merged = []
    for group in groups:
        for b in group:
            key = b.get("key") or (normalize_query(b.get("title", "")) + "|" + normalize_query(" ".join(b.get("author_name", []))))
            if key in seen:
                continue
            seen.add(key); merged.append(b)
    return merged

def smart_open_library_search(q):
    queries = [q]
    nq = normalize_query(q)
    if nq != q.lower().strip():
        queries.append(nq)
    # If the user supplied a title + author, also try a quoted title-style query.
    parts = nq.split()
    if len(parts) >= 3:
        queries.append('title:"' + ' '.join(parts[:5]) + '"')
    groups = []
    for candidate in queries[:3]:
        data = open_library_search(candidate)
        groups.append(data.get("docs", []))
        if groups[-1]:
            # One successful relevance search is normally enough, but merge a second
            # normalized query to catch punctuation/case variants.
            continue
    docs = merge_docs(groups)
    return {"numFound": len(docs), "docs": docs}

def google_books_search(q):
    r = requests.get("https://www.googleapis.com/books/v1/volumes",
                     params={"q": q, "maxResults": 10}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    raw = r.json(); docs = []
    for item in raw.get("items", []):
        v = item.get("volumeInfo", {})
        docs.append({
            "key": item.get("id"), "title": v.get("title") or "Untitled",
            "author_name": v.get("authors") or [],
            "first_publish_year": (v.get("publishedDate") or "")[:4] or None,
            "subject": v.get("categories") or [], "ddc": [],
            "isbn": [x.get("identifier") for x in v.get("industryIdentifiers", []) if x.get("identifier")],
            "publisher": [v.get("publisher")] if v.get("publisher") else [],
            "language": [v.get("language")] if v.get("language") else [],
            "description": v.get("description"), "first_sentence": [],
            "number_of_pages": v.get("pageCount"), "cover_i": None,
            "source": "Google Books"
        })
    return {"numFound": raw.get("totalItems", len(docs)), "docs": docs}


@app.get("/")
def home():
    return send_from_directory(BASE, "index.html")


@app.get("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"numFound": 0, "docs": []})
    errors = []
    try:
        data = smart_open_library_search(q)
        if data["docs"]:
            return jsonify(data)
    except requests.RequestException as exc:
        errors.append("Open Library: " + str(exc))
    try:
        data = google_books_search(q)
        if data["docs"]:
            return jsonify(data)
    except requests.RequestException as exc:
        errors.append("Google Books: " + str(exc))
    return jsonify({"numFound": 0, "docs": [], "error": "No records found or external catalog services are unreachable.", "details": errors})


@app.get("/api/lcsh")
def lcsh():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"query": q, "headings": [], "source": "Library of Congress"})
    # LC Linked Data Service exposes subject-authority suggestions. Keep this isolated so
    # the catalog search still works if the authority service is unavailable.
    try:
        r = requests.get(
            "https://id.loc.gov/authorities/subjects/suggest/",
            params={"q": q, "count": 8}, headers=HEADERS, timeout=12)
        r.raise_for_status()
        raw = r.json()
        headings = []
        if isinstance(raw, dict):
            candidates = raw.get("suggestions") or raw.get("results") or []
            for x in candidates:
                if isinstance(x, str): headings.append(x)
                elif isinstance(x, list) and x: headings.append(str(x[0]))
                elif isinstance(x, dict): headings.append(x.get("label") or x.get("term") or x.get("title"))
        elif isinstance(raw, list):
            for x in raw:
                if isinstance(x, str): headings.append(x)
                elif isinstance(x, list) and x: headings.append(str(x[0]))
                elif isinstance(x, dict): headings.append(x.get("label") or x.get("term") or x.get("title"))
        headings = [h for h in headings if h]
        return jsonify({"query": q, "headings": list(dict.fromkeys(headings))[:8], "source": "Library of Congress Linked Data Service"})
    except (requests.RequestException, ValueError) as exc:
        return jsonify({"query": q, "headings": [], "source": "Library of Congress", "error": str(exc)}), 200


@app.get("/health")
def health():
    return jsonify({"status": "ok", "backend": "Flask", "search": "/api/search", "catalog_sources": ["Open Library", "Google Books"], "authority_source": "Library of Congress Linked Data Service"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
