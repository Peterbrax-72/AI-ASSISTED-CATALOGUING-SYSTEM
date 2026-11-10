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
   SOURCE STATUS PANEL
========================= */

const STATUS_LABEL = {
    ok: "Records returned",
    no_results: "Responded — no matching records",
    failed: "FAILED — results incomplete",
    skipped: "Not used for this search"
};

const ERROR_LABEL = {
    timeout: "Timed out",
    network: "Network error",
    quota: "Quota / rate limit reached",
    auth: "Access refused",
    http_error: "HTTP error",
    invalid_response: "Unreadable response"
};

function renderStatus(data) {
    const panel = $("apiStatus");
    const sources = Array.isArray(data.sources) ? data.sources : [];
    if (!sources.length && !data.message) {
        panel.innerHTML = "";
        return;
    }

    const cards = sources.map((s) => {
        const cls = s.status === "failed" ? "error" : s.status;
        const kind = s.error_kind ? (ERROR_LABEL[s.error_kind] || s.error_kind) : "";
        const detail = s.status === "failed"
            ? `<small>${esc(kind)}${s.error ? " — " + esc(s.error) : ""}</small>`
            : (s.status === "skipped" && s.error ? `<small>${esc(s.error)}</small>` : "");
        return `
            <div class="api-status-card ${esc(cls)}">
                <strong>${esc(s.name)}</strong>
                <span>${esc(STATUS_LABEL[s.status] || s.status)}${s.status === "ok" ? ` (${esc(s.count)})` : ""}</span>
                ${detail}
            </div>`;
    }).join("");

    const failed = sources.filter((s) => s.status === "failed").length;
    const noticeClass = data.all_sources_failed ? "fallback-notice danger" : "fallback-notice";
    const notice = data.message ? `<div class="${noticeClass}">${esc(data.message)}</div>` : "";

    panel.innerHTML = `
        <div class="api-status-head">
            <div>
                <span class="eyebrow">SOURCE STATUS</span>
                <h3>Bibliographic sources</h3>
            </div>
            <span class="api-total">${sources.length - failed} of ${sources.length} responded</span>
        </div>
        <div class="api-status-grid">${cards}</div>
        ${notice}`;
}


/* =========================
   DISPLAY SEARCH RESULTS
========================= */

function badge(text, kind) {
    return `<span class="badge-mini ${kind || ""}">${esc(text)}</span>`;
}

function renderMatches(data) {
    const list = $("matchList");
    const books = Array.isArray(data.docs) ? data.docs : [];

    list.innerHTML = "";
    $("matchCount").textContent = data.fallback ? "no records" : `${books.length} found`;

    if (books.length === 0) {
        list.innerHTML = `
            <div class="match"><div>
                <h3>No matching records</h3>
                <p>Try the full book title, author name, or a different spelling.</p>
            </div></div>`;
        $("matches").classList.remove("hidden");
        return;
    }

    books.forEach((book) => {
        const item = document.createElement("div");
        item.className = "match";

        const authors = Array.isArray(book.author_name) && book.author_name.length
            ? book.author_name.join(", ") : "Author unknown";
        const year = book.first_publish_year || "Year unknown";
        const sources = book.sources?.length ? book.sources.join(" + ") : (book.source || "Catalog");

        const badges = [];
        if (book.synthetic) badges.push(badge("Not a bibliographic record", "warn"));
        if (book.source_ddcs?.length) badges.push(badge("Source DDC " + [...new Set(book.source_ddcs.map((d) => d.number))].join(", "), "good"));
        if (book.source_call_numbers?.length) badges.push(badge("Source call number", "good"));
        if (book.metadata_type === "scholarly_bibliographic_record") badges.push(badge("Scholarly record", "muted"));
        if ((book.sources || []).length > 1) badges.push(badge(`Merged from ${book.sources.length} sources`, "muted"));

        item.innerHTML = `
            <div>
                <h3>${esc(book.title || "Untitled")}</h3>
                <p>${esc(authors)} • ${esc(year)} • ${esc(sources)}</p>
                <p class="badges">${badges.join(" ")}</p>
            </div>
            <button class="secondary analyze-btn">Analyze</button>`;

        item.querySelector(".analyze-btn").addEventListener("click", () => showCatalog(book));
        list.appendChild(item);
    });

    $("matches").classList.remove("hidden");
}


/* =========================
   CATALOG CARDS (AACR2-style draft)
========================= */

