const uploadForm = document.querySelector("#uploadForm");
const uploadStatus = document.querySelector("#uploadStatus");
const documentList = document.querySelector("#documentList");
const runtimeConfig = document.querySelector("#runtimeConfig");
const auditUserId = document.querySelector("#auditUserId");
const auditUserName = document.querySelector("#auditUserName");
const auditUserRole = document.querySelector("#auditUserRole");
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
const auditActionFilter = document.querySelector("#auditActionFilter");
const guardrailText = document.querySelector("#guardrailText");
const modeBadge = document.querySelector("#modeBadge");
const validationStatus = document.querySelector("#validationStatus");
const answerProvider = document.querySelector("#answerProvider");
const viewerDialog = document.querySelector("#viewerDialog");
const viewerFrame = document.querySelector("#viewerFrame");
const viewerTitle = document.querySelector("#viewerTitle");
const closeViewer = document.querySelector("#closeViewer");
const previousPage = document.querySelector("#previousPage");
const nextPage = document.querySelector("#nextPage");
const pageIndicator = document.querySelector("#pageIndicator");
const viewerStatus = document.querySelector("#viewerStatus");
const pdfViewer = document.querySelector("#pdfViewer");
const pdfPage = document.querySelector("#pdfPage");
const pdfCanvas = document.querySelector("#pdfCanvas");
const highlightLayer = document.querySelector("#highlightLayer");

const PDFJS_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs";
const PDFJS_WORKER_URL = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs";

let pdfjsLibPromise = null;
let activePdf = null;
let activePageNumber = 1;
let activeHighlightText = "";
let activeOcrHighlights = [];
let activeOcrPage = null;
let activeRenderTask = null;

const defaultIdentity = {
  userId: "judge.demo",
  displayName: "Demo Judge",
  role: "judge",
};

loadIdentity();

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...identityHeaders(),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function loadIdentity() {
  const stored = JSON.parse(localStorage.getItem("judgeRagIdentity") || "null") || defaultIdentity;
  auditUserId.value = stored.userId || defaultIdentity.userId;
  auditUserName.value = stored.displayName || defaultIdentity.displayName;
  auditUserRole.value = stored.role || defaultIdentity.role;
}

function saveIdentity() {
  localStorage.setItem("judgeRagIdentity", JSON.stringify(currentIdentity()));
}

function currentIdentity() {
  return {
    userId: auditUserId.value.trim() || defaultIdentity.userId,
    displayName: auditUserName.value.trim() || auditUserId.value.trim() || defaultIdentity.displayName,
    role: auditUserRole.value || defaultIdentity.role,
  };
}

function identityHeaders() {
  const identity = currentIdentity();
  return {
    "X-User-Id": identity.userId,
    "X-User-Name": identity.displayName,
    "X-User-Role": identity.role,
    "X-Auth-Source": "prototype-ui",
  };
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

function renderConfig(config) {
  const azure = config.azureDocumentIntelligence || {};
  const isAzure = config.ocrProvider === "azure";
  runtimeConfig.className = `config-banner ${isAzure ? "azure" : "local"}`;
  runtimeConfig.textContent = isAzure
    ? `OCR mode: Azure Document Intelligence (${azure.model || "prebuilt-read"}) · endpoint ${azure.endpointConfigured ? "set" : "missing"} · key ${azure.keyConfigured ? "set" : "missing"} · local fallback disabled`
    : `OCR mode: local · Tesseract/Poppler may be used when available`;
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
    const openButton = citation.fileUrl || citation.viewerUrl ? `<button type="button">Open cited page</button>` : "";
    const card = document.createElement("article");
    card.className = "citation-card";
    card.innerHTML = `
      <strong>${escapeHtml(sourceLine)}</strong>
      <span class="meta">${escapeHtml(citation.caseNumber)} · ${escapeHtml(formatDate(citation.filingDate))} · ${escapeHtml(citation.documentId)} · ${escapeHtml(citation.searchMode || "keyword")} · ${citation.verified ? "verified" : "needs review"}</span>
      <span class="meta">Hybrid ${formatScore(citation.score)} · Keyword ${formatScore(citation.keywordScore)} · Vector ${formatScore(citation.vectorScore)}</span>
      <span class="meta">Matched: ${escapeHtml((citation.matchedTerms || []).join(", ") || "source text")}</span>
      <p>${escapeHtml(citation.snippet)}</p>
      ${openButton}
    `;
    const openCitation = card.querySelector("button");
    if (openCitation) {
      openCitation.addEventListener("click", () => {
        openCitationSource(citation);
      });
    }
    citationList.appendChild(card);
  }
}

