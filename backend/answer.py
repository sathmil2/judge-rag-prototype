from __future__ import annotations

import os
import json
import urllib.error
import urllib.request
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
    if provider == "openai":
        return generate_with_openai(question, citations)
    if provider == "azure-openai":
        return generate_with_azure_openai(question, citations)
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


def generate_with_openai(question: str, citations: list[dict]) -> AnswerResult:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    if not api_key:
        return llm_fallback("openai-not-configured", question, citations, "OPENAI_API_KEY is not set.")

    payload = build_responses_payload(model, question, citations)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return call_responses_api(
        url="https://api.openai.com/v1/responses",
        payload=payload,
        headers=headers,
        provider=f"openai:{model}",
        fallback_question=question,
        fallback_citations=citations,
    )


def generate_with_azure_openai(question: str, citations: list[dict]) -> AnswerResult:
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    responses_url = os.getenv("AZURE_OPENAI_RESPONSES_URL", "").strip()
    model = os.getenv("AZURE_OPENAI_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini")).strip()

    if not api_key:
        return llm_fallback("azure-openai-not-configured", question, citations, "AZURE_OPENAI_API_KEY is not set.")
    if not responses_url:
        return llm_fallback(
            "azure-openai-not-configured",
            question,
            citations,
            "AZURE_OPENAI_RESPONSES_URL is not set. Provide the full Azure OpenAI Responses API endpoint for your deployment.",
        )

    payload = build_responses_payload(model, question, citations)
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
    }
    return call_responses_api(
        url=responses_url,
        payload=payload,
        headers=headers,
        provider=f"azure-openai:{model}",
        fallback_question=question,
        fallback_citations=citations,
    )


def build_responses_payload(model: str, question: str, citations: list[dict]) -> dict:
    return {
        "model": model,
        "instructions": (
            "You are a court-document assistant. Answer only from the provided cited sources. "
            "Do not use outside knowledge. If the sources do not support an answer, say that the provided sources do not answer the question. "
            "Keep the answer concise. Include bracketed source labels like [C1] after factual claims."
        ),
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": build_llm_context(question, citations),
                    }
                ],
            }
        ],
        "max_output_tokens": int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "700")),
    }


def build_llm_context(question: str, citations: list[dict]) -> str:
    source_blocks = []
    for index, citation in enumerate(citations, start=1):
        label = f"C{index}"
        source_title = citation.get("sourceLabel") or citation.get("documentTitle", "source")
        source_type = citation.get("sourceType", "source")
        page = citation.get("pageNumber")
        page_text = f", page {page}" if page else ""
        snippet = citation.get("snippet", "")
        source_blocks.append(
            f"[{label}] {source_type}: {source_title}{page_text}\n{snippet}"
        )
    return (
        f"Question:\n{question}\n\n"
        "Cited sources:\n"
        + "\n\n".join(source_blocks)
        + "\n\nWrite the answer using only these cited sources."
    )


def call_responses_api(
    url: str,
    payload: dict,
    headers: dict,
    provider: str,
    fallback_question: str,
    fallback_citations: list[dict],
) -> AnswerResult:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45"))) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        text = extract_response_text(response_payload)
        if not text:
            return llm_fallback(provider, fallback_question, fallback_citations, "LLM response did not include output text.")
        return AnswerResult(answer=text, provider=provider, status="complete", warnings=[])
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        return llm_fallback(provider, fallback_question, fallback_citations, f"LLM HTTP {error.code}: {details}")
    except urllib.error.URLError as error:
        return llm_fallback(provider, fallback_question, fallback_citations, f"LLM network error: {error.reason}")
    except (OSError, json.JSONDecodeError, TimeoutError) as error:
        return llm_fallback(provider, fallback_question, fallback_citations, f"LLM request failed: {error}")


def extract_response_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()

    pieces: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                pieces.append(content["text"])
    return "\n".join(piece.strip() for piece in pieces if piece.strip())


def llm_fallback(provider: str, question: str, citations: list[dict], warning: str) -> AnswerResult:
    fallback = generate_extractive_answer(question, citations, "all")
    fallback.provider = provider
    fallback.status = "fallback"
    fallback.warnings.append(f"{warning} Used extractive answer generation instead.")
    return fallback


def answer_lead(source_filter: str) -> str:
    if source_filter == "documents":
        return "The retrieved case document pages indicate:"
    if source_filter == "events":
        return "The retrieved docket events indicate:"
    if source_filter == "law":
        return "The retrieved legal references indicate:"
    return "The retrieved sources indicate:"
