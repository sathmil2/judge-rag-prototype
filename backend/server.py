from __future__ import annotations

import json
import mimetypes
import re
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
INDEX_FILE = DATA_DIR / "index.json"


@dataclass
class PageChunk:
    caseNumber: str
    documentId: str
    documentTitle: str
    filingDate: str
    pageNumber: int
    chunkText: str
    sourceFile: str
    viewerUrl: str


@dataclass
class CaseEvent:
    caseNumber: str
    eventId: str
    eventDate: str
    eventType: str
    eventText: str
    source: str


def ensure_storage() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text(json.dumps({"documents": [], "chunks": [], "events": [], "auditLog": []}, indent=2), encoding="utf-8")


def read_index() -> dict:
    ensure_storage()
    index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    index.setdefault("documents", [])
    index.setdefault("chunks", [])
    index.setdefault("events", [])
    index.setdefault("auditLog", [])
    return index


def write_index(index: dict) -> None:
    ensure_storage()
    tmp = INDEX_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=2), encoding="utf-8")
    tmp.replace(INDEX_FILE)


def extract_pages(file_path: Path, content_type: str) -> list[str]:
    """Dependency-free text extraction for the prototype.

    Production hook: replace this with OCR/page extraction from Azure Document
    Intelligence, AWS Textract, Google Document AI, or a PDF text parser.
    """
    raw = file_path.read_bytes()
    if content_type.startswith("text/") or file_path.suffix.lower() in {".txt", ".md", ".csv"}:
        text = raw.decode("utf-8", errors="replace")
        pages = [page.strip() for page in text.split("\f")]
        return [page for page in pages if page] or [text.strip()]

    if file_path.suffix.lower() == ".pdf":
        # Very rough fallback for simple digital PDFs. Scanned PDFs need OCR.
        text = raw.decode("latin-1", errors="ignore")
        snippets = re.findall(r"\(([^()]{1,1000})\)", text)
        fallback = " ".join(snippets).strip()
        if fallback:
            return [fallback]
        return ["Text extraction is unavailable for this PDF in the dependency-free prototype. Add OCR to index this document."]

    return ["Text extraction is unavailable for this file type. Add OCR to index this document."]


def tokenize(text: str) -> list[str]:
    stop_words = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in",
        "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were", "with",
    }
    return [word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in stop_words]


def score_chunk(query_terms: list[str], chunk: dict) -> int:
    text = chunk["chunkText"].lower()
    title = chunk.get("documentTitle", chunk.get("eventType", "")).lower()
    score = 0
    for term in query_terms:
        score += text.count(term)
        if term in title:
            score += 2
    return score


