const $ = (id) => document.getElementById(id);

/* Application state for the record currently under review. */
let current = null; // { book, cls, authority: [] , edited: false }
let editing = false;

/* =========================
   API FUNCTIONS
========================= */

async function fetchJson(url, options) {
    const response = await fetch(url, options);
    let data = null;
    try {
        data = await response.json();
    } catch (_) {
        throw new Error(`Server returned an unreadable response (HTTP ${response.status})`);
    }
    if (!response.ok) {
        throw new Error(data.error || `Request failed (HTTP ${response.status})`);
    }
    return data;
}

const searchBooks = (query) =>
    fetchJson(`/api/search?q=${encodeURIComponent(query)}`, { headers: { Accept: "application/json" } });

const getLCSH = (query) =>
    fetchJson(`/api/lcsh?q=${encodeURIComponent(query)}`, { headers: { Accept: "application/json" } });

const classifyBook = (book) =>
    fetchJson("/api/classify", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(book)
    });


/* =========================
   HELPERS
========================= */

function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[char]));
}

/* "Brianna Wiest" -> "Wiest, Brianna"; names already inverted are kept. */
function invertName(name) {
    const text = String(name || "").trim();
    if (!text || text.includes(",")) return text;
    const parts = text.split(/\s+/);
    if (parts.length < 2) return text;
    const surname = parts.pop();
    return `${surname}, ${parts.join(" ")}`;
}

function firstIsbn(book) {
    const list = Array.isArray(book.isbn) ? book.isbn : [];
    return list.find((i) => String(i).replace(/[^0-9X]/gi, "").length === 13) || list[0] || null;
}

const MISSING = (what) => `[${what} not supplied — review]`;


/* =========================
   SOURCE STATUS (compact)
========================= */

const ERROR_LABEL = {
    timeout: "Timed out",
    network: "Network error",
    quota: "Quota reached",
    auth: "Access refused",
    http_error: "HTTP error",
    invalid_response: "Unreadable response"
};

function renderStatus(data) {
    const panel = $("apiStatus");
    const sources = Array.isArray(data.sources) ? data.sources : [];
    const used = sources.filter((s) => s.status !== "skipped");
    if (!used.length && !data.message) {
        panel.innerHTML = "";
        return;
    }

    const failed = used.filter((s) => s.status === "failed");
    const chips = used.map((s) => {
        const cls = s.status === "failed" ? "error" : s.status;
        const why = s.status === "failed"
            ? `${ERROR_LABEL[s.error_kind] || "Failed"}${s.error ? ": " + s.error : ""}`
            : (s.status === "ok" ? `${s.count} record(s)` : "No matching records");
        return `<span class="src-chip ${esc(cls)}" title="${esc(why)}"><i></i>${esc(s.name)}${s.status === "failed" ? " — " + esc(ERROR_LABEL[s.error_kind] || "failed") : ""}</span>`;
    }).join("");

    const notice = data.message && (failed.length || data.fallback)
        ? `<div class="fallback-notice${data.all_sources_failed ? " danger" : ""}">${esc(data.message)}</div>` : "";

    panel.innerHTML = `<div class="src-row"><span class="src-label">Sources</span>${chips}</div>${notice}`;
}


/* =========================
   SEARCH RESULTS (compact list)
========================= */

const PAGE_SIZE = 8;

