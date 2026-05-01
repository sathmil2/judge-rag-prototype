from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ExtractedPage:
    pageNumber: int
    text: str
    confidence: float | None = None


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
    if provider == "azure":
        return extract_with_azure_placeholder(file_path, content_type)
    return extract_with_local_provider(file_path, content_type)


def extract_with_local_provider(file_path: Path, content_type: str) -> ExtractionResult:
    raw = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    warnings: list[str] = []

    if content_type.startswith("text/") or suffix in {".txt", ".md", ".csv"}:
        text = raw.decode("utf-8", errors="replace")
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

    if not endpoint or not key:
        result = extract_with_local_provider(file_path, content_type)
        result.warnings.append(
            "OCR_PROVIDER=azure is set, but Azure Document Intelligence endpoint/key are missing."
        )
        return result

    return ExtractionResult(
        pages=[
            ExtractedPage(
                pageNumber=1,
                text=(
                    "Azure OCR is configured but not implemented in this dependency-free prototype. "
                    "Replace extract_with_azure_placeholder with an Azure Document Intelligence Read/Layout call."
                ),
                confidence=None,
            )
        ],
        provider="azure-document-intelligence-placeholder",
        status="needs_implementation",
        warnings=["Azure adapter boundary is ready; HTTP polling implementation is the next integration step."],
    )
