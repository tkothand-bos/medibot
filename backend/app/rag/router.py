"""Route an incoming question to SQL RAG (analytical) or Hybrid RAG (documents).

Uses a fast keyword heuristic first, then falls back to an LLM classification
for ambiguous cases. SQL RAG is only ever chosen if the role is permitted
(billing_executive, admin) — everyone else always goes to document RAG.
"""
from __future__ import annotations

import logging
import re

from app.rag.llm import get_llm
from app.rbac import can_use_sql_rag

logger = logging.getLogger(__name__)

# Strong signals that the answer lives in the relational DB, not documents.
_ANALYTICAL_PATTERNS = [
    r"\bhow many\b", r"\bcount\b", r"\baverage\b", r"\btotal\b", r"\bsum\b",
    r"\bclaims?\b", r"\bmaintenance tickets?\b", r"\bescalated\b",
    r"\bper (month|department|category)\b", r"\bmost (open|recent|common)\b",
    r"\blast (week|month|quarter|year)\b", r"\bstatistics?\b", r"\btrend\b",
]


def _looks_analytical(question: str) -> bool:
    q = question.lower()
    return any(re.search(p, q) for p in _ANALYTICAL_PATTERNS)


def _llm_classify(question: str) -> bool:
    """Return True if the LLM classifies the question as analytical/SQL."""
    prompt = (
        "Classify the staff question as either DOCUMENT (answered from policy/"
        "clinical/billing/equipment documents) or ANALYTICAL (answered by "
        "querying a database of billing claims and equipment maintenance "
        "tickets — counts, sums, trends, statistics).\n"
        f"Question: {question}\n"
        "Reply with exactly one word: DOCUMENT or ANALYTICAL."
    )
    try:
        reply = get_llm().invoke(prompt).content
        text = reply if isinstance(reply, str) else str(reply)
        return "ANALYTICAL" in text.upper()
    except Exception:  # classification failure -> safe default
        logger.exception("LLM routing failed; defaulting to document RAG")
        return False


def choose_route(question: str, role: str) -> str:
    """Return 'sql_rag' or 'hybrid_rag' for this question + role."""
    if not can_use_sql_rag(role):
        return "hybrid_rag"
    if _looks_analytical(question):
        return "sql_rag"
    return "sql_rag" if _llm_classify(question) else "hybrid_rag"
