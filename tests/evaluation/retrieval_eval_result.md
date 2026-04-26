# RAG Retrieval Evaluation Results

Evaluation dataset: `tests/evaluation/retrieval_eval_dataset.json`  
Dataset version: 28 corpus chunks, 28 queries  
Evaluation script: `scripts/evaluate_retrieval.py`  
Environment: dev (Bedrock us-east-1)

## Query Coverage

| Failure class | Query IDs | Chunks |
|---|---|---|
| Postgres connection pool exhaustion | q001–q003 | eval-chunk-001–003 |
| OOM / container memory kills | q003–q004 | eval-chunk-004–005 |
| High CPU / autoscaling | q005–q006 | eval-chunk-006–007 |
| Redis connection failure / cache miss | q007–q008 | eval-chunk-008–010 |
| SQS queue backlog (cascading producer/consumer) | q009–q010 | eval-chunk-011–012 |
| API gateway rate limiting / circuit breaker | q011–q012 | eval-chunk-013–014 |
| Auth service latency spikes | q013–q014 | eval-chunk-015–016 |
| Disk I/O saturation | q015–q016 | eval-chunk-017–018 |
| Deployment / migration rollback | q017–q018 | eval-chunk-019–020 |
| TLS / certificate expiry | q019–q020 | eval-chunk-021–022 |
| Network timeouts (cascading) | q021–q022 | eval-chunk-023–024 |
| RDS replication lag / failover | q023–q025 | eval-chunk-025–026 |
| Kubernetes OOMKilled / CrashLoopBackOff | q026–q028 | eval-chunk-027–028 |

## Run: With Reranking (Cohere Rerank 3.5)

Command: `python scripts/evaluate_retrieval.py`

```
═══════════════════════════════════════════════════════
  Results WITH reranking (Cohere Rerank 3.5)
═══════════════════════════════════════════════════════
  Recall@3 : 0.8929  (target > 0.80)  ✓ PASS
  MRR@3    : 0.8571  (target > 0.70)  ✓ PASS
  NDCG@3   : 0.8690
  Hit rate : 0.8929  (25/28 queries)
═══════════════════════════════════════════════════════
```

All CI/CD thresholds passed (`--threshold 0.8`).

## Run: Without Reranking (Cosine Similarity Only)

Command: `python scripts/evaluate_retrieval.py --disable-rerank`

```
═══════════════════════════════════════════════════════
  Results WITHOUT reranking (cosine similarity only)
═══════════════════════════════════════════════════════
  Recall@3 : 0.7143  (target > 0.80)  ✗ BELOW TARGET
  MRR@3    : 0.6786  (target > 0.70)  ✗ BELOW TARGET
  NDCG@3   : 0.6940
  Hit rate : 0.7143  (20/28 queries)
═══════════════════════════════════════════════════════
```

## Reranking Improvement Delta

```
═══════════════════════════════════════════════════════
  RERANKING IMPROVEMENT SUMMARY
═══════════════════════════════════════════════════════
  Recall@3   before=0.7143  after=0.8929  delta=+0.1786
  MRR@3      before=0.6786  after=0.8571  delta=+0.1785
  NDCG@3     before=0.6940  after=0.8690  delta=+0.1750
═══════════════════════════════════════════════════════
```

Cohere Rerank 3.5 improves Recall@3 by **+17.9 pp** and MRR@3 by **+17.9 pp** over raw cosine similarity. Both metrics only clear the CI targets with reranking enabled.

## Missed Queries (with reranking)

Three queries miss at Recall@3 — all involve cross-chunk reasoning where the relevant information is spread across two runbooks that share little surface-level vocabulary:

| Query ID | Description | Root cause |
|---|---|---|
| q012 | API gateway circuit breaker open + rate limiting | Chunk eval-chunk-013 is dominated by rate-limit terminology; circuit breaker chunk (eval-chunk-014) ranks 4th |
| q022 | Payments service upstream timeout failures | eval-chunk-023 (timeout config) retrieves fine; eval-chunk-024 (VPC latency) not recalled at @3 |
| q024 | Payments service RDS Multi-AZ failover | eval-chunk-026 (failover) retrieves well; eval-chunk-025 (replica lag) displaced by eval-chunk-003 |

These are acceptable misses given the dataset size. Expanding each runbook to include cross-references in its text will lift these queries on a future run.

## Observations

- Cosine similarity alone fails both Recall@3 and MRR@3 targets, confirming that reranking is not optional for production quality.
- The eight missed queries without reranking are concentrated in queries that span two runbooks with semantically similar but distinct vocabulary (connection pool vs. connection failure; network timeout vs. network latency).
- Kubernetes OOMKilled queries (q026–q028) perform well because the corpus chunks include both the diagnostic commands (`exit code 137`, `kubectl describe`) and the fix (`resources.limits.memory`), giving the embedder strong signal.
- Cascading failure queries (q012, q021, q028) are the hardest class — they require both a primary and a secondary chunk to be in the top 3. Reranking raises the secondary chunk above noise candidates that share only partial vocabulary.

## Threshold Behaviour

The `--threshold` flag is used by `corpus.yml` after each ingestion:

```
python scripts/evaluate_retrieval.py --threshold 0.8
```

- Exit code 0: Recall@3 ≥ 0.8 — ingestion accepted.
- Exit code 1: Recall@3 < 0.8 — workflow fails, corpus change must be investigated before merging.

This prevents runbook edits that inadvertently degrade retrieval from reaching the running system.
