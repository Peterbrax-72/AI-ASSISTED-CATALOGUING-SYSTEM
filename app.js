const $ = (id) => document.getElementById(id);

/* =========================
   API FUNCTIONS
========================= */

async function searchBooks(query) {
    const response = await fetch(
        `/api/search?q=${encodeURIComponent(query)}`,
        {
            headers: {
                "Accept": "application/json"
            }
        }
    );

    const data = await response.json();

    console.log("SEARCH API RESPONSE:", data);

    if (!response.ok) {
        throw new Error(data.error || "Backend search failed");
    }

    return data;
}

async function getLCSH(query) {
    const response = await fetch(
        `/api/lcsh?q=${encodeURIComponent(query)}`,
        {
            headers: {
                "Accept": "application/json"
            }
        }
    );

    const data = await response.json();

    console.log("LCSH API RESPONSE:", data);

    if (!response.ok) {
        throw new Error(data.error || "LCSH service failed");
    }

    return data;
}


/* =========================
   SECURITY / HTML ESCAPING
========================= */

function esc(value) {
    return String(value ?? "").replace(
        /[&<>"']/g,
        (char) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;"
        }[char])
    );
}


/* =========================
   DISPLAY SEARCH RESULTS
========================= */

function renderMatches(data) {

    const list = $("matchList");
    const matches = $("matches");
    const count = $("matchCount");

    list.innerHTML = "";

    const books = Array.isArray(data.docs)
        ? data.docs
        : [];

    count.textContent = `${books.length} found`;

    console.log("BOOKS TO DISPLAY:", books);

    if (books.length === 0) {

        list.innerHTML = `
            <div class="match">
                <div>
                    <h3>No matching records</h3>
                    <p>
                        Try the full book title, author name,
                        or a different spelling.
                    </p>
                </div>
            </div>
        `;

        matches.classList.remove("hidden");
        return;
    }

    books.forEach((book) => {

        const item = document.createElement("div");

        item.className = "match";

        const title = book.title || "Untitled";

        const authors =
            Array.isArray(book.author_name)
                ? book.author_name.join(", ")
                : "Author unknown";

        const year =
            book.first_publish_year ||
            "Year unknown";

        const source =
            book.source ||
            "Catalog";

        item.innerHTML = `
            <div>
                <h3>${esc(title)}</h3>

                <p>
                    ${esc(authors)}
                    • ${esc(year)}
                    • ${esc(source)}
                </p>
            </div>

            <button class="secondary analyze-btn">
                Analyze
            </button>
        `;

        const button =
            item.querySelector(".analyze-btn");

        button.addEventListener("click", () => {
            showCatalog(book);
        });

        list.appendChild(item);
    });

    matches.classList.remove("hidden");
}


/* =========================
   SUBJECT / DDC RULES
========================= */

const rules = [

    [
        /library|cataloging|cataloguing|librarianship|information science/,
        {
            subject: "Library & Information Science",
            ddc: "020",
            lcsh: [
                "Libraries",
                "Library science",
                "Information science"
            ],
            shelf: "000–099 • General Works / Library & Information Science"
        }
    ],

    [
        /computer|programming|software|information technology|ict|python|javascript|coding/,
        {
            subject: "Computer Science & Information Technology",
            ddc: "004–006",
            lcsh: [
                "Computer science",
                "Information technology"
            ],
            shelf: "000–099 • General Works / Computing"
        }
    ],

    [
        /economics|finance|banking|business|accounting|entrepreneur|marketing/,
        {
            subject: "Economics / Business",
            ddc: "330",
            lcsh: [
                "Economics",
                "Finance",
                "Business"
            ],
            shelf: "300–399 • Social Sciences"
        }
    ],

    [
        /education|teaching|teacher|school|learning|curriculum/,
        {
            subject: "Education",
            ddc: "370",
            lcsh: [
                "Education",
                "Teaching"
            ],
            shelf: "300–399 • Social Sciences"
        }
    ],

    [
        /psychology|behavior|behaviour|mental|personality/,
        {
            subject: "Psychology",
            ddc: "150",
            lcsh: [
                "Psychology",
                "Behavior"
            ],
            shelf: "100–199 • Philosophy & Psychology"
        }
    ],

    [
        /self-help|success|motivation|personal development|leadership|achievement/,
        {
            subject: "Self-help / Personal Development",
            ddc: "158.1",
            lcsh: [
                "Self-help techniques",
                "Success",
                "Personal development"
            ],
            shelf: "100–199 • Philosophy & Psychology"
        }
    ],

    [
        /fiction|novel|poetry|poems|short stories|literature/,
        {
            subject: "Literature / Fiction",
            ddc: "800",
            lcsh: [
                "Literature",
                "Fiction"
            ],
            shelf: "800–899 • Literature",
            type: "Fiction"
        }
    ],

    [
        /history|civilization|war|colonial|independence|historical/,
        {
            subject: "History",
            ddc: "900",
            lcsh: [
                "History",
                "Civilization"
            ],
            shelf: "900–999 • History & Geography"
        }
    ],

    [
        /africa|kenya|kenyan|east africa|ethiopia|uganda|tanzania/,
        {
            subject: "Africa / Regional History",
            ddc: "960",
            lcsh: [
                "Africa",
                "Africa—History"
            ],
            shelf: "900–999 • History & Geography"
        }
    ],

    [
        /religion|christian|church|bible|theology|islam|muslim/,
        {
            subject: "Religion",
            ddc: "200",
            lcsh: [
                "Religion",
                "Christianity"
            ],
            shelf: "200–299 • Religion"
        }
    ],

    [
        /science|physics|chemistry|biology|astronomy/,
        {
            subject: "Science",
            ddc: "500",
            lcsh: [
                "Science"
            ],
            shelf: "500–599 • Science"
        }
    ],

    [
        /medicine|medical|health|nursing|disease|clinical/,
        {
            subject: "Medicine / Health",
            ddc: "610",
            lcsh: [
                "Medicine",
                "Health"
            ],
            shelf: "600–699 • Technology / Medicine"
        }
    ],

    [
        /engineering|mechanical|electrical|civil engineering|construction/,
        {
            subject: "Engineering & Technology",
            ddc: "620",
            lcsh: [
                "Engineering",
                "Technology"
            ],
            shelf: "600–699 • Technology"
        }
    ]
];


