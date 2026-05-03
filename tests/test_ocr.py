from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from backend.ocr import extract_document


class OcrTests(unittest.TestCase):
    def test_text_file_skips_azure_ocr_when_azure_provider_enabled(self) -> None:
        previous_provider = os.environ.get("OCR_PROVIDER")
        os.environ["OCR_PROVIDER"] = "azure"
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                text_path = Path(tmp_dir) / "sample.txt"
                text_path.write_text("Page one\fPage two", encoding="utf-8")

                result = extract_document(text_path, "text/plain")

            self.assertEqual(result.provider, "local-text")
            self.assertEqual(result.status, "complete")
            self.assertEqual(len(result.pages), 2)
            self.assertEqual(result.pages[0].text, "Page one")
        finally:
            restore_env("OCR_PROVIDER", previous_provider)

    def test_azure_ocr_missing_credentials_does_not_fall_back_to_tesseract(self) -> None:
        previous = snapshot_env(
            "OCR_PROVIDER",
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY",
        )
        os.environ["OCR_PROVIDER"] = "azure"
        os.environ.pop("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", None)
        os.environ.pop("AZURE_DOCUMENT_INTELLIGENCE_KEY", None)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                image_path = Path(tmp_dir) / "scan.tiff"
                image_path.write_bytes(b"not a real image")

                result = extract_document(image_path, "image/tiff")

            self.assertEqual(result.provider, "azure-document-intelligence:prebuilt-read")
            self.assertEqual(result.status, "needs_ocr")
            self.assertIn("local OCR fallback is disabled", result.warnings[0])
        finally:
            restore_env_snapshot(previous)


def snapshot_env(*keys: str) -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in keys}


def restore_env_snapshot(snapshot: dict[str, str | None]) -> None:
    for key, value in snapshot.items():
        restore_env(key, value)


def restore_env(key: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
