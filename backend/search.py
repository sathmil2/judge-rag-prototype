from __future__ import annotations

import hashlib
import json
import math
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
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
    searchMode: str = "hybrid-local"


def retrieve_sources(
    index: dict,
    question: str,
    case_number: str = "",
    source_filter: str = "all",
    limit: int = 5,
) -> list[SearchResult]:
    if search_provider() == "azure" and source_filter in {"all", "documents"}:
        try:
            azure_results = retrieve_sources_from_azure(question, case_number, limit)
            enrich_results_from_local_index(index, azure_results)
            if source_filter == "documents":
                return azure_results
            local_supplement = retrieve_sources_local(index, question, case_number, "events", limit=3)
            local_supplement.extend(retrieve_sources_local(index, question, case_number, "law", limit=3))
            return sorted(
                azure_results + local_supplement,
                key=lambda result: result.score,
                reverse=True,
            )[:limit]
        except Exception:
            return retrieve_sources_local(index, question, case_number, source_filter, limit)

    return retrieve_sources_local(index, question, case_number, source_filter, limit)


def retrieve_sources_local(
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
                searchMode="hybrid-local",
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


def search_provider() -> str:
    return os.getenv("SEARCH_PROVIDER", "local").strip().lower()


def azure_search_configured() -> bool:
    return all([
        os.getenv("AZURE_SEARCH_ENDPOINT", "").strip(),
        os.getenv("AZURE_SEARCH_KEY", "").strip(),
        os.getenv("AZURE_SEARCH_INDEX", "").strip(),
    ]) and embedding_configured()


def embedding_configured() -> bool:
    return embedding_provider() == "local" or bool(
        os.getenv("OPENAI_API_KEY", "").strip()
        or (
            os.getenv("AZURE_OPENAI_EMBEDDINGS_URL", "").strip()
            and os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        )
    )


def embedding_provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "auto").strip().lower()


def azure_search_settings() -> dict:
    return {
        "endpoint": os.getenv("AZURE_SEARCH_ENDPOINT", "").strip().rstrip("/"),
        "key": os.getenv("AZURE_SEARCH_KEY", "").strip(),
        "index": os.getenv("AZURE_SEARCH_INDEX", "case-pages").strip(),
        "apiVersion": os.getenv("AZURE_SEARCH_API_VERSION", "2025-09-01").strip(),
        "embeddingDimensions": int(os.getenv("OPENAI_EMBEDDING_DIMENSIONS", "1536")),
    }


def enrich_results_from_local_index(index: dict, results: list[SearchResult]) -> None:
    chunks_by_location = {
        (chunk.get("documentId"), int(chunk.get("pageNumber") or 0)): chunk
        for chunk in index.get("chunks", [])
    }
    for result in results:
        key = (result.source.get("documentId"), int(result.source.get("pageNumber") or 0))
        local_chunk = chunks_by_location.get(key)
        if not local_chunk:
            continue
        result.source["ocrWords"] = local_chunk.get("ocrWords") or []
        result.source["pageWidth"] = local_chunk.get("pageWidth")
        result.source["pageHeight"] = local_chunk.get("pageHeight")
        result.source["pageUnit"] = local_chunk.get("pageUnit", "")


def index_chunks_if_configured(chunks: list[dict]) -> dict:
    if search_provider() != "azure":
        return {"provider": "local", "status": "skipped", "indexedCount": 0, "warnings": []}
    if not azure_search_configured():
        return {
            "provider": "azure-ai-search",
            "status": "skipped",
            "indexedCount": 0,
            "warnings": ["Azure AI Search or embedding settings are incomplete; local search remains available."],
        }

    try:
        ensure_azure_search_index()
        documents = []
        for chunk in chunks:
            text = chunk.get("chunkText", "")
            documents.append({
                "@search.action": "mergeOrUpload",
                "id": azure_document_key(chunk),
                "caseNumber": chunk.get("caseNumber", ""),
                "documentId": chunk.get("documentId", ""),
                "documentTitle": chunk.get("documentTitle", ""),
                "filingDate": chunk.get("filingDate", ""),
                "pageNumber": int(chunk.get("pageNumber") or 0),
                "chunkText": text,
                "sourceFile": chunk.get("sourceFile", ""),
                "viewerUrl": chunk.get("viewerUrl", ""),
                "pageWidth": number_or_zero(chunk.get("pageWidth")),
                "pageHeight": number_or_zero(chunk.get("pageHeight")),
                "pageUnit": chunk.get("pageUnit", ""),
                "embedding": create_embedding(text),
            })
        upload_azure_documents(documents)
        return {"provider": "azure-ai-search", "status": "complete", "indexedCount": len(documents), "warnings": []}
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        return {
            "provider": "azure-ai-search",
            "status": "failed",
            "indexedCount": 0,
            "warnings": [f"Azure AI Search indexing failed: HTTP {error.code}: {details}"],
        }
    except Exception as error:
        return {
            "provider": "azure-ai-search",
            "status": "failed",
            "indexedCount": 0,
            "warnings": [f"Azure AI Search indexing failed: {error}"],
        }


