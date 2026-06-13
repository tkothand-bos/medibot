"""MediBot FastAPI backend.

Endpoints:
    POST /login                Cognito auth -> role-tagged tokens
    POST /chat                 RBAC-scoped RAG (hybrid+rerank or SQL)
    GET  /collections/{role}   Collections accessible to a role
    GET  /health               Health check

Security model: the role used for retrieval comes from the VERIFIED Cognito
access token (cognito:groups), never from the request body. The RBAC filter
is applied inside the Qdrant query, so restricted chunks never reach the
application layer or the LLM.
"""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth.cognito import get_current_user, login as cognito_login
from app.rag.chain import hybrid_rag_chain, rbac_refusal_message
from app.rag.router import choose_route
from app.rag.sql_rag import sql_rag_chain
from app.rbac import ROLE_COLLECTIONS, collections_for_role
from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medibot")

app = FastAPI(title="MediBot API", version="1.0.0",
              description="Advanced RAG with RBAC for MediAssist Health Network")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().frontend_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Schemas ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int | None = None
    username: str
    role: str
    collections: list[str]


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Source(BaseModel):
    source_document: str
    section_title: str
    collection: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    retrieval_type: str  # "hybrid_rag" | "sql_rag"
    role: str
    blocked: bool = False


# ---------- Endpoints ----------

@app.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    """Authenticate with Cognito; returns a role-tagged session token."""
    result = cognito_login(body.username, body.password)
    return LoginResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
        expires_in=result.get("expires_in"),
        username=result["username"],
        role=result["role"],
        collections=collections_for_role(result["role"]),
    )


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    """Main RAG endpoint. Role comes from the verified token, not the client."""
    role = user["role"]
    question = body.question.strip()
    route = choose_route(question, role)
    logger.info("chat user=%s role=%s route=%s q=%r", user["username"], role, route, question[:100])

    if route == "sql_rag":
        answer = sql_rag_chain(question)
        return ChatResponse(answer=answer, sources=[], retrieval_type="sql_rag", role=role)

    result = hybrid_rag_chain(question, role)
    return ChatResponse(
        answer=result.answer,
        sources=[Source(**s) for s in result.sources],
        retrieval_type="hybrid_rag",
        role=role,
        blocked=result.blocked,
    )


@app.get("/collections/{role}")
def collections(role: str):
    """List the document collections accessible to a role."""
    if role not in ROLE_COLLECTIONS:
        raise HTTPException(404, f"Unknown role '{role}'. Valid roles: {sorted(ROLE_COLLECTIONS)}")
    return {"role": role, "collections": collections_for_role(role)}


@app.get("/health")
def health():
    return {"status": "ok", "service": "medibot-api"}


@app.get("/rbac-message/{role}")
def rbac_message(role: str):
    """Helper for the frontend: the informative refusal message for a role."""
    if role not in ROLE_COLLECTIONS:
        raise HTTPException(404, "Unknown role")
    return {"message": rbac_refusal_message(role)}
