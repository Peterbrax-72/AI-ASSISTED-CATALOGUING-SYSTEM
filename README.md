# 📚 Universal Cataloging Assistant

> An intelligent web-based cataloging assistant designed to help librarians, library science students, information professionals, and catalogers discover bibliographic records and generate preliminary cataloging recommendations.

![Project Status](https://img.shields.io/badge/status-active%20development-orange)
![Python](https://img.shields.io/badge/Python-3.x-blue)
![Flask](https://img.shields.io/badge/Flask-Web%20Framework-black)
![JavaScript](https://img.shields.io/badge/JavaScript-ES6%2B-yellow)
![HTML5](https://img.shields.io/badge/HTML5-orange)
![CSS3](https://img.shields.io/badge/CSS3-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 📖 Overview

The **Universal Cataloging Assistant** is a web-based library cataloging support tool that combines bibliographic search, metadata retrieval, subject analysis, classification suggestions, and authority-data lookup into a single interface.

Instead of relying on a small, manually maintained database of books, the system connects to external bibliographic services to retrieve real-world records.

A user can:

- Search by **book title**
- Search by **author**
- Upload a **photograph of a book**
- Retrieve bibliographic metadata
- Analyze available subject information
- Generate preliminary **DDC classification suggestions**
- Suggest **Library of Congress Subject Headings (LCSH)**
- Generate a preliminary **call number**
- Recommend a broad **shelf/location range**
- Review and edit cataloging information before approval

The project is designed as a **cataloging decision-support system**, not a replacement for professional catalogers.

---

# 🎯 Project Goals

The main goal of the project is to make preliminary cataloging and classification faster and more accessible.

### The system aims to:

1. 🔎 Find bibliographic records from external sources.
2. 📚 Reduce repetitive cataloging work.
3. 🧠 Analyze book metadata to identify possible subjects.
4. 🔢 Suggest appropriate Dewey Decimal Classification (DDC) ranges.
5. 🏷️ Suggest relevant Library of Congress Subject Headings.
6. 📖 Generate preliminary library call numbers.
7. 🗄️ Recommend a general shelving range.
8. 📷 Support book-cover/image-based searching through OCR.
9. ✏️ Allow librarians to review and modify generated suggestions.
10. 🚀 Provide a foundation for a more advanced AI-assisted cataloging platform.

---

# ✨ Current Features

## 🔍 Universal Bibliographic Search

The system searches external bibliographic databases instead of depending on a fixed local book database.

Supported sources currently include:

- **Open Library**
- **Google Books**

Search can be performed using:

```text / coverbook image
Book title
Author name
Title + author
```

Main files;

| File               | Purpose                                    |
| ------------------ | ------------------------------------------ |
| `index.html`       | Main application interface                 |
| `style.css`        | Application styling                        |
| `app.js`           | Frontend logic and cataloging interface    |
| `server.py`        | Flask backend and external API integration |
| `requirements.txt` | Python dependencies                        |
| `README.md`        | Project documentation                      |



```Getting Started```
1. Clone the repository
git clone https://github.com/YOUR-USERNAME/universal-cataloging-assistant.git

Move into the project directory:

cd universal-cataloging-assistant
2. Create a virtual environment
Windows
python -m venv venv

Activate it:

venv\Scripts\activate
Linux / macOS
python3 -m venv venv
source venv/bin/activate
3. Install dependencies
pip install -r requirements.txt
4. Start the Flask server
python server.py

You should see something similar to:

Running on http://127.0.0.1:5000
5. Open the application

Open your browser and visit:

http://127.0.0.1:5000
