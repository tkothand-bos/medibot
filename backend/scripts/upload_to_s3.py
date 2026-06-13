"""Upload the local dataset to S3 in the <prefix>/<collection>/<file> layout.

Expects local data laid out as:
    data/
      general/   *.pdf|*.md
      clinical/  ...
      nursing/   ...
      billing/   ...
      equipment/ ...

Run:
    python scripts/upload_to_s3.py [--data-dir ../data]
"""
from __future__ import annotations

import argparse
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings          # noqa: E402
from app.ingestion.s3_loader import SUPPORTED_SUFFIXES  # noqa: E402
from app.rbac import ALL_COLLECTIONS         # noqa: E402
from pathlib import Path                      # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()

    settings = get_settings()
    root = Path(args.data_dir or settings.data_dir)
    s3 = boto3.client("s3", region_name=settings.aws_region)

    # Create bucket if missing (us-east-1 needs no LocationConstraint).
    try:
        s3.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        kwargs = {"Bucket": settings.s3_bucket}
        if settings.aws_region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": settings.aws_region}
        s3.create_bucket(**kwargs)
        print(f"Created bucket {settings.s3_bucket}")

    count = 0
    for collection in ALL_COLLECTIONS:
        cdir = root / collection
        if not cdir.is_dir():
            print(f"(skip) no local folder for collection '{collection}'")
            continue
        for path in sorted(cdir.iterdir()):
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            key = f"{settings.s3_prefix}{collection}/{path.name}"
            s3.upload_file(str(path), settings.s3_bucket, key)
            print(f"Uploaded s3://{settings.s3_bucket}/{key}")
            count += 1
    print(f"\nDone — {count} files uploaded.")


if __name__ == "__main__":
    main()