/* =========================
   SUBJECT INFERENCE
========================= */

function infer(text) {

    const normalized =
        String(text || "").toLowerCase();

    const match =
        rules.find((rule) =>
            rule[0].test(normalized)
        );

    if (match) {
        return match[1];
    }

    return {
        subject: "General / needs review",
        ddc: "—",
        lcsh: [],
        shelf: "Librarian review required"
    };
}


/* =========================
   DDC CLEANUP
========================= */

function cleanDDC(values) {

    if (!Array.isArray(values) || values.length === 0) {
        return null;
    }

    const value =
        String(values[0])
            .replace(/[^0-9.]/g, "");

    return value || null;
}


/* =========================
   CALL NUMBER AUTHOR MARK
========================= */

function authorMark(name) {

    const parts =
        String(name || "")
            .trim()
            .split(/\s+/);

    const surname =
        parts[parts.length - 1] || "";

    const cleaned =
        surname.replace(/[^A-Za-z]/g, "");

    return (
        cleaned || "XXX"
    )
        .slice(0, 3)
        .toUpperCase();
}


/* =========================
   CATALOG ANALYSIS
========================= */

async function showCatalog(book) {

    console.log("ANALYZING BOOK:", book);

    const text = [
        book.title,
        ...(book.subject || []),
        book.description,
        ...(book.first_sentence || [])
    ]
        .filter(Boolean)
        .join(" ");

    const inferred =
        infer(text);

    let ddc =
        cleanDDC(book.ddc) ||
        inferred.ddc;

    let subject =
        inferred.subject;

    let lcsh =
        [...(inferred.lcsh || [])];

    let shelf =
        inferred.shelf;

    let confidence =
        book.ddc?.length
            ? "Metadata-supported DDC • Review required"
            : "Rule-based suggestion • Review required";

    const subjectTerms =
        [...(book.subject || [])]
            .filter(Boolean)
            .slice(0, 12);

    if (
        subject === "General / needs review" &&
        subjectTerms.length
    ) {
        subject =
            subjectTerms
                .slice(0, 3)
                .join("; ");
    }


    /* =========================
       DISPLAY BASIC RESULTS
    ========================= */

    $("resultTitle").textContent =
        book.title || "Untitled";

    $("resultAuthor").textContent =
        (book.author_name || []).join(", ") ||
        "Author not supplied";

    $("materialType").textContent =
        inferred.type ||
        (
            String(ddc || "").startsWith("8")
                ? "Fiction / Literature"
                : "Non-fiction"
        );

    $("subject").textContent =
        subject;

    $("ddc").textContent =
        ddc || "—";

    $("lcsh").textContent =
        "Searching authoritative headings…";

    $("shelf").textContent =
        shelf;

    $("callNumber").textContent =
        ddc
            ? `${ddc} ${authorMark(book.author_name?.[0])}`
            : "—";

    $("source").textContent =
        book.source ||
        "Bibliographic record";

    $("confidence").textContent =
        confidence;

    $("result").classList.remove("hidden");

    $("result").scrollIntoView({
        behavior: "smooth"
    });


    /* =========================
       LCSH
    ========================= */

    const lcshQuery = (
        inferred.lcsh?.[0] ||
        subjectTerms[0] ||
        subject
    )
        .replace(/[—–]/g, " ")
        .trim();

    if (
        lcshQuery &&
        lcshQuery !== "General / needs review"
    ) {

        try {

            const data =
                await getLCSH(lcshQuery);

            if (data.headings?.length) {

                lcsh =
                    data.headings;

                confidence =
                    "LCSH candidates from Library of Congress • Review required";
            }

            $("lcsh").textContent =
                lcsh.length
                    ? lcsh.slice(0, 5).join("; ")
                    : "No authoritative heading returned — review manually";

            $("confidence").textContent =
                confidence;

        } catch (error) {

            console.error(
                "LCSH ERROR:",
                error
            );

            $("lcsh").textContent =
                lcsh.length
                    ? lcsh.join("; ")
                    : "Authority service unavailable — review manually";
        }

    } else {

        $("lcsh").textContent =
            lcsh.length
                ? lcsh.join("; ")
                : "No LCSH candidate";
    }
}


