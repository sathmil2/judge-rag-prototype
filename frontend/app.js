const uploadForm = document.querySelector("#uploadForm");
const uploadStatus = document.querySelector("#uploadStatus");
const documentList = document.querySelector("#documentList");
const eventForm = document.querySelector("#eventForm");
const eventStatus = document.querySelector("#eventStatus");
const eventList = document.querySelector("#eventList");
const askForm = document.querySelector("#askForm");
const questionInput = document.querySelector("#questionInput");
const caseFilter = document.querySelector("#caseFilter");
const sourceFilter = document.querySelector("#sourceFilter");
const answerText = document.querySelector("#answerText");
const citationList = document.querySelector("#citationList");
const guardrailText = document.querySelector("#guardrailText");
const modeBadge = document.querySelector("#modeBadge");
const viewerDialog = document.querySelector("#viewerDialog");
const viewerFrame = document.querySelector("#viewerFrame");
const viewerTitle = document.querySelector("#viewerTitle");
const closeViewer = document.querySelector("#closeViewer");

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function formatDate(value) {
  if (!value) return "No filing date";
  return value;
}

function renderDocuments(documents) {
  documentList.innerHTML = "";
  if (!documents.length) {
    documentList.innerHTML = `<p class="empty">No documents indexed yet.</p>`;
    return;
  }

  for (const doc of documents.slice().reverse()) {
    const extraction = doc.extraction || { provider: "unknown", status: "unknown", warnings: [] };
    const warnings = extraction.warnings?.length
      ? `<span class="meta warning">${escapeHtml(extraction.warnings[0])}</span>`
      : "";
    const item = document.createElement("article");
    item.className = "document-item";
    item.innerHTML = `
      <strong>${escapeHtml(doc.documentTitle)}</strong>
      <span class="meta">${escapeHtml(doc.caseNumber)} · ${escapeHtml(formatDate(doc.filingDate))} · ${doc.pageCount} page${doc.pageCount === 1 ? "" : "s"}</span>
      <span class="meta">${escapeHtml(doc.documentId)} · ${escapeHtml(extraction.provider)} · ${escapeHtml(extraction.status)}</span>
      ${warnings}
    `;
    documentList.appendChild(item);
  }
}

function renderEvents(events) {
  eventList.innerHTML = "";
  if (!events.length) {
    eventList.innerHTML = `<p class="empty">No docket events added yet.</p>`;
    return;
  }

  for (const event of events.slice().reverse()) {
    const item = document.createElement("article");
    item.className = "document-item";
    item.innerHTML = `
      <strong>${escapeHtml(event.eventType)}</strong>
      <span class="meta">${escapeHtml(event.caseNumber)} · ${escapeHtml(formatDate(event.eventDate))}</span>
      <span class="meta">${escapeHtml(event.eventText.slice(0, 130))}${event.eventText.length > 130 ? "..." : ""}</span>
    `;
    eventList.appendChild(item);
  }
}

function renderCitations(citations) {
  citationList.innerHTML = "";
  if (!citations.length) {
    citationList.innerHTML = `<p class="empty">No cited pages found for this question.</p>`;
    return;
  }

  for (const citation of citations) {
    const sourceLine = citation.sourceType === "docket event"
      ? `${citation.sourceType} · ${citation.sourceLabel}`
      : `${citation.sourceType} · ${citation.documentTitle}, page ${citation.pageNumber}`;
    const openButton = citation.fileUrl ? `<button type="button">Open cited page</button>` : "";
    const card = document.createElement("article");
    card.className = "citation-card";
    card.innerHTML = `
      <strong>${escapeHtml(sourceLine)}</strong>
      <span class="meta">${escapeHtml(citation.caseNumber)} · ${escapeHtml(formatDate(citation.filingDate))} · ${escapeHtml(citation.documentId)} · ${citation.verified ? "verified" : "needs review"}</span>
      <p>${escapeHtml(citation.snippet)}</p>
      ${openButton}
    `;
    const openCitation = card.querySelector("button");
    if (openCitation) {
      openCitation.addEventListener("click", () => {
        viewerTitle.textContent = `${citation.documentTitle} · page ${citation.pageNumber}`;
        viewerFrame.src = citation.fileUrl;
        viewerDialog.showModal();
      });
    }
    citationList.appendChild(card);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadDocuments() {
  const payload = await api("/api/documents");
  renderDocuments(payload.documents);
}

async function loadEvents() {
  const payload = await api("/api/events");
  renderEvents(payload.events);
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  uploadStatus.textContent = "Uploading and indexing...";
  uploadStatus.classList.remove("error");

  try {
    const payload = await api("/api/upload", {
      method: "POST",
      body: new FormData(uploadForm),
    });
    uploadStatus.textContent = `Indexed ${payload.document.documentTitle}.`;
    uploadForm.reset();
    await loadDocuments();
  } catch (error) {
    uploadStatus.textContent = error.message;
    uploadStatus.classList.add("error");
  }
});

eventForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  eventStatus.textContent = "Adding docket event...";
  eventStatus.classList.remove("error");

  const form = new FormData(eventForm);
  try {
    const payload = await api("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        caseNumber: form.get("caseNumber"),
        eventType: form.get("eventType"),
        eventDate: form.get("eventDate"),
        eventText: form.get("eventText"),
      }),
    });
    eventStatus.textContent = `Added ${payload.event.eventType}.`;
    eventForm.reset();
    await loadEvents();
  } catch (error) {
    eventStatus.textContent = error.message;
    eventStatus.classList.add("error");
  }
});

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  answerText.textContent = "Retrieving cited pages...";
  citationList.innerHTML = "";

  try {
    const payload = await api("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: questionInput.value,
        caseNumber: caseFilter.value,
        sourceFilter: sourceFilter.value,
      }),
    });
    answerText.textContent = payload.answer;
    guardrailText.textContent = payload.guardrail;
    modeBadge.textContent = payload.mode;
    renderCitations(payload.citations);
  } catch (error) {
    answerText.textContent = error.message;
    citationList.innerHTML = "";
  }
});

closeViewer.addEventListener("click", () => {
  viewerDialog.close();
  viewerFrame.src = "about:blank";
});

loadDocuments().catch((error) => {
  documentList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
});

loadEvents().catch((error) => {
  eventList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
});
