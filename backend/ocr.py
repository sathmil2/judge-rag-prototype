from __future__ import annotations

import os
import re
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ExtractedPage:
    pageNumber: int
    text: str
    confidence: float | None = None
    pageWidth: float | None = None
    pageHeight: float | None = None
    pageUnit: str = ""
    ocrWords: list[dict] | None = None


@dataclass
class ExtractionResult:
    pages: list[ExtractedPage]
    provider: str
    status: str
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "pages": [asdict(page) for page in self.pages],
            "provider": self.provider,
            "status": self.status,
            "warnings": self.warnings,
        }


def extract_document(file_path: Path, content_type: str) -> ExtractionResult:
    provider = os.getenv("OCR_PROVIDER", "local").strip().lower()
    if is_plain_text_file(file_path, content_type):
        return extract_text_file(file_path)
    if provider == "azure":
        return extract_with_azure_placeholder(file_path, content_type)
    return extract_with_local_provider(file_path, content_type)


def extract_with_local_provider(file_path: Path, content_type: str) -> ExtractionResult:
    raw = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    warnings: list[str] = []

    if is_plain_text_file(file_path, content_type):
        return extract_text_file(file_path)

    if suffix == ".pdf":
        return extract_pdf(file_path, raw)

    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"} or content_type.startswith("image/"):
        return extract_image_with_tesseract(file_path)

    warnings.append("This file type needs an OCR provider before it can be searched reliably.")
    return ExtractionResult(
        pages=[ExtractedPage(pageNumber=1, text="No searchable text was extracted from this file. Add OCR to index it.")],
        provider="local-unsupported",
        status="needs_ocr",
        warnings=warnings,
    )


def is_plain_text_file(file_path: Path, content_type: str) -> bool:
    return content_type.startswith("text/") or file_path.suffix.lower() in {".txt", ".md", ".csv"}


def extract_text_file(file_path: Path) -> ExtractionResult:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    page_texts = [page.strip() for page in text.split("\f")]
    pages = [
        ExtractedPage(pageNumber=page_number, text=page_text, confidence=1.0)
        for page_number, page_text in enumerate(page_texts, start=1)
        if page_text
    ]
    return ExtractionResult(
        pages=pages or [ExtractedPage(pageNumber=1, text=text.strip(), confidence=1.0)],
        provider="local-text",
        status="complete",
        warnings=[],
    )


def extract_pdf(file_path: Path, raw: bytes) -> ExtractionResult:
    if shutil.which("pdftotext"):
        result = extract_pdf_with_pdftotext(file_path)
        if result.status == "complete":
            return result

    if shutil.which("pdftoppm") and shutil.which("tesseract"):
        result = extract_scanned_pdf_with_tesseract(file_path)
        if result.status == "complete":
            return result

    warnings: list[str] = []
    text = raw.decode("latin-1", errors="ignore")
    snippets = re.findall(r"\(([^()]{1,1000})\)", text)
    fallback = " ".join(snippets).strip()
    if fallback:
        warnings.append("Used rough PDF text fallback. Install poppler for page-aware PDF extraction.")
        return ExtractionResult(
            pages=[ExtractedPage(pageNumber=1, text=fallback, confidence=None)],
            provider="local-pdf-fallback",
            status="partial",
            warnings=warnings,
        )

    missing = missing_tools(["pdftotext", "pdftoppm", "tesseract"])
    warnings.append(f"No PDF text extracted. Install OCR/PDF tools for scanned PDFs: {', '.join(missing)}.")
    return ExtractionResult(
        pages=[ExtractedPage(pageNumber=1, text="No text was extracted from this PDF. Install OCR tools or configure Azure OCR to index it.")],
        provider="local-pdf-fallback",
        status="needs_ocr",
        warnings=warnings,
    )


