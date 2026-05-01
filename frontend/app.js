const uploadForm = document.querySelector("#uploadForm");
const uploadStatus = document.querySelector("#uploadStatus");
const documentList = document.querySelector("#documentList");
const eventForm = document.querySelector("#eventForm");
const eventStatus = document.querySelector("#eventStatus");
const eventList = document.querySelector("#eventList");
const lawForm = document.querySelector("#lawForm");
const lawStatus = document.querySelector("#lawStatus");
const lawList = document.querySelector("#lawList");
const askForm = document.querySelector("#askForm");
const questionInput = document.querySelector("#questionInput");
const caseFilter = document.querySelector("#caseFilter");
const sourceFilter = document.querySelector("#sourceFilter");
const answerText = document.querySelector("#answerText");
const citationList = document.querySelector("#citationList");
const auditList = document.querySelector("#auditList");
const refreshAudit = document.querySelector("#refreshAudit");
const guardrailText = document.querySelector("#guardrailText");
const modeBadge = document.querySelector("#modeBadge");
const validationStatus = document.querySelector("#validationStatus");
const answerProvider = document.querySelector("#answerProvider");
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

function renderLegalReferences(references) {
  lawList.innerHTML = "";
  if (!references.length) {
    lawList.innerHTML = `<p class="empty">No legal references added yet.</p>`;
    return;
  }

  for (const reference of references.slice().reverse()) {
    const item = document.createElement("article");
    item.className = "document-item";
    item.innerHTML = `
      <strong>${escapeHtml(reference.citation)}</strong>
      <span class="meta">${escapeHtml(reference.title)} · ${escapeHtml(reference.jurisdiction)} · ${escapeHtml(formatDate(reference.effectiveDate))}</span>
      <span class="meta">${escapeHtml(reference.referenceText.slice(0, 130))}${reference.referenceText.length > 130 ? "..." : ""}</span>
    `;
    lawList.appendChild(item);
  }
}

function renderCitations(citations) {
  citationList.innerHTML = "";
  if (!citations.length) {
    citationList.innerHTML = `<p class="empty">No cited pages found for this question.</p>`;
    return;
  }

  for (const citation of citations) {
    const sourceLine = citation.sourceType === "case document"
      ? `${citation.sourceType} · ${citation.documentTitle}, page ${citation.pageNumber}`
      : `${citation.sourceType} · ${citation.sourceLabel}`;
    const openButton = citation.fileUrl || citation.viewerUrl ? `<button type="button">Open source</button>` : "";
    const card = document.createElement("article");
    card.className = "citation-card";
    card.innerHTML = `
      <strong>${escapeHtml(sourceLine)}</strong>
      <span class="meta">${escapeHtml(citation.caseNumber)} · ${escapeHtml(formatDate(citation.filingDate))} · ${escapeHtml(citation.documentId)} · score ${citation.score ?? 0} · ${citation.verified ? "verified" : "needs review"}</span>
      <span class="meta">Matched: ${escapeHtml((citation.matchedTerms || []).join(", ") || "source text")}</span>
      <p>${escapeHtml(citation.snippet)}</p>
      ${openButton}
    `;
    const openCitation = card.querySelector("button");
    if (openCitation) {
      openCitation.addEventListener("click", () => {
        if (citation.fileUrl) {
          viewerTitle.textContent = `${citation.documentTitle} · page ${citation.pageNumber}`;
          viewerFrame.src = citation.fileUrl;
          viewerDialog.showModal();
        } else if (citation.viewerUrl) {
          window.open(citation.viewerUrl, "_blank", "noopener");
        }
      });
    }
    citationList.appendChild(card);
  }
}

function renderValidation(validation) {
  if (!validation) {
    validationStatus.textContent = "Validation has not run yet.";
    validationStatus.className = "validation-status";
    return;
  }

  const summary = `${validation.validCitationCount} of ${validation.totalCitationCount} citations validated`;
  validationStatus.textContent = `${validation.status}: ${summary}`;
  validationStatus.className = `validation-status ${validation.status === "passed" ? "valid" : "invalid"}`;
}

function renderAnswerMeta(answerMeta) {
  if (!answerMeta) {
    answerProvider.textContent = "Answer provider has not run yet.";
    answerProvider.className = "answer-provider";
    return;
  }

  answerProvider.textContent = `${answerMeta.provider} · ${answerMeta.status}`;
  answerProvider.className = `answer-provider ${answerMeta.status === "complete" ? "valid" : "warning"}`;
}

function renderAudit(auditLog) {
  auditList.innerHTML = "";
  if (!auditLog.length) {
    auditList.innerHTML = `<p class="empty">No questions logged yet.</p>`;
    return;
  }

  for (const entry of auditLog.slice().reverse().slice(0, 8)) {
    const item = document.createElement("article");
    item.className = "citation-card audit-card";
    const date = new Date(entry.timestamp * 1000).toLocaleString();
    item.innerHTML = `
      <strong>${escapeHtml(entry.question)}</strong>
      <span class="meta">${escapeHtml(entry.caseNumber || "all cases")} · ${escapeHtml(entry.sourceFilter)} · ${escapeHtml(entry.validation?.status || "not validated")} · ${escapeHtml(entry.answerProvider || "unknown provider")} · ${escapeHtml(date)}</span>
      <span class="meta">${entry.citations?.length || 0} citation${entry.citations?.length === 1 ? "" : "s"}</span>
    `;
    auditList.appendChild(item);
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

async function loadLegalReferences() {
  const payload = await api("/api/legal-references");
  renderLegalReferences(payload.legalReferences);
}

async function loadAudit() {
  const payload = await api("/api/audit");
  renderAudit(payload.auditLog);
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

lawForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  lawStatus.textContent = "Adding legal reference...";
  lawStatus.classList.remove("error");

  const form = new FormData(lawForm);
  try {
    const payload = await api("/api/legal-references", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        citation: form.get("citation"),
        title: form.get("title"),
        effectiveDate: form.get("effectiveDate"),
        sourceUrl: form.get("sourceUrl"),
        referenceText: form.get("referenceText"),
      }),
    });
    lawStatus.textContent = `Added ${payload.legalReference.citation}.`;
    lawForm.reset();
    await loadLegalReferences();
  } catch (error) {
    lawStatus.textContent = error.message;
    lawStatus.classList.add("error");
  }
});

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  answerText.textContent = "Retrieving cited pages...";
  renderValidation(null);
  renderAnswerMeta(null);
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
    renderValidation(payload.validation);
    renderAnswerMeta(payload.answerMeta);
    renderCitations(payload.citations);
    await loadAudit();
  } catch (error) {
    answerText.textContent = error.message;
    renderValidation(null);
    renderAnswerMeta(null);
    citationList.innerHTML = "";
  }
});

closeViewer.addEventListener("click", () => {
  viewerDialog.close();
  viewerFrame.src = "about:blank";
});

refreshAudit.addEventListener("click", () => {
  loadAudit().catch((error) => {
    auditList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
  });
});

loadDocuments().catch((error) => {
  documentList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
});

loadEvents().catch((error) => {
  eventList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
});

loadLegalReferences().catch((error) => {
  lawList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
});

loadAudit().catch((error) => {
  auditList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
});
