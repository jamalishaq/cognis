# Cognis

An AI system that monitors infrastructure alerts, retrieves relevant runbooks and past incident context, and assists on-call engineers in diagnosing and resolving incidents in real time.

---

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | System health check |
| `/analyse` | POST | Receives alert payload, normalises to internal schema, runs triage → RAG → reasoning, stores incident brief, returns `incident_id` + status to caller |
| `/chat` | POST | Accepts `incident_id` + user message, runs chat → RAG → reasoning, stores and returns conversational response |
| `/incidents/{id}` | GET | Retrieves a stored incident brief by ID — used to load original context when an engineer opens the chat UI or joins an active incident |
| `/incidents/{id}/history` | GET | Retrieves full conversation history for an incident — used by `/chat` to maintain context across turns |
| `/incidents/{id}/resolve` | POST | Accepts resolution details from engineer, updates incident record in DynamoDB, triggers async corpus ingestion |

**Decision: `/analyse` as webhook**

Alerting tools like PagerDuty and Grafana POST directly to `/analyse` when an alert fires. This is the simplest integration pattern and sufficient for the project scope.

**Future improvement — SQS queue:** Place an SQS queue in front of `/analyse` so that if the service is temporarily unavailable or overwhelmed, alerts are not lost. SQS adds retry guarantees and decouples the alerting tool from the system — the endpoint drains the queue at its own pace rather than handling bursts directly.

**Future improvement — Rate limiting:** Rate limiting on `/analyse` was considered to protect against alert storms overwhelming Bedrock rate limits. It was deferred for three reasons: alert storms are simulated in the capstone so bursts won't occur in practice; error handling already retries gracefully on Bedrock throttles; and the SQS queue improvement above is the more correct production solution — it absorbs bursts naturally without dropping requests. If SQS is not implemented, `slowapi` on the `/analyse` endpoint is the lightweight addition needed.

---

## System Overview

```
/analyse endpoint                    /chat endpoint
        │                                  │
        ▼                                  ▼
Normaliser                           Chat Model
(converts Grafana/PagerDuty/         (fetches incident brief +
 generic payload to internal schema)  conversation history via incident_id)
        │                                  │
        ▼                                  │
Triage Classifier                         │
(service, severity, failure_class)        │
        │                                  │
        └──────────────┬───────────────────┘
                       ▼
             RAG Retrieval (pipeline)
             Fetches: runbooks + similar past incidents
                       │
                       ▼
             Reasoning Agent
             Diagnoses root cause using context + tools
                       │
                       ▼
             Store Incident Brief
                       │
             ┌─────────┴──────────┐
             ▼                    ▼
     Return incident_id      Async Notification
     + status to caller      SQS → Lambda → SES → Engineer email
                                                        │
                                                        ▼
                                              Email contains link to UI
                                                        │
                                                        ▼
                                          Engineer resolves incident on UI
                                                        │
                                                        ▼
                                        POST /incidents/{id}/resolve
                                                        │
                                                        ▼
                                         Update DynamoDB (resolution details)
                                                        │
                                             ┌──────────┴──────────┐
                                             ▼                     ▼
                                     Return Response          Async ingestion
                                                         SQS → Lambda → corpus
```

---

## Architecture Decisions

### Alert Normaliser

Every alerting tool sends its own payload format. Designing `/analyse` around one specific format would tightly couple the system to a single tool and break if the format changes. A normalisation layer sits at the very start of the `/analyse` pipeline and converts any incoming payload into a consistent internal schema before triage runs.

**Supported formats:**

| Source | Format |
|---|---|
| Grafana / Alertmanager | `alerts[]` array with `labels` and `annotations` |
| PagerDuty | `messages[]` array with nested `data.incident` |
| Generic fallback | Best-effort extraction from any other payload |

**Internal normalised schema:**

```json
{
  "source": "grafana",
  "service": "payments-api",
  "severity": "critical",
  "alert_name": "HighLatency",
  "description": "p99 latency exceeded 2000ms",
  "triggered_at": "2025-04-23T10:15:00Z",
  "raw_payload": { "...": "original payload preserved" }
}
```

The `raw_payload` field preserves the original so no information is lost. The triage classifier always receives the normalised schema regardless of the source tool.

---

### Notification Service

After the incident brief is stored, the on-call engineer or team is notified asynchronously via email.

**Decision: Async via SQS → Lambda → SES**

Two approaches were considered:

| | Synchronous | Asynchronous |
|---|---|---|
| Email timing | Before response returns | After response returns, in background |
| Latency impact | Adds 200–500ms to `/analyse` | None — critical path unaffected |
| Failure impact | SES failure breaks `/analyse` response | SES failure is isolated, analysis still returns |
| Complexity | Low | Slightly higher |

Async was chosen because the email is a side effect — it should not be able to slow down or break the core analysis response. The `/analyse` endpoint returns immediately after storing the brief; the notification fires in the background via a three-component chain.

**Component roles:**

| Component | Role |
|---|---|
| **SQS** | Queue that decouples FastAPI from the notification logic. FastAPI drops a message into the queue and returns immediately — it does not wait for the email to send |
| **Lambda** | Worker that picks up the message from SQS, composes the email content, and calls SES to deliver it |
| **SES** | Email delivery service — receives the composed email from Lambda and delivers it to the engineer's inbox |

**Why SQS instead of calling Lambda directly from FastAPI?**

Calling Lambda directly would still be async but fragile — if Lambda is temporarily unavailable the notification is lost. SQS holds the message safely in the queue until Lambda is ready to process it, and automatically retries if Lambda fails. If retries are exhausted, the message moves to a Dead Letter Queue (DLQ) for inspection rather than being silently dropped.

**Flow:**
```
FastAPI stores incident brief
    │
    └──→ drops message into SQS       (non-blocking, fast)
                │
                ▼
          Lambda picks up message      (background)
                │
                ▼
          Composes email
                │
                ▼
          SES delivers to engineer
```

**Email content:** Incident ID, affected service, severity, top root cause hypothesis, recommended next actions, and a link to open the chat interface for that incident.

**Future improvement:** Integrate Slack or Microsoft Teams notifications in addition to email, giving teams the option to receive alerts in their existing communication channels.



---



### Frontend Deployment

The frontend is a static app (HTML, CSS, JS) hosted on an S3 bucket, accessed by engineers via an internal ALB.

**Decision: S3 + Internal ALB, no CloudFront**

CloudFront is a CDN — its value is edge caching across regions to reduce latency for geographically distributed users. That benefit does not apply here. This is an internal tool accessed by on-call engineers on the same corporate network or VPN. What matters is access control and network isolation, not global distribution.

| | S3 + CloudFront | S3 + Internal ALB |
|---|---|---|
| Public internet reachable | Yes | No |
| Access control | Cognito / signed URLs | VPC security groups |
| Geo-distribution benefit | Yes | Not needed |
| Complexity | Lower | Higher |

The Internal ALB sits inside a private VPC subnet. Engineers reach the frontend only via VPN or the internal network — the app is never reachable from the public internet.

---

### API Gateway vs Internal ALB Direct

**Decision: Internal ALB direct to ECS Fargate, no API Gateway**

API Gateway sits in front of a compute layer and adds cross-cutting capabilities. Two options were considered:

| Capability | ALB alone | API Gateway + ALB |
|---|---|---|
| Route traffic to ECS | ✅ | ✅ |
| Rate limiting | ❌ | ✅ |
| Request validation | ❌ | ✅ |
| Auth (API keys, JWT) | ❌ | ✅ |
| Throttling per endpoint | ❌ | ✅ |
| Cost | Lower | Additional |

API Gateway is unnecessary for this system because:
- Auth is handled at the network level via VPC — only engineers on the internal network or VPN can reach the ALB
- Rate limiting is not a concern with a small on-call team
- Request validation, routing, and serialisation are handled by FastAPI internally

**What FastAPI handles directly:**
- **Request validation** — Pydantic models validate every incoming request payload, rejecting malformed inputs before they reach the pipeline
- **Response serialisation** — structured JSON responses are automatically serialised from Python models
- **Routing** — each endpoint (`/analyse`, `/chat`, `/incidents/{id}`, etc.) is defined and handled within FastAPI
- **Error handling** — HTTP exceptions and pipeline errors are caught and returned as structured error responses
- **Streaming** — `/chat` responses stream tokens back to the client as they are generated, keeping perceived latency low

**Future improvement:** If the system is ever exposed externally or becomes multi-tenant, API Gateway would be the right addition for per-client auth and throttling.



### RAG: Pipeline Step vs Agent Tool

RAG retrieval runs as a **fixed pipeline step** — it always executes between triage and the reasoning agent.

| | Pipeline Step | Agent Tool |
|---|---|---|
| Retrieval timing | Always, before agent | On demand, agent decides |
| Latency | Predictable | Variable (extra reasoning hop) |
| Complexity | Low | High |
| Flexibility | Fixed query strategy | Dynamic, context-aware queries |

**Decision: Pipeline Step**

Retrieval always fires using the triage classification output as the query. This keeps latency predictable and the architecture simple within the project timeline.

**Future improvement:** Migrate RAG to an agent tool so the reasoning agent can decide when and what to retrieve dynamically. This enables more flexible, context-aware retrieval at the cost of added complexity.

---

## Model Selection

### Chat Model

**Role:** Handle follow-up questions on the `/chat` endpoint. Understands conversation history and incident context, frames the question, then passes to the same RAG → Reasoning Agent pipeline. Does not perform reasoning itself.

**Evaluation criteria (priority order):** conversational quality → instruction following → latency → cost

| Model | Conversational Quality | Instruction Following | Latency (p50) | Cost per 1M tokens |
|---|---|---|---|---|
| **claude-haiku-4.5** ✅ | Very good | Excellent | ~0.8s | $0.80 in / $4 out |
| GPT-4o mini | Very good | Excellent | ~0.9s | $0.15 in / $0.60 out |
| claude-sonnet-4 | Excellent | Excellent | ~2.5s | $3 in / $15 out |
| Gemini 1.5 Flash | Good | Good | ~0.7s | $0.075 in / $0.30 out |

**Decision: `claude-haiku-4.5`**

`claude-sonnet-4.6` has better conversational depth but at ~2.5s p50 it makes chat feel sluggish — users expect near-instant responses in a chat interface. `Gemini 1.5 Flash` is the cheapest but instruction following degrades on technical follow-up questions where precise, grounded answers matter. `GPT-4o mini` is a close cheaper alternative, but Haiku's consistency on technical content edges it out. Using Haiku for both triage and chat also keeps the model surface area minimal — one fewer vendor to manage.

**Latency SLO:** < 3s first token (streaming recommended)

---

### Triage Classifier

**Role:** Classify every incoming alert into `{ service, severity, failure_class }` as structured JSON.

**Evaluation criteria (priority order):** latency → structured output reliability → cost

| Model | Latency (p50) | Structured Output | Cost per 1M tokens |
|---|---|---|---|
| **claude-haiku-4.5** ✅ | ~0.8s | Excellent | $0.80 in / $4 out |
| GPT-4o mini | ~0.9s | Excellent | $0.15 in / $0.60 out |
| Gemini 1.5 Flash | ~0.7s | Good | $0.075 in / $0.30 out |

**Decision: `claude-haiku-4.5`**

Gemini 1.5 Flash is the cheapest and GPT-4o mini is cheaper than Haiku, but both were ruled out. A misclassified alert poisons every downstream stage, so structured output reliability is non-negotiable. Haiku delivers consistent, well-formed JSON on edge cases (ambiguous alerts, missing fields, multi-service cascades) where cheaper models degrade. Cost was traded off in favour of latency and output reliability.