def extract_pdf_with_pdftotext(file_path: Path) -> ExtractionResult:
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "pages.txt"
        command = ["pdftotext", "-layout", "-f", "1", "-l", "9999", str(file_path), str(output_path)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        if completed.returncode != 0:
            return ExtractionResult(
                pages=[ExtractedPage(pageNumber=1, text="PDF text extraction failed.")],
                provider="pdftotext",
                status="needs_ocr",
                warnings=[completed.stderr.strip() or "pdftotext failed."],
            )

        text = output_path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            return ExtractionResult(
                pages=[ExtractedPage(pageNumber=1, text="No digital text found in this PDF.")],
                provider="pdftotext",
                status="needs_ocr",
                warnings=["PDF appears scanned or empty; OCR is required."],
            )

        page_texts = [page.strip() for page in text.split("\f")]
        pages = [
            ExtractedPage(pageNumber=page_number, text=page_text, confidence=None)
            for page_number, page_text in enumerate(page_texts, start=1)
            if page_text
        ]
        return ExtractionResult(
            pages=pages,
            provider="pdftotext",
            status="complete",
            warnings=[],
        )


def extract_scanned_pdf_with_tesseract(file_path: Path) -> ExtractionResult:
    with tempfile.TemporaryDirectory() as tmp_dir:
        prefix = Path(tmp_dir) / "page"
        render_command = ["pdftoppm", "-png", "-r", "200", str(file_path), str(prefix)]
        rendered = subprocess.run(render_command, capture_output=True, text=True, timeout=90, check=False)
        if rendered.returncode != 0:
            return ExtractionResult(
                pages=[ExtractedPage(pageNumber=1, text="PDF page rendering failed.")],
                provider="pdftoppm+tesseract",
                status="needs_ocr",
                warnings=[rendered.stderr.strip() or "pdftoppm failed."],
            )

        image_paths = sorted(Path(tmp_dir).glob("page-*.png"))
        pages: list[ExtractedPage] = []
        warnings: list[str] = []
        for page_number, image_path in enumerate(image_paths, start=1):
            page = run_tesseract(image_path, page_number)
            pages.append(page)
            if not page.text.strip():
                warnings.append(f"No OCR text found on rendered PDF page {page_number}.")

        if not pages or not any(page.text.strip() for page in pages):
            return ExtractionResult(
                pages=[ExtractedPage(pageNumber=1, text="No OCR text was found in this scanned PDF.")],
                provider="pdftoppm+tesseract",
                status="needs_ocr",
                warnings=warnings or ["Tesseract did not return text."],
            )

        return ExtractionResult(
            pages=pages,
            provider="pdftoppm+tesseract",
            status="complete" if not warnings else "partial",
            warnings=warnings,
        )


def extract_image_with_tesseract(file_path: Path) -> ExtractionResult:
    if not shutil.which("tesseract"):
        return ExtractionResult(
            pages=[ExtractedPage(pageNumber=1, text="No OCR text was extracted. Install Tesseract or configure Azure OCR.")],
            provider="tesseract",
            status="needs_ocr",
            warnings=["Tesseract is not installed or not on PATH."],
        )

    page = run_tesseract(file_path, 1)
    if not page.text.strip():
        return ExtractionResult(
            pages=[page],
            provider="tesseract",
            status="needs_ocr",
            warnings=["Tesseract ran but returned no text."],
        )

    return ExtractionResult(
        pages=[page],
        provider="tesseract",
        status="complete",
        warnings=[],
    )


def run_tesseract(image_path: Path, page_number: int) -> ExtractedPage:
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_base = Path(tmp_dir) / "ocr"
        command = ["tesseract", str(image_path), str(output_base), "--psm", "6"]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        output_path = output_base.with_suffix(".txt")
        if completed.returncode != 0 or not output_path.exists():
            return ExtractedPage(pageNumber=page_number, text="", confidence=None)
        return ExtractedPage(
            pageNumber=page_number,
            text=output_path.read_text(encoding="utf-8", errors="replace").strip(),
            confidence=None,
        )


def missing_tools(tool_names: list[str]) -> list[str]:
    return [tool_name for tool_name in tool_names if not shutil.which(tool_name)]


def extract_with_azure_placeholder(file_path: Path, content_type: str) -> ExtractionResult:
    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "").strip()
    key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "").strip()
    api_version = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_API_VERSION", "2024-11-30").strip()
    model_id = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_MODEL", "prebuilt-read").strip()
    poll_seconds = float(os.getenv("AZURE_DOCUMENT_INTELLIGENCE_POLL_SECONDS", "1.5"))
    timeout_seconds = float(os.getenv("AZURE_DOCUMENT_INTELLIGENCE_TIMEOUT_SECONDS", "90"))

    if not endpoint or not key:
        return ExtractionResult(
            pages=[ExtractedPage(pageNumber=1, text="Azure OCR was requested, but Azure credentials are missing.")],
            provider=f"azure-document-intelligence:{model_id}",
            status="needs_ocr",
            warnings=[
                "OCR_PROVIDER=azure is set, so local OCR fallback is disabled. Set AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY."
            ],
        )

    try:
        analyze_url = build_azure_analyze_url(endpoint, model_id, api_version)
        operation_url = submit_azure_analyze_request(analyze_url, key, file_path, content_type)
        result = poll_azure_analyze_result(operation_url, key, poll_seconds, timeout_seconds)
        pages = pages_from_azure_result(result)
        if not pages:
            return ExtractionResult(
                pages=[ExtractedPage(pageNumber=1, text="Azure Document Intelligence returned no page text.")],
                provider=f"azure-document-intelligence:{model_id}",
                status="needs_ocr",
                warnings=["Azure analysis succeeded, but no page text was found."],
            )
        return ExtractionResult(
            pages=pages,
            provider=f"azure-document-intelligence:{model_id}",
            status="complete",
            warnings=[],
        )
    except TimeoutError as error:
        return azure_error_result(model_id, str(error))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        return azure_error_result(model_id, f"Azure OCR HTTP {error.code}: {details}")
    except urllib.error.URLError as error:
        return azure_error_result(model_id, f"Azure OCR network error: {error.reason}")
    except OSError as error:
        return azure_error_result(model_id, f"Azure OCR request failed: {error}")


