"""Seed DynamoDB Local with tables and sample data for local development."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

DYNAMODB_ENDPOINT = os.getenv("DYNAMODB_ENDPOINT", "http://localhost:8001")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# DynamoDB Local accepts any non-empty credentials
_resource = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    endpoint_url=DYNAMODB_ENDPOINT,
    aws_access_key_id="local",
    aws_secret_access_key="local",
)


# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

TABLE_SCHEMAS = [
    {
        "TableName": "Incidents",
        "KeySchema": [{"AttributeName": "incident_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "incident_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "ChatMessages",
        "KeySchema": [
            {"AttributeName": "incident_id", "KeyType": "HASH"},
            {"AttributeName": "message_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "incident_id", "AttributeType": "S"},
            {"AttributeName": "message_id", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "CorpusChunks",
        "KeySchema": [{"AttributeName": "chunk_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "chunk_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": "Counters",
        "KeySchema": [{"AttributeName": "counter_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "counter_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    },
]


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc).isoformat()

SAMPLE_INCIDENT = {
    "incident_id": "INC-20260423-001",
    "title": "High error rate on payments-service",
    "summary": (
        "Payments service is returning 5xx errors at 18% of requests. "
        "Root cause appears to be exhausted DB connection pool following a "
        "deploy at 14:32 UTC. Downstream checkout and order services are degraded."
    ),
    "severity": "critical",
    "affected_service": "payments-service",
    "failure_class": "resource-exhaustion",
    "status": "open",
    "recommended_actions": [
        "Increase DB connection pool size via APP_DB_POOL_MAX env var and redeploy",
        "Check for long-running transactions holding connections",
        "Scale payments-service task count to shed load while investigating",
    ],
    "runbook_references": [
        "runbooks/payments-service.md",
        "runbooks/database-connection-pool.md",
    ],
    "retrieval_context_available": True,
    "created_at": NOW,
    "resolved_at": None,
    "resolution_notes": None,
    "resolved_by": None,
}

SAMPLE_CHAT_MESSAGES = [
    {
        "incident_id": "INC-20260423-001",
        "message_id": "MSG-001",
        "role": "user",
        "content": "What is causing the high error rate on payments-service?",
        "timestamp": NOW,
    },
    {
        "incident_id": "INC-20260423-001",
        "message_id": "MSG-002",
        "role": "assistant",
        "content": (
            "Based on the incident data and runbook context, the error spike correlates "
            "with the 14:32 UTC deploy. The payments-service DB connection pool is likely "
            "exhausted — each new deploy resets existing connections while in-flight "
            "requests hold slots open. Recommended immediate action: increase "
            "APP_DB_POOL_MAX and trigger a rolling redeploy to refresh the pool."
        ),
        "timestamp": NOW,
    },
    {
        "incident_id": "INC-20260423-001",
        "message_id": "MSG-003",
        "role": "user",
        "content": "How do I check current connection pool usage?",
        "timestamp": NOW,
    },
    {
        "incident_id": "INC-20260423-001",
        "message_id": "MSG-004",
        "role": "assistant",
        "content": (
            "Run the following against the payments-service RDS instance:\n\n"
            "```sql\n"
            "SELECT count(*), state\n"
            "FROM pg_stat_activity\n"
            "WHERE datname = 'payments'\n"
            "GROUP BY state;\n"
            "```\n\n"
            "If idle connections are near `max_connections`, the pool is saturated. "
            "Cross-reference with CloudWatch metric `DatabaseConnections` on the RDS "
            "dashboard for the trend over the last hour."
        ),
        "timestamp": NOW,
    },
]

SAMPLE_CORPUS_CHUNKS = [
    {
        "chunk_id": "chunk-001",
        "source_file": "runbooks/payments-service.md",
        "text": (
            "## Payments Service — Connection Pool Runbook\n\n"
            "When the payments service reports elevated 5xx rates after a deploy, "
            "the most common cause is DB connection pool exhaustion. "
            "Increase APP_DB_POOL_MAX (default: 10) and redeploy. "
            "Monitor pg_stat_activity to confirm connections drain within 2 minutes."
        ),
        "chunk_index": 0,
        "embedding_model": "amazon.titan-embed-text-v2:0",
    },
    {
        "chunk_id": "chunk-002",
        "source_file": "runbooks/database-connection-pool.md",
        "text": (
            "## Database Connection Pool Management\n\n"
            "Each service instance holds a pool of persistent DB connections. "
            "Pool size is controlled by APP_DB_POOL_MAX and APP_DB_POOL_MIN. "
            "Under high concurrency, exhausted pools surface as connection timeout "
            "errors and manifest as HTTP 500/503 responses to callers."
        ),
        "chunk_index": 0,
        "embedding_model": "amazon.titan-embed-text-v2:0",
    },
    {
        "chunk_id": "chunk-003",
        "source_file": "runbooks/database-connection-pool.md",
        "text": (
            "## Diagnosing Pool Exhaustion\n\n"
            "Query pg_stat_activity to count connections by state. "
            "If idle connections approach max_connections, reduce idle timeout "
            "(APP_DB_POOL_IDLE_TIMEOUT) or scale down the number of service replicas "
            "to free headroom. Always prefer reducing replicas over raising "
            "max_connections on shared RDS instances."
        ),
        "chunk_index": 1,
        "embedding_model": "amazon.titan-embed-text-v2:0",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_table(schema: dict) -> None:
    name = schema["TableName"]
    try:
        _resource.create_table(**schema)
        print(f"  created  {name}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceInUseException":
            print(f"  exists   {name} (skipped)")
        else:
            raise


def seed_table(table_name: str, items: list[dict]) -> None:
    table = _resource.Table(table_name)
    for item in items:
        # Remove None values — DynamoDB rejects explicit nulls
        clean = {k: v for k, v in item.items() if v is not None}
        table.put_item(Item=clean)
    print(f"  seeded   {table_name} ({len(items)} item{'s' if len(items) != 1 else ''})")


def verify_tables() -> None:
    client = _resource.meta.client
    response = client.list_tables()
    tables = response.get("TableNames", [])
    expected = {"Incidents", "ChatMessages", "CorpusChunks", "Counters"}
    missing = expected - set(tables)
    if missing:
        print(f"ERROR: missing tables after creation: {missing}", file=sys.stderr)
        sys.exit(1)
    print(f"\n  verified tables: {sorted(tables)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"DynamoDB endpoint: {DYNAMODB_ENDPOINT}\n")

    print("Creating tables...")
    for schema in TABLE_SCHEMAS:
        create_table(schema)

    print("\nSeeding data...")
    seed_table("Incidents", [SAMPLE_INCIDENT])
    seed_table("ChatMessages", SAMPLE_CHAT_MESSAGES)
    seed_table("CorpusChunks", SAMPLE_CORPUS_CHUNKS)

    verify_tables()
    print("\nDone. Local database is ready.")


if __name__ == "__main__":
    main()