function buildCards(book, cls) {
    const authors = Array.isArray(book.author_name) ? book.author_name : [];
    const publisher = (book.publisher || [])[0];
    const year = book.first_publish_year;
    const pages = book.number_of_pages;
    const isbn = firstIsbn(book);
    const heading = authors.length ? invertName(authors[0]) : MISSING("Main entry");
    const responsibility = authors.length ? authors.join(", ") : MISSING("Statement of responsibility");
    const pub = [
        MISSING("Place of publication"),
        " : ",
        publisher || MISSING("Publisher"),
        ", ",
        year || MISSING("Date")
    ].join("");

    const lines = [
        `<p class="catalog-entry"><strong class="editable">${esc(heading)}</strong></p>`,
        `<p class="catalog-entry"><span class="editable">${esc(book.title || "Untitled")} / ${esc(responsibility)}.</span></p>`,
        `<p class="catalog-entry"><span class="editable">${esc(pub)}.</span></p>`,
        `<p class="catalog-entry"><span class="editable">${pages ? esc(pages) + " p." : esc(MISSING("Extent"))}</span></p>`,
        `<p class="catalog-entry"><span class="editable">${isbn ? "ISBN " + esc(isbn) : esc(MISSING("ISBN"))}</span></p>`
    ];

    const subjects = cls.lcsh_terms?.length ? cls.lcsh_terms : [];
    const cn = cls.call_number?.value
        ? `${esc(cls.call_number.value)} <small>(source record: ${esc(cls.call_number.source || "unknown")})</small>`
        : (cls.suggested_call_number
            ? `<span class="editable">${esc(cls.suggested_call_number.value)}</span> <small>(generated suggestion, not a source call number)</small>`
            : "—");

    return `
        <div class="catalog-section-head">
            <div>
                <span class="eyebrow">DRAFT CATALOGUE RECORD</span>
                <h3>AACR2-style description from available metadata</h3>
            </div>
            <span class="catalog-standard">Elements marked [ … ] were not supplied by any source</span>
        </div>
        <div class="catalog-card-grid">
            <article class="catalog-card main-entry-card">
                <div class="card-label">MAIN ENTRY</div>
                <div class="card-body">${lines.join("")}</div>
            </article>
            <article class="catalog-card">
                <div class="card-label">SUBJECT ENTRIES</div>
                <div class="card-body catalog-subjects">
                    ${subjects.length ? subjects.map((s, i) => `<p><span class="editable">${i + 1}. ${esc(s)}</span></p>`).join("") : "<p>No subject candidates</p>"}
                    <p><small>Candidates only — authority verification required.</small></p>
                </div>
            </article>
            <article class="catalog-card">
                <div class="card-label">CLASSIFICATION &amp; CALL NUMBER</div>
                <div class="card-body">
                    <p>DDC: <span class="editable">${esc(cls.classification.number || "—")}</span> <small>(${esc(cls.classification.provenance === "source_record" ? "source-supplied" : cls.classification.provenance === "inferred" ? "inferred" : "none")})</small></p>
                    <p class="catalog-call">${cn}</p>
                </div>
            </article>
        </div>`;
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
    if (cls.source_subject_terms?.length) out.push("Source subject terms: " + cls.source_subject_terms.slice(0, 6).join("; "));
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
    $("subject").textContent = "Analyzing…";
    $("ddc").textContent = "…";
    $("lcsh").textContent = "Searching authoritative headings…";
    $("shelf").textContent = "…";
    $("callNumber").textContent = "…";
    $("basis").textContent = "…";
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

    current = { book, cls, authority: [], edited: false };

    $("materialType").textContent = cls.material_type || "—";
    $("subject").textContent = cls.primary_subject || "General / needs review";
    $("ddc").textContent = cls.classification.number || "—";
    $("shelf").textContent = cls.shelf;
    $("confidence").textContent = provenanceText(cls, book);
    $("basis").textContent = basisText(cls);

    if (cls.call_number?.value) {
        $("callNumber").textContent = `${cls.call_number.value} (source record: ${cls.call_number.source || "unknown"})`;
    } else if (cls.suggested_call_number) {
        $("callNumber").textContent = `Suggested (generated): ${cls.suggested_call_number.value}`;
    } else {
        $("callNumber").textContent = "—";
    }
    $("source").textContent = (book.sources?.length ? book.sources.join(" + ") : book.source || "Bibliographic record")
        + (cls.call_number?.value ? " • source call number available" : "");

    $("catalogCards").innerHTML = buildCards(book, cls);

    await loadAuthority(cls);
}

async function loadAuthority(cls) {
    const terms = (cls.lcsh_terms || []).slice(0, 3);
    const recordTerms = cls.lcsh_terms || [];
    const lines = [];

    if (!terms.length) {
        $("lcsh").textContent = "No subject candidates — review manually";
        return;
    }

    const results = await Promise.all(terms.map((t) =>
        getLCSH(t.replace(/[—–]/g, " ").trim()).catch((e) => ({ headings: [], error: e.message }))
    ));

    const authority = [...new Set(results.flatMap((r) => r.headings || []))].slice(0, 6);
    const failed = results.every((r) => r.error);
    if (current) current.authority = authority;

    lines.push(`Record / inferred terms: ${recordTerms.slice(0, 5).join("; ")}`);
    if (authority.length) {
        lines.push(`LC authority candidates (unverified): ${authority.join("; ")}`);
    } else if (failed) {
        lines.push("Authority service unavailable — verify headings manually");
    } else {
        lines.push("No authority headings returned — verify manually");
    }
    $("lcsh").textContent = lines.join("\n");
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
        lcsh_displayed: text("lcsh"),
        lcsh_authority_candidates_unverified: current.authority,
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
