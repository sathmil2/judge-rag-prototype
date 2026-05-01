from __future__ import annotations

import re
from dataclasses import dataclass


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were", "with",
}


@dataclass
class SearchResult:
    score: int
    matchedTerms: list[str]
    source: dict


def retrieve_sources(
    index: dict,
    question: str,
    case_number: str = "",
    source_filter: str = "all",
    limit: int = 5,
) -> list[SearchResult]:
    terms = tokenize(question)
    phrases = extract_phrases(question)
    dates = extract_dates(question)
    records = build_search_records(index, case_number, source_filter)

    ranked = []
    for record in records:
        score, matched_terms = score_record(record, terms, phrases, dates)
        if score > 0:
            ranked.append(SearchResult(score=score, matchedTerms=matched_terms, source=record))

    return sorted(
        ranked,
        key=lambda result: (result.score, len(result.matchedTerms)),
        reverse=True,
    )[:limit]


def build_search_records(index: dict, case_number: str, source_filter: str) -> list[dict]:
    normalized_case = case_number.lower()
    records: list[dict] = []

    if source_filter in {"all", "documents"}:
        for chunk in index["chunks"]:
            if normalized_case and chunk["caseNumber"].lower() != normalized_case:
                continue
            records.append({
                **chunk,
                "searchText": chunk["chunkText"],
                "sourceType": "case document",
                "sourceLabel": f"{chunk['documentTitle']}, page {chunk['pageNumber']}",
                "documentId": chunk["documentId"],
                "documentTitle": chunk["documentTitle"],
                "filingDate": chunk["filingDate"],
                "pageNumber": chunk["pageNumber"],
                "viewerUrl": chunk["viewerUrl"],
                "sourceFile": chunk["sourceFile"],
            })

    if source_filter in {"all", "events"}:
        for event in index["events"]:
            if normalized_case and event["caseNumber"].lower() != normalized_case:
                continue
            records.append({
                **event,
                "searchText": event["eventText"],
                "chunkText": event["eventText"],
                "sourceType": "docket event",
                "sourceLabel": event["eventType"],
                "documentId": event["eventId"],
                "documentTitle": event["eventType"],
                "filingDate": event["eventDate"],
                "pageNumber": None,
                "viewerUrl": "",
                "sourceFile": "",
            })

    if source_filter in {"all", "law"}:
        for reference in index["legalReferences"]:
            records.append({
                **reference,
                "caseNumber": "",
                "searchText": reference["referenceText"],
                "chunkText": reference["referenceText"],
                "sourceType": "legal reference",
                "sourceLabel": reference["citation"],
                "documentId": reference["referenceId"],
                "documentTitle": reference["title"],
                "filingDate": reference["effectiveDate"],
                "pageNumber": None,
                "viewerUrl": reference["sourceUrl"],
                "sourceFile": "",
            })

    return records


def tokenize(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOP_WORDS]


def extract_phrases(text: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"', text.lower())
    unquoted = re.findall(r"\b[a-z0-9]+(?:\s+[a-z0-9]+){1,3}\b", text.lower())
    return list(dict.fromkeys([phrase.strip() for phrase in quoted + unquoted if phrase.strip()]))


def extract_dates(text: str) -> list[str]:
    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
    ]
    matches: list[str] = []
    lowered = text.lower()
    for pattern in patterns:
        matches.extend(re.findall(pattern, lowered))
    return list(dict.fromkeys(matches))


def score_record(record: dict, terms: list[str], phrases: list[str], dates: list[str]) -> tuple[int, list[str]]:
    text = record["searchText"].lower()
    title = record["documentTitle"].lower()
    source_type = record["sourceType"].lower()
    source_label = record.get("sourceLabel", "").lower()
    matched_terms: list[str] = []
    score = 0

    for phrase in phrases:
        if phrase in text:
            score += 8
            matched_terms.append(phrase)

    for date in dates:
        if date in text or date in record.get("filingDate", "").lower():
            score += 12
            matched_terms.append(date)

    for term in terms:
        occurrences = text.count(term)
        if occurrences:
            score += occurrences
            matched_terms.append(term)
        if term in title:
            score += 3
            matched_terms.append(f"title:{term}")
        if term in source_label:
            score += 4
            matched_terms.append(f"citation:{term}")
        if term in source_type:
            score += 2
            matched_terms.append(f"source:{term}")

    return score, list(dict.fromkeys(matched_terms))


def summarize_answer(results: list[SearchResult]) -> str:
    if not results:
        return "I could not find a cited source for that in the uploaded case documents or docket events."

    snippets = []
    for result in results[:3]:
        text = " ".join(result.source["chunkText"].split())
        snippets.append(text[:280] + ("..." if len(text) > 280 else ""))

    return (
        "Based on the retrieved case records, the most relevant source text says: "
        + " ".join(snippets)
    )


def build_citations(results: list[SearchResult]) -> list[dict]:
    citations = []
    for result in results:
        source = result.source
        snippet = " ".join(source["chunkText"].split())[:420]
        citations.append({
            "caseNumber": source["caseNumber"],
            "documentId": source["documentId"],
            "documentTitle": source["documentTitle"],
            "filingDate": source["filingDate"],
            "pageNumber": source["pageNumber"],
            "snippet": snippet,
            "viewerUrl": source["viewerUrl"],
            "fileUrl": f"/uploads/{source['sourceFile']}#page={source['pageNumber']}" if source["sourceFile"] else "",
            "sourceType": source["sourceType"],
            "sourceLabel": source["sourceLabel"],
            "sourceText": source["chunkText"],
            "score": result.score,
            "matchedTerms": result.matchedTerms,
            "verified": snippet[:80].lower() in " ".join(source["chunkText"].split()).lower(),
        })
    return citations
