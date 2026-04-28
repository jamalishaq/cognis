"""Ingest runbook Markdown files into the corpus (S3 Vectors + DynamoDB CorpusChunks).

Usage:
    python scripts/ingest_corpus.py --all
    python scripts/ingest_corpus.py --files runbooks/kubernetes/crashloopbackoff.md
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

# Make `app` importable from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.app.config import settings
from backend.app.utils.chunker import chunk_markdown
from backend.app.services import bedrock, dynamodb, s3vectors

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent
_RUNBOOKS_DIR = _REPO_ROOT / "runbooks"


def _file_slug(path: Path) -> str:
    """Derive a stable chunk-id prefix from the file stem."""
    return re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")


def ingest_file(path: Path) -> int:
    """Chunk, embed, and store one Markdown file. Returns number of chunks ingested."""
    text = path.read_text(encoding="utf-8")
    chunks = chunk_markdown(text)
    slug = _file_slug(path)
    source_file = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")

    ingested = 0
    for idx, chunk_text in enumerate(chunks):
        chunk_id = f"{slug}-chunk-{idx:03d}"

        try:
            vector = bedrock.embed(settings.embedding_model_id, chunk_text, input_type="search_document")
        except Exception as exc:
            logger.error("embed failed for %s chunk %d: %s", path.name, idx, exc)
            continue

        try:
            s3vectors.upsert_vectors(
                settings.s3_vectors_bucket_name,
                settings.s3_vectors_index_name,
                [
                    {
                        "key": chunk_id,
                        "vector": vector,
                        "metadata": {"source_file": source_file, "chunk_index": idx},
                    }
                ],
            )
        except Exception as exc:
            logger.error("S3 Vectors upsert failed for %s chunk %d: %s", path.name, idx, exc)
            continue

        try:
            dynamodb.put_item(
                "CorpusChunks",
                {
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "source_file": source_file,
                    "chunk_index": idx,
                },
            )
        except Exception as exc:
            logger.error("DynamoDB put failed for %s chunk %d: %s", path.name, idx, exc)
            continue

        ingested += 1

    logger.info("%s → %d/%d chunks ingested", source_file, ingested, len(chunks))
    return ingested


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest runbook Markdown files into the corpus.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Ingest all .md files under runbooks/")
    group.add_argument("--files", nargs="+", metavar="PATH", help="Ingest specific file paths")
    args = parser.parse_args()

    if args.all:
        files = sorted(_RUNBOOKS_DIR.glob("**/*.md"))
        if not files:
            logger.warning("No Markdown files found under %s", _RUNBOOKS_DIR)
            return
    else:
        files = [Path(f) for f in args.files]
        missing = [str(f) for f in files if not f.exists()]
        if missing:
            for m in missing:
                logger.error("File not found: %s", m)
            sys.exit(1)

    total_chunks = 0
    for f in files:
        total_chunks += ingest_file(f)

    print(f"\nDone. {len(files)} file(s), {total_chunks} chunk(s) ingested.")


if __name__ == "__main__":
    main()
