# Cognis

An AI-powered incident response system that intercepts infrastructure alerts, diagnoses root causes using RAG-augmented reasoning, and assists on-call engineers via a chat interface.

---

## Note: 
See [SUMMARY.md](SUMMARY.md) for detailed architectural decisions, model selection benchmarks, and design rationale.

## Overview

When an alert fires from an alerting tool (Grafana, PagerDuty), the system:

1. Normalises the alert payload into a standard internal schema
2. Classifies the incident (service, severity, failure class)
3. Retrieves relevant runbooks and past incidents from the knowledge base
4. Produces a structured incident brief with root cause hypothesis and recommended actions
5. Notifies the on-call engineer via email with a link to the chat interface
6. Allows the engineer to ask follow-up questions and mark the incident as resolved

Resolved incidents are automatically ingested into the knowledge base, making the system smarter over time.

---

## Architecture

```
/analyse endpoint or SQS             /chat endpoint
        │                                  │
        ▼                                  ▼
Normaliser                           Chat Model
        │                                  │
        ▼                                  │
Triage Classifier                         │
        │                                  │
        └──────────────┬───────────────────┘
                       ▼
             RAG Retrieval
             (S3 Vectors + DynamoDB)
                       │
                       ▼
             Reasoning Agent
                       │
                       ▼
             LLM as a Judge
                       | 
                       ▼
             Store Incident Brief (DynamoDB)
                       │
             ┌─────────┴──────────┐
             ▼                    ▼
     Return incident_id      SQS → Lambda → SES
     + status to caller       (async notification)
                                   │
                                   ▼
                             Email → Engineer
                                   │
                                   ▼
                        Engineer resolves via UI
                                   │
                                   ▼
                       POST /incidents/{id}/resolve
                                   │
                        ┌──────────┴──────────┐
                        ▼                     ▼
                Return response          SQS → Lambda
                                     (async corpus ingestion)
                                              │
                                              ▼
                                    Chunk → Embed → Store
                                    (S3 Vectors + DynamoDB)
```

---

## Tech Stack

| Layer | Choice |
|---|---|
| Frontend framework | React + Vite |
| UI components | Shadcn/ui + Tailwind CSS |
| Markdown rendering | React Markdown + rehype-highlight |
| State management | Zustand |
| Data fetching | TanStack Query |
| Frontend hosting | Amazon S3 |
| Frontend access | Internal ALB (private VPC) |
| API server | FastAPI on ECS Fargate |
| Data validation | Pydantic |
| LLM orchestration | Native Bedrock SDK (boto3) |
| Database | DynamoDB |
| Triage model | claude-haiku-3.5 (via Bedrock) |
| Chat model | claude-haiku-3.5 (via Bedrock) |
| Reasoning model | claude-sonnet-4 (via Bedrock) |
| Embedding model | Cohere embed-v4 (via Bedrock) |
| Vector store | Amazon S3 Vectors |
| Notification service | Amazon SES (async via SQS + Lambda) |
| Observability | Amazon CloudWatch + AWS X-Ray + Langfuse |
| Authentication | AWS Cognito User Pool |
| Secrets | AWS Secrets Manager + Parameter Store |
| Container registry | Amazon ECR |
| IaC | Terraform |
| CI/CD | GitHub Actions |
| Cloud | AWS |

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/analyse` | POST | Receives alert, runs pipeline, returns `incident_id` |
| `/chat` | POST | Follow-up questions on an incident |
| `/incidents/{id}` | GET | Retrieve incident brief |
| `/incidents/{id}/history` | GET | Retrieve chat history |
| `/incidents/{id}/resolve` | POST | Mark incident as resolved |

---

## Project Structure

```
cognis/
    ├── backend/
    │     ├── app/
    │     │     ├── main.py
    │     │     ├── config.py
    │     │     ├── api/
    │     │     │     ├── analyse.py
    │     │     │     ├── chat.py
    │     │     │     ├── incidents.py
    │     │     │     ├── resolve.py
    │     │     │     └── health.py
    │     │     ├── pipeline/
    │     │     │     ├── normaliser.py
    │     │     │     ├── triage.py
    │     │     │     ├── retrieval.py
    │     │     │     ├── agent.py
    │     │     │     └── judge.py
    │     │     ├── providers/
    │     │     │     ├── base.py
    │     │     │     ├── notifications/
    │     │     │     │     ├── ses.py
    │     │     │     │     ├── slack.py
    │     │     │     │     └── teams.py
    │     │     │     └── normalisers/
    │     │     │           ├── grafana.py
    │     │     │           ├── pagerduty.py
    │     │     │           └── generic.py
    │     │     ├── registry/
    │     │     │     ├── notification_registry.py
    │     │     │     └── normaliser_registry.py
    │     │     ├── models/
    │     │     │     ├── alert.py
    │     │     │     ├── incident.py
    │     │     │     ├── chat.py
    │     │     │     └── resolve.py
    │     │     ├── services/
    │     │     │     ├── bedrock.py
    │     │     │     ├── dynamodb.py
    │     │     │     ├── s3vectors.py
    │     │     │     └── sqs.py
    │     │     └── lambdas/
    │     │           ├── notify.py
    │     │           └── ingest.py
    │     ├── tests/
    │     │     ├── unit/
    │     │     ├── integration/
    │     │     └── smoke/
    │     ├── Dockerfile
    │     ├── requirements.txt
    │     └── .dockerignore
    │
    ├── frontend/
    │     ├── src/
    │     │     ├── pages/
    │     │     ├── components/
    │     │     ├── hooks/
    │     │     ├── store/
    │     │     ├── lib/
    │     │     └── types/
    │     ├── vite.config.ts
    │     ├── tailwind.config.ts
    │     └── package.json
    │
    ├── terraform/
    │     ├── modules/
    │     │     ├── networking/
    │     │     ├── compute/
    │     │     ├── storage/
    │     │     ├── messaging/
    │     │     ├── ai/
    │     │     ├── auth/
    │     │     ├── secrets/
    │     │     └── observability/
    │     └── environments/
    │           ├── dev/
    │           └── prod/
    │
    ├── runbooks/
    │     ├── kubernetes/
    │     ├── redis/
    │     ├── postgres/
    │     ├── post-mortems/
    │     ├── sre-general/
    │     └── org-specific/
    │
    ├── scripts/
    │     ├── seed_local.py
    │     ├── ingest_corpus.py
    │     ├── evaluate_retrieval.py
    │     └── evaluate_agent.py
    │
    ├── tests/
    │     └── evaluation/
    │           ├── retrieval_eval_dataset.json
    │           └── agent_eval_dataset.json
    │
    ├── .github/
    │     └── workflows/
    │           ├── backend.yml
    │           ├── frontend.yml
    │           ├── terraform.yml
    │           └── corpus.yml
    │
    ├── .env.local.example
    ├── .gitignore
    ├── docker-compose.yml
    └── README.md