/* =========================
   SEARCH BUTTON
========================= */

$("searchBtn").addEventListener(
    "click",
    async () => {

        const query =
            $("query").value.trim();

        if (!query) {
            alert("Enter a title or author.");
            return;
        }

        $("searchStatus").textContent =
            "Searching real bibliographic records…";

        $("searchBtn").disabled = true;
        $("searchBtn").textContent = "Searching…";

        try {

            const data =
                await searchBooks(query);

            renderMatches(data);

            $("searchStatus").textContent =
                data.docs?.length
                    ? `Search complete — ${data.docs.length} records found.`
                    : "Search complete — no records found.";

        } catch (error) {

            console.error(
                "SEARCH ERROR:",
                error
            );

            $("searchStatus").textContent =
                `Search error: ${error.message}`;

            $("matchList").innerHTML = `
                <div class="match">
                    <div>
                        <h3>Unable to retrieve results</h3>
                        <p>
                            ${esc(error.message)}
                        </p>
                    </div>
                </div>
            `;

            $("matches").classList.remove("hidden");

        } finally {

            $("searchBtn").disabled = false;
            $("searchBtn").textContent = "Search";
        }
    }
);


/* =========================
   ENTER KEY SEARCH
========================= */

$("query").addEventListener(
    "keydown",
    (event) => {

        if (event.key === "Enter") {
            $("searchBtn").click();
        }
    }
);


/* =========================
   SEARCH / PHOTO TABS
========================= */

document
    .querySelectorAll(".tab")
    .forEach((tab) => {

        tab.addEventListener(
            "click",
            () => {

                document
                    .querySelectorAll(".tab")
                    .forEach((item) =>
                        item.classList.remove("active")
                    );

                tab.classList.add("active");

                const photoMode =
                    tab.dataset.mode === "photo";

                $("searchMode")
                    .classList
                    .toggle(
                        "hidden",
                        photoMode
                    );

                $("photoMode")
                    .classList
                    .toggle(
                        "hidden",
                        !photoMode
                    );
            }
        );
    });


/* =========================
   BOOK PHOTO PREVIEW
========================= */

$("bookPhoto").addEventListener(
    "change",
    (event) => {

        const file =
            event.target.files[0];

        if (!file) {
            return;
        }

        $("preview").innerHTML = `
            <img
                src="${URL.createObjectURL(file)}"
                alt="Book cover preview"
            >
        `;
    }
);


/* =========================
   OCR
========================= */

$("photoAnalyzeBtn").addEventListener(
    "click",
    async () => {

        const file =
            $("bookPhoto").files[0];

        if (!file) {
            alert("Upload a book photo first.");
            return;
        }

        $("ocrStatus").textContent =
            "Reading image…";

        try {

            const result =
                await Tesseract.recognize(
                    file,
                    "eng"
                );

            const text =
                result.data.text || "";

            const query =
                text
                    .split(/\n+/)
                    .filter(Boolean)
                    .slice(0, 5)
                    .join(" ");

            if (!query) {

                $("ocrStatus").textContent =
                    "No readable text found.";

                return;
            }

            $("ocrStatus").textContent =
                "Text found. Searching…";

            $("query").value =
                query;

            $("searchBtn").click();

        } catch (error) {

            console.error(
                "OCR ERROR:",
                error
            );

            $("ocrStatus").textContent =
                "OCR failed. Try a clearer image.";
        }
    }
);


/* =========================
   EDIT / APPROVE
========================= */

$("editBtn").addEventListener(
    "click",
    () => {

        document
            .querySelectorAll("#result strong")
            .forEach(
                (element) => {
                    element.contentEditable = "true";
                }
            );

        alert(
            "Fields are editable."
        );
    }
);


$("approveBtn").addEventListener(
    "click",
    () => {

        alert(
            "Approved for this prototype."
        );
    }
);