from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass


VECTOR_DIMENSIONS = 256

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were", "with",
    "about", "after", "before", "can", "could", "did", "does", "do", "had", "have",
    "how", "into", "may", "should", "what", "when", "where", "which", "who", "why",
}


@dataclass
class SearchResult:
    score: float
    keywordScore: float
    vectorScore: float
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
    query_vector = embed_text(question)

    ranked = []
    for record in records:
        keyword_score, matched_terms = score_record(record, terms, phrases, dates)
        vector_score = cosine_similarity(query_vector, embed_text(record["searchText"]))
        score = hybrid_score(keyword_score, vector_score)
        if score > 0:
            ranked.append(SearchResult(
                score=score,
                keywordScore=keyword_score,
                vectorScore=vector_score,
                matchedTerms=matched_terms,
                source=record,
            ))

    return sorted(
        ranked,
        key=lambda result: (result.score, result.keywordScore, result.vectorScore, len(result.matchedTerms)),
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
                "pageWidth": chunk.get("pageWidth"),
                "pageHeight": chunk.get("pageHeight"),
                "pageUnit": chunk.get("pageUnit", ""),
                "ocrWords": chunk.get("ocrWords") or [],
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


def score_record(record: dict, terms: list[str], phrases: list[str], dates: list[str]) -> tuple[float, list[str]]:
    text = record["searchText"].lower()
    title = record["documentTitle"].lower()
    source_type = record["sourceType"].lower()
    source_label = record.get("sourceLabel", "").lower()
    matched_terms: list[str] = []
    score = 0.0

    for phrase in phrases:
        if phrase in text:
            score += 8.0
            matched_terms.append(phrase)

    for date in dates:
        if date in text or date in record.get("filingDate", "").lower():
            score += 12.0
            matched_terms.append(date)

    for term in terms:
        occurrences = text.count(term)
        if occurrences:
            score += float(occurrences)
            matched_terms.append(term)
        if term in title:
            score += 3.0
            matched_terms.append(f"title:{term}")
        if term in source_label:
            score += 4.0
            matched_terms.append(f"citation:{term}")
        if term in source_type:
            score += 2.0
            matched_terms.append(f"source:{term}")

    return score, list(dict.fromkeys(matched_terms))


def hybrid_score(keyword_score: float, vector_score: float) -> float:
    return round(keyword_score + (vector_score * 20.0), 4)


def embed_text(text: str) -> list[float]:
    features = vector_features(text)
    vector = [0.0] * VECTOR_DIMENSIONS
    for token, count in features.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        bucket = int.from_bytes(digest, "big") % VECTOR_DIMENSIONS
        vector[bucket] += 1.0 + math.log(count)
    return normalize_vector(vector)


def vector_features(text: str) -> Counter[str]:
    tokens = tokenize(text)
    features: Counter[str] = Counter(tokens)
    for index in range(len(tokens) - 1):
        features[f"{tokens[index]} {tokens[index + 1]}"] += 2
    for index in range(len(tokens) - 2):
        features[f"{tokens[index]} {tokens[index + 1]} {tokens[index + 2]}"] += 3
    return features


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return round(sum(a * b for a, b in zip(left, right)), 4)


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
            "pageWidth": source.get("pageWidth"),
            "pageHeight": source.get("pageHeight"),
            "pageUnit": source.get("pageUnit", ""),
            "ocrHighlights": build_ocr_highlights(snippet, source.get("ocrWords") or []),
            "score": result.score,
            "keywordScore": result.keywordScore,
            "vectorScore": result.vectorScore,
            "searchMode": "hybrid",
            "matchedTerms": result.matchedTerms,
            "verified": snippet[:80].lower() in " ".join(source["chunkText"].split()).lower(),
        })
    return citations


def build_ocr_highlights(snippet: str, words: list[dict]) -> list[dict]:
    terms = set(tokenize(snippet))
    highlights = []
    for word in words:
        word_terms = set(tokenize(str(word.get("text", ""))))
        if not word_terms or not terms.intersection(word_terms):
            continue
        polygon = word.get("polygon") or []
        if not polygon:
            continue
        highlights.append({
            "text": word.get("text", ""),
            "polygon": polygon,
            "confidence": word.get("confidence"),
        })
    return highlights[:120]