**Latency SLO:** < 2s

---

### Reasoning Agent

**Role:** Receive alert + triage output + retrieved docs, call tools to gather signal, and produce a structured incident brief.

**Evaluation criteria (priority order):** tool use quality → reasoning depth → context window → cost

| Model | Tool Use | Reasoning | Context Window | Cost per 1M tokens |
|---|---|---|---|---|
| **claude-sonnet-4** ✅ | Excellent | Excellent | 200K | $3 in / $15 out |
| GPT-4o | Excellent | Excellent | 128K | $2.50 in / $10 out |
| Gemini 1.5 Pro | Good | Very good | 1M | $1.25 in / $5 out |
| o3-mini | Very good | Excellent | 200K | $1.10 in / $4.40 out |

**Decision: `claude-sonnet-4.6`**

GPT-4o, Gemini 1.5 Pro, and o3-mini are all cheaper. However, the reasoning agent runs 3–5 sequential tool calls while holding retrieved runbooks in context — this is where smaller or cheaper models visibly degrade (dropped tool results, wrong tool selection, failure to synthesise across documents). Sonnet-4's tool use quality and 200K context window handle this reliably. Cost was traded off in favour of tool use accuracy and reasoning depth.

> **Cost in practice:** At ~2,000 tokens per incident, a single reasoning agent call costs approximately $0.01. Cost only becomes a concern at very high P1/P2 incident volumes.

**Latency SLO:** < 15s end-to-end including tool calls

---

### Embedding Model

**Role:** Embed the runbook and incident corpus at index time; embed incoming queries at retrieval time.

**Evaluation criteria (priority order):** retrieval quality → latency per embed → cost at scale

| Model | Retrieval Quality | Embed Latency | Cost per 1M tokens | Dimensions | Bedrock |
|---|---|---|---|---|---|
| **Cohere embed-v4 (`cohere.embed-v4:0`)** ✅ | Excellent | ~40–55ms | $0.01 | 1024 | ✅ |
| text-embedding-3-large | Excellent | ~50ms | $0.13 | 3072 | ❌ |
| text-embedding-3-small | Very good | ~30ms | $0.02 | 1536 | ❌ |
| voyage-code-2 | Excellent (code/technical) | ~40ms | $0.12 | 1536 | ❌ |
| Cohere embed-v3 | Excellent | ~60ms | $0.10 | 1024 | ✅ |

**Decision: `Cohere embed-v4 (`cohere.embed-v4:0`)`**

`text-embedding-3-large` was the original choice before the decision to go fully AWS via Bedrock. On retrieval quality and latency the two models are comparable — embed-v4 holds a marginal edge on MTEB benchmarks (65.2 vs 64.6) and matches on latency. The decisive factors for switching were cost ($0.01 vs $0.13 per million tokens — a 13x difference at scale) and Bedrock availability, which keeps the entire stack within AWS under IAM-based auth with no external API keys to manage. `text-embedding-3-large` and `voyage-code-2` were ruled out as they are not available on Bedrock.

---

## Observability & Monitoring

**Tooling stack:**

| Concern | Tool |
|---|---|
| Infrastructure health | Amazon CloudWatch + AWS X-Ray |
| AI pipeline observability | Langfuse |
| Alerting | CloudWatch Alarms |

CloudWatch was chosen over Datadog because the system is fully on AWS — ECS, Lambda, SQS, and Bedrock metrics are all captured automatically with no additional agent setup. Datadog would add cost and setup complexity without meaningful benefit at this scope. X-Ray provides distributed tracing across the pipeline stages. Langfuse was chosen for AI observability because CloudWatch has no native understanding of LLM concepts — token usage, prompt traces, and retrieval quality require a purpose-built tool. Langfuse is open source, has a free tier, supports Bedrock, and provides full pipeline-level tracing.

---

### 1. Infrastructure & API Observability
*Tooling: CloudWatch + X-Ray*

| Metric | What it signals |
|---|---|
| p50/p95/p99 latency per endpoint | SLO health for `/analyse` and `/chat` |
| Error rate (4xx / 5xx) per endpoint | Pipeline failures — 5xx on `/analyse` means incidents are not being processed |
| ECS CPU / memory / task restarts | Container health — OOM kills or crash loops |
| Bedrock API errors and throttles | Model call failures that break the pipeline |
| SQS queue depth | Notification backlog — a growing queue signals Lambda can't keep up |
| Lambda execution errors | Failed notification deliveries |

---

### 2. Pipeline Observability
*Tooling: X-Ray + Langfuse*

Each pipeline stage is traced independently so the source of a latency breach or failure can be pinpointed without guessing.

| What is tracked | Why |
|---|---|
| Stage-level latency (triage, RAG, agent) | Identifies exactly where time is spent when an SLO is breached |
| Stage-level failure rate | Distinguishes a RAG timeout from a Bedrock throttle |
| Distributed trace per request | A single trace ID follows a request through the full pipeline — reconstructs the complete execution for any incident |

---

### 3. AI-Specific Observability
*Tooling: Langfuse*

| Metric | What it signals |
|---|---|
| Token usage per model call (input + output) | Real-time cost tracking and prompt bloat detection |
| Model response latency | Bedrock-level degradation separate from pipeline latency |
| RAG retrieval similarity scores | Low scores signal a stale corpus or a poor query match — retrieved documents are not relevant |
| Triage malformed output rate | Rising rate signals a change in alert payload format the model is not handling |
| Reasoning agent citation rate | Proxy for hallucination — briefs that don't cite retrieved documents are reasoning from training data, not grounded context |

---

### 4. Business & Operational Metrics
*Tooling: CloudWatch custom metrics*

| Metric | What it signals |
|---|---|
| Incidents processed per hour | Volume tracking and capacity planning |
| Mean time to brief | From alert firing to incident brief delivered — end-to-end system effectiveness |
| SES delivery and bounce rate | Whether engineers are actually receiving notifications |
| `/chat` engagement rate | Whether engineers use the chat interface after receiving a brief — low engagement signals the briefs are not useful enough |

---

### 5. Alerting
*Tooling: CloudWatch Alarms*

Alerts fire when:
- Endpoint p95 latency breaches SLO thresholds
- Endpoint error rate exceeds 1% over a 5-minute window
- Bedrock throttling errors spike
- SQS queue depth grows beyond expected baseline
- ECS task restart count exceeds threshold
- Lambda execution error rate rises

---

## Latency Budget

**`/analyse` endpoint**

| Stage | Target |
|---|---|
| Triage classification | < 2s |
| RAG retrieval | < 1s |
| Reasoning agent (incl. tool calls) | < 12s |
| **End-to-end** | **< 15s** |

**`/chat` endpoint**

| Stage | Target |
|---|---|
| Chat model (first token) | < 3s |
| RAG retrieval | < 1s |
| Reasoning agent (incl. tool calls) | < 12s |
| **End-to-end** | **< 16s** |

---

## Benchmarking Plan

| Component | Method | Metric |
|---|---|---|
| Chat model | 20 multi-turn conversations with technical follow-up questions | Response relevance, instruction following rate, p50/p95 latency |
| Triage classifier | 50 synthetic alert payloads incl. edge cases | Classification accuracy, malformed JSON rate, p50/p95 latency |
| Reasoning agent | 10 incident scenarios with known root causes | Tool call accuracy, root cause hit rate, hallucination rate, time-to-brief |
| Embedding model | 20 queries with known relevant documents | Recall@3, MRR, query latency |

---

## Frontend & Backend Decisions

### Frontend Framework

**Decision: React + Vite**

Next.js was ruled out because its SSR capability requires a Node.js runtime — it cannot be deployed as pure static files to S3. SSR and SEO are irrelevant for an internal tool. React with Vite builds pure static files that deploy directly to S3, consistent with the S3 + Internal ALB decision and adds no extra infrastructure.

---

### UI Components & Styling

**Decision: Shadcn/ui + Tailwind CSS**

Shadcn/ui components are copied directly into the project — only what is used is shipped. No bloated dependency and full control over styling. Tailwind CSS handles all custom styling. Material UI, Chakra UI, and Ant Design were ruled out due to larger bundle sizes and CSS-in-JS overhead.

---

### Markdown Rendering

**Decision: React Markdown + rehype-highlight**

LLM responses from the reasoning agent are returned in Markdown — headers, bullet points, bold text, and code blocks containing commands and config snippets. A rendering library is required to display these properly in the chat UI.

| | React Markdown | MDX | Marked |
|---|---|---|---|
| React native | ✅ | ✅ | ❌ |
| Streaming friendly | ✅ | ❌ | ✅ |
| Syntax highlighting | Via rehype-highlight | Via plugin | Manual |
| Lightweight | ✅ | ❌ | ✅ |

React Markdown renders Markdown as React components, integrating cleanly with Tailwind styling and re-rendering incrementally as streamed chunks arrive. The `rehype-highlight` plugin adds syntax highlighting for code blocks. MDX is designed for content authoring with embedded React components — not for rendering LLM output. Marked has no native React integration.

---

### Streaming

**Decision: Native `fetch` with `ReadableStream`**

Streaming for the `/chat` endpoint is handled at the data fetching layer, not the UI layer — Shadcn/ui is purely a component library and has no involvement in streaming. TanStack Query does not handle streaming well out of the box, so the `/chat` endpoint uses native `fetch` with `ReadableStream` directly, reading chunks as they arrive and appending to message state. TanStack Query handles all non-streaming endpoints — `/incidents/{id}` and `/incidents/{id}/history`.

---

### State Management

**Decision: Zustand**

Incident state and chat history need to be shared across components. React Context is too limited for this and Redux Toolkit introduces heavy boilerplate for the scope of this project. Zustand is lightweight with minimal setup and handles shared state cleanly.

---

### Data Fetching

**Decision: TanStack Query**

Handles caching, loading states, and error handling automatically for non-streaming endpoints. Used for `/incidents/{id}` and `/incidents/{id}/history`. Removes manual state management for data that needs to be cached and refetched.

---

### Backend: LLM Orchestration

**Decision: Native Bedrock SDK (boto3)**

LangChain and LlamaIndex were considered but ruled out. The pipeline is simple and predefined by code — triage → RAG → reasoning agent. Heavy orchestration frameworks add abstraction that makes debugging harder, which is the opposite of what is needed in an incident response system. Calling each model directly via boto3 keeps full control and makes the pipeline straightforward to trace and debug.

---

### Backend: Data Validation

**Decision: Pydantic**

Already built into FastAPI. Validates every incoming alert payload and outgoing response with no additional dependency.

---

### Backend: Database

Incident briefs and conversation history need to be stored and retrieved for `/incidents/{id}` and `/incidents/{id}/history`.

| | DynamoDB | PostgreSQL (RDS) | Redis |
|---|---|---|---|
| Lookup by ID | Excellent | Good | Good |
| Query flexibility | Limited | High | Limited |
| AWS managed | ✅ | ✅ RDS | ✅ ElastiCache |
| Operational overhead | None | Medium | Low |

**Decision: DynamoDB**

Incident briefs and chat history are retrieved by `incident_id` — simple key-based lookups with no complex joins. DynamoDB is purpose-built for this access pattern, is fully managed on AWS with no server to maintain, and stays consistent with the AWS-first stack.

---

## Infrastructure as Code

**Tooling: Terraform**

---

### State Backend

**Decision: S3 with native locking (`use_lockfile = true`)**

Prior to Terraform 1.10, S3 state backends required a separate DynamoDB table for state locking. From Terraform 1.11 this is no longer needed — Terraform creates a `.tflock` file directly in the S3 bucket using S3 conditional writes, achieving the same locking guarantee with fewer resources.