function resultRow(book) {
    const item = document.createElement("div");
    item.className = "match" + (book.synthetic ? " synthetic" : "");

    const authors = Array.isArray(book.author_name) && book.author_name.length
        ? invertName(book.author_name[0]) + (book.author_name.length > 1 ? " et al." : "")
        : "Author unknown";
    const meta = [authors, book.first_publish_year, (book.publisher || [])[0]].filter(Boolean).join(" · ");
    const sourceCount = (book.sources || []).length;
    const sourceText = book.synthetic
        ? "Not a bibliographic record"
        : (book.sources?.[0] || book.source || "") + (sourceCount > 1 ? ` +${sourceCount - 1}` : "");
    const ddc = (book.source_ddcs || [])[0]?.number;

    item.innerHTML = `
        <div class="match-main">
            <h3>${esc(book.title || "Untitled")}</h3>
            <p class="match-meta">${esc(meta)}</p>
            <p class="match-src">${esc(sourceText)}${ddc ? `<span class="ddc-tag">DDC ${esc(ddc)}</span>` : ""}</p>
        </div>
        <button class="primary analyze-btn">Select</button>`;
    item.querySelector(".analyze-btn").addEventListener("click", () => {
        document.querySelectorAll(".match.selected").forEach((el) => el.classList.remove("selected"));
        item.classList.add("selected");
        showCatalog(book);
    });
    return item;
}

function renderMatches(data) {
    const list = $("matchList");
    const books = Array.isArray(data.docs) ? data.docs : [];

    list.innerHTML = "";
    $("matchCount").textContent = data.fallback ? "" : `${books.length} found`;

    if (books.length === 0) {
        list.innerHTML = `<div class="empty">No matching records. Try the full title, the author, or an ISBN.</div>`;
        $("matches").classList.remove("hidden");
        return;
    }

    let shown = 0;
    const more = document.createElement("button");
    more.className = "secondary more-btn";
    const showNext = () => {
        books.slice(shown, shown + PAGE_SIZE).forEach((b) => list.insertBefore(resultRow(b), more));
        shown = Math.min(books.length, shown + PAGE_SIZE);
        more.textContent = `Show ${books.length - shown} more`;
        more.classList.toggle("hidden", shown >= books.length);
    };
    more.addEventListener("click", showNext);
    list.appendChild(more);
    showNext();

    $("matches").classList.remove("hidden");
}


/* =========================
   CATALOG CARDS (AACR2-style draft; one of each element)
========================= */

function buildCards(book, cls, heading) {
    const authors = Array.isArray(book.author_name) ? book.author_name : [];
    const publisher = (book.publisher || [])[0];
    const pages = book.number_of_pages;
    const isbn = firstIsbn(book);
    const main = authors.length ? invertName(authors[0]) : MISSING("Main entry");
    const responsibility = authors.length ? authors.join(", ") : MISSING("Statement of responsibility");
    const pub = `${MISSING("Place")} : ${publisher || MISSING("Publisher")}, ${book.first_publish_year || MISSING("Date")}`;
    const call = callNumberInfo(cls);

    return `
        <div class="catalog-section-head">
            <div>
                <span class="eyebrow">DRAFT CATALOGUE RECORD</span>
                <h3>AACR2-style description</h3>
            </div>
            <span class="catalog-standard">[ … ] = not supplied by any source</span>
        </div>
        <div class="catalog-card-grid">
            <article class="catalog-card main-entry-card">
                <div class="card-body">
                    <p class="catalog-entry"><strong class="editable">${esc(main)}</strong></p>
                    <p class="catalog-entry"><span class="editable">${esc(book.title || "Untitled")} / ${esc(responsibility)}.</span></p>
                    <p class="catalog-entry"><span class="editable">${esc(pub)}.</span></p>
                    <p class="catalog-entry"><span class="editable">${pages ? esc(pages) + " p." : esc(MISSING("Extent"))}</span>
                        <span class="editable">${isbn ? " ISBN " + esc(isbn) : ""}</span></p>
                    <p class="catalog-entry catalog-tracing">
                        <span class="editable">1. ${esc(heading || MISSING("Subject heading"))}</span>
                        &nbsp;&nbsp;<span class="editable">I. ${esc(authors[0] ? invertName(authors[0]) : "Title")}</span>
                    </p>
                    <p class="catalog-call"><span class="editable">${esc(call.value || "—")}</span>
                        <small>${esc(call.label)}</small></p>
                </div>
            </article>
        </div>`;
}

