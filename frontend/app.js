const uploadForm = document.querySelector("#uploadForm");
const uploadStatus = document.querySelector("#uploadStatus");
const documentList = document.querySelector("#documentList");
const askForm = document.querySelector("#askForm");
const questionInput = document.querySelector("#questionInput");
const caseFilter = document.querySelector("#caseFilter");
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
    const item = document.createElement("article");
    item.className = "document-item";
    item.innerHTML = `
      <strong>${escapeHtml(doc.documentTitle)}</strong>
      <span class="meta">${escapeHtml(doc.caseNumber)} · ${escapeHtml(formatDate(doc.filingDate))} · ${doc.pageCount} page${doc.pageCount === 1 ? "" : "s"}</span>
      <span class="meta">${escapeHtml(doc.documentId)}</span>
    `;
    documentList.appendChild(item);
  }
}

function renderCitations(citations) {
  citationList.innerHTML = "";
  if (!citations.length) {
    citationList.innerHTML = `<p class="empty">No cited pages found for this question.</p>`;
    return;
  }

  for (const citation of citations) {
    const card = document.createElement("article");
    card.className = "citation-card";
    card.innerHTML = `
      <strong>${escapeHtml(citation.documentTitle)}, page ${citation.pageNumber}</strong>
      <span class="meta">${escapeHtml(citation.caseNumber)} · ${escapeHtml(formatDate(citation.filingDate))} · ${escapeHtml(citation.documentId)}</span>
      <p>${escapeHtml(citation.snippet)}</p>
      <button type="button">Open cited page</button>
    `;
    card.querySelector("button").addEventListener("click", () => {
      viewerTitle.textContent = `${citation.documentTitle} · page ${citation.pageNumber}`;
      viewerFrame.src = citation.fileUrl;
      viewerDialog.showModal();
    });
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