async function openCitationSource(citation) {
  if (!citation.fileUrl && citation.viewerUrl) {
    window.open(citation.viewerUrl, "_blank", "noopener");
    return;
  }

  const fileUrl = citation.fileUrl || "";
  const cleanUrl = fileUrl.split("#")[0];
  const isPdf = cleanUrl.toLowerCase().includes(".pdf");

  viewerTitle.textContent = `${citation.documentTitle} · page ${citation.pageNumber || 1}`;
  activePageNumber = Number(citation.pageNumber || 1);
  activeHighlightText = citation.snippet || citation.sourceText || "";
  activeOcrHighlights = citation.ocrHighlights || [];
  activeOcrPage = {
    width: Number(citation.pageWidth || 0),
    height: Number(citation.pageHeight || 0),
    unit: citation.pageUnit || "",
  };
  viewerDialog.showModal();

  if (!isPdf) {
    showFrameViewer(fileUrl || citation.viewerUrl);
    return;
  }

  try {
    showPdfViewer();
    viewerStatus.textContent = "Loading PDF page...";
    const pdfjsLib = await loadPdfJs();
    activePdf = await pdfjsLib.getDocument(cleanUrl).promise;
    activePageNumber = clamp(activePageNumber, 1, activePdf.numPages);
    await renderPdfPage(activePageNumber);
  } catch (error) {
    showFrameViewer(fileUrl);
    viewerStatus.textContent = `PDF.js preview failed, showing browser preview instead. ${error.message}`;
  }
}

async function loadPdfJs() {
  if (!pdfjsLibPromise) {
    pdfjsLibPromise = import(PDFJS_URL).then((module) => {
      module.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
      window.pdfjsLib = module;
      return module;
    });
  }
  return pdfjsLibPromise;
}

function showPdfViewer() {
  viewerFrame.hidden = true;
  viewerFrame.src = "about:blank";
  pdfViewer.hidden = false;
  viewerStatus.hidden = false;
  previousPage.hidden = false;
  nextPage.hidden = false;
  pageIndicator.hidden = false;
}

function showFrameViewer(url) {
  activePdf = null;
  pdfViewer.hidden = true;
  viewerFrame.hidden = false;
  viewerFrame.src = url;
  viewerStatus.hidden = false;
  previousPage.hidden = true;
  nextPage.hidden = true;
  pageIndicator.hidden = true;
}

async function renderPdfPage(pageNumber) {
  if (!activePdf) return;

  if (activeRenderTask) {
    activeRenderTask.cancel();
    activeRenderTask = null;
  }

  highlightLayer.innerHTML = "";
  viewerStatus.textContent = "Rendering page...";
  activePageNumber = clamp(pageNumber, 1, activePdf.numPages);

  const page = await activePdf.getPage(activePageNumber);
  const containerWidth = Math.min(pdfViewer.clientWidth - 32, 960);
  const unscaledViewport = page.getViewport({ scale: 1 });
  const scale = Math.max(0.6, Math.min(1.7, containerWidth / unscaledViewport.width));
  const viewport = page.getViewport({ scale });
  const context = pdfCanvas.getContext("2d");

  pdfCanvas.width = Math.floor(viewport.width);
  pdfCanvas.height = Math.floor(viewport.height);
  pdfCanvas.style.width = `${Math.floor(viewport.width)}px`;
  pdfCanvas.style.height = `${Math.floor(viewport.height)}px`;
  pdfPage.style.width = `${Math.floor(viewport.width)}px`;
  pdfPage.style.height = `${Math.floor(viewport.height)}px`;
  highlightLayer.style.width = `${Math.floor(viewport.width)}px`;
  highlightLayer.style.height = `${Math.floor(viewport.height)}px`;

  activeRenderTask = page.render({ canvasContext: context, viewport });
  await activeRenderTask.promise;
  activeRenderTask = null;

  const textContent = await page.getTextContent();
  renderHighlights(textContent.items, viewport, activeHighlightText);
  if (!highlightLayer.children.length) {
    renderOcrHighlights(activeOcrHighlights, activeOcrPage);
  }
  pageIndicator.textContent = `Page ${activePageNumber} of ${activePdf.numPages}`;
  previousPage.disabled = activePageNumber <= 1;
  nextPage.disabled = activePageNumber >= activePdf.numPages;
  viewerStatus.textContent = highlightLayer.children.length
    ? "Highlighted matching citation text on this page."
    : "Page rendered. No exact text or OCR highlight match found for the citation snippet.";
}

function renderHighlights(textItems, viewport, snippet) {
  const terms = importantTerms(snippet);
  if (!terms.size) return;

  for (const item of textItems) {
    const itemTerms = importantTerms(item.str);
    const overlap = [...itemTerms].filter((term) => terms.has(term));
    if (!overlap.length) continue;

    const rect = textItemRect(item, viewport);
    if (!rect.width || !rect.height) continue;

    const mark = document.createElement("span");
    mark.className = "pdf-highlight";
    mark.style.left = `${rect.left}px`;
    mark.style.top = `${rect.top}px`;
    mark.style.width = `${rect.width}px`;
    mark.style.height = `${rect.height}px`;
    highlightLayer.appendChild(mark);
  }
}