def ensure_azure_search_index() -> None:
    settings = azure_search_settings()
    path = f"/indexes/{urllib.parse.quote(settings['index'])}?api-version={urllib.parse.quote(settings['apiVersion'])}"
    try:
        azure_search_request("GET", path)
        return
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise

    schema = {
        "name": settings["index"],
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "caseNumber", "type": "Edm.String", "filterable": True, "sortable": True},
            {"name": "documentId", "type": "Edm.String", "filterable": True},
            {"name": "documentTitle", "type": "Edm.String", "searchable": True, "filterable": True},
            {"name": "filingDate", "type": "Edm.String", "filterable": True, "sortable": True},
            {"name": "pageNumber", "type": "Edm.Int32", "filterable": True, "sortable": True},
            {"name": "chunkText", "type": "Edm.String", "searchable": True},
            {"name": "sourceFile", "type": "Edm.String", "filterable": True},
            {"name": "viewerUrl", "type": "Edm.String"},
            {"name": "pageWidth", "type": "Edm.Double"},
            {"name": "pageHeight", "type": "Edm.Double"},
            {"name": "pageUnit", "type": "Edm.String"},
            {
                "name": "embedding",
                "type": "Collection(Edm.Single)",
                "searchable": True,
                "dimensions": settings["embeddingDimensions"],
                "vectorSearchProfile": "case-page-vector-profile",
            },
        ],
        "vectorSearch": {
            "algorithms": [{"name": "case-page-hnsw", "kind": "hnsw"}],
            "profiles": [{"name": "case-page-vector-profile", "algorithm": "case-page-hnsw"}],
        },
    }
    azure_search_request("PUT", path, schema)


def upload_azure_documents(documents: list[dict]) -> None:
    if not documents:
        return
    settings = azure_search_settings()
    path = f"/indexes/{urllib.parse.quote(settings['index'])}/docs/index?api-version={urllib.parse.quote(settings['apiVersion'])}"
    azure_search_request("POST", path, {"value": documents})


def retrieve_sources_from_azure(question: str, case_number: str, limit: int) -> list[SearchResult]:
    settings = azure_search_settings()
    query_embedding = create_embedding(question)
    body = {
        "search": question,
        "top": limit,
        "select": "caseNumber,documentId,documentTitle,filingDate,pageNumber,chunkText,sourceFile,viewerUrl,pageWidth,pageHeight,pageUnit",
        "vectorQueries": [{
            "kind": "vector",
            "vector": query_embedding,
            "fields": "embedding",
            "k": limit,
        }],
    }
    if case_number:
        body["filter"] = f"caseNumber eq '{escape_odata_string(case_number)}'"

    path = f"/indexes/{urllib.parse.quote(settings['index'])}/docs/search?api-version={urllib.parse.quote(settings['apiVersion'])}"
    payload = azure_search_request("POST", path, body)
    results = []
    for item in payload.get("value", []):
        source = {
            "caseNumber": item.get("caseNumber", ""),
            "documentId": item.get("documentId", ""),
            "documentTitle": item.get("documentTitle", ""),
            "filingDate": item.get("filingDate", ""),
            "pageNumber": item.get("pageNumber"),
            "chunkText": item.get("chunkText", ""),
            "searchText": item.get("chunkText", ""),
            "sourceFile": item.get("sourceFile", ""),
            "viewerUrl": item.get("viewerUrl", ""),
            "sourceType": "case document",
            "sourceLabel": f"{item.get('documentTitle', '')}, page {item.get('pageNumber')}",
            "pageWidth": item.get("pageWidth") or None,
            "pageHeight": item.get("pageHeight") or None,
            "pageUnit": item.get("pageUnit", ""),
            "ocrWords": [],
        }
        score = float(item.get("@search.score", 0) or 0)
        results.append(SearchResult(
            score=round(score, 4),
            keywordScore=score,
            vectorScore=score,
            matchedTerms=tokenize(question)[:8],
            source=source,
            searchMode="azure-ai-search-hybrid",
        ))
    return results


def azure_search_request(method: str, path: str, payload: dict | None = None) -> dict:
    settings = azure_search_settings()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{settings['endpoint']}{path}",
        data=data,
        headers={
            "api-key": settings["key"],
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def create_embedding(text: str) -> list[float]:
    if embedding_provider() == "local":
        return local_hash_embedding(text)

    azure_url = os.getenv("AZURE_OPENAI_EMBEDDINGS_URL", "").strip()
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    try:
        if azure_url and azure_key:
            return create_azure_openai_embedding(text, azure_url, azure_key)
        return create_openai_embedding(text)
    except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, OSError):
        if os.getenv("EMBEDDING_ALLOW_LOCAL_FALLBACK", "true").strip().lower() in {"1", "true", "yes"}:
            return local_hash_embedding(text)
        raise


def local_hash_embedding(text: str) -> list[float]:
    dimensions = azure_search_settings()["embeddingDimensions"]
    features = vector_features(text)
    vector = [0.0] * dimensions
    for token, count in features.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        bucket = int.from_bytes(digest, "big") % dimensions
        vector[bucket] += 1.0 + math.log(count)
    return normalize_vector(vector)


def create_openai_embedding(text: str) -> list[float]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for Azure AI Search embeddings.")
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
    body = {"model": model, "input": text[:24000]}
    request = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["data"][0]["embedding"]


def create_azure_openai_embedding(text: str, url: str, key: str) -> list[float]:
    model = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "").strip()
    body = {"input": text[:24000]}
    if model:
        body["model"] = model
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "api-key": key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["data"][0]["embedding"]


def ssl_context() -> ssl.SSLContext:
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


def azure_document_key(chunk: dict) -> str:
    raw = f"{chunk.get('caseNumber', '')}-{chunk.get('documentId', '')}-{chunk.get('pageNumber', '')}"
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:180]


def escape_odata_string(value: str) -> str:
    return value.replace("'", "''")


def number_or_zero(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


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
            "searchMode": result.searchMode,
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
