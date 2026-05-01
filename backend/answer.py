from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AnswerResult:
    answer: str
    provider: str
    status: str
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "status": self.status,
            "warnings": self.warnings,
        }


def generate_answer(question: str, citations: list[dict], source_filter: str) -> AnswerResult:
    provider = os.getenv("ANSWER_PROVIDER", "extractive").strip().lower()
    if provider in {"openai", "azure-openai"}:
        return generate_with_llm_placeholder(provider, question, citations)
    return generate_extractive_answer(question, citations, source_filter)


def generate_extractive_answer(question: str, citations: list[dict], source_filter: str) -> AnswerResult:
    if not citations:
        return AnswerResult(
            answer="I could not produce a validated answer with cited source support.",
            provider="extractive",
            status="no_sources",
            warnings=[],
        )

    lead = answer_lead(source_filter)
    snippets = []
    for citation in citations[:3]:
        source_name = citation.get("sourceLabel") or citation.get("documentTitle", "source")
        snippet = " ".join(citation.get("snippet", "").split())
        if snippet:
            snippets.append(f"{source_name}: {snippet}")

    return AnswerResult(
        answer=f"{lead} " + " ".join(snippets),
        provider="extractive",
        status="complete",
        warnings=[
            "This prototype uses extractive answer generation. It does not call an LLM unless ANSWER_PROVIDER is configured."
        ],
    )


def generate_with_llm_placeholder(provider: str, question: str, citations: list[dict]) -> AnswerResult:
    api_key_name = "OPENAI_API_KEY" if provider == "openai" else "AZURE_OPENAI_API_KEY"
    if not os.getenv(api_key_name):
        fallback = generate_extractive_answer(question, citations, "all")
        fallback.provider = f"{provider}-not-configured"
        fallback.warnings.append(f"{api_key_name} is not set; used extractive answer generation instead.")
        return fallback

    fallback = generate_extractive_answer(question, citations, "all")
    fallback.provider = f"{provider}-placeholder"
    fallback.status = "needs_implementation"
    fallback.warnings.append(
        "LLM provider configuration was detected, but the network call is intentionally not implemented in this dependency-free prototype."
    )
    return fallback


def answer_lead(source_filter: str) -> str:
    if source_filter == "documents":
        return "The retrieved case document pages indicate:"
    if source_filter == "events":
        return "The retrieved docket events indicate:"
    if source_filter == "law":
        return "The retrieved legal references indicate:"
    return "The retrieved sources indicate:"
