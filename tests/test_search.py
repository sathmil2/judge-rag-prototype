from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.search import (
    SearchResult,
    build_citations,
    index_chunks_if_configured,
    retrieve_sources,
)


class SearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_snapshot = snapshot_env(
            "SEARCH_PROVIDER",
            "EMBEDDING_PROVIDER",
            "OPENAI_EMBEDDING_DIMENSIONS",
            "AZURE_SEARCH_ENDPOINT",
            "AZURE_SEARCH_KEY",
            "AZURE_SEARCH_INDEX",
        )

    def tearDown(self) -> None:
        restore_env_snapshot(self.env_snapshot)

    def test_local_hybrid_search_returns_cited_page(self) -> None:
        os.environ["SEARCH_PROVIDER"] = "local"
        index = {
            "chunks": [{
                "caseNumber": "2026-TEST",
                "documentId": "DOC-1",
                "documentTitle": "Petition",
                "filingDate": "2026-05-03",
                "pageNumber": 3,
                "chunkText": "Temporary relief was granted pending a full hearing.",
                "sourceFile": "petition.pdf",
                "viewerUrl": "/viewer?page=3",
            }],
            "events": [],
            "legalReferences": [],
        }

        results = retrieve_sources(index, "Was temporary relief granted?", "2026-TEST", "documents")
        citations = build_citations(results)

        self.assertEqual(citations[0]["documentId"], "DOC-1")
        self.assertEqual(citations[0]["pageNumber"], 3)
        self.assertEqual(citations[0]["searchMode"], "hybrid-local")

    def test_azure_indexing_skips_when_not_configured(self) -> None:
        os.environ["SEARCH_PROVIDER"] = "azure"
        os.environ.pop("AZURE_SEARCH_ENDPOINT", None)
        os.environ.pop("AZURE_SEARCH_KEY", None)
        os.environ.pop("AZURE_SEARCH_INDEX", None)

        result = index_chunks_if_configured([{"chunkText": "hello"}])

        self.assertEqual(result["provider"], "azure-ai-search")
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["indexedCount"], 0)

    def test_azure_retrieval_falls_back_to_local_when_azure_query_fails(self) -> None:
        os.environ["SEARCH_PROVIDER"] = "azure"
        index = {
            "chunks": [{
                "caseNumber": "2026-TEST",
                "documentId": "DOC-LOCAL",
                "documentTitle": "Local fallback",
                "filingDate": "2026-05-03",
                "pageNumber": 1,
                "chunkText": "Temporary relief was granted.",
                "sourceFile": "fallback.pdf",
                "viewerUrl": "/viewer?page=1",
            }],
            "events": [],
            "legalReferences": [],
        }

        with patch("backend.search.retrieve_sources_from_azure", side_effect=RuntimeError("search down")):
            results = retrieve_sources(index, "temporary relief", "2026-TEST", "documents")

        self.assertEqual(results[0].source["documentId"], "DOC-LOCAL")
        self.assertEqual(results[0].searchMode, "hybrid-local")

    def test_build_citations_keeps_azure_search_mode(self) -> None:
        result = SearchResult(
            score=1.0,
            keywordScore=0.5,
            vectorScore=0.5,
            matchedTerms=["temporary"],
            searchMode="azure-ai-search-hybrid",
            source={
                "caseNumber": "2026-TEST",
                "documentId": "DOC-AZURE",
                "documentTitle": "Azure result",
                "filingDate": "2026-05-03",
                "pageNumber": 2,
                "chunkText": "Temporary relief was granted.",
                "sourceFile": "azure.pdf",
                "viewerUrl": "/viewer?page=2",
                "sourceType": "case document",
                "sourceLabel": "Azure result, page 2",
            },
        )

        citation = build_citations([result])[0]

        self.assertEqual(citation["searchMode"], "azure-ai-search-hybrid")


def snapshot_env(*keys: str) -> dict[str, str | None]:
    return {key: os.environ.get(key) for key in keys}


def restore_env_snapshot(snapshot: dict[str, str | None]) -> None:
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