function textItemRect(item, viewport) {
  const tx = window.pdfjsLib
    ? window.pdfjsLib.Util.transform(viewport.transform, item.transform)
    : null;
  if (!tx) {
    return { left: 0, top: 0, width: 0, height: 0 };
  }

  const height = Math.max(Math.hypot(tx[2], tx[3]), (item.height || 10) * viewport.scale);
  const width = Math.max((item.width || 0) * viewport.scale, 4);
  return {
    left: tx[4],
    top: tx[5] - height,
    width,
    height: Math.max(height, 8),
  };
}

function renderOcrHighlights(highlights, pageInfo) {
  if (!highlights?.length || !pageInfo?.width || !pageInfo?.height) return;

  const xScale = pdfCanvas.width / pageInfo.width;
  const yScale = pdfCanvas.height / pageInfo.height;

  for (const highlight of highlights) {
    const polygon = highlight.polygon || [];
    if (!polygon.length) continue;

    const xs = polygon.map((point) => Number(point.x)).filter(Number.isFinite);
    const ys = polygon.map((point) => Number(point.y)).filter(Number.isFinite);
    if (!xs.length || !ys.length) continue;

    const left = Math.min(...xs) * xScale;
    const top = Math.min(...ys) * yScale;
    const width = (Math.max(...xs) - Math.min(...xs)) * xScale;
    const height = (Math.max(...ys) - Math.min(...ys)) * yScale;
    if (width <= 0 || height <= 0) continue;

    const mark = document.createElement("span");
    mark.className = "pdf-highlight ocr-highlight";
    mark.title = highlight.text || "OCR highlight";
    mark.style.left = `${left}px`;
    mark.style.top = `${top}px`;
    mark.style.width = `${width}px`;
    mark.style.height = `${Math.max(height, 8)}px`;
    highlightLayer.appendChild(mark);
  }
}

function importantTerms(text) {
  const stopWords = new Set(["the", "and", "for", "with", "that", "this", "from", "page", "source", "case", "document"]);
  return new Set(
    String(text || "")
      .toLowerCase()
      .match(/[a-z0-9]{3,}/g)
      ?.filter((term) => !stopWords.has(term))
      .slice(0, 80) || []
  );
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
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
    const user = entry.user || {};
    const resource = entry.resource || {};
    const details = entry.details || {};
    const title = entry.action === "assistant.ask"
      ? details.question || resource.title || "Question"
      : resource.title || entry.action || "Audit event";
    const citationCount = details.citationCount ?? entry.citations?.length ?? 0;
    item.innerHTML = `
      <strong>${escapeHtml(title)}</strong>
      <span class="meta">${escapeHtml(entry.action || "unknown action")} · ${escapeHtml(entry.outcome || "unknown")} · ${escapeHtml(date)}</span>
      <span class="meta">${escapeHtml(user.displayName || user.userId || "unknown user")} · ${escapeHtml(user.role || "unknown role")} · ${escapeHtml(entry.caseNumber || "all cases")}</span>
      <span class="meta">${escapeHtml(resource.type || "resource")} ${escapeHtml(resource.id || "")} · ${citationCount} citation${citationCount === 1 ? "" : "s"}</span>
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

function formatScore(value) {
  const number = Number(value || 0);
  return Number.isInteger(number) ? String(number) : number.toFixed(3);
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
  const params = new URLSearchParams({ limit: "100" });
  if (auditActionFilter.value) {
    params.set("action", auditActionFilter.value);
  }
  const payload = await api(`/api/audit?${params.toString()}`);
  renderAudit(payload.auditLog);
}

async function loadConfig() {
  const payload = await api("/api/config");
  renderConfig(payload);
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
  activePdf = null;
  highlightLayer.innerHTML = "";
  activeHighlightText = "";
  activeOcrHighlights = [];
  activeOcrPage = null;
  activeRenderTask = null;
});

previousPage.addEventListener("click", () => {
  renderPdfPage(activePageNumber - 1).catch((error) => {
    viewerStatus.textContent = error.message;
  });
});

nextPage.addEventListener("click", () => {
  renderPdfPage(activePageNumber + 1).catch((error) => {
    viewerStatus.textContent = error.message;
  });
});

refreshAudit.addEventListener("click", () => {
  loadAudit().catch((error) => {
    auditList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
  });
});

auditActionFilter.addEventListener("change", () => {
  loadAudit().catch((error) => {
    auditList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
  });
});

for (const input of [auditUserId, auditUserName, auditUserRole]) {
  input.addEventListener("change", saveIdentity);
}

loadDocuments().catch((error) => {
  documentList.innerHTML = `<p class="empty error">${escapeHtml(error.message)}</p>`;
});

loadConfig().catch((error) => {
  runtimeConfig.className = "config-banner local";
  runtimeConfig.textContent = `Could not load OCR mode: ${error.message}`;
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
