from __future__ import annotations

import os
import re
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
        text = raw.decode("latin-1", errors="ignore")
        snippets = re.findall(r"\(([^()]{1,1000})\)", text)
        fallback = " ".join(snippets).strip()
        if fallback:
            warnings.append("Used rough PDF text fallback. Add OCR for production-grade page mapping.")
            return ExtractionResult(
                pages=[ExtractedPage(pageNumber=1, text=fallback, confidence=None)],
                provider="local-pdf-fallback",
                status="partial",
                warnings=warnings,
            )

        warnings.append("No text extracted. Scanned or complex PDFs require OCR.")
        return ExtractionResult(
            pages=[ExtractedPage(pageNumber=1, text="No text was extracted from this PDF. Add OCR to index it.")],
            provider="local-pdf-fallback",
            status="needs_ocr",
            warnings=warnings,
        )

    warnings.append("This file type needs an OCR provider before it can be searched reliably.")
    return ExtractionResult(
        pages=[ExtractedPage(pageNumber=1, text="No searchable text was extracted from this file. Add OCR to index it.")],
        provider="local-unsupported",
        status="needs_ocr",
        warnings=warnings,
    )


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