| | S3 + DynamoDB lock | S3 native lock (v1.11+) |
|---|---|---|
| Extra resource needed | DynamoDB table | None |
| IAM permissions | S3 + DynamoDB | S3 only |
| Cost | S3 + DynamoDB costs | S3 only |
| Complexity | Higher | Lower |
| Future support | Being deprecated | Recommended path forward |

DynamoDB locking is deprecated and will be removed in a future Terraform version. S3 native locking requires S3 bucket versioning to be enabled.

```hcl
terraform {
  required_version = ">= 1.11"
  backend "s3" {
    bucket     = "incident-platform-terraform-state"
    key        = "terraform.tfstate"
    region     = "us-east-1"
    use_lockfile = true
    encrypt    = true
  }
}
```

---

### Module Structure

**Decision: Modular**

The system has enough distinct infrastructure concerns that a flat structure becomes unmanageable quickly. Each module owns a single concern and can be developed, reviewed, and changed independently.

```
terraform/
  modules/
    networking/       # VPC, subnets, security groups, Internal ALB
    compute/          # ECS cluster, Fargate service, ECR repository
    storage/          # S3 (frontend + state), DynamoDB, S3 Vectors
    messaging/        # SQS queue, Lambda function, DLQ
    ai/               # Bedrock IAM roles and policies
    observability/    # CloudWatch dashboards, alarms, X-Ray, Langfuse config
  environments/
    dev/              # dev-specific variable values and backend config
    prod/             # prod-specific variable values and backend config
```

Each environment directory references the same modules with different variable values — no duplication of resource definitions.

---

### Environments

**Decision: dev and prod**

Two environments are maintained — `dev` for development and testing, `prod` for the stable running system. They share the same module definitions but differ in:

- Instance sizes and capacity (smaller in dev)
- Bedrock model selection (could use cheaper models in dev)
- Alerting thresholds (relaxed in dev)
- State stored in separate S3 keys per environment

---

## CI/CD

**Tooling: GitHub Actions**

AWS CodePipeline was considered but ruled out — it is significantly more complex to set up for a straightforward build and deploy pipeline and is AWS-only. GitHub Actions has a generous free tier, a large ecosystem, and integrates cleanly with AWS via OIDC.

---

### AWS Authentication

**Decision: OIDC federation (no long-lived credentials)**

GitHub Actions assumes an IAM role via OIDC federation on each run. No AWS credentials are stored in GitHub secrets — tokens are short-lived and scoped per pipeline run. Storing long-lived IAM credentials in GitHub secrets is a security risk and not acceptable for a production system.

---

### Branch & Trigger Strategy

**Decision: Trunk-based with manual prod promotion**

A long-lived `dev` branch was considered but ruled out. It adds process overhead — two PRs per feature — without meaningful benefit for a solo or small team. What actually protects prod at this scale is tests on every PR and deliberate promotion, not a branch gate.

```
feature branch → PR → main
                         │
                    auto-deploy to dev
                         │
                    verify in dev
                         │
                    manual trigger → deploy to prod
```

| Trigger | What fires |
|---|---|
| Pull request to `main` | Tests run — no deploy |
| Merge to `main` | Auto-deploy to **dev environment** |
| Manual trigger | Deploy to **prod environment** |
| Pull request opened | Terraform plan posted as PR comment |
| Merge to `main` | Terraform apply to dev |
| Manual trigger | Terraform apply to prod |

---

### Backend Pipeline (FastAPI → ECS Fargate)

```
Merge to main
    │
    ▼
Run tests
    │
    ▼
Build Docker image
    │
    ▼
Push image to ECR
    │
    ▼
Update ECS service (force new deployment)
    │
    ▼
Verify ECS task is healthy
```

---

### Frontend Pipeline (React → S3)

```
Merge to main
    │
    ▼
Run tests
    │
    ▼
npm run build (Vite produces static files)
    │
    ▼
Sync build output to S3 bucket
```

---

### Terraform Pipeline

```
Pull request opened
    │
    ▼
terraform fmt + validate
    │
    ▼
terraform plan (output posted as PR comment)
    │
    ▼
PR merged to main → terraform apply (dev)
    │
    ▼
Manual trigger → terraform apply (prod)
```

---

## Containerisation

Only the FastAPI backend is containerised. The React frontend is not — Vite produces pure static files that are synced directly to S3 by the CI/CD pipeline. There is no server to run and therefore no container needed.

| | Containerised | Deployment target |
|---|---|---|
| FastAPI | ✅ Docker image → ECR → ECS Fargate | CI/CD builds image, pushes to ECR, updates ECS service |
| React | ❌ | CI/CD runs `npm run build`, syncs static files to S3 |

---

### Base Image

**Decision: `python:3.12-slim`**

| | python:3.12-slim | python:3.12-alpine | python:3.12 |
|---|---|---|---|
| Image size | ~150MB | ~50MB | ~1GB |
| Compatibility | Excellent | ⚠️ C extensions break | Excellent |
| Build complexity | Low | Medium | Low |
| Production suitable | ✅ | ⚠️ | ❌ Too large |

Alpine was ruled out despite its smaller size — many Python packages with C extensions that FastAPI dependencies rely on break or require extra build steps on Alpine. `python:3.12-slim` is small enough, production appropriate, and has no compatibility surprises.

---

### Image Storage

**Decision: Amazon ECR**

AWS-native container registry. Integrates directly with ECS so no separate credentials are needed — IAM controls access. Images stay within the AWS network and never traverse the public internet.

---

### Dockerfile Approach

**Multi-stage build** — separates build environment from runtime image. The final image only contains what is needed to run the app, not build tools, keeping the image size minimal.

```dockerfile
# Stage 1 — build
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2 — runtime
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY . .
USER nonroot
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Non-root user** — the container runs as a non-privileged user. Running as root inside a container is a security risk even in a managed environment.

**`.dockerignore`** — excludes `.git`, `__pycache__`, `.env`, and test files from the build context, keeping the image clean and builds fast.

**Pinned dependencies** — `requirements.txt` uses pinned versions to ensure reproducible builds across dev and prod environments.

---

### ECS Task Definition

| Setting | Decision |
|---|---|
| Health check | Points at `/health` endpoint — ECS marks task unhealthy and replaces it if `/health` stops responding |
| Environment variables | Injected at runtime from AWS Secrets Manager — never baked into the image |
| CPU / Memory | Sized to handle concurrent pipeline executions — tuned per environment (smaller in dev) |

---

## Secrets Management

**Decision: Split — Secrets Manager for sensitive values, Parameter Store for non-sensitive config**

Both services integrate natively with ECS — values are injected as environment variables into the container at task startup via IAM permissions. FastAPI reads them via `os.environ` with no knowledge of where they came from.

| Config | Sensitive | Store |
|---|---|---|
| Langfuse API key | ✅ | Secrets Manager |
| Third-party credentials (if any) | ✅ | Secrets Manager |
| Bedrock region + model IDs | ❌ | Parameter Store |
| DynamoDB table names | ❌ | Parameter Store |
| SQS queue URLs | ❌ | Parameter Store |
| SES sender address | ❌ | Parameter Store |

| | Secrets Manager | Parameter Store |
|---|---|---|
| Sensitive secrets | ✅ | ✅ SecureString |
| Non-sensitive config | ⚠️ Overkill | ✅ Standard String |
| Automatic rotation | ✅ | ❌ Manual |
| Cost | $0.40/secret/month | Free (Standard tier) |
| ECS native injection | ✅ | ✅ |

Secrets Manager is used only for values that are genuinely sensitive — it charges per secret per month so using it for non-sensitive config is unnecessary cost. Parameter Store Standard tier is free and sufficient for config values.

**Secrets never live in:**
- The Docker image
- The GitHub repository
- `.env` files committed to source control

All secrets are injected at runtime by ECS via IAM — the container has an IAM role with permissions to read only the specific secrets and parameters it needs.

---

## Authentication & Authorization

**Decision: AWS Cognito User Pool**

Network-level access via VPC + Internal ALB ensures only engineers on the corporate network or VPN can reach the app. However, network-level access alone does not distinguish between individual engineers — anyone on the VPN could access the system. For an incident platform surfacing production infrastructure details, application-level authentication is required.

| | AWS Cognito | Auth0 | Network only |
|---|---|---|---|
| AWS native | ✅ | ❌ | N/A |
| ALB integration | ✅ Built-in | ❌ Manual | N/A |
| Cost | Free up to 50K MAU | Free tier limited | Free |
| Setup complexity | Medium | Low | None |
| Acceptable for prod | ✅ | ✅ | ❌ |

Cognito integrates directly with the Internal ALB via built-in authentication rules — the ALB enforces login before any request reaches the React app or FastAPI, with no auth code needed in the application layer.

**Auth flow:**
```
Engineer opens app
    │
    ▼
ALB checks for valid Cognito session
    │
    ├── No session → redirects to Cognito hosted login page
    │                   │
    │               Engineer logs in
    │                   │
    │               Cognito issues JWT
    │                   │
    └── Valid session → request passes through to app
