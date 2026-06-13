"""Cross-encoder reranking.

A cross-encoder reads (query, chunk) PAIRS jointly — unlike the bi-encoder
used for retrieval, which embeds them independently — and assigns a relevance
score. We retrieve a broad candidate set (top-10 hybrid) and let the reranker
narrow it to the top-3 chunks that actually reach the LLM.

Reranker scores are logged so you can observe candidates being re-ordered
(the 4th or 5th retrieved chunk frequently outranks the 1st).
"""
from __future__ import annotations

import logging
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.config import get_settings
from app.retrieval.hybrid import RetrievedChunk

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    return CrossEncoder(get_settings().rerank_model)


def rerank(query: str, candidates: list[RetrievedChunk], top_k: int | None = None) -> list[RetrievedChunk]:
    """Score (query, chunk) pairs jointly; return the top_k highest scorers."""
    if not candidates:
        return []
    settings = get_settings()
    top_k = top_k or settings.final_k

    model = get_reranker()
    scores = model.predict([(query, c.text) for c in candidates])
    for chunk, score in zip(candidates, scores):
        chunk.rerank_score = float(score)

    ranked = sorted(candidates, key=lambda c: c.rerank_score, reverse=True)

    logger.info("Reranker scores for query %r:", query[:80])
    for i, c in enumerate(ranked):
        marker = "KEEP" if i < top_k else "drop"
        logger.info(
            "  [%s] rerank=%.4f hybrid=%.4f  %s :: %s",
            marker, c.rerank_score, c.score, c.source_document, c.section_title[:60],
        )

    return ranked[:top_k]
