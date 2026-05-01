from __future__ import annotations


def validate_citations(citations: list[dict]) -> dict:
    checks = [validate_citation(citation) for citation in citations]
    failed = [check for check in checks if not check["valid"]]
    status = "passed" if citations and not failed else "failed"
    if not citations:
        status = "no_sources"

    return {
        "status": status,
        "validCitationCount": len(checks) - len(failed),
        "totalCitationCount": len(checks),
        "checks": checks,
    }


def validate_citation(citation: dict) -> dict:
    snippet = normalize(citation.get("snippet", ""))
    source_text = normalize(citation.get("sourceText", ""))
    required_fields = ["caseNumber", "documentId", "documentTitle", "sourceType", "sourceLabel"]
    missing_fields = [field for field in required_fields if not citation.get(field)]

    snippet_supported = bool(snippet) and snippet[:80] in source_text
    has_location = citation.get("sourceType") == "docket event" or citation.get("pageNumber") is not None
    valid = not missing_fields and snippet_supported and has_location

    reasons = []
    if missing_fields:
        reasons.append(f"Missing fields: {', '.join(missing_fields)}")
    if not snippet_supported:
        reasons.append("Snippet was not found in the retrieved source text.")
    if not has_location:
        reasons.append("Document citation is missing a page number.")

    return {
        "citationId": citation.get("documentId", ""),
        "sourceLabel": citation.get("sourceLabel", ""),
        "valid": valid,
        "reasons": reasons,
    }


def strip_internal_source_text(citations: list[dict]) -> list[dict]:
    public_citations = []
    for citation in citations:
        public_citation = dict(citation)
        public_citation.pop("sourceText", None)
        public_citations.append(public_citation)
    return public_citations


def normalize(text: str) -> str:
    return " ".join(str(text).split()).lower()

