"""Download MediAssist documents from S3 into a local staging directory.

Documents live in S3 under <prefix>/<collection>/<filename>, e.g.
    docs/clinical/treatment_protocols.pdf
The first path segment after the prefix is the document collection and drives
the RBAC metadata stamped onto every chunk at ingestion time.

If S3 is not configured (or for local development), `discover_local`
reads the same <collection>/<filename> layout from DATA_DIR instead.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import boto3

from app.config import get_settings
from app.rbac import ALL_COLLECTIONS

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".pdf", ".md", ".markdown"}


@dataclass
class SourceDocument:
    local_path: Path
    collection: str          # general | clinical | nursing | billing | equipment
    source_document: str     # original filename


def download_from_s3(staging_dir: str | Path = "s3_staging") -> list[SourceDocument]:
    """Sync all supported documents from the S3 bucket to a local folder."""
    settings = get_settings()
    s3 = boto3.client("s3", region_name=settings.aws_region)
    staging = Path(staging_dir)
    staging.mkdir(parents=True, exist_ok=True)

    docs: list[SourceDocument] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=settings.s3_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel = key[len(settings.s3_prefix):].lstrip("/")
            parts = rel.split("/")
            if len(parts) < 2:
                continue  # not in <collection>/<file> layout
            collection, filename = parts[0], parts[-1]
            if collection not in ALL_COLLECTIONS:
                logger.warning("Skipping %s — unknown collection %r", key, collection)
                continue
            if Path(filename).suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            local_path = staging / collection / filename
            local_path.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(settings.s3_bucket, key, str(local_path))
            logger.info("Downloaded s3://%s/%s", settings.s3_bucket, key)
            docs.append(SourceDocument(local_path, collection, filename))
    return docs


def discover_local(data_dir: str | Path | None = None) -> list[SourceDocument]:
    """Discover documents on disk laid out as <data_dir>/<collection>/<file>."""
    settings = get_settings()
    root = Path(data_dir or settings.data_dir)
    docs: list[SourceDocument] = []
    for collection in ALL_COLLECTIONS:
        cdir = root / collection
        if not cdir.is_dir():
            continue
        for path in sorted(cdir.iterdir()):
            if path.suffix.lower() in SUPPORTED_SUFFIXES:
                docs.append(SourceDocument(path, collection, path.name))
    return docs