function callNumberInfo(cls) {
    if (cls.call_number?.value) {
        return { value: cls.call_number.value, label: `source record · ${cls.call_number.source || "unknown"}` };
    }
    if (cls.suggested_call_number) {
        return { value: cls.suggested_call_number.value, label: "generated suggestion (not a source call number)" };
    }
    return { value: null, label: "" };
}


/* =========================
   CATALOG ANALYSIS
========================= */

function provenanceText(cls, book) {
    const c = cls.classification;
    if (c.provenance === "source_record") {
        return `Source-supplied DDC from ${c.source || book.source || "bibliographic record"} • Review required`;
    }
    if (c.provenance === "inferred") {
        return `Inferred suggestion (${c.confidence} confidence) from title/subject keywords • Review required`;
    }
    return "No classification evidence • Librarian review required";
}

function basisText(cls) {
    const out = [];
    const c = cls.classification;
    if (c.evidence?.length) out.push("Evidence: " + c.evidence.join(", "));
    if (cls.conflict) {
        out.push(`⚠ ${cls.conflict.message} Subject evidence suggests ${cls.conflict.inferred_number} (${cls.conflict.inferred_subject}).`);
    }
    if (cls.alternatives?.length) {
        out.push("Alternatives: " + cls.alternatives.map((a) => `${a.number} ${a.subject}`).join("; "));
    }
    (cls.notes || []).forEach((n) => out.push(n));
    return out.join("\n") || "—";
}

async function showCatalog(book) {
    setEditing(false);
    $("approveStatus").textContent = "";
    $("result").classList.remove("hidden");
    $("resultTitle").textContent = book.title || "Untitled";
    $("resultAuthor").textContent = (book.author_name || []).join(", ") || "Author not supplied";
    ["materialType", "subject", "ddc", "shelf", "callNumber", "basis", "lcsh", "source"].forEach((id) => { $(id).textContent = "…"; });
    $("confidence").textContent = "Analyzing…";
    $("catalogCards").innerHTML = "";
    $("result").scrollIntoView({ behavior: "smooth" });

    let cls;
    try {
        cls = await classifyBook(book);
    } catch (error) {
        console.error("CLASSIFY ERROR:", error);
        $("subject").textContent = "Classification service unavailable";
        $("ddc").textContent = "—";
        $("shelf").textContent = "Librarian review required";
        $("callNumber").textContent = "—";
        $("basis").textContent = error.message;
        $("confidence").textContent = "Classification failed • Manual cataloguing required";
        $("lcsh").textContent = "—";
        current = null;
        return;
    }

    current = { book, cls, heading: null, headingBasis: null, edited: false };

    // Exactly one value for each of: DDC, LCSH heading, call number.
    const call = callNumberInfo(cls);
    $("materialType").textContent = cls.material_type || "—";
    $("subject").textContent = cls.primary_subject || "General / needs review";
    $("ddc").textContent = cls.classification.number || "—";
    $("shelf").textContent = cls.shelf;
    $("callNumber").innerHTML = call.value ? `${esc(call.value)}<small class="sub">${esc(call.label)}</small>` : "—";
    $("confidence").textContent = provenanceText(cls, book);
    $("basis").textContent = basisText(cls);
    $("source").textContent = book.sources?.length ? book.sources.join(" + ") : (book.source || "Bibliographic record");

    const first = (cls.lcsh_terms || [])[0] || null;
    $("catalogCards").innerHTML = buildCards(book, cls, first);
    await loadAuthority(cls, book);
}

/* Pick ONE heading: an exact LC authority match if there is one, otherwise the
   top LC suggestion for the first subject term, otherwise the record's own term. */
function pickHeading(terms, results) {
    for (let i = 0; i < terms.length; i++) {
        const exact = (results[i]?.headings || []).find((h) => h.toLowerCase() === terms[i].toLowerCase());
        if (exact) return { heading: exact, basis: "LC authority heading (exact match) — verify" };
    }
    for (let i = 0; i < terms.length; i++) {
        const top = (results[i]?.headings || [])[0];
        if (top) return { heading: top, basis: "LC authority candidate — verify" };
    }
    return null;
}

