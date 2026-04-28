# Cognis — Technical Summary

AI-powered incident response system. Sits between alerting tools (Grafana, PagerDuty) and on-call engineers. Intercepts alerts, diagnoses root causes using RAG + tool-calling agent, notifies engineers, and supports follow-up via chat.

---

## System Flow

```
Alerting tool → POST /analyse → Normaliser → Triage → RAG (embed → S3 Vectors top 20 → Rerank top 5)
→ Reasoning Agent (tool loop) → LLM Judge (async) → Store DynamoDB → Return incident_id
→ SQS → Lambda → SES email to engineer

Engineer → opens UI (S3) → GET /incidents/{id} → POST /chat (streaming)
→ POST /incidents/{id}/resolve → SQS → Lambda → re-embed into knowledge base
```

---

## API Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/analyse` | Receives alert, runs full pipeline, returns `incident_id` |
| POST | `/chat` | Streaming follow-up questions on an incident |
| GET | `/incidents/{id}` | Fetch incident brief |
| GET | `/incidents/{id}/history` | Fetch chat history |
| POST | `/incidents/{id}/resolve` | Mark resolved, triggers corpus ingestion |

---

## AI Pipeline

**Triage** — `claude-haiku-4.5` classifies alert into `{ service, severity, failure_class }` as structured JSON. Retry 3x exponential backoff.

**RAG Retrieval** — Query embedded via `cohere.embed-v4:0` → S3 Vectors top 20 candidates → `cohere.rerank-v3-5:0` reranks → top 5 chunks passed to agent. Degrades gracefully if retrieval fails.

**Reasoning Agent** — `claude-sonnet-4-6` tool-calling loop (2–5 tool calls per incident):

| Tool | Source |
|---|---|
| `get_metrics` | Mock (canned data keyed by service) |
| `get_deployment_history` | Mock |
| `search_incident_history` | Real DynamoDB query |
| `get_service_dependencies` | Real CorpusChunks lookup |

**LLM Judge** — `claude-haiku-4.5` runs async after agent. Scores groundedness, completeness, actionability, confidence. Scores stored in DynamoDB — never exposed in API responses. Judge failure never blocks the brief.

**Chat** — same agent with tools, streaming via `StreamingResponse`. Loads incident brief + full conversation history before each turn.

---

## Models (AWS Bedrock — us-east-1)

| Role | Model ID |
|---|---|
| Reasoning agent | `us.anthropic.claude-sonnet-4-6` |
| Triage / Chat / Judge | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Embedding | `cohere.embed-v4:0` (dimensions=1024) |
| Reranking | `cohere.rerank-v3-5:0` |

---

## Extensibility — Provider Pattern

Two extension points using abstract base classes:

**Notification providers** — `NotificationProvider` ABC with `send()`. Active providers read from `ACTIVE_NOTIFICATION_PROVIDERS` config. Multiple can be active simultaneously. Current: `ses.py`. Stubs: `slack.py`, `teams.py`.

**Alert normalisers** — `AlertNormaliser` ABC with `can_handle()` + `normalise()`. Registry iterates in order, first match wins. `GenericNormaliser` always last. Current: Grafana, PagerDuty, Generic.

Adding a new provider = one new file + register it. Zero existing code changes.

---

## RAG Knowledge Base

Markdown files in `/runbooks/`. Covers: Kubernetes, Redis, Postgres runbooks, SRE post-mortems, service catalogue, alert definitions, on-call playbooks, known issues.

**Ingestion:** Markdown-aware chunking (512 tokens, 50 token overlap) → embed → S3 Vectors (vector + chunk_id) + DynamoDB CorpusChunks (chunk_id + text).

**Triggers:**
- Manual: `python scripts/ingest_corpus.py --all`
- CI/CD: auto on `/runbooks/**` changes → `ingest_corpus.py --files <changed>`
- Runtime: resolved incidents auto-ingested via SQS → Lambda

**Retrieval evaluation:** `scripts/evaluate_retrieval.py` — Recall@3, MRR, NDCG@3. Runs in CI/CD after ingestion with `--threshold 0.8`. Fails workflow if quality drops.

---

## Database — DynamoDB (on-demand)

**Incidents** — PK: `incident_id`. Fields: service, severity, failure_class, hypothesis, recommended_actions, status, resolution details, eval scores (internal), raw_payload.

**ChatMessages** — PK: `incident_id` + SK: `message_id`. Fields: role, content, created_at.

**CorpusChunks** — PK: `chunk_id`. Fields: document_title, document_type, content, source. Linked to S3 Vectors by `chunk_id`.

---

## Notifications — Async SQS → Lambda → SES

After `/analyse` stores the brief → drops message to SQS notification queue → Lambda composes and sends email via SES. FastAPI returns immediately — email is a side effect. SQS DLQ catches failures after 3 retries.

Email contains: incident ID, service, severity, hypothesis, recommended actions, link to UI.

---

## Infrastructure

| Layer | Choice |
|---|---|
| API server | FastAPI on ECS Fargate (python:3.12-slim, multi-stage Docker) |
| Frontend | React + Vite → S3 static website (public read) |
| Load balancer | Internet-facing ALB → ECS port 8000 |
| Database | DynamoDB (on-demand, 3 tables) |
| Vector store | Amazon S3 Vectors |
| Async messaging | SQS (2 queues) + Lambda (2 functions) |
| Email | Amazon SES |
| Auth | AWS Cognito (provisioned, not enforced for capstone) |
| Secrets | AWS Secrets Manager (sensitive) + Parameter Store (config) |
| Observability | CloudWatch + X-Ray (infra) + Langfuse (AI pipeline) |
| IaC | Terraform (modular, S3 native locking ≥ v1.11) |
| CI/CD | GitHub Actions (OIDC auth, 4 workflows) |

---

## Networking (Capstone — simplified)

Single public subnet. ECS has public IP (`assign_public_ip=true`). No NAT Gateway, no VPC Endpoints, no IP restrictions. ALB open to `0.0.0.0/0`. ECS reachable only via ALB security group (port 8000 locked to ALB).

**Production hardening (deferred):** Private subnets, NAT Gateway, VPC Endpoints, IP allowlist on `/analyse`, Cognito enforced on ALB.

---

## Error Handling

| Stage | Failure behaviour |
|---|---|
| Triage | Retry 3x → 503 to caller |
| RAG S3 Vectors | Retry 3x → empty chunks + `retrieval_context_available=false` |
| RAG Rerank | Retry 3x → degrade to raw similarity results |
| Reasoning agent | Retry 3x → return triage result + 503 |
| DynamoDB write | Log + return brief anyway |
| LLM Judge | Catch all exceptions → `eval_ran=false` → continue |
| /chat agent | Retry 3x → 503 with "Unable to process your request" |
| SQS/Lambda | DLQ after 3 retries — never blocks API response |

---

## CI/CD — GitHub Actions (OIDC, no stored credentials)

| Workflow | Trigger | Action |
|---|---|---|
| `backend.yml` | Push to main | Test → Docker (SHA+latest) → ECR → ECS |
| `frontend.yml` | Push to main | Test → Vite build → S3 sync |
| `terraform.yml` | PR / merge / manual | Plan on PR, apply dev on merge, apply prod manually |
| `corpus.yml` | `/runbooks/**` change | Ingest changed files → evaluate retrieval (fails if Recall@3 < 0.8) |

Dev deploys automatically on merge. Prod requires manual trigger.