def summarize_answer(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return "I could not find a cited source for that in the uploaded case documents."

    snippets = []
    for chunk in chunks[:3]:
        text = " ".join(chunk["chunkText"].split())
        snippets.append(text[:280] + ("..." if len(text) > 280 else ""))

    return (
        "Based on the retrieved case document pages, the most relevant source text says: "
        + " ".join(snippets)
    )


def parse_multipart(headers, body: bytes) -> dict[str, dict]:
    content_type = headers.get("Content-Type", "")
    pseudo_message = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    message = BytesParser(policy=default).parsebytes(pseudo_message)
    fields: dict[str, dict] = {}
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        name_match = re.search(r'name="([^"]+)"', disposition)
        if not name_match:
            continue
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', disposition)
        payload = part.get_payload(decode=True) or b""
        fields[name] = {
            "filename": filename_match.group(1) if filename_match else None,
            "content_type": part.get_content_type(),
            "value": payload,
        }
    return fields


class Handler(BaseHTTPRequestHandler):
    server_version = "JudgeRAGPrototype/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        if path == "/api/documents":
            self.send_json({"documents": read_index()["documents"]})
            return

        if path == "/api/events":
            parsed_query = parse_qs(parsed.query)
            case_number = parsed_query.get("caseNumber", [""])[0].strip().lower()
            events = read_index()["events"]
            if case_number:
                events = [event for event in events if event["caseNumber"].lower() == case_number]
            self.send_json({"events": events})
            return

        if path == "/api/audit":
            self.send_json({"auditLog": read_index()["auditLog"][-50:]})
            return

        if path.startswith("/uploads/"):
            self.serve_file(UPLOAD_DIR / path.removeprefix("/uploads/"))
            return

        if path == "/" or path.startswith("/assets/"):
            file_path = FRONTEND_DIR / ("index.html" if path == "/" else path.removeprefix("/assets/"))
            self.serve_file(file_path)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/upload":
            self.handle_upload()
            return

        if parsed.path == "/api/ask":
            self.handle_ask()
            return

        if parsed.path == "/api/events":
            self.handle_event()
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_upload(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        fields = parse_multipart(self.headers, self.rfile.read(length))

        file_field = fields.get("document")
        if not file_field or not file_field["filename"]:
            self.send_json({"error": "Missing document file."}, HTTPStatus.BAD_REQUEST)
            return

        case_number = (fields.get("caseNumber", {}).get("value", b"").decode("utf-8", errors="replace").strip())
        title = (fields.get("documentTitle", {}).get("value", b"").decode("utf-8", errors="replace").strip())
        filing_date = (fields.get("filingDate", {}).get("value", b"").decode("utf-8", errors="replace").strip())

        if not case_number:
            self.send_json({"error": "Case number is required."}, HTTPStatus.BAD_REQUEST)
            return

        document_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
        original_name = Path(file_field["filename"]).name
        saved_name = f"{document_id}-{original_name}"
        saved_path = UPLOAD_DIR / saved_name
        saved_path.write_bytes(file_field["value"])

        title = title or original_name
        content_type = file_field["content_type"] or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
        pages = extract_pages(saved_path, content_type)

        index = read_index()
        document = {
            "caseNumber": case_number,
            "documentId": document_id,
            "documentTitle": title,
            "filingDate": filing_date,
            "sourceFile": saved_name,
            "contentType": content_type,
            "pageCount": len(pages),
            "uploadedAt": int(time.time()),
        }
        index["documents"].append(document)

        for page_number, page_text in enumerate(pages, start=1):
            viewer_url = f"/document-viewer?case={case_number}&docId={document_id}&page={page_number}"
            index["chunks"].append(asdict(PageChunk(
                caseNumber=case_number,
                documentId=document_id,
                documentTitle=title,
                filingDate=filing_date,
                pageNumber=page_number,
                chunkText=page_text,
                sourceFile=saved_name,
                viewerUrl=viewer_url,
            )))

        write_index(index)
        self.send_json({"document": document})

    def handle_event(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json({"error": "Request body must be valid JSON."}, HTTPStatus.BAD_REQUEST)
            return

        case_number = payload.get("caseNumber", "").strip()
        event_date = payload.get("eventDate", "").strip()
        event_type = payload.get("eventType", "").strip()
        event_text = payload.get("eventText", "").strip()
        source = payload.get("source", "manual docket entry").strip()

        if not case_number or not event_type or not event_text:
            self.send_json({"error": "Case number, event type, and event text are required."}, HTTPStatus.BAD_REQUEST)
            return

        event = asdict(CaseEvent(
            caseNumber=case_number,
            eventId=f"EVT-{uuid.uuid4().hex[:8].upper()}",
            eventDate=event_date,
            eventType=event_type,
            eventText=event_text,
            source=source,
        ))

        index = read_index()
        index["events"].append(event)
        write_index(index)
        self.send_json({"event": event})

    def handle_ask(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self.send_json({"error": "Request body must be valid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        question = payload.get("question", "").strip()
        case_number = payload.get("caseNumber", "").strip()
        source_filter = payload.get("sourceFilter", "all").strip()

        if not question:
            self.send_json({"error": "Question is required."}, HTTPStatus.BAD_REQUEST)
            return

        index = read_index()
        terms = tokenize(question)
        candidates = []

        if source_filter in {"all", "documents"}:
            candidates.extend(
                {
                    **chunk,
                    "sourceType": "case document",
                    "sourceLabel": f"{chunk['documentTitle']}, page {chunk['pageNumber']}",
                    "chunkText": chunk["chunkText"],
                }
                for chunk in index["chunks"]
                if not case_number or chunk["caseNumber"].lower() == case_number.lower()
            )

        if source_filter in {"all", "events"}:
            candidates.extend(
                {
                    **event,
                    "sourceType": "docket event",
                    "sourceLabel": event["eventType"],
                    "documentId": event["eventId"],
                    "documentTitle": event["eventType"],
                    "filingDate": event["eventDate"],
                    "pageNumber": None,
                    "chunkText": event["eventText"],
                    "viewerUrl": "",
                    "sourceFile": "",
                }
                for event in index["events"]
                if not case_number or event["caseNumber"].lower() == case_number.lower()
            )

        ranked = sorted(
            ((score_chunk(terms, chunk), chunk) for chunk in candidates),
            key=lambda pair: pair[0],
            reverse=True,
        )
        matches = [chunk for score, chunk in ranked if score > 0][:5]

        answer = summarize_answer(question, matches)
        citations = []
        for chunk in matches:
            snippet = " ".join(chunk["chunkText"].split())[:420]
            citation = {
                "caseNumber": chunk["caseNumber"],
                "documentId": chunk["documentId"],
                "documentTitle": chunk["documentTitle"],
                "filingDate": chunk["filingDate"],
                "pageNumber": chunk["pageNumber"],
                "snippet": snippet,
                "viewerUrl": chunk["viewerUrl"],
                "fileUrl": f"/uploads/{chunk['sourceFile']}#page={chunk['pageNumber']}" if chunk["sourceFile"] else "",
                "sourceType": chunk["sourceType"],
                "sourceLabel": chunk["sourceLabel"],
                "verified": snippet[:80].lower() in " ".join(chunk["chunkText"].split()).lower(),
            }
            citations.append(citation)

        index["auditLog"].append({
            "timestamp": int(time.time()),
            "caseNumber": case_number,
            "question": question,
            "sourceFilter": source_filter,
            "citations": citations,
        })
        write_index(index)

        self.send_json({
            "answer": answer,
            "citations": citations,
            "mode": "keyword-prototype",
            "guardrail": "No citation, no case-specific answer.",
        })

    def serve_file(self, file_path: Path) -> None:
        try:
            resolved = file_path.resolve()
            allowed_roots = [FRONTEND_DIR.resolve(), UPLOAD_DIR.resolve()]
            if not any(resolved == root or root in resolved.parents for root in allowed_roots):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if not resolved.exists() or not resolved.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(resolved.stat().st_size))
            self.end_headers()
            with resolved.open("rb") as handle:
                shutil.copyfileobj(handle, self.wfile)
        except BrokenPipeError:
            return

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    ensure_storage()
    host = "127.0.0.1"
    port = 8000
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Judge RAG prototype running at http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