async function loadAuthority(cls, book) {
    const terms = (cls.lcsh_terms || []).slice(0, 3);
    if (!terms.length) {
        $("lcsh").textContent = "No subject candidate — review manually";
        return;
    }

    const results = await Promise.all(terms.map((t) =>
        getLCSH(t.replace(/[—–]/g, " ").trim()).catch((e) => ({ headings: [], error: e.message }))
    ));
    const picked = pickHeading(terms, results)
        || { heading: terms[0], basis: results.every((r) => r.error)
            ? "Record subject term — authority service unavailable, verify" : "Record subject term — no authority match, verify" };

    if (!current || current.book !== book) return; // user selected another record meanwhile
    current.heading = picked.heading;
    current.headingBasis = picked.basis;
    $("lcsh").innerHTML = `${esc(picked.heading)}<small class="sub">${esc(picked.basis)}</small>`;
    $("catalogCards").innerHTML = buildCards(book, cls, picked.heading);
}


/* =========================
   SEARCH BUTTON
========================= */

$("searchBtn").addEventListener("click", async () => {
    const query = $("query").value.trim();
    if (!query) {
        $("searchStatus").textContent = "Enter a title, author or ISBN.";
        return;
    }

    $("searchStatus").textContent = "Searching real bibliographic records…";
    $("searchBtn").disabled = true;
    $("searchBtn").textContent = "Searching…";

    try {
        const data = await searchBooks(query);
        renderStatus(data);
        renderMatches(data);

        if (data.all_sources_failed) {
            $("searchStatus").textContent = "Search FAILED — every source returned an error (not an empty result).";
        } else if (data.fallback) {
            $("searchStatus").textContent = "No bibliographic records found — showing a query-based suggestion only.";
        } else {
            $("searchStatus").textContent = `Search complete — ${data.docs.length} records found.`;
        }
    } catch (error) {
        console.error("SEARCH ERROR:", error);
        $("searchStatus").textContent = `Search error: ${error.message}`;
        $("apiStatus").innerHTML = "";
        $("matchList").innerHTML = `
            <div class="match"><div>
                <h3>Unable to retrieve results</h3>
                <p>${esc(error.message)}</p>
            </div></div>`;
        $("matches").classList.remove("hidden");
    } finally {
        $("searchBtn").disabled = false;
        $("searchBtn").textContent = "Search";
    }
});

$("query").addEventListener("keydown", (event) => {
    if (event.key === "Enter") $("searchBtn").click();
});


/* =========================
   SEARCH / PHOTO TABS
========================= */

document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
        tab.classList.add("active");
        const photoMode = tab.dataset.mode === "photo";
        $("searchMode").classList.toggle("hidden", photoMode);
        $("photoMode").classList.toggle("hidden", !photoMode);
    });
});

function showTab(mode) {
    const tab = document.querySelector(`.tab[data-mode="${mode}"]`);
    if (tab) tab.click();
}


/* =========================
   BOOK PHOTO PREVIEW
========================= */

let previewUrl = null;

$("bookPhoto").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    $("preview").innerHTML = `<img src="${previewUrl}" alt="Book cover preview">`;
});


/* =========================
   OCR (discovery only; the user corrects the text before searching)
========================= */

