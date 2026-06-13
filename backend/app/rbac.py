"""Role-Based Access Control matrix for MediAssist Health Network.

The single source of truth for which document collections each role may
retrieve from. Enforcement happens at the Qdrant query level (see
app/retrieval/hybrid.py) — never only in the UI.
                    User Logs In
                           │
                           ▼
                    User Role
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
      Doctor            Nurse         Billing Executive
        │                  │                  │
        ▼                  ▼                  ▼
  Allowed Collections Allowed Collections Allowed Collections
        │                  │                  │
        ▼                  ▼                  ▼
                Qdrant Retrieval Filter
                           │
                           ▼
                  Retrieve Documents
"""

from __future__ import annotations

ALL_COLLECTIONS = ["general", "clinical", "nursing", "billing", "equipment"]

# Role -> document collections that role may access.
ROLE_COLLECTIONS: dict[str, list[str]] = {
    "doctor": ["general", "clinical", "nursing"],
    "nurse": ["general", "nursing"],
    "billing_executive": ["general", "billing"],
    "technician": ["general", "equipment"],
    "admin": list(ALL_COLLECTIONS),
}

# Collection -> roles allowed (inverse view, used at ingestion time to stamp
# the `access_roles` metadata onto every chunk).
COLLECTION_ROLES: dict[str, list[str]] = {
    collection: [role for role, cols in ROLE_COLLECTIONS.items() if collection in cols]
    for collection in ALL_COLLECTIONS
}

# Roles permitted to use SQL RAG (analytical questions over mediassist.db).
SQL_RAG_ROLES = {"billing_executive", "admin"}


def collections_for_role(role: str) -> list[str]:
    """Return the collections a role can access; empty list if role unknown."""
    return ROLE_COLLECTIONS.get(role, [])


def roles_for_collection(collection: str) -> list[str]:
    """Return the roles allowed to access a collection."""
    return COLLECTION_ROLES.get(collection, [])


def can_use_sql_rag(role: str) -> bool:
    return role in SQL_RAG_ROLES
