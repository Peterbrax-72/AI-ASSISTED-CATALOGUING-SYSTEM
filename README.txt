UNIVERSAL CATALOGING ASSISTANT — V6.1 (stabilised V6)

FILES
- server.py: Flask backend, multi-source search, merging, ranking, /api/classify, /api/lcsh
- classifier.py: the single evidence-based DDC classification engine (Class 000 first)
- index.html / app.js / style.css: browser interface
- tests/test_uca.py: offline tests (no network needed)
- requirements.txt: Python dependencies

INSTALLATION (Windows PowerShell)
1. Extract to a folder and open PowerShell there.
2. py -m venv .venv
3. .venv\Scripts\Activate.ps1
4. pip install -r requirements.txt
5. python server.py
6. Open http://127.0.0.1:5000

RUN THE TESTS
python -m unittest discover -s tests -v

SETTINGS (environment variables, all optional)
- UCA_PORT   default 5000
- UCA_HOST   default 127.0.0.1 (local only). Use 0.0.0.0 only if you want LAN access.
- UCA_DEBUG  set to 1 for Flask debug mode. Never enable on a shared network.

WHAT CHANGED IN 6.1
- Security: debugger and LAN exposure off by default; only app.js and style.css are served
  under /static (server.py and classifier.py are no longer downloadable).
- A failed source is reported with its reason (timeout, network, quota, auth, HTTP, invalid
  response). A total outage is never shown as an empty search.
- Source status panel and fallback warning in the interface.
- One classification engine on the backend. Source DDC is validated strictly; subject and
  shelf are derived from the number so they cannot contradict it; conflicts are flagged,
  not mixed. Inferred numbers are labelled and need review.
- DDC Class 000 hierarchy (004, 005.x, 006.x, 010, 020, 023, 025.x, 027.x, 030, 050, 069,
  070.x, 080, 090) plus first-pass rules for classes 100-900.
- Records from different sources are merged (ISBN/DOI, or main title + author + compatible
  year) with per-source DDC and call-number provenance kept. ISBN searches rank exact ISBN
  matches first; journal articles rank below books.
- Draft AACR2-style description cards; working Edit; Approve downloads a JSON record.
- OCR text is placed in the search box for correction before searching.

NOTES
- All inferred DDC numbers are suggestions. Verify every number against an authorised DDC edition.
- Classes 100-900 rules are first-pass and not yet tested class by class.
- Google Books may return HTTP 429 when its quota is unavailable; the panel shows this.
- Crossref/OpenAlex do not provide DDC or library call numbers; none are invented.
- Suggested call numbers are basic author marks, not Cutter numbers, and are labelled as generated.
