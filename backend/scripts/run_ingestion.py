"""Run the full ingestion pipeline once, before serving/demoing.

By default pulls documents from S3 (the source of truth). Use --local to
ingest straight from the local data/ folder during development.

Run:
    python scripts/run_ingestion.py            # from S3
    python scripts/run_ingestion.py --local    # from ../data
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ingestion.ingest import ingest                      # noqa: E402
from app.ingestion.s3_loader import discover_local, download_from_s3  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true",
                        help="Ingest from the local data dir instead of S3")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    if args.local:
        docs = discover_local(args.data_dir)
    else:
        docs = download_from_s3()

    if not docs:
        print("No documents found. Check your S3 bucket/prefix or data dir layout:")
        print("  <collection>/<file>.pdf|.md  where collection is one of "
              "general, clinical, nursing, billing, equipment")
        sys.exit(1)

    print(f"Found {len(docs)} documents across collections.")
    total = ingest(docs)
    print(f"\nIngestion complete: {total} chunks indexed.")


if __name__ == "__main__":
    main()