```

---

## Local Development

**Prerequisites:** Docker, Docker Compose, Node.js, Python 3.12, AWS credentials (for Bedrock)

**1. Copy environment template:**
```bash
cp .env.local.example .env.local
# Fill in AWS credentials for Bedrock
```

**2. Start backend services:**
```bash
docker compose up
```

**3. Seed local database:**
```bash
python scripts/seed_local.py
```

**4. Start frontend:**
```bash
cd frontend
npm install
npm run dev
```

**Services running locally:**

| Service | URL |
|---|---|
| FastAPI | http://localhost:8000 |
| React | http://localhost:3000 |
| DynamoDB Local | http://localhost:8001 |
| ElasticMQ (SQS) | http://localhost:9324 |

> Cognito auth is disabled locally. S3 Vectors is mocked. Emails are logged to console.

---

## Running Tests

**Backend:**
```bash
cd backend
pytest tests/unit/
pytest tests/integration/
pytest tests/smoke/        # requires running dev environment
```

**Frontend:**
```bash
cd frontend
npm run test               # Vitest unit tests
npm run test:integration   # React Testing Library
```

---

## Corpus Management

Runbooks are stored as Markdown files in `/runbooks`. Changes merged to `main` automatically trigger re-ingestion of updated files and retrieval evaluation via GitHub Actions.

**Initial corpus load:**
```bash
python scripts/ingest_corpus.py --all
```

**Re-embed specific files (called automatically by CI/CD):**
```bash
python scripts/ingest_corpus.py --files runbooks/kubernetes/oomkilled.md
```

**Retrieval evaluation (dev environment only):**
```bash
python scripts/evaluate_retrieval.py                    # full evaluation
python scripts/evaluate_retrieval.py --disable-rerank   # baseline without reranking
```

**Agent output evaluation (dev environment only):**
```bash
python scripts/evaluate_agent.py
```

---

## Deployment

Deployment is handled automatically via GitHub Actions:

| Trigger | Action |
|---|---|
| Merge to `main` | Deploy backend + frontend to **dev** |
| Manual trigger | Deploy backend + frontend to **prod** |
| PR opened | Terraform plan posted as PR comment |
| Merge to `main` | Terraform apply to dev |
| Manual trigger | Terraform apply to prod |

---

## Database Schema

**Three DynamoDB tables:**

**Incidents** — PK: `incident_id`
Stores incident briefs created by `/analyse` and updated by `/incidents/{id}/resolve`.

**ChatMessages** — PK: `incident_id`, SK: `message_id`
Stores conversation history per incident for `/chat` and `/incidents/{id}/history`.

**CorpusChunks** — PK: `chunk_id`
Stores runbook and incident chunk text retrieved after S3 Vectors similarity search.

---

## Environment Variables

| Variable | Description |
|---|---|
| `ENVIRONMENT` | `local`, `dev`, or `prod` |
| `AWS_REGION` | AWS region |
| `DYNAMODB_ENDPOINT` | DynamoDB endpoint (local only) |
| `SQS_ENDPOINT` | SQS endpoint (local only) |
| `S3_VECTORS_MOCK` | Mock S3 Vectors locally (`true`/`false`) |
| `SES_MODE` | `log` for local, `send` for deployed |
| `AUTH_DISABLED` | Disable Cognito auth locally (`true`/`false`) |
| `AWS_ACCESS_KEY_ID` | AWS credentials (local only — for Bedrock) |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials (local only — for Bedrock) |

In deployed environments all config is injected at runtime from AWS Secrets Manager and Parameter Store.

---

## Further Reading

See [SUMMARY.md](SUMMARY.md) for detailed architectural decisions, model selection benchmarks, and design rationale.
