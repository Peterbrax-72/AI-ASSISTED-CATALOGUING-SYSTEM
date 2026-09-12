# Universal Cataloging Assistant — V5

what was working in V4 bibliographic search/OCR and adds a cataloging-intelligence layer.

## Added
- Explicit Open Library metadata fields including subjects and DDC.
- Google Books fallback metadata.
- DDC reuse when an existing DDC value is present.
- Rule-based DDC inference when no DDC is supplied.
- Subject/topic inference from title, subjects, description and first sentence.
- Library of Congress Linked Data Service LCSH authority suggestions.
- Basic author mark and suggested call number.
- Shelf-range recommendation.
- Clear review language: suggestions are not a substitute for professional cataloging.

## Run
```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python server.py
```
Open http://127.0.0.1:5000

## Notes
LCSH depends on the Library of Congress authority service being reachable from the machine running Flask. If unavailable, the UI shows fallback candidate headings and asks for manual review.

DDC inference is deliberately conservative and transparent. A real production cataloging system should add authoritative DDC data/licensing, edition-level bibliographic matching, MARC/RDA validation, and cataloger approval before records are committed.