```

FastAPI receives the JWT in request headers and can extract engineer identity (email, group membership) for any downstream logic.

**User management: Cognito User Pool**

Engineers log in with accounts manually created in the Cognito User Pool. This is sufficient for a small closed team.

**Authorization:** All authenticated engineers have the same access level for now.

**Future improvements:**
- Federate Cognito with an existing organisational IdP (Google Workspace, Microsoft Entra) so engineers log in with their existing accounts
- Role-based access control (RBAC) — e.g. read-only vs admin roles

---

## RAG Corpus & Ingestion

The corpus is the knowledge base the RAG pipeline searches through when retrieving context for the reasoning agent. Without it the reasoning agent has no grounded context — it would reason only from its training knowledge which may be outdated or too general for specific infrastructure.

All documents are stored as Markdown files in the `/runbooks` directory of the GitHub repository — the repo is the single source of truth for the corpus. When a document is added or updated, a PR is opened and merged like any other code change. CI/CD detects changes to `/runbooks/**` on merge to main and automatically triggers the ingestion pipeline.

---

### Corpus Contents

| Document type | Source | Coverage |
|---|---|---|
| Kubernetes runbooks | Public docs → Markdown in repo | OOMKilled, CrashLoopBackOff, pod eviction, node pressure |
| Redis runbooks | Public docs → Markdown in repo | Connection failures, memory limits, replication lag |
| Postgres runbooks | Public docs → Markdown in repo | Connection pool exhaustion, replication, slow queries |
| Public post-mortems | Google SRE book, GitHub → Markdown in repo | Real incident patterns to match against |
| Generic SRE runbooks | Google SRE book, open source → Markdown in repo | Broad failure classes — latency spikes, cascading failures |
| Infrastructure documentation | Org-specific → Markdown in repo | Service architecture, data flows, dependency maps |
| Service catalogue | Org-specific → Markdown in repo | What each service does, its dependencies, SLOs, and owning team |
| Deployment runbooks | Org-specific → Markdown in repo | Rollback procedures, scaling steps, safe restart sequences |
| Alert definitions | Org-specific → Markdown in repo | What each alert means, threshold that triggered it, historical false positive rate |
| Known issues & workarounds | Org-specific → Markdown in repo | Recurring issues with known fixes — prevents re-diagnosing the same problem |
| Dependency & integration docs | Org-specific → Markdown in repo | External services the system depends on — helps identify third-party outages |
| On-call playbooks | Org-specific → Markdown in repo | Escalation paths, who to page, communication templates |
| Past incident briefs | Generated by the system → seeded manually for capstone | How similar incidents were previously diagnosed and resolved |

**Note on past incident briefs:** This is the only document type not stored statically in the repo — it is generated dynamically by the system as engineers resolve incidents. When an engineer marks an incident as resolved via the UI, a Lambda function automatically generates a Markdown document from the full incident record (diagnosis + resolution steps + chat history summary) and ingests it into the corpus. For the capstone, a set of manually written sample past incidents will be used to seed this portion of the corpus before the resolve flow is in place.

---

### Chunking Strategy

Chunking splits large documents into smaller pieces before embedding. Each chunk is embedded and stored independently so retrieval is precise — returning the specific section relevant to a query rather than an entire document.

**Decision: Markdown-aware chunking — 512 tokens, 50 token overlap**

| Strategy | How it works | Suitable |
|---|---|---|
| Fixed size | Split every N tokens | General purpose |
| Recursive character | Split by paragraphs → sentences → words | General prose |
| Semantic | Split at meaning boundaries | High quality but complex |
| **Markdown-aware** | Split at headers and sections | ✅ Structured runbooks |

The corpus is structured Markdown with clear headers and sections. Markdown-aware chunking splits at natural document boundaries — each chunk is a coherent unit of information rather than a fragment cut mid-sentence. The 50 token overlap between chunks ensures context is not lost at boundaries.

---

### Ingestion Pipeline

Two ingestion flows exist — static corpus ingestion from the repo and dynamic ingestion from resolved incidents.

**Static corpus ingestion** — runs automatically when changes to `/runbooks/**` are detected on merge to main, and manually for the initial corpus load.

```
/runbooks/** changes merged to main
    │
    ▼
CI/CD triggers ingestion pipeline
    │
    ▼
Chunking (Markdown-aware, 512 tokens, 50 token overlap)
    │
    ▼
Embedding (Cohere embed-v4 (`cohere.embed-v4:0`) via Bedrock)
    │
    ▼
Store vectors + metadata → S3 Vectors
    │
    ▼
Store chunk text + ID → DynamoDB
```

**Resolved incident ingestion** — triggered automatically when an engineer marks an incident as resolved via the UI. This is what grows the corpus over time with organisation-specific resolution knowledge.

```
Engineer submits "Mark as Resolved" form on UI
    │
    ▼
POST /incidents/{id}/resolve
    │
    ▼
DynamoDB incident record updated:
  - actual_root_cause
  - resolution_steps
  - resolution_time_minutes
  - resolved_at
  - status: resolved
    │
    ├──→ Return response immediately
    │
    └──→ SQS message dropped (async)
              │
              ▼
         Lambda picks up message
              │
              ▼
         Generates Markdown document
         from full incident record
         (diagnosis + resolution steps + chat history summary)
              │
              ▼
         Chunking → Embedding → S3 Vectors + DynamoDB
```

**Why the resolve flow matters for the corpus:**

The incident brief stored at analysis time contains the diagnosis but not the resolution. Only after an engineer confirms the actual root cause and resolution steps does the record become valuable as a past incident reference. The corpus needs complete records — diagnosis and resolution — to be useful for future similar incidents.

**Mark as Resolved UI flow:**

The email sent to the engineer contains a link to the incident page in the UI. On that page:
- Original incident brief is displayed
- Chat history is displayed
- A "Mark as Resolved" button opens a form pre-filled with the system's hypothesis
- Engineer confirms or corrects the root cause and adds resolution steps
- On submission, `POST /incidents/{id}/resolve` is called

**Why both S3 Vectors and DynamoDB?**

S3 Vectors stores vector representations for similarity search and returns a reference ID for each match — not the original text. DynamoDB stores the chunk text keyed by that ID. The retrieval flow is: S3 Vectors finds the closest vectors → DynamoDB fetches the corresponding text to pass to the reasoning agent.

**Ingestion triggers:**

| Trigger | When |
|---|---|
| Manual script | Initial corpus load |
| CI/CD on merge to main | Changes detected in `/runbooks/**` — re-embeds changed files only |
| `POST /incidents/{id}/resolve` | Engineer marks incident resolved — async via SQS → Lambda |

---

## Error Handling Strategy

**General principles:**

| Principle | Application |
|---|---|
| Retry with exponential backoff | All Bedrock API calls and RAG retrieval — up to 3 retries |
| Graceful degradation | When retries are exhausted on non-critical stages — proceed with what is available |
| Always return something | Partial results are better than nothing when production is down |
| Never silently fail | Every failure is logged to CloudWatch with enough context to debug |
| Side effects must not block the critical path | Storage failure and notification failure must not prevent the incident brief being returned |

---

### Stage-by-stage failure behaviour

**Triage classifier fails (Bedrock call fails)**

```
Bedrock call fails
    │
    ▼
Retry up to 3 times with exponential backoff
    │
    ├── Retry succeeds → continue normally
    │
    └── All retries exhausted → return 503 to alerting tool
                                 log failure to CloudWatch
```

Nothing downstream can run without a triage classification — fail fast and clearly.

---

**RAG retrieval fails (S3 Vectors unavailable)**

```
S3 Vectors call fails
    │
    ▼
Retry up to 3 times with exponential backoff
    │
    ├── Retry succeeds → continue normally
    │
    └── All retries exhausted → degrade gracefully
        Pass triage output to reasoning agent without retrieved context
        Flag in incident brief: "Context retrieval failed — diagnosis based on triage only"
        Log failure to CloudWatch
```

A diagnosis without retrieved context is better than no diagnosis when production is down.

---

**Reasoning agent fails (Bedrock call fails)**

```
Bedrock call fails
    │
    ▼
Retry up to 3 times with exponential backoff
    │
    ├── Retry succeeds → continue normally
    │
    └── All retries exhausted → return triage classification to caller
                                 log failure to CloudWatch
                                 return 503 with triage result included
```

The triage classification is still returned so the engineer knows the service and severity even if the full diagnosis failed.

---

**DynamoDB write fails (storing incident brief)**

```
DynamoDB write fails
    │
    ▼
Return incident brief to caller regardless
Log storage failure to CloudWatch
```

The engineer receives the diagnosis even if storage failed. Chat and corpus ingestion features will not work for this incident but the immediate value — the diagnosis — is delivered. The storage failure is investigated separately via CloudWatch.

---

**SQS notification fails**

Handled by the async SQS pattern — SQS retries automatically and failed messages move to the DLQ. The `/analyse` response is never affected.

---

**LLM Judge fails (Bedrock call fails)**

```
Judge Bedrock call fails
    │
    ▼
Log failure to CloudWatch
Set eval_ran = false on incident record
    │
    ▼
Return incident brief to engineer as normal
(engineer never knows judge failed)
```

Judge failure is completely isolated — it never affects the incident brief, the notification, or any other pipeline stage. No retry — the brief is more important than the evaluation.

---

**`/chat` — reasoning agent fails mid-conversation**

```
Reasoning agent call fails
    │
    ▼
Retry up to 3 times with exponential backoff
    │
    ├── Retry succeeds → stream response normally
    │
    └── All retries exhausted → return clear error message in chat UI
                                 "Unable to process your request, please try again"
                                 Chat history is preserved — no context is lost
```

---

## Testing Strategy

---

### Backend

**Unit Tests — pytest + unittest.mock**

Test individual functions in isolation. All external dependencies (Bedrock, DynamoDB, S3 Vectors, SQS) are mocked — no real AWS services are called.

| Component | What is tested |
|---|---|
| Triage classifier | Given an alert payload, produces correct structured JSON output |
| RAG retrieval | Given a query, calls S3 Vectors with correct parameters |
| Reasoning agent | Given triage output + retrieved docs, constructs correct prompt |
| Notification service | Given an incident brief, composes correct email content |
| `/resolve` endpoint | Given resolution details, updates DynamoDB with correct fields |
| Error handling | Each stage retries correctly and degrades gracefully when mocked to fail |

**Integration Tests — pytest + moto**

Test pipeline stages working together with mocked AWS services. `moto` mocks DynamoDB, SQS, and S3 locally without a real AWS account.

| Flow | What is tested |
|---|---|
| Triage → RAG → Agent | Full `/analyse` pipeline produces a valid incident brief from a raw alert payload |
| Chat → RAG → Agent | `/chat` pipeline maintains conversation context correctly across turns |
| Resolve → DynamoDB → SQS | Marking an incident resolved correctly updates the record and triggers ingestion |

**Smoke Tests — pytest + httpx**

A small set of tests that fire a mock alert at `/analyse` and verify a valid response is returned. Run automatically after each deploy to dev. `httpx` is an async-capable HTTP client used to make real requests against the running FastAPI server.

---

### Frontend

**Unit Tests — Vitest**

Vitest is the natural choice for a Vite project — it uses the same config and runs in the same environment. Tests that individual React components render correctly.

**Integration Tests — React Testing Library**

Tests user interactions — clicking the resolve button, submitting the resolution form, chat input and response rendering, Markdown rendering of incident briefs.

---

### What runs in CI/CD

| Pipeline stage | Tests that run |
|---|---|
| Pull request to `main` | Backend unit + integration tests, frontend unit + integration tests |
| After deploy to dev | Smoke tests against live dev environment |
| Before promoting to prod | Manual E2E verification in dev environment |

---

### Tools Summary

| Layer | Tool |
|---|---|
| Backend unit + integration | pytest + unittest.mock + moto |
| Frontend unit | Vitest |
| Frontend integration | React Testing Library |
| Smoke / E2E | pytest + httpx |

---

## CORS Configuration

When the React frontend (served from S3) makes requests to the FastAPI server (on ECS via ALB), the browser blocks them by default because the two are on different origins. CORS tells the browser which origins are permitted to call the API. Without it every API call from the frontend fails in the browser regardless of whether the request reaches the server.

**Configured on FastAPI using built-in CORS middleware:**

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,  # loaded from Parameter Store per environment
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

| Setting | Decision | Why |
|---|---|---|
| `allow_origins` | Explicit list per environment | Never wildcard — see below |
| `allow_credentials` | True | Cognito JWT is sent in the Authorization header |
| `allow_methods` | GET, POST only | The API only uses these two methods |
| `allow_headers` | Authorization, Content-Type | Authorization carries the JWT, Content-Type is needed for JSON POST bodies |

**Allowed origins per environment:**

| Environment | Allowed origin |
|---|---|
| Dev | `https://dev.incident-platform.internal` |
| Prod | `https://incident-platform.internal` |

Allowed origins are loaded from AWS Parameter Store at runtime — the same Docker image runs in both environments with different CORS settings injected. Origins are never hardcoded in the application.

**`allow_origins=["*"]` is never used — not even in dev.**

Wildcard CORS defeats the purpose of network-level access control. If the ALB is ever misconfigured and the app becomes reachable outside the VPN, wildcard CORS means any website can make requests to the API on behalf of a logged-in engineer.

---

## API Request & Response Schemas

---

### `POST /analyse`

**Request** — raw alert payload from alerting tool (normalised internally before triage):

*Grafana / Alertmanager:*
```json
{
  "alerts": [{
    "status": "firing",
    "labels": {
      "alertname": "HighLatency",
      "severity": "critical",
      "service": "payments-api"
    },
    "annotations": {
      "description": "p99 latency exceeded 2000ms"
    },
    "startsAt": "2025-04-23T10:15:00Z"
  }]
}
```

*PagerDuty:*
```json
{
  "messages": [{
    "type": "trigger",
    "data": {
      "incident": {
        "id": "P1234567",
        "title": "High latency on payments-api",
        "severity": "critical",
        "service": { "name": "payments-api" },
        "created_at": "2025-04-23T10:15:00Z"
      }
    }
  }]
}
```

**Response** — returned to the alerting tool (acknowledgement only — full brief goes to engineer via email):
```json
{
  "incident_id": "INC-20250423-001",
  "status": "received",
  "timestamp": "2025-04-23T10:15:03Z"
}
```

---

### `POST /chat`

**Request:**
```json
{
  "incident_id": "INC-20250423-001",
  "message": "What should I check first?"
}
```

The `incident_id` is used to fetch the original incident brief and full conversation history from DynamoDB before passing to the chat model — this gives the model full context of the incident and everything discussed so far.

**Response** — streamed, final assembled shape:
```json
{
  "incident_id": "INC-20250423-001",
  "message_id": "MSG-002",
  "role": "assistant",
  "content": "Start by checking PgBouncer connection pool metrics...",
  "created_at": "2025-04-23T10:16:02Z"
}
```

---

### `GET /incidents/{id}`

**Response:**
```json
{
  "incident_id": "INC-20250423-001",
  "service": "payments-api",
  "severity": "P1",
  "failure_class": "latency_spike",
  "hypothesis": "Connection pool exhaustion likely cause — pool size at limit during peak traffic",
  "recommended_actions": [
    "Check PgBouncer connection pool metrics",
    "Inspect active DB connections",
    "Consider temporary pool size increase"
  ],
  "retrieval_context_available": true,
  "status": "open",
  "created_at": "2025-04-23T10:15:03Z"
}
```

---

### `GET /incidents/{id}/history`

**Response:**
```json
{
  "incident_id": "INC-20250423-001",
  "messages": [
    {
      "message_id": "MSG-001",
      "role": "user",
      "content": "What should I check first?",
      "created_at": "2025-04-23T10:16:00Z"
    },
    {
      "message_id": "MSG-002",
      "role": "assistant",
      "content": "Start by checking PgBouncer metrics...",
      "created_at": "2025-04-23T10:16:02Z"
    }
  ]
}
```

---

### `POST /incidents/{id}/resolve`

**Request** — submitted by engineer via the resolve form on the UI:
```json
{
  "actual_root_cause": "PgBouncer pool size was too small for peak traffic",
  "resolution_steps": "Increased pool size from 10 to 50, restarted PgBouncer, monitored recovery",
  "resolution_time_minutes": 23
}
```

**Response:**
```json
{
  "incident_id": "INC-20250423-001",
  "status": "resolved",
  "resolved_at": "2025-04-23T10:38:00Z"
}
```

---

### Error Response — consistent shape across all endpoints

```json
{
  "error": "triage_failed",
  "message": "Unable to classify alert after 3 retries",
  "incident_id": null,
  "timestamp": "2025-04-23T10:15:05Z"
}
```

A consistent error shape means the frontend handles all errors the same way without special-casing each endpoint.

---

## Database Schema

DynamoDB schema is designed around access patterns — not normalisation. Every table and attribute exists to serve a specific query the system makes.

**Three tables:**

| Table | PK | SK | Purpose |
|---|---|---|---|
| `Incidents` | `incident_id` | — | Incident records and resolution details |
| `ChatMessages` | `incident_id` | `message_id` | Conversation history per incident |
| `CorpusChunks` | `chunk_id` | — | Runbook and incident chunk text for RAG retrieval |

Two separate tables for incidents and chat messages rather than single-table design — single-table is a performance optimisation for very high scale that adds complexity without benefit at capstone scope.

---

### Incidents Table

Created by `POST /analyse`. Updated by `POST /incidents/{id}/resolve`.

| Attribute | Type | Notes |
|---|---|---|
| `incident_id` | String (PK) | e.g. `INC-20250423-001` |
| `service` | String | e.g. `payments-api` |
| `severity` | String | P1, P2, P3 |
| `failure_class` | String | e.g. `latency_spike` |
| `source` | String | `grafana`, `pagerduty`, `generic` |
| `alert_name` | String | e.g. `HighLatency` |
| `description` | String | Alert description |
| `hypothesis` | String | Reasoning agent root cause hypothesis |
| `recommended_actions` | List | List of action strings |
| `retrieval_context_available` | Boolean | Whether RAG retrieval succeeded |
| `status` | String | `open` or `resolved` |
| `actual_root_cause` | String | Added on resolve — confirmed by engineer |
| `resolution_steps` | String | Added on resolve — how the incident was fixed |
| `resolution_time_minutes` | Number | Added on resolve |
| `raw_payload` | Map | Original alert payload preserved |
| `created_at` | String (ISO8601) | |
| `resolved_at` | String (ISO8601) | Added on resolve |
| `eval_groundedness` | Number | Added by judge — 1-5 score |
| `eval_completeness` | Number | Added by judge — 1-5 score |
| `eval_actionability` | Number | Added by judge — 1-5 score |
| `eval_confidence` | String | Added by judge — low/medium/high |
| `eval_flags` | List | Added by judge — list of concern strings |
| `eval_ran` | Boolean | Whether judge completed successfully |

**Access pattern:** Always by `incident_id` (PK) — get, update. No secondary indexes needed.

---

### ChatMessages Table

Created by `POST /chat`. Retrieved by `GET /incidents/{id}/history` and internally by `/chat` to build conversation context.

| Attribute | Type | Notes |
|---|---|---|
| `incident_id` | String (PK) | Links message to its incident |
| `message_id` | String (SK) | e.g. `MSG-001` — sort key returns messages in order |
| `role` | String | `user` or `assistant` |
| `content` | String | Message text |
| `created_at` | String (ISO8601) | |

**Access pattern:** Query by `incident_id` (PK) to get all messages for an incident. Sort key `message_id` returns them in insertion order.

---

### CorpusChunks Table

Created by the ingestion pipeline (both static runbook ingestion and resolved incident ingestion). Retrieved by RAG after S3 Vectors returns matching chunk IDs.

| Attribute | Type | Notes |
|---|---|---|
| `chunk_id` | String (PK) | Same ID stored in S3 Vectors as reference — links vector to text |
| `document_title` | String | e.g. `kubernetes-oomkilled-runbook` |
| `document_type` | String | `runbook`, `post_mortem`, `incident_brief`, `service_catalogue` etc |
| `content` | String | Full chunk text passed to reasoning agent |
| `source` | String | File path in repo or `resolved_incident` |
| `created_at` | String (ISO8601) | |

**Access pattern:** Always by `chunk_id` (PK) — S3 Vectors returns IDs from similarity search, DynamoDB fetches the corresponding text.

**Why CorpusChunks is separate from S3 Vectors:**

S3 Vectors stores vectors for fast similarity search and returns chunk IDs — it does not store text. DynamoDB stores the chunk text keyed by those IDs. They are linked by `chunk_id`.

```
Ingestion:
  chunk text → embed → S3 Vectors (vector + chunk_id)
  chunk text → DynamoDB CorpusChunks (chunk_id + text)

Retrieval:
  query → embed → S3 Vectors similarity search → chunk_ids
  chunk_ids → DynamoDB CorpusChunks → chunk texts
  chunk texts → reasoning agent
```

S3 Vectors is the index — it tells you which chunks are relevant.
DynamoDB is the content — it gives you what those chunks say.

---

## Tech Stack

| Layer | Choice |
|---|---|
| Frontend framework | React + Vite |
| UI components | Shadcn/ui + Tailwind CSS |
| Markdown rendering | React Markdown + rehype-highlight |
| Streaming | Native fetch + ReadableStream |
| State management | Zustand |
| Data fetching | TanStack Query |
| Frontend hosting | Amazon S3 |
| Frontend access | Internal ALB (private VPC) |
| API server | FastAPI on ECS Fargate |
| Data validation | Pydantic (FastAPI built-in) |
| LLM orchestration | Native Bedrock SDK (boto3) |
| Database | DynamoDB |
| Chat model | claude-haiku-4.5 (via Bedrock) |
| Triage model | claude-haiku-4.5 (via Bedrock) |
| Reasoning model | claude-sonnet-4.6 (via Bedrock) |
| Embedding model | Cohere embed-v4 (`cohere.embed-v4:0`) (via Bedrock) |
| Notification service | Amazon SES (async via SQS + Lambda) |
| Vector store | Amazon S3 Vectors |
| Observability (infrastructure) | Amazon CloudWatch + AWS X-Ray |
| Observability (AI pipeline) | Langfuse |
| Alerting | CloudWatch Alarms |
| Authentication | AWS Cognito User Pool |
| Secrets (sensitive) | AWS Secrets Manager |
| Config (non-sensitive) | AWS Parameter Store |
| Backend testing | pytest + unittest.mock + moto |
| Frontend testing | Vitest + React Testing Library |
| Smoke / E2E testing | pytest + httpx |
| Container registry | Amazon ECR |
| Container base image | python:3.12-slim |
| IaC | Terraform (modular, S3 native locking) |
| CI/CD | GitHub Actions (OIDC auth) |
| Cloud deployment | AWS |
| Local orchestration | Docker Compose |

---

*This document is updated as decisions are made throughout the project.*

Engineers run the full system locally without connecting to real AWS services — except Bedrock. Docker Compose starts all local service replacements with a single command.

---

### Service Replacements

| Service | Local replacement | Reason |
|---|---|---|
| DynamoDB | DynamoDB Local (Docker) | Official AWS image — same API, no credentials needed |
| SQS | ElasticMQ (Docker) | Emulates SQS locally |
| S3 Vectors | Mocked via env flag | No local emulator exists yet |
| Bedrock | Real AWS | See decision below |
| SES | Log to console | No emails sent locally |
| Cognito | Disabled via env flag | No auth enforced locally |

---

### Bedrock in Local Dev

**Decision: Real Bedrock calls with AWS credentials in `.env.local`**

Mocking Bedrock responses was considered — it would remove the need for AWS credentials locally and cost nothing. It was ruled out because mocked responses hide an entire class of bugs that only surface when hitting the real model. The cost of real Bedrock calls during local development is negligible — a few cents per dev session. Engineers configure credentials once in `.env.local` which is never committed to the repo.

---

### Docker Compose

```yaml
services:
  fastapi:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env.local
    depends_on:
      - dynamodb-local
      - elasticmq

  dynamodb-local:
    image: amazon/dynamodb-local
    ports:
      - "8001:8000"

  elasticmq:
    image: softwaremill/elasticmq
    ports:
      - "9324:9324"
```

The React frontend runs separately via the Vite dev server:
```bash
npm run dev    # starts on http://localhost:3000
```

Start all backend services:
```bash
docker compose up
```

---

### Local Environment Configuration

`.env.local` — never committed to the repo:

```bash
ENVIRONMENT=local
AWS_REGION=us-east-1
DYNAMODB_ENDPOINT=http://dynamodb-local:8001
SQS_ENDPOINT=http://elasticmq:9324
S3_VECTORS_MOCK=true
SES_MODE=log
AUTH_DISABLED=true
AWS_ACCESS_KEY_ID=<real credentials for Bedrock>
AWS_SECRET_ACCESS_KEY=<real credentials for Bedrock>
```

`ENVIRONMENT=local` tells FastAPI to:
- Use local DynamoDB and SQS endpoints
- Mock S3 Vectors retrieval — returns hardcoded sample chunks
- Log emails to console instead of calling SES
- Skip Cognito auth — all requests treated as authenticated

The same Docker image runs in dev and prod — behaviour is controlled entirely by environment variables injected at runtime.

---

### Database Seeding

On first run, a setup script creates DynamoDB tables locally and seeds sample data:

```bash
python scripts/seed_local.py
```

This script:
- Creates `Incidents`, `ChatMessages`, `CorpusChunks` tables in DynamoDB Local
- Seeds `CorpusChunks` with a sample set of runbook chunks so RAG retrieval returns meaningful results
- Seeds a sample past incident for testing the resolve flow end to end

---

### Local Dev Summary

| Component | How it runs locally |
|---|---|
| FastAPI | Docker container via Docker Compose |
| React | Vite dev server (`npm run dev`) |
| DynamoDB | DynamoDB Local (Docker) |
| SQS | ElasticMQ (Docker) |
| S3 Vectors | Mocked via `S3_VECTORS_MOCK=true` |
| Bedrock | Real AWS — credentials in `.env.local` |
| SES | Logs to console via `SES_MODE=log` |
| Cognito | Disabled via `AUTH_DISABLED=true` |

---

## Tech Stack

| Layer | Choice |
|---|---|
| Frontend framework | React + Vite |
| UI components | Shadcn/ui + Tailwind CSS |
| Markdown rendering | React Markdown + rehype-highlight |
| Streaming | Native fetch + ReadableStream |
| State management | Zustand |
| Data fetching | TanStack Query |
| Frontend hosting | Amazon S3 |
| Frontend access | Internal ALB (private VPC) |
| API server | FastAPI on ECS Fargate |
| Data validation | Pydantic (FastAPI built-in) |
| LLM orchestration | Native Bedrock SDK (boto3) |
| Database | DynamoDB |
| Chat model | claude-haiku-4.5 (via Bedrock) |
| Triage model | claude-haiku-4.5 (via Bedrock) |
| Reasoning model | claude-sonnet-4.6 (via Bedrock) |
| Embedding model | Cohere embed-v4 (`cohere.embed-v4:0`) (via Bedrock) |
| Notification service | Amazon SES (async via SQS + Lambda) |
| Vector store | Amazon S3 Vectors |
| Observability (infrastructure) | Amazon CloudWatch + AWS X-Ray |
| Observability (AI pipeline) | Langfuse |
| Alerting | CloudWatch Alarms |
| Authentication | AWS Cognito User Pool |
| Secrets (sensitive) | AWS Secrets Manager |
| Config (non-sensitive) | AWS Parameter Store |
| Backend testing | pytest + unittest.mock + moto |
| Frontend testing | Vitest + React Testing Library |
| Smoke / E2E testing | pytest + httpx |
| Container registry | Amazon ECR |
| Container base image | python:3.12-slim |
| IaC | Terraform (modular, S3 native locking) |
| CI/CD | GitHub Actions (OIDC auth) |
| Cloud deployment | AWS |
| Local orchestration | Docker Compose |

---

## IAM Design

**Core principle: least privilege** — every component gets exactly the permissions it needs for its role. No component shares an IAM role with another unless they have identical permission needs.

---

### IAM Identities

| Component | Identity type |
|---|---|
| ECS Fargate (FastAPI) | IAM Task Role — attached to the ECS task |
| Lambda (notification) | IAM Execution Role — attached to the Lambda function |
| Lambda (corpus ingestion) | IAM Execution Role — attached to the Lambda function |
| GitHub Actions | IAM Role — assumed via OIDC federation per pipeline run |
| Terraform | IAM Role — assumed by engineer or CI/CD running Terraform |

---

### ECS Task Role (FastAPI)

FastAPI talks to the most services — this role is scoped tightly to only what each action requires.

| Permission | Service | Why |
|---|---|---|
| `bedrock:InvokeModel` | Bedrock | Call triage, chat, and reasoning models |
| `dynamodb:GetItem` | DynamoDB | Read incident briefs and chat history |
| `dynamodb:PutItem` | DynamoDB | Write incident briefs and chat messages |
| `dynamodb:UpdateItem` | DynamoDB | Update incident record on resolve |
| `dynamodb:Query` | DynamoDB | Fetch chat history by `incident_id` |
| `s3vectors:QueryVectors` | S3 Vectors | RAG similarity search |
| `sqs:SendMessage` | SQS (notification queue) | Drop notification message after analysis |
| `sqs:SendMessage` | SQS (ingestion queue) | Drop corpus ingestion message after resolve |
| `secretsmanager:GetSecretValue` | Secrets Manager | Fetch Langfuse API key |
| `ssm:GetParameter` | Parameter Store | Fetch non-sensitive config |

FastAPI does **not** have: `s3:*`, `ses:*`, `lambda:*`, `iam:*`

---

### Lambda Execution Role — Notification

| Permission | Service | Why |
|---|---|---|
| `sqs:ReceiveMessage` | SQS (notification queue only) | Pick up notification messages |
| `sqs:DeleteMessage` | SQS (notification queue only) | Remove message after processing |
| `sqs:GetQueueAttributes` | SQS (notification queue only) | Read queue metadata |
| `ses:SendEmail` | SES | Send notification email to engineer |
| `ssm:GetParameter` | Parameter Store | Fetch SES sender address |

---

### Lambda Execution Role — Corpus Ingestion

| Permission | Service | Why |
|---|---|---|
| `sqs:ReceiveMessage` | SQS (ingestion queue only) | Pick up ingestion messages |
| `sqs:DeleteMessage` | SQS (ingestion queue only) | Remove message after processing |
| `sqs:GetQueueAttributes` | SQS (ingestion queue only) | Read queue metadata |
| `dynamodb:GetItem` | DynamoDB | Fetch resolved incident record |
| `dynamodb:PutItem` | DynamoDB | Write corpus chunks |
| `bedrock:InvokeModel` | Bedrock | Generate embeddings via Cohere embed-v4 (`cohere.embed-v4:0`) |
| `s3vectors:PutVectors` | S3 Vectors | Store new vectors after ingestion |

---

### GitHub Actions Role

Assumed via OIDC — short-lived token per pipeline run. No long-lived credentials stored.

| Permission | Service | Why |
|---|---|---|
| `ecr:GetAuthorizationToken` | ECR | Authenticate Docker push |
| `ecr:BatchCheckLayerAvailability` | ECR | Push Docker image layers |
| `ecr:PutImage` | ECR | Push final image |
| `ecs:UpdateService` | ECS | Force new deployment after image push |
| `ecs:DescribeServices` | ECS | Verify deployment health |
| `s3:PutObject` | S3 | Sync frontend build to S3 bucket |
| `s3:DeleteObject` | S3 | Remove stale frontend files |
| `s3:ListBucket` | S3 | List existing files for sync |

---

### Terraform Role

Broader than other roles — its job is to provision all infrastructure. Only assumed by trusted principals (engineers, CI/CD). Never attached to a running application.

Scoped to specific services: `ec2`, `ecs`, `ecr`, `dynamodb`, `s3`, `sqs`, `lambda`, `iam`, `bedrock`, `cognito-idp`, `secretsmanager`, `ssm`, `cloudwatch`, `xray`

---

### Resource-level Scoping

All policies scope to specific resource ARNs — not wildcards. Example for ECS task role DynamoDB permissions:

```json
{
  "Resource": [
    "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/Incidents",
    "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/ChatMessages",
    "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/CorpusChunks"
  ]
}
```

Not `arn:aws:dynamodb:*:*:table/*` — that would allow access to any DynamoDB table in the account.

---

### SQS Queue Separation

Two separate SQS queues with separate permissions:

| Queue | Who writes | Who reads |
|---|---|---|
| Notification queue | FastAPI (`SendMessage`) | Notification Lambda (`ReceiveMessage`, `DeleteMessage`) |
| Corpus ingestion queue | FastAPI (`SendMessage`) | Ingestion Lambda (`ReceiveMessage`, `DeleteMessage`) |

Each Lambda only has permission to its own queue. FastAPI has `SendMessage` on both but `ReceiveMessage` on neither.

---

## VPC & Networking

---

### Structure

```
VPC (10.0.0.0/16)
    │
    ├── Public Subnets (2 AZs)
    │     ├── us-east-1a: 10.0.1.0/24   ← ALB, NAT Gateway
    │     └── us-east-1b: 10.0.2.0/24   ← ALB
    │
    └── Private Subnets (2 AZs)
          ├── us-east-1a: 10.0.3.0/24   ← ECS Fargate, Lambda
          └── us-east-1b: 10.0.4.0/24   ← ECS Fargate, Lambda
```

Two AZs for basic high availability — if one AZ goes down, the ALB routes traffic to the other and ECS runs tasks in the surviving AZ.

---

### Outbound Traffic — VPC Endpoints + NAT Gateway

ECS Fargate tasks run in private subnets with no public IP. They need to reach AWS services (Bedrock, ECR, DynamoDB, SQS, S3, Secrets Manager, Parameter Store, CloudWatch, X-Ray).

**Decision: VPC Endpoints for AWS services + NAT Gateway as fallback**

| | NAT Gateway | VPC Endpoints |
|---|---|---|
| Cost | ~$0.045/hr + data transfer | ~$0.01/hr per endpoint |
| Covers | Everything (internet + AWS) | AWS services only |
| Security | Traffic leaves VPC | Traffic stays within AWS network |

VPC Endpoints are created for all AWS services FastAPI and Lambda need — traffic stays within the AWS network and never traverses the public internet. A NAT Gateway is retained for any outbound traffic not covered by endpoints.

**VPC Endpoints provisioned:** Bedrock, ECR, S3, DynamoDB, SQS, Secrets Manager, Parameter Store, CloudWatch, X-Ray

---

### Security Groups

| Resource | Inbound | Outbound |
|---|---|---|
| ALB | 443 from VPC CIDR | All to ECS security group |
| ECS Fargate | 8000 from ALB security group only | All (to AWS services via VPC endpoints) |
| Lambda | No inbound | All (to DynamoDB, SQS, SES, S3 Vectors) |

---

## ECS Task Sizing

FastAPI makes sequential Bedrock API calls and waits for responses — the heavy compute runs on Bedrock's side. The container needs enough memory to hold concurrent requests in flight but is not CPU-intensive.

| Environment | CPU | Memory | Min tasks | Max tasks |
|---|---|---|---|---|
| Dev | 512 (0.5 vCPU) | 1024 MB | 1 | 1 |
| Prod | 1024 (1 vCPU) | 2048 MB | 1 | 3 |

ECS Application Auto Scaling adds tasks in prod when CPU utilisation exceeds 70%. For a small on-call team, 1 task handles normal load and scales to 3 under an alert storm.

---

## DynamoDB Capacity Mode

**Decision: On-demand for all tables in both environments**

| | On-demand | Provisioned |
|---|---|---|
| Capacity planning | None | Required |
| Throttling risk | None | Yes, if under-provisioned |
| Cost at low traffic | Pay per request | Cheaper with consistent traffic |
| Capstone suitable | ✅ | ⚠️ |

Traffic is unpredictable and low — incidents fire occasionally, not constantly. On-demand removes capacity planning entirely, never throttles, and charges only for what is used. Applies to `Incidents`, `ChatMessages`, and `CorpusChunks` tables in both dev and prod.

---

## Logging Strategy

**Tool: `structlog` (Python) — JSON structured logging**

Plain text logs are hard to query in CloudWatch. JSON logs can be filtered and searched by field in CloudWatch Logs Insights. `structlog` adds structured JSON logging to FastAPI with minimal setup.

**Log entry shape:**

```json
{
  "timestamp": "2025-04-23T10:15:03Z",
  "level": "INFO",
  "environment": "prod",
  "service": "cognis",
  "incident_id": "INC-20250423-001",
  "stage": "triage",
  "message": "Triage classification completed",
  "duration_ms": 823,
  "metadata": {}
}
```

`incident_id` and `stage` are the key fields — they let you filter all logs for a specific incident and pinpoint exactly which pipeline stage produced a log entry.

**Log levels:**

| Environment | Level | Why |
|---|---|---|
| Dev | DEBUG | Full visibility during development |
| Prod | INFO | Normal operations captured without noise — WARNING and ERROR automatically included |

**Log retention:**

| Environment | Retention | Why |
|---|---|---|
| Dev | 7 days | Dev logs are for active debugging only |
| Prod | 30 days | Long enough to investigate incidents and audit |

---

## ECR Image Lifecycle Policy

**Tagging strategy: Git commit SHA + `latest`**

Every image is tagged with its Git commit SHA and `latest`. The SHA tag makes every image traceable to the exact commit that produced it. ECS pulls `latest` on deploy — rollback is done by pointing ECS to a specific SHA tag.

When a new image is pushed, `latest` moves to the new image. The old image retains its SHA tag and is never untagged — it remains protected and counts toward the 10-image retention limit.

**Two lifecycle rules:**

| Rule | What it does |
|---|---|
| Keep last 10 tagged images | Oldest SHA-tagged image deleted when count exceeds 10 — sufficient rollback history |
| Delete untagged images after 1 day | Cleans up images that end up with no tags due to edge cases in failed pushes |

```json
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Keep last 10 images",
      "selection": {
        "tagStatus": "tagged",
        "tagPrefixList": [""],
        "countType": "imageCountMoreThan",
        "countNumber": 10
      },
      "action": { "type": "expire" }
    },
    {
      "rulePriority": 2,
      "description": "Delete untagged images after 1 day",
      "selection": {
        "tagStatus": "untagged",
        "countType": "sinceImagePushed",
        "countUnit": "days",
        "countNumber": 1
      },
      "action": { "type": "expire" }
    }
  ]
}
```

---

*This document is updated as decisions are made throughout the project.*

## Project Structure

---

### Top Level

```
cognis/
    │
    ├── backend/                 # FastAPI application
    ├── frontend/                # React + Vite application
    ├── terraform/               # Infrastructure as Code
    ├── runbooks/                # RAG corpus — Markdown documents
    ├── scripts/                 # Utility scripts (seeding, ingestion)
    ├── .github/                 # GitHub Actions workflows
    ├── .env.local.example       # Template for local env config (committed)
    ├── .gitignore
    ├── docker-compose.yml       # Local development orchestration
    └── README.md
```

---

### Backend

```
backend/
    ├── app/
    │     ├── main.py                  # FastAPI app entry point, middleware, CORS
    │     ├── config.py                # Settings loaded from env vars / Parameter Store
    │     │
    │     ├── api/                     # Endpoint route handlers
    │     │     ├── analyse.py         # POST /analyse
    │     │     ├── chat.py            # POST /chat
    │     │     ├── incidents.py       # GET /incidents/{id}, GET /incidents/{id}/history
    │     │     ├── resolve.py         # POST /incidents/{id}/resolve
    │     │     └── health.py          # GET /health
    │     │
    │     ├── pipeline/                # Core AI pipeline stages
    │     │     ├── normaliser.py      # Alert payload normalisation (Grafana, PagerDuty, generic)
    │     │     ├── triage.py          # Triage classifier — Bedrock Haiku
    │     │     ├── retrieval.py       # RAG retrieval — S3 Vectors + DynamoDB
    │     │     └── agent.py           # Reasoning agent — Bedrock Sonnet
    │     │
    │     ├── models/                  # Pydantic schemas
    │     │     ├── alert.py           # Incoming alert payload schemas (Grafana, PagerDuty)
    │     │     ├── incident.py        # Incident record schema
    │     │     ├── chat.py            # Chat request/response schemas
    │     │     └── resolve.py         # Resolution request/response schemas
    │     │
    │     ├── services/                # External service integrations
    │     │     ├── bedrock.py         # Bedrock client wrapper
    │     │     ├── dynamodb.py        # DynamoDB read/write operations
    │     │     ├── s3vectors.py       # S3 Vectors similarity search
    │     │     └── sqs.py             # SQS message publishing
    │     │
    │     └── notifications/           # Lambda handlers (deployed separately)
    │           ├── notify.py          # SES email composition and sending
    │           └── ingest.py          # Corpus ingestion from resolved incidents
    │
    ├── tests/
    │     ├── unit/
    │     │     ├── test_normaliser.py
    │     │     ├── test_triage.py
    │     │     ├── test_retrieval.py
    │     │     └── test_agent.py
    │     ├── integration/
    │     │     ├── test_analyse_pipeline.py
    │     │     ├── test_chat_pipeline.py
    │     │     └── test_resolve_flow.py
    │     └── smoke/
    │           └── test_endpoints.py
    │
    ├── Dockerfile
    ├── requirements.txt
    └── .dockerignore
```

Pipeline stages are explicit — `normaliser`, `triage`, `retrieval`, `agent` are separate files, not one large function. Services are isolated — Bedrock, DynamoDB, S3 Vectors, SQS each have their own wrapper in `services/` so swapping one out does not touch pipeline logic.

---

### Frontend

```
frontend/
    ├── src/
    │     ├── main.tsx
    │     ├── App.tsx                  # Root component, routing
    │     │
    │     ├── pages/
    │     │     ├── IncidentPage.tsx   # Incident brief + chat UI
    │     │     └── NotFoundPage.tsx
    │     │
    │     ├── components/
    │     │     ├── IncidentBrief.tsx  # Renders incident brief card
    │     │     ├── ChatWindow.tsx     # Streaming chat interface
    │     │     ├── ChatMessage.tsx    # Individual message with Markdown rendering
    │     │     ├── ResolveModal.tsx   # Mark as Resolved form
    │     │     └── StatusBadge.tsx    # Open / Resolved badge
    │     │
    │     ├── hooks/
    │     │     ├── useIncident.ts     # TanStack Query — fetch incident by ID
    │     │     ├── useHistory.ts      # TanStack Query — fetch chat history
    │     │     └── useChat.ts         # Streaming chat via fetch + ReadableStream
    │     │
    │     ├── store/
    │     │     └── incidentStore.ts   # Zustand — incident state shared across components
    │     │
    │     ├── lib/
    │     │     └── api.ts             # API base URL, shared fetch helpers
    │     │
    │     └── types/
    │           └── index.ts           # Incident, Message, Resolution TypeScript types
    │
    ├── index.html
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── tsconfig.json
    └── package.json
```

---

### Terraform

```
terraform/
    ├── modules/
    │     ├── networking/              # VPC, subnets, ALB, NAT Gateway, VPC Endpoints
    │     ├── compute/                 # ECS cluster, Fargate service, ECR
    │     ├── storage/                 # S3 buckets, DynamoDB tables, S3 Vectors
    │     ├── messaging/               # SQS queues, Lambda functions, DLQ
    │     ├── ai/                      # Bedrock IAM roles and policies
    │     ├── auth/                    # Cognito User Pool, ALB auth rules
    │     ├── secrets/                 # Secrets Manager, Parameter Store
    │     └── observability/           # CloudWatch dashboards, alarms, X-Ray
    │
    └── environments/
          ├── dev/
          │     ├── main.tf            # References modules with dev variable values
          │     ├── variables.tf
          │     ├── outputs.tf
          │     └── backend.tf         # S3 native locking backend config for dev
          └── prod/
                ├── main.tf
                ├── variables.tf
                ├── outputs.tf
                └── backend.tf
```

Each Terraform module owns one concern and maps directly to an architecture decision — networking, compute, storage, messaging, AI, auth, secrets, observability.

---

### Runbooks

```
runbooks/
    ├── kubernetes/
    │     ├── oomkilled.md
    │     ├── crashloopbackoff.md
    │     ├── pod-eviction.md
    │     └── node-pressure.md
    ├── redis/
    │     ├── connection-failure.md
    │     ├── memory-limits.md
    │     └── replication-lag.md
    ├── postgres/
    │     ├── connection-pool-exhaustion.md
    │     ├── replication.md
    │     └── slow-queries.md
    ├── post-mortems/
    │     └── sample-incident-001.md
    ├── sre-general/
    │     ├── latency-spikes.md
    │     └── cascading-failures.md
    └── org-specific/
          ├── service-catalogue.md
          ├── alert-definitions.md
          ├── on-call-playbook.md
          └── known-issues.md
```

Changes to any file in `/runbooks/**` automatically trigger the corpus ingestion pipeline via GitHub Actions on merge to main.

---

### Scripts

```
scripts/
    ├── seed_local.py                  # Creates DynamoDB tables + seeds sample data locally
    └── ingest_corpus.py               # Ingestion pipeline — chunks, embeds, stores
                                       # --files <paths>  re-embeds specific changed files (CI/CD)
                                       # --all            re-embeds entire corpus (initial load)
```

`ingest_corpus.py` is called in two contexts — by CI/CD with `--files` to re-embed only changed runbooks, and manually with `--all` for the initial corpus load.

---

### GitHub Actions

```
.github/
    └── workflows/
          ├── backend.yml              # Test + build + deploy backend
          ├── frontend.yml             # Test + build + deploy frontend
          ├── terraform.yml            # Plan on PR, apply on merge
          └── corpus.yml               # Triggers on /runbooks/** changes — runs ingest_corpus.py
```

**`corpus.yml` flow:**

```
Changes to /runbooks/** on merge to main
    │
    ▼
Identify changed files via git diff
    │
    ▼
python scripts/ingest_corpus.py --files <changed files>
    │
    ▼
Re-embeds only changed files → S3 Vectors + DynamoDB
```

---

## Decisions To Revisit

The following were identified as relevant but deferred — they will not block the initial build and can be decided when the system is stable.

---

### S3 Bucket Versioning & Lifecycle Policies

Versioning is already required on the Terraform state bucket (native S3 locking depends on it). The remaining buckets — frontend and any corpus file storage — have not had versioning or lifecycle policies defined. Without lifecycle policies, old object versions accumulate over time and storage costs grow. To be decided: which buckets need versioning, and how long old versions are retained before expiry.

---

### Cognito Token Expiry

Cognito JWT token expiry was not explicitly configured. JWTs that never expire are a security risk — a stolen token remains valid indefinitely. To be decided: access token lifetime (standard default is 1 hour) and refresh token lifetime (standard default is 30 days). These are set in the Cognito User Pool client configuration.

---

### DynamoDB TTL (Time to Live)

Incidents and chat messages will accumulate in DynamoDB indefinitely without a TTL policy. DynamoDB's built-in TTL feature automatically deletes items after a configurable period at no extra cost. To be decided: whether old incidents expire and after how long (e.g. 90 days), and whether chat messages follow the same or a shorter retention window.

## Extensibility — Plugin / Strategy Pattern

The backend is designed for extension without modification — new notification channels (Slack, Teams) and new alert source normalisers (Datadog, OpsGenie) can be added by implementing a defined contract, with zero changes to existing code.

**Decision: Provider Pattern with Registry**

Two extension points are defined:

**Notification providers** — any channel that delivers incident notifications to engineers.
**Alert normalisers** — any source format that can be converted to the internal `NormalisedAlert` schema.

Each extension point has:
- An abstract base class in `providers/base.py` defining the contract
- Concrete implementations in `providers/notifications/` and `providers/normalisers/`
- A registry in `registry/` that holds all available providers and selects the correct one at runtime

**Adding a new notification channel (e.g. Slack):**
1. Create `providers/notifications/slack.py` implementing `NotificationProvider`
2. Register it in `notification_registry.py`
3. Set `ACTIVE_NOTIFICATION_PROVIDERS=ses,slack` in config
No existing code changes.

**Adding a new alert source (e.g. Datadog):**
1. Create `providers/normalisers/datadog.py` implementing `AlertNormaliser`
2. Register it in `normaliser_registry.py`
No existing code changes.

**Notification registry** — driven by config (`ACTIVE_NOTIFICATION_PROVIDERS`). Multiple providers can be active simultaneously — the same incident brief is sent to all active channels.

**Normaliser registry** — driven by payload detection. Each normaliser implements `can_handle(payload)`. The registry iterates through normalisers in order, the first match wins. `GenericNormaliser` is always last as the fallback.

**Does the frontend need this?** No. The frontend is a consumer of the API, not a provider of integrations. Extensibility lives entirely in the backend.


---

## Reasoning Agent — Agent with Tools

**Decision: True agent with tools via Bedrock native tool use**

A pure LLM call was considered — pass triage output and retrieved docs to the model and return a structured brief. This was ruled out because RAG retrieval provides only static knowledge. Diagnosing a live incident requires dynamic information the model cannot reason over without actively fetching it.

Claude Sonnet-4 runs as a true agent that decides which tools to call, in what order, and when to stop and produce the brief. The agent loop runs until the model produces its final output — typically 2-5 tool calls per incident.

**Four tools:**

| Tool | What it fetches | Real production source | Capstone |
|---|---|---|---|
| `get_metrics` | CPU, memory, latency, error rate, DB connections for the affected service | Monitoring API (Datadog, Grafana, CloudWatch) | Mock function returning canned data keyed by service |
| `get_deployment_history` | Recent deployments for the affected service | Deployment system (ArgoCD, GitHub releases) | Mock function |
| `search_incident_history` | Past incidents for the same service | DynamoDB incident records | Real DynamoDB query |
| `get_service_dependencies` | What services the affected service depends on | Service catalogue in corpus | Real corpus lookup |

**On alert payloads and metrics:**

The alert payload from Grafana or PagerDuty contains what breached (alert name, threshold, service, severity) — it does not contain the full metrics picture. CPU, memory, error rate, and latency trends require a separate call to the monitoring tool's API. `get_metrics` exists to fetch this dynamic signal. For the capstone, mock data is designed to tell a consistent story — if the alert is connection pool exhaustion, the mock metrics show active connections near the pool limit.

**Future improvement:** Replace each mock tool function with a real API call to the appropriate monitoring or deployment tool. The tool interface stays the same — only the implementation changes. This follows the same provider pattern as notification channels and alert normalisers.

**Tool calling implementation:** Tools are defined as JSON schemas passed to Bedrock. The Bedrock response indicates which tool to call and with what arguments. The agent loop calls the tool, passes the result back to the model, and continues until the model produces its final structured brief.

---

## RAG Retrieval Evaluation

**Evaluation dataset:** 20-30 query/answer pairs manually created — each query maps to a known relevant chunk in the corpus.

**Metrics:**

| Metric | What it measures | Target |
|---|---|---|
| Recall@3 | Does the relevant chunk appear in top 3 results? | > 80% |
| MRR (Mean Reciprocal Rank) | How high does the relevant chunk rank on average? | > 0.7 |
| NDCG@3 | Quality of the full ranked list considering position | > 0.75 |

**Ingestion verification (before retrieval evaluation):**

| Check | How |
|---|---|
| All documents ingested | Count chunks in DynamoDB CorpusChunks vs expected count from source files |
| Chunks are semantically coherent | Manual inspection — each chunk makes sense standalone |
| No important context split across boundaries | Inspect chunk boundaries around key runbook sections |
| Embedding captures technical meaning | Run known-related queries and verify results are semantically sensible |

Evaluation runs before and after adding reranking to quantify the improvement in retrieval quality.

---

## Reasoning Agent Output Evaluation

Four dimensions evaluated for every benchmark incident:

| Dimension | How measured | Target |
|---|---|---|
| Structural correctness | Pydantic validation — all required fields present, correct types | 100% |
| Factual grounding (citation rate) | What percentage of hypothesis statements trace back to a retrieved chunk | > 80% |
| Diagnostic accuracy (root cause hit rate) | 10 benchmark incidents with known ground truth root causes — does agent identify the correct root cause? | > 70% |
| Hallucination detection | Recommended actions that appear nowhere in retrieved runbooks — flagged as hallucinated | < 10% |

**Benchmark incident set:** 10 scenarios with known root causes covering the main failure classes — connection pool exhaustion, OOMKilled, replication lag, latency spike, cascading dependency failure.

---

## RAG Optimisation — Reranking

**Decision: Cohere Rerank 3.5 via Bedrock Rerank API**

Standard vector similarity search returns the top-K chunks by semantic closeness — not by true relevance to the specific incident. A chunk can be semantically similar but not actually useful for diagnosing the alert. Reranking adds a second pass that reorders candidates by true relevance.

**Updated retrieval flow:**
```
Query (triage output)
    │
    ▼
Embed query → Cohere embed-v4 (`cohere.embed-v4:0`) (Bedrock)
    │
    ▼
S3 Vectors similarity search → top 20 candidates
    │
    ▼
Cohere Rerank 3.5 (Bedrock Rerank API) → scored and reordered
    │
    ▼
Top 5 highest-scoring chunks → reasoning agent
```

Retrieving 20 candidates and reranking to 5 ensures the agent reasons over the most relevant context rather than the most semantically similar. The difference matters for technical content where subtle phrasing differences can affect similarity scores.

**Cohere Rerank 3.5 on Bedrock:** Available in `us-east-1` (Cohere Rerank 3.5 is the only rerank model supported in this region). Charged per query where a query contains up to 100 document chunks — at 20 candidates per incident the cost per rerank call is negligible.

**Reranking IAM permission:** `bedrock:Rerank` on Cohere Rerank 3.5 model ARN — added to ECS task role.

---

## Retrieval Evaluation — When and Where It Runs

Retrieval evaluation is a quality assurance concern — not a runtime concern. It answers whether the RAG pipeline retrieves the right documents. It runs in two contexts only:

| Context | How | When |
|---|---|---|
| Local development | `python scripts/evaluate_retrieval.py` manually | After initial corpus load, after adding new runbooks |
| CI/CD (corpus.yml) | Automatic after ingestion | Every time runbooks change and are merged to main |
| Prod at runtime | Never | Not applicable |

**CI/CD integration:** After `ingest_corpus.py --files` completes, `evaluate_retrieval.py --threshold 0.8` runs against the dev environment. If Recall@3 drops below 0.8 the workflow fails — the corpus change must be investigated before it affects the running system. Evaluation scores are posted as a GitHub Actions workflow summary for visibility.

**Agent output evaluation** follows the same principle — run manually during development and after significant changes to the pipeline. Never runs at runtime.

**evaluate_retrieval.py flags:**
- `--threshold` — exit non-zero if Recall@3 drops below this value (used in CI/CD)
- `--disable-rerank` — run without reranking for comparison baseline
- Outputs `evaluation_report.json` with per-query scores and aggregate metrics

**evaluate_agent.py:**
- Run manually against dev environment after Task 28 (retrieval evaluation) is complete
- Outputs per-scenario scores and aggregate metrics for four dimensions
- Not integrated into CI/CD — agent quality is harder to automate than retrieval quality

---

## Runtime Agent Evaluation — LLM as Judge

**Decision: Silent observer using claude-haiku-4.5 as judge**

Agent output is evaluated at runtime after every `/analyse` call. The judge runs asynchronously — it never blocks the incident brief being returned to the caller or the engineer being notified.

**What is evaluated:**

| Dimension | Question | Scale |
|---|---|---|
| Groundedness | Is the hypothesis supported by the retrieved context? | 1-5 |
| Completeness | Are all required fields present and substantive? | 1-5 |
| Actionability | Are recommended actions specific and executable? | 1-5 |
| Confidence | How certain is the agent about its hypothesis? | low/medium/high |
| Flags | Any concerns — hallucination, vague actions, missing context | List |

**Judge model: claude-haiku-4.5**
Fast, cheap, consistent structured scoring. The evaluation task does not require deep reasoning — Haiku is sufficient.

**Judge runs async after agent, before storage:**
```
Reasoning agent → IncidentBrief
    │
    ▼
LLM Judge (async, non-blocking)
Scores attached to IncidentBrief
    │
    ▼
Store enriched record in DynamoDB
    │
    ├──→ Return brief to caller (no scores exposed)
    └──→ SQS notification
```

**Judge output is internal only — never exposed to frontend or engineer.**
The engineer receives the brief without quality scores. Scores exist solely for internal monitoring and improvement.

**DynamoDB schema additions to Incidents table:**

| Attribute | Type | Notes |
|---|---|---|
| `eval_groundedness` | Number | 1-5 score |
| `eval_completeness` | Number | 1-5 score |
| `eval_actionability` | Number | 1-5 score |
| `eval_confidence` | String | low/medium/high |
| `eval_flags` | List | List of concern strings |
| `eval_ran` | Boolean | Whether evaluation completed successfully |

**Error handling:**
Judge failure never blocks the incident brief. If the Bedrock call for the judge fails:
- Log failure to CloudWatch
- Set `eval_ran = false` on the incident record
- Return brief to engineer without scores
- No retry — the brief is more important than the evaluation

**Observability:**
- All judge calls traced in Langfuse automatically
- Aggregate scores logged as CloudWatch custom metrics:
  - Average groundedness score per day
  - Percentage of briefs with `eval_confidence = low`
  - Percentage of briefs with flags
- Trending scores signal pipeline quality changes over time

**`GET /incidents/{id}` response:** Evaluation scores are stored in DynamoDB but not included in the API response — they are internal monitoring data only.

**Future improvement — Quality gate with retry:**
If judge scores are critically low (e.g. groundedness < 2), the system retries the agent with a modified prompt — additional instructions to ground its reasoning more explicitly in the retrieved context. The engineer still receives a brief but the system attempts to improve it first. This requires sufficient judge data to establish what threshold actually indicates a bad brief before implementing.

---

## Verified Active Bedrock Model IDs

Model IDs verified against AWS Bedrock documentation as of April 2026. Update these in AWS Parameter Store and config.py if they change.

| Role | Model | Bedrock Model ID | EOL |
|---|---|---|---|
| Reasoning agent | Claude Sonnet 4.6 | `anthropic.claude-sonnet-4-6` | N/A |
| Chat | Claude Haiku 4.5 | `anthropic.claude-haiku-4-5-20251001-v1:0` | N/A |
| Triage | Claude Haiku 4.5 | `anthropic.claude-haiku-4-5-20251001-v1:0` | N/A |
| Judge | Claude Haiku 4.5 | `anthropic.claude-haiku-4-5-20251001-v1:0` | N/A |
| Embedding | Cohere Embed v4 | `cohere.embed-v4:0` | N/A |
| Reranking | Cohere Rerank 3.5 | `cohere.rerank-v3-5:0` | N/A |

**Embedding dimensions:** Cohere Embed v4 supports configurable dimensions (256–1536). Set `dimensions=1024` to match the S3 Vectors index. Changing dimensions requires re-creating the index and re-embedding the entire corpus.

**Migrated from:**
- `us.anthropic.claude-3-5-sonnet-20241022-v2:0` → reached EOL, replaced by `anthropic.claude-sonnet-4-6`
- `anthropic.claude-haiku-3-5-20241022-v1:0` → replaced by `anthropic.claude-haiku-4-5-20251001-v1:0`
- `cohere.embed-english-v3` → replaced by `cohere.embed-v4:0` (larger context window, configurable dimensions)

**How to verify model status:** AWS Bedrock Console → Model Catalog → filter by provider. Active models show no EOL date. Or run:
```bash
aws bedrock list-foundation-models --by-provider anthropic --region us-east-1 \
  --query 'modelSummaries[?modelLifecycle.status==`ACTIVE`].[modelId,modelName]' \
  --output table
```
