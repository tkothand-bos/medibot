"""SQL RAG over mediassist.db — a plain Python function with three explicit
steps, exactly as required by the assignment:

    1. Translate the natural-language question into SQL with an LLM
    2. Clean the raw LLM output to extract ONLY the SQL statement
    3. Execute the SQL, then pass the result back to the LLM for a
       natural-language answer

Available only to `billing_executive` and `admin` (enforced in the API layer
via app.rbac.can_use_sql_rag).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from app.config import get_settings
from app.rag.llm import get_llm


def _get_schema(db_path: str) -> str:
    """Inspect the live database schema so the LLM sees real columns/types."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
        schema = "\n\n".join(r[0] for r in rows)
        # Add a small sample of each table so the LLM sees value formats
        samples = []
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        for (table,) in tables:
            cur = conn.execute(f"SELECT * FROM {table} LIMIT 3")  # noqa: S608 — table name from sqlite_master
            cols = [d[0] for d in cur.description]
            sample_rows = cur.fetchall()
            samples.append(f"-- {table} sample rows ({', '.join(cols)}):\n" +
                           "\n".join(f"--   {row}" for row in sample_rows))
        return schema + "\n\n" + "\n\n".join(samples)
    finally:
        conn.close()


def _clean_sql(raw: str) -> str:
    """Step 2: extract only the SQL statement from raw LLM output.

    LLMs often wrap SQL in markdown fences or prefix it with prose. Strip all
    of that and return just the statement.
    """
    text = raw.strip()
    fence = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    # Drop any leading prose before the first SQL keyword.
    match = re.search(r"\b(SELECT|WITH)\b", text, flags=re.IGNORECASE)
    if match:
        text = text[match.start():]
    # Keep only the first statement.
    text = text.split(";")[0].strip()
    return text


def _is_safe_select(sql: str) -> bool:
    """Read-only guard: only SELECT/WITH queries may run."""
    lowered = sql.strip().lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return False
    forbidden = ("insert", "update", "delete", "drop", "alter", "create",
                 "attach", "pragma", "vacuum", "replace")
    return not any(re.search(rf"\b{kw}\b", lowered) for kw in forbidden)


def sql_rag_chain(question: str) -> str:
    """Answer an analytical question against mediassist.db. Plain function."""
    settings = get_settings()
    db_path = settings.sqlite_db_path
    if not Path(db_path).exists():
        return f"Database not found at {db_path}. Run the data setup first."

    llm = get_llm()
    schema = _get_schema(db_path)

    # ---- Step 1: NL -> SQL ----
    nl2sql_prompt = (
        "You are an expert SQLite analyst. Given the database schema below, "
        "write ONE SQLite SELECT query that answers the user's question.\n"
        "Return ONLY the SQL query — no explanation, no markdown.\n\n"
        f"Schema:\n{schema}\n\n"
        f"Question: {question}\n\nSQL:"
    )
    raw_sql = llm.invoke(nl2sql_prompt).content
    if not isinstance(raw_sql, str):
        raw_sql = str(raw_sql)

    # ---- Step 2: clean the raw output to pure SQL ----
    sql = _clean_sql(raw_sql)
    if not _is_safe_select(sql):
        return ("I could not produce a safe read-only SQL query for that question. "
                "Please rephrase it as a data question about claims or maintenance tickets.")

    # ---- Step 3: execute, then LLM turns the result into natural language ----
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(50)
    except sqlite3.Error as exc:
        return f"The generated SQL failed to execute ({exc}). Please rephrase your question."
    finally:
        conn.close()

    result_text = f"Columns: {columns}\nRows: {rows}"
    answer_prompt = (
        "You are MediBot answering an analytical question for MediAssist staff.\n"
        f"Question: {question}\n"
        f"SQL executed: {sql}\n"
        f"Query result:\n{result_text}\n\n"
        "Give a concise natural-language answer based strictly on the query result. "
        "Include the key numbers."
    )
    answer = llm.invoke(answer_prompt).content
    return answer if isinstance(answer, str) else str(answer)