function bestOcrQuery(data) {
    const lines = (data.lines || [])
        .map((l) => ({ text: String(l.text || "").replace(/[^\p{L}\p{N}' :,&.-]+/gu, " ").replace(/\s+/g, " ").trim(), conf: l.confidence ?? 0 }))
        .filter((l) => {
            const letters = (l.text.match(/\p{L}/gu) || []).length;
            return l.text.length >= 3 && letters / l.text.length >= 0.6 && l.conf >= 55;
        });
    const picked = lines.slice(0, 4);
    const avg = picked.length ? picked.reduce((a, l) => a + l.conf, 0) / picked.length : 0;
    let query = picked.map((l) => l.text).join(" ");
    if (!query) {
        // Fall back to raw text when line data is missing or confidence was low.
        query = String(data.text || "").split(/\n+/).map((s) => s.trim()).filter((s) => s.length >= 3).slice(0, 4).join(" ");
    }
    return { query, avg };
}

$("photoAnalyzeBtn").addEventListener("click", async () => {
    const file = $("bookPhoto").files[0];
    if (!file) {
        $("ocrStatus").textContent = "Upload a book photo first.";
        return;
    }
    if (typeof Tesseract === "undefined") {
        $("ocrStatus").textContent = "OCR library could not be loaded (check your internet connection). Type the title in the Search tab instead.";
        return;
    }

    $("ocrStatus").textContent = "Reading image…";
    $("photoAnalyzeBtn").disabled = true;

    try {
        const result = await Tesseract.recognize(file, "eng");
        const { query, avg } = bestOcrQuery(result.data || {});

        if (!query) {
            $("ocrStatus").textContent = "No readable text found. Try a clearer, straight-on photo.";
            return;
        }

        $("query").value = query;
        showTab("search");
        const quality = avg && avg < 70 ? " Confidence is low, so check the spelling carefully." : "";
        $("searchStatus").textContent =
            `Text read from the photo is in the box above.${quality} Correct it if needed, then press Search.`;
        $("ocrStatus").textContent = "Text extracted — review it in the Search tab.";
        $("query").focus();
    } catch (error) {
        console.error("OCR ERROR:", error);
        $("ocrStatus").textContent = "OCR failed. Try a clearer image.";
    } finally {
        $("photoAnalyzeBtn").disabled = false;
    }
});


/* =========================
   EDIT / APPROVE
========================= */

function editableNodes() {
    return document.querySelectorAll("#result .result-item strong, #result .editable");
}

function setEditing(on) {
    editing = on;
    editableNodes().forEach((el) => {
        el.contentEditable = on ? "true" : "false";
        el.classList.toggle("is-editing", on);
    });
    $("editBtn").textContent = on ? "Done editing" : "Edit";
}

$("editBtn").addEventListener("click", () => {
    if (!current) {
        $("approveStatus").textContent = "Analyze a record first.";
        return;
    }
    if (editing) current.edited = true;
    setEditing(!editing);
    $("approveStatus").textContent = editing
        ? "Fields are editable. Click “Done editing” when finished."
        : "Edits kept. Approve to export the record.";
});

function downloadJson(name, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$("approveBtn").addEventListener("click", () => {
    if (!current) {
        $("approveStatus").textContent = "Analyze a record before approving.";
        return;
    }
    if (editing) {
        current.edited = true;
        setEditing(false);
    }

    const { book, cls } = current;
    const text = (id) => $(id).textContent.trim();
    const record = {
        approved_at: new Date().toISOString(),
        status: "approved_by_librarian",
        edited_by_librarian: current.edited,
        title: text("resultTitle"),
        author: text("resultAuthor"),
        material_type: text("materialType"),
        primary_subject: text("subject"),
        ddc: text("ddc"),
        ddc_provenance: cls.classification.provenance,
        ddc_source: cls.classification.source,
        lcsh_heading: current.heading,
        lcsh_heading_basis: current.headingBasis,
        shelf: text("shelf"),
        call_number_displayed: text("callNumber"),
        source_call_number: cls.call_number,
        suggested_call_number: cls.suggested_call_number,
        record_sources: book.sources || [book.source],
        isbn: book.isbn || [],
        doi: book.doi || null,
        original_classification: cls.classification,
        conflict_flag: cls.conflict || null
    };

    try {
        const key = "uca_approved_records";
        const saved = JSON.parse(localStorage.getItem(key) || "[]");
        saved.push(record);
        localStorage.setItem(key, JSON.stringify(saved));
    } catch (_) {
        /* storage may be unavailable; the downloaded file is the record of truth */
    }

    const safe = (record.title || "record").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
    downloadJson(`catalog-${safe || "record"}-${Date.now()}.json`, record);
    $("approveStatus").textContent = "Approved. The record was downloaded as a JSON file.";
});
