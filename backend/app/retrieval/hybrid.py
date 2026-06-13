"""Hybrid retrieval (dense + BM25) with RBAC enforced inside the Qdrant query.

Key properties (assignment requirements):
- Dense and sparse vectors are queried TOGETHER in a single Qdrant Query API
  call using prefetch + Reciprocal Rank Fusion — not two separate queries
  merged in application code.
- The `access_roles` metadata filter is part of the query itself, so chunks a
  role cannot see are never returned to the application layer. An adversarial
  prompt cannot leak them because the LLM never receives them.
"""
from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from app.config import get_settings


@dataclass
class RetrievedChunk:
    text: str
    source_document: str
    section_title: str
    collection: str
    chunk_type: str
    score: float
    rerank_score: float | None = None

    def citation(self) -> dict:
        return {
            "source_document": self.source_document,
            "section_title": self.section_title,
            "collection": self.collection,
        }


def rbac_filter(role: str) -> models.Filter:
    """Build the Qdrant payload filter that scopes retrieval to the role.

    MatchValue against a list payload field matches if the value is one of the
    list elements, so this returns only chunks whose `access_roles` contains
    the requesting role.
    """
    return models.Filter(
        must=[
            models.FieldCondition(
                key="access_roles",
                match=models.MatchValue(value=role),
            )
        ]
    )


def hybrid_search(
    client: QdrantClient,
    query: str,
    role: str,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    """Single hybrid query: dense + BM25 prefetch, RRF fusion, RBAC filter."""
    settings = get_settings()
    limit = limit or settings.candidate_k
    query_filter = rbac_filter(role)

    response = client.query_points(
        collection_name=settings.qdrant_collection,
        prefetch=[
            models.Prefetch(
                query=models.Document(text=query, model=settings.dense_model),
                using="dense",
                filter=query_filter,   # RBAC applied to the dense branch
                limit=limit * 2,
            ),
            models.Prefetch(
                query=models.Document(text=query, model=settings.sparse_model),
                using="bm25",
                filter=query_filter,   # RBAC applied to the sparse branch
                limit=limit * 2,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        query_filter=query_filter,     # and to the fused result, belt-and-braces
        limit=limit,
        with_payload=True,
    )

    return [
        RetrievedChunk(
            text=p.payload.get("text", ""),
            source_document=p.payload.get("source_document", "unknown"),
            section_title=p.payload.get("section_title", ""),
            collection=p.payload.get("collection", ""),
            chunk_type=p.payload.get("chunk_type", "text"),
            score=p.score,
        )
        for p in response.points
    ]
