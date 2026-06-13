"""Quick smoke-test for SQL RAG — runs 4 questions against the local mediassist.db.

Run from backend/ with the venv active:
    python scripts/test_sql_rag.py

Requires:
  - .env pointing at mediassist.db (SQLITE_DB_PATH)
  - BEDROCK_MODEL_ID / AWS_REGION valid and model access granted
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.rag.sql_rag import sql_rag_chain

QUESTIONS = [
    "How many billing claims were escalated last month?",
    "What is the total claim amount per department?",
    "Which equipment category has the most open maintenance tickets?",
    "What is the average claim amount for rejected claims?",
]

if __name__ == "__main__":
    for q in QUESTIONS:
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        print(f"A: {sql_rag_chain(q)}")
