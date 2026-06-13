"""Document ingestion: Docling structural parsing -> hierarchical chunking ->
Qdrant indexing with dense + sparse (BM25) vectors and full RBAC metadata.

Pipeline
--------
1. Docling's DocumentConverter parses PDFs/Markdown with structural awareness:
   headings, tables and code blocks are recognised, not flattened.
2. Docling's HybridChunker performs hierarchical chunking: it splits along the
   document's natural structure (section -> subsection -> paragraph / table)
   first, then applies a token-aware size limit as a second pass.
   `contextualize()` prepends parent section headings to each chunk's text so
   the embedded text carries its section context.
3. Every chunk is stored in Qdrant with BOTH a dense vector (semantic) and a
   sparse BM25 vector (keyword), enabling true hybrid search in one query.
4. Every chunk payload carries the mandated metadata schema:
   source_document, collection, access_roles, section_title, chunk_type.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from docling_core.types.doc.labels import DocItemLabel
from qdrant_client import QdrantClient, models

from app.config import get_settings
from app.ingestion.s3_loader import SourceDocument
from app.rbac import roles_for_collection

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    text: str                 # contextualized text (with parent headings) — what gets embedded
    source_document: str
    collection: str
    access_roles: list[str]
    section_title: str
    chunk_type: str           # text | table | heading | code
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def payload(self) -> dict:
        return {
            "text": self.text,
            "source_document": self.source_document,
            "collection": self.collection,
            "access_roles": self.access_roles,
            "section_title": self.section_title,
            "chunk_type": self.chunk_type,
        }


def _chunk_type_of(chunk) -> str:
    """Map Docling item labels in a chunk to our chunk_type vocabulary."""
    labels = {item.label for item in chunk.meta.doc_items if hasattr(item, "label")}
    if DocItemLabel.TABLE in labels:
        return "table"
    if DocItemLabel.CODE in labels:
        return "code"
    if labels & {DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE}:
        return "heading"
    return "text"


def parse_and_chunk(doc: SourceDocument, max_tokens: int | None = None) -> list[Chunk]:
    """Parse one document with Docling and hierarchically chunk it."""
    settings = get_settings()
    converter = DocumentConverter()
    result = converter.convert(str(doc.local_path))
    dl_doc = result.document

    chunker = HybridChunker(max_tokens=max_tokens or settings.max_tokens_per_chunk)
    access_roles = roles_for_collection(doc.collection)

    chunks: list[Chunk] = []
    for raw in chunker.chunk(dl_doc):
        # contextualize() prepends the heading hierarchy to the chunk body, so
        # the embedded text is e.g. "Paediatric Dosage > IV Fluids\n25mg twice daily"
        contextualized = chunker.contextualize(chunk=raw)
        headings = list(getattr(raw.meta, "headings", None) or [])
        chunks.append(
            Chunk(
                text=contextualized,
                source_document=doc.source_document,
                collection=doc.collection,
                access_roles=access_roles,
                section_title=" > ".join(headings) if headings else doc.source_document,
                chunk_type=_chunk_type_of(raw),
            )
        )
    logger.info("%s: %d chunks", doc.source_document, len(chunks))
    return chunks


def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)


def ensure_collection(client: QdrantClient) -> None:
    """Create the Qdrant collection with named dense + sparse vectors."""
    settings = get_settings()
    if client.collection_exists(settings.qdrant_collection):
        return
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config={
            "dense": models.VectorParams(
                size=client.get_embedding_size(settings.dense_model),
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors_config={
            "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )
    # Index payload fields used for filtering.
    for field_name in ("access_roles", "collection"):
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name=field_name,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )


def index_chunks(client: QdrantClient, chunks: list[Chunk], batch_size: int = 32) -> None:
    """Embed (dense + BM25 sparse) and upsert chunks into Qdrant."""
    settings = get_settings()
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        points = [
            models.PointStruct(
                id=c.chunk_id,
                vector={
                    "dense": models.Document(text=c.text, model=settings.dense_model),
                    "bm25": models.Document(text=c.text, model=settings.sparse_model),
                },
                payload=c.payload(),
            )
            for c in batch
        ]
        client.upsert(collection_name=settings.qdrant_collection, points=points)
        logger.info("Upserted %d/%d chunks", min(start + batch_size, len(chunks)), len(chunks))


def ingest(documents: list[SourceDocument]) -> int:
    """Full pipeline: parse, chunk, embed, index. Returns total chunk count."""
    client = get_qdrant_client()
    ensure_collection(client)
    total = 0
    for doc in documents:
        chunks = parse_and_chunk(doc)
        index_chunks(client, chunks)
        total += len(chunks)
    return total
