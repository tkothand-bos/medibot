"""Hybrid RAG chain: RBAC-filtered hybrid retrieval -> cross-encoder rerank ->
Bedrock LLM answer with source citations.
"""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings
from app.ingestion.ingest import get_qdrant_client
from app.rbac import collections_for_role
from app.retrieval.hybrid import RetrievedChunk, hybrid_search
from app.retrieval.rerank import rerank
from app.rag.llm import get_llm

ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are MediBot, the internal assistant for MediAssist Health Network. "
            "Answer the staff member's question using ONLY the context passages below. "
            "Each passage is labelled [n] with its source document and section. "
            "Cite the passages you used inline, e.g. [1]. "
            "If the context does not contain the answer, say so clearly — do not guess. "
            "This is a healthcare setting: never invent dosages, codes, or procedures.\n\n"
            "Context passages:\n{context}",
        ),
        ("human", "{question}"),
    ]
)


@dataclass
class HybridRagResult:
    answer: str
    sources: list[dict]
    chunks: list[RetrievedChunk]
    blocked: bool = False


def _format_context(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{i + 1}] (source: {c.source_document} — {c.section_title} — collection: {c.collection})\n{c.text}"
        for i, c in enumerate(chunks)
    )


def rbac_refusal_message(role: str) -> str:
    allowed = collections_for_role(role)
    pretty = ", ".join(allowed[:-1]) + f" and {allowed[-1]}" if len(allowed) > 1 else allowed[0]
    return (
        f"As a {role.replace('_', ' ')}, you don't have access to documents outside your "
        f"permitted collections. I can only answer questions from the {pretty} collections."
    )


def hybrid_rag_chain(question: str, role: str) -> HybridRagResult:
    """Full document-RAG pipeline for one question, scoped to `role`.

    1. Hybrid (dense + BM25) retrieval with the RBAC filter applied inside the
       Qdrant query — broad candidate set (top-10).
    2. Cross-encoder reranking narrows candidates to the final top-3. Only the
       reranked top chunks reach the LLM; the full candidate set never does.
    3. Bedrock LLM produces a cited answer.
    """
    settings = get_settings()
    client = get_qdrant_client()

    candidates = hybrid_search(client, question, role, limit=settings.candidate_k)
    if not candidates:
        # Nothing retrievable within this role's collections — likely an
        # out-of-scope / restricted-topic question.
        return HybridRagResult(answer=rbac_refusal_message(role), sources=[], chunks=[], blocked=True)

    top_chunks = rerank(question, candidates, top_k=settings.final_k)

    llm = get_llm()
    messages = ANSWER_PROMPT.format_messages(
        context=_format_context(top_chunks), question=question
    )
    response = llm.invoke(messages)
    answer = response.content if isinstance(response.content, str) else str(response.content)

    return HybridRagResult(
        answer=answer,
        sources=[c.citation() for c in top_chunks],
        chunks=top_chunks,
    )
