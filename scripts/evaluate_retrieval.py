#!/usr/bin/env python3
"""
RAG retrieval evaluation script.

Measures Recall@3, MRR@3, and NDCG@3 for the retrieval pipeline against
a known evaluation dataset with query/relevant_chunk_id pairs.

Local cosine similarity replaces the S3 Vectors mock (which returns only
hardcoded chunk_ids and is unsuitable for quality measurement).

Requirements:
  - DynamoDB Local running on localhost:8001 (docker compose up)
  - AWS credentials with Bedrock access configured (for embed + rerank)
  - ENVIRONMENT=local or env vars pointing to local DynamoDB

Usage:
    # Run with reranking (default)
    python scripts/evaluate_retrieval.py

    # Run without reranking
    python scripts/evaluate_retrieval.py --no-rerank

    # Run both and show improvement delta
    python scripts/evaluate_retrieval.py --compare

    # Cache embeddings to avoid re-embedding on subsequent runs
    python scripts/evaluate_retrieval.py --compare --cache-embeddings

Baseline results are printed to stdout in a summary table.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap — allow importing from backend/app
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

os.environ.setdefault("ENVIRONMENT", "local")
if os.environ["ENVIRONMENT"] == "local":
    os.environ.setdefault("DYNAMODB_ENDPOINT", "http://localhost:8001")
    os.environ.setdefault("S3_VECTORS_MOCK", "true")

from backend.app.config import settings  # noqa: E402 (import after env setup)
from backend.app.services import bedrock, dynamodb  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATASET_PATH = REPO_ROOT / "tests" / "evaluation" / "retrieval_eval_dataset.json"
EMBEDDINGS_CACHE_PATH = REPO_ROOT / "tests" / "evaluation" / ".embeddings_cache.json"

EMBED_MODEL_ID = "cohere.embed-english-v4:0"
RERANK_MODEL_ID = "cohere.rerank-v3-5:0"
TOP_CANDIDATES = 20
TOP_RESULTS = 5
EVAL_K = 3


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for r in retrieved[:k] if r in relevant)
    return hits / len(relevant)


def mrr_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    for i, r in enumerate(retrieved[:k], start=1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(
        1.0 / math.log2(i + 1)
        for i, r in enumerate(retrieved[:k], start=1)
        if r in relevant
    )
    ideal_n = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_n + 1))
    return dcg / idcg if idcg > 0 else 0.0


# ---------------------------------------------------------------------------
# Cosine similarity (pure Python, no external deps)
# ---------------------------------------------------------------------------

def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    denom = _norm(a) * _norm(b)
    return _dot(a, b) / denom if denom > 0 else 0.0


def local_vector_search(
    query_vec: list[float],
    corpus_embeddings: dict[str, list[float]],
    top_k: int,
) -> list[str]:
    """Return top_k chunk_ids ranked by cosine similarity to query_vec."""
    scored = [
        (chunk_id, cosine_similarity(query_vec, emb))
        for chunk_id, emb in corpus_embeddings.items()
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [chunk_id for chunk_id, _ in scored[:top_k]]


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _embed_text(text: str, input_type: str) -> list[float]:
    """Call Bedrock Cohere embed-v4 with the correct input_type."""
    import boto3  # noqa: PLC0415

    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    body = json.dumps({
        "texts": [text],
        "input_type": input_type,
        "embedding_types": ["float"],
    })
    response = client.invoke_model(
        modelId=EMBED_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    data = json.loads(response["body"].read())
    return data["embeddings"]["float"][0]


def embed_corpus_chunks(
    chunks: list[dict],
    cache: bool = False,
) -> dict[str, list[float]]:
    """Embed all corpus chunks using search_document input type.

    If cache=True, reads from / writes to EMBEDDINGS_CACHE_PATH so that
    subsequent runs with --compare avoid re-embedding.
    """
    if cache and EMBEDDINGS_CACHE_PATH.exists():
        print("  Loading embeddings from cache...")
        cached = json.loads(EMBEDDINGS_CACHE_PATH.read_text())
        chunk_ids = {c["chunk_id"] for c in chunks}
        if chunk_ids.issubset(cached.keys()):
            return {k: cached[k] for k in chunk_ids}
        print("  Cache incomplete — re-embedding missing chunks")

    embeddings: dict[str, list[float]] = {}
    for i, chunk in enumerate(chunks, start=1):
        chunk_id = chunk["chunk_id"]
        print(f"  Embedding chunk {i}/{len(chunks)}: {chunk_id}", end="\r")
        embeddings[chunk_id] = _embed_text(chunk["text"], "search_document")
        time.sleep(0.1)  # avoid throttling
    print()

    if cache:
        EMBEDDINGS_CACHE_PATH.write_text(json.dumps(embeddings))
        print(f"  Embeddings cached to {EMBEDDINGS_CACHE_PATH.name}")

    return embeddings


def embed_query(query: str) -> list[float]:
    return _embed_text(query, "search_query")


# ---------------------------------------------------------------------------
# DynamoDB corpus seeding
# ---------------------------------------------------------------------------

def seed_eval_corpus(chunks: list[dict]) -> None:
    """Upsert evaluation corpus chunks into the local CorpusChunks table."""
    for chunk in chunks:
        dynamodb.put_item("CorpusChunks", {
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "source_file": chunk["source_file"],
            "chunk_index": 0,
            "embedding_model": EMBED_MODEL_ID,
        })


def fetch_chunk_text(chunk_id: str) -> str | None:
    item = dynamodb.get_item("CorpusChunks", {"chunk_id": chunk_id})
    return item["text"] if item and "text" in item else None


# ---------------------------------------------------------------------------
# Evaluation run
# ---------------------------------------------------------------------------

def run_evaluation(
    dataset: dict[str, Any],
    corpus_embeddings: dict[str, list[float]],
    use_rerank: bool,
    verbose: bool = True,
) -> tuple[dict[str, float], list[dict]]:
    """Run all queries and return (aggregate metrics, per-query results)."""
    queries = dataset["queries"]
    results: list[dict] = []

    label = "with reranking" if use_rerank else "without reranking"
    print(f"\nEvaluating {len(queries)} queries ({label})...")

    for query_obj in queries:
        q_id = query_obj["query_id"]
        query_text = query_obj["query"]
        relevant = set(query_obj["relevant_chunk_ids"])

        # Embed query
        q_vec = embed_query(query_text)

        # Local cosine similarity → top-20 candidate chunk_ids
        candidate_ids = local_vector_search(q_vec, corpus_embeddings, TOP_CANDIDATES)

        if use_rerank:
            # Fetch texts for reranking
            texts: list[str] = []
            valid_ids: list[str] = []
            for cid in candidate_ids:
                text = fetch_chunk_text(cid)
                if text:
                    texts.append(text)
                    valid_ids.append(cid)

            if not texts:
                ranked_ids = candidate_ids[:TOP_RESULTS]
            else:
                # Rerank and map back to chunk_ids via text → id lookup
                text_to_id = dict(zip(texts, valid_ids))
                reranked_texts = bedrock.rerank(
                    RERANK_MODEL_ID, query_text, texts, top_n=TOP_RESULTS
                )
                ranked_ids = [text_to_id[t] for t in reranked_texts if t in text_to_id]
        else:
            ranked_ids = candidate_ids[:TOP_RESULTS]

        r3 = recall_at_k(ranked_ids, relevant, EVAL_K)
        mrr = mrr_at_k(ranked_ids, relevant, EVAL_K)
        ndcg = ndcg_at_k(ranked_ids, relevant, EVAL_K)

        results.append({
            "query_id": q_id,
            "description": query_obj["description"],
            "recall": r3,
            "mrr": mrr,
            "ndcg": ndcg,
            "retrieved": ranked_ids[:EVAL_K],
            "relevant": list(relevant),
            "hit": r3 > 0,
        })

        status = "✓" if r3 > 0 else "✗"
        if verbose:
            print(
                f"  {status} {q_id}: R@3={r3:.2f}  MRR={mrr:.2f}  NDCG={ndcg:.2f}"
                f"  — {query_obj['description']}"
            )

    n = len(results)
    metrics = {
        "recall_at_3": sum(r["recall"] for r in results) / n,
        "mrr_at_3": sum(r["mrr"] for r in results) / n,
        "ndcg_at_3": sum(r["ndcg"] for r in results) / n,
        "hit_rate": sum(1 for r in results if r["hit"]) / n,
        "n_queries": n,
    }

    # Surface failures for debugging
    misses = [r for r in results if not r["hit"]]
    if misses:
        print(f"\n  Missed queries ({len(misses)}):")
        for r in misses:
            print(f"    {r['query_id']}: retrieved={r['retrieved']}  relevant={r['relevant']}")

    return metrics, results


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_metrics_table(label: str, metrics: dict[str, float]) -> None:
    print(f"\n{'─' * 55}")
    print(f"  {label}")
    print(f"{'─' * 55}")
    print(f"  Recall@3 : {metrics['recall_at_3']:.4f}  (target > 0.80)")
    print(f"  MRR@3    : {metrics['mrr_at_3']:.4f}  (target > 0.70)")
    print(f"  NDCG@3   : {metrics['ndcg_at_3']:.4f}")
    print(f"  Hit rate : {metrics['hit_rate']:.4f}  ({int(metrics['hit_rate'] * metrics['n_queries'])}/{int(metrics['n_queries'])} queries)")
    print(f"{'─' * 55}")


def print_comparison(with_r: dict, without_r: dict) -> None:
    print(f"\n{'═' * 55}")
    print("  RERANKING IMPROVEMENT SUMMARY")
    print(f"{'═' * 55}")
    rows = [
        ("Recall@3", "recall_at_3"),
        ("MRR@3", "mrr_at_3"),
        ("NDCG@3", "ndcg_at_3"),
    ]
    for name, key in rows:
        before = without_r[key]
        after = with_r[key]
        delta = after - before
        sign = "+" if delta >= 0 else ""
        print(f"  {name:<10}  before={before:.4f}  after={after:.4f}  delta={sign}{delta:.4f}")
    print(f"{'═' * 55}")


def write_report(
    metrics: dict[str, float],
    per_query_results: list[dict],
    use_rerank: bool,
    threshold: float | None,
) -> None:
    """Write evaluation_report.json to the repo root (read by corpus.yml CI step)."""
    import datetime  # noqa: PLC0415

    report = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "rerank_enabled": use_rerank,
        "n_queries": int(metrics["n_queries"]),
        "aggregate": {
            "recall_at_3": round(metrics["recall_at_3"], 4),
            "mrr_at_3": round(metrics["mrr_at_3"], 4),
            "ndcg_at_3": round(metrics["ndcg_at_3"], 4),
            "hit_rate": round(metrics["hit_rate"], 4),
        },
        "per_query": per_query_results,
    }
    if threshold is not None:
        report["threshold_check"] = {
            "metric": "recall_at_3",
            "threshold": threshold,
            "value": round(metrics["recall_at_3"], 4),
            "passed": metrics["recall_at_3"] >= threshold,
        }
    report_path = REPO_ROOT / "evaluation_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Report written to {report_path.relative_to(REPO_ROOT)}")


def check_targets(metrics: dict[str, float]) -> bool:
    passed = True
    if metrics["recall_at_3"] < 0.80:
        print(f"\n  WARNING: Recall@3 {metrics['recall_at_3']:.4f} is below target 0.80")
        passed = False
    if metrics["mrr_at_3"] < 0.70:
        print(f"\n  WARNING: MRR@3 {metrics['mrr_at_3']:.4f} is below target 0.70")
        passed = False
    return passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval quality")
    parser.add_argument(
        "--disable-rerank",
        action="store_true",
        help="Disable Cohere Rerank — measure raw cosine similarity quality",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        metavar="FLOAT",
        help="Fail with exit code 1 if Recall@3 drops below this value (used by CI/CD)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run both with and without reranking and show the improvement delta",
    )
    parser.add_argument(
        "--cache-embeddings",
        action="store_true",
        help=f"Cache corpus embeddings to {EMBEDDINGS_CACHE_PATH.name} to speed up repeated runs",
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip seeding eval corpus into DynamoDB (use when already seeded)",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("  Cognis RAG Retrieval Evaluation")
    print(f"  Dataset : {DATASET_PATH.relative_to(REPO_ROOT)}")
    print(f"  DynamoDB: {settings.dynamodb_endpoint or 'AWS'}")
    print(f"  Region  : {settings.aws_region}")
    print("=" * 55)

    # Load dataset
    if not DATASET_PATH.exists():
        print(f"ERROR: dataset not found at {DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    dataset = json.loads(DATASET_PATH.read_text())
    corpus_chunks = dataset["corpus_chunks"]
    print(f"\nLoaded {len(corpus_chunks)} corpus chunks, {len(dataset['queries'])} queries")

    # Seed eval corpus into DynamoDB Local
    if not args.skip_seed:
        print("\nSeeding eval corpus into DynamoDB CorpusChunks...")
        try:
            seed_eval_corpus(corpus_chunks)
            print(f"  Seeded {len(corpus_chunks)} chunks")
        except Exception as exc:
            print(f"ERROR: Failed to seed DynamoDB — is docker compose up? ({exc})", file=sys.stderr)
            sys.exit(1)

    # Embed corpus chunks
    print("\nEmbedding corpus chunks via Bedrock...")
    try:
        corpus_embeddings = embed_corpus_chunks(corpus_chunks, cache=args.cache_embeddings)
        print(f"  Embedded {len(corpus_embeddings)} chunks")
    except Exception as exc:
        print(f"ERROR: Bedrock embedding failed — check AWS credentials. ({exc})", file=sys.stderr)
        sys.exit(1)

    if args.compare:
        # Run both modes
        metrics_with, per_query_with = run_evaluation(dataset, corpus_embeddings, use_rerank=True)
        metrics_without, _ = run_evaluation(dataset, corpus_embeddings, use_rerank=False)

        print_metrics_table("Results WITH reranking (Cohere Rerank 3.5)", metrics_with)
        print_metrics_table("Results WITHOUT reranking (cosine similarity only)", metrics_without)
        print_comparison(metrics_with, metrics_without)

        write_report(metrics_with, per_query_with, use_rerank=True, threshold=args.threshold)

        print("\nChecking targets (with reranking)...")
        passed = check_targets(metrics_with)
        if args.threshold is not None and metrics_with["recall_at_3"] < args.threshold:
            print(f"\n  FAIL: Recall@3 {metrics_with['recall_at_3']:.4f} is below threshold {args.threshold}")
            passed = False
        sys.exit(0 if passed else 1)

    else:
        use_rerank = not args.disable_rerank
        metrics, per_query = run_evaluation(dataset, corpus_embeddings, use_rerank=use_rerank)
        label = "WITH reranking" if use_rerank else "WITHOUT reranking"
        print_metrics_table(f"Results {label}", metrics)

        write_report(metrics, per_query, use_rerank=use_rerank, threshold=args.threshold)

        passed = True
        if use_rerank:
            print("\nChecking targets...")
            passed = check_targets(metrics)
        if args.threshold is not None and metrics["recall_at_3"] < args.threshold:
            print(f"\n  FAIL: Recall@3 {metrics['recall_at_3']:.4f} is below threshold {args.threshold}")
            passed = False
        sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
