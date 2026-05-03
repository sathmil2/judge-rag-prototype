from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from server import audit_citation_summary, audit_event, current_user
from backend.validation import strip_internal_source_text, validate_citations


class HeaderStub:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, key: str, fallback: str = "") -> str:
        return self.values.get(key, fallback)


class ValidationAndAuditTests(unittest.TestCase):
    def test_validate_citation_passes_with_source_support_and_page_number(self) -> None:
        validation = validate_citations([{
            "caseNumber": "2026-TEST",
            "documentId": "DOC-1",
            "documentTitle": "Petition",
            "sourceType": "case document",
            "sourceLabel": "Petition, page 1",
            "pageNumber": 1,
            "snippet": "Temporary relief was granted.",
            "sourceText": "Temporary relief was granted. The hearing was continued.",
        }])

        self.assertEqual(validation["status"], "passed")
        self.assertEqual(validation["validCitationCount"], 1)

    def test_strip_internal_source_text_removes_private_source_text(self) -> None:
        public = strip_internal_source_text([{
            "documentId": "DOC-1",
            "snippet": "safe",
            "sourceText": "internal full text",
        }])

        self.assertNotIn("sourceText", public[0])
        self.assertEqual(public[0]["snippet"], "safe")

    def test_current_user_sanitizes_headers(self) -> None:
        user = current_user(HeaderStub({
            "X-User-Id": "judge.chen\nignored",
            "X-User-Name": "Judge Chen",
            "X-User-Role": "judge",
            "X-Auth-Source": "test",
        }))

        self.assertEqual(user.userId, "judge.chen ignored")
        self.assertEqual(user.displayName, "Judge Chen")
        self.assertEqual(user.role, "judge")
        self.assertEqual(user.authSource, "test")

    def test_audit_event_appends_structured_identity_entry(self) -> None:
        index = {"auditLog": []}
        user = current_user(HeaderStub({"X-User-Id": "judge.chen"}))

        event = audit_event(
            index,
            action="assistant.ask",
            user=user,
            case_number="2026-TEST",
            resource_type="assistant-answer",
            resource_id="ANS-1",
            resource_title="Question?",
            outcome="passed",
            details={"citationCount": 1},
        )

        self.assertEqual(index["auditLog"][0], event)
        self.assertEqual(event["user"]["userId"], "judge.chen")
        self.assertEqual(event["action"], "assistant.ask")
        self.assertEqual(event["resource"]["id"], "ANS-1")

    def test_audit_citation_summary_removes_snippet_text(self) -> None:
        summary = audit_citation_summary([{
            "sourceType": "case document",
            "sourceLabel": "Petition, page 1",
            "documentId": "DOC-1",
            "pageNumber": 1,
            "score": 0.9,
            "verified": True,
            "snippet": "Do not include this in summary",
        }])

        self.assertEqual(summary[0]["documentId"], "DOC-1")
        self.assertNotIn("snippet", summary[0])


if __name__ == "__main__":
    unittest.main()