def build_azure_analyze_url(endpoint: str, model_id: str, api_version: str) -> str:
    clean_endpoint = endpoint.rstrip("/")
    encoded_model = urllib.parse.quote(model_id, safe="")
    query = urllib.parse.urlencode({"api-version": api_version})
    return f"{clean_endpoint}/documentintelligence/documentModels/{encoded_model}:analyze?{query}"


def submit_azure_analyze_request(analyze_url: str, key: str, file_path: Path, content_type: str) -> str:
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": content_type or "application/octet-stream",
    }
    request = urllib.request.Request(
        analyze_url,
        data=file_path.read_bytes(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=azure_ssl_context()) as response:
        operation_url = response.headers.get("Operation-Location")
        if not operation_url:
            raise OSError("Azure response did not include Operation-Location.")
        return operation_url


def poll_azure_analyze_result(
    operation_url: str,
    key: str,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    headers = {"Ocp-Apim-Subscription-Key": key}

    while time.monotonic() < deadline:
        request = urllib.request.Request(operation_url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=60, context=azure_ssl_context()) as response:
            payload = json_loads(response.read())

        status = payload.get("status", "").lower()
        if status == "succeeded":
            return payload
        if status == "failed":
            raise OSError(f"Azure analysis failed: {payload.get('error', payload)}")
        time.sleep(poll_seconds)

    raise TimeoutError(f"Azure analysis did not finish within {timeout_seconds:g} seconds.")


def azure_ssl_context() -> ssl.SSLContext:
    ca_bundle = os.getenv("AZURE_CA_BUNDLE", "").strip()
    verify_ssl = os.getenv("AZURE_VERIFY_SSL", "true").strip().lower()

    if verify_ssl in {"0", "false", "no"}:
        return ssl._create_unverified_context()

    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle)

    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def pages_from_azure_result(payload: dict) -> list[ExtractedPage]:
    analyze_result = payload.get("analyzeResult", {})
    content = analyze_result.get("content", "")
    pages = analyze_result.get("pages", [])
    extracted_pages: list[ExtractedPage] = []

    for page_index, page in enumerate(pages, start=1):
        spans = page.get("spans", [])
        page_text = text_from_spans(content, spans)
        if not page_text:
            page_text = text_from_words(page.get("words", []))
        extracted_pages.append(ExtractedPage(
            pageNumber=page.get("pageNumber", page_index),
            text=page_text.strip(),
            confidence=average_word_confidence(page.get("words", [])),
            pageWidth=number_or_none(page.get("width")),
            pageHeight=number_or_none(page.get("height")),
            pageUnit=str(page.get("unit", "")),
            ocrWords=normalize_azure_words(page.get("words", [])),
        ))

    if not extracted_pages and content.strip():
        extracted_pages.append(ExtractedPage(pageNumber=1, text=content.strip(), confidence=None))

    return [page for page in extracted_pages if page.text]


def normalize_azure_words(words: list[dict]) -> list[dict]:
    normalized_words = []
    for word in words:
        text = str(word.get("content", "")).strip()
        polygon = normalize_polygon(word.get("polygon", []))
        if not text or not polygon:
            continue
        normalized_words.append({
            "text": text,
            "polygon": polygon,
            "confidence": word.get("confidence"),
        })
    return normalized_words


def normalize_polygon(polygon: list) -> list[dict]:
    if not polygon:
        return []

    if all(isinstance(point, dict) for point in polygon):
        points = [
            {"x": number_or_none(point.get("x")), "y": number_or_none(point.get("y"))}
            for point in polygon
        ]
    else:
        points = []
        for index in range(0, len(polygon) - 1, 2):
            points.append({"x": number_or_none(polygon[index]), "y": number_or_none(polygon[index + 1])})

    return [
        {"x": point["x"], "y": point["y"]}
        for point in points
        if point["x"] is not None and point["y"] is not None
    ]


def number_or_none(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def text_from_spans(content: str, spans: list[dict]) -> str:
    pieces: list[str] = []
    for span in spans:
        offset = int(span.get("offset", 0))
        length = int(span.get("length", 0))
        if length > 0:
            pieces.append(content[offset:offset + length])
    return "\n".join(piece.strip() for piece in pieces if piece.strip())


def text_from_words(words: list[dict]) -> str:
    return " ".join(str(word.get("content", "")).strip() for word in words if word.get("content"))


def average_word_confidence(words: list[dict]) -> float | None:
    confidences = [
        float(word["confidence"])
        for word in words
        if isinstance(word.get("confidence"), int | float)
    ]
    if not confidences:
        return None
    return round(sum(confidences) / len(confidences), 4)


def azure_error_result(model_id: str, warning: str) -> ExtractionResult:
    return ExtractionResult(
        pages=[ExtractedPage(pageNumber=1, text="Azure OCR did not return searchable text for this document.")],
        provider=f"azure-document-intelligence:{model_id}",
        status="needs_ocr",
        warnings=[warning],
    )


def json_loads(raw: bytes) -> dict:
    import json

    return json.loads(raw.decode("utf-8"))
