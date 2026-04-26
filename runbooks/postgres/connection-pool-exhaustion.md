# PostgreSQL — Connection Pool Exhaustion

## Overview

Each PostgreSQL connection consumes ~5–10 MB of server memory and a file descriptor. When `max_connections` is reached, new connection attempts receive `FATAL: sorry, too many clients already`. Application-side connection pool exhaustion occurs earlier — when all pool slots are in use — and manifests as connection timeout errors and HTTP 5xx responses to callers.

**Common causes:**
- Recent deploy that restarted services, transiently doubling open connections
- Long-running transactions holding connections open
- Connection pool sized too small for current replica count
- Missing connection pool (app opens a new connection per request)
- Idle connections not being returned to the pool (leak)

## Diagnosis

### 1. Count connections by state

```sql
SELECT state, count(*)
FROM pg_stat_activity
WHERE datname = '<your_database>'
GROUP BY state
ORDER BY count DESC;
```

States:
- `active` — query is running
- `idle` — connection is open but not doing anything (pool holding it)
- `idle in transaction` — dangerous; a transaction is open but no query is running
- `idle in transaction (aborted)` — error inside a transaction that was not rolled back

### 2. Check approach to max_connections

```sql
SELECT
  max_conn,
  used,
  max_conn - used AS available
FROM
  (SELECT count(*) AS used FROM pg_stat_activity) t1,
  (SELECT setting::int AS max_conn FROM pg_settings WHERE name = 'max_connections') t2;
```

### 3. Find long-running queries

```sql
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes'
  AND state != 'idle'
ORDER BY duration DESC;
```

### 4. Find idle-in-transaction connections (dangerous)

```sql
SELECT pid, usename, application_name, state, query_start, state_change, query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND state_change < NOW() - INTERVAL '5 minutes';
```

These hold locks and prevent VACUUM from reclaiming dead tuples.

### 5. Check application pool settings

Application env vars to verify (names vary by framework):

| Framework | Pool size var | Default |
|-----------|--------------|---------|
| SQLAlchemy | `SQLALCHEMY_POOL_SIZE` / `pool_size=` | 5 |
| psycopg3 | `min_size` / `max_size` in connection pool | 4 / 10 |
| Django | `CONN_MAX_AGE` | 0 (no pooling) |
| PgBouncer | `max_client_conn` / `default_pool_size` | varies |

## Immediate Mitigation

### Terminate idle-in-transaction connections

```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle in transaction'
  AND state_change < NOW() - INTERVAL '10 minutes';
```

Use `pg_cancel_backend(pid)` first if you prefer a soft interrupt — it sends SIGINT (cancels the query but keeps the connection). `pg_terminate_backend` sends SIGTERM and closes the connection.

### Terminate long-running queries blocking others

```sql
SELECT pg_cancel_backend(pid)
FROM pg_stat_activity
WHERE (now() - query_start) > interval '30 minutes'
  AND state = 'active';
```

### Increase pool size via env var and redeploy

If pool is the bottleneck, update the service's pool-size env var and trigger a rolling deploy:

```bash
# Example for ECS — update task definition and force new deployment
aws ecs update-service \
  --cluster <cluster-name> \
  --service <service-name> \
  --force-new-deployment
```

Target: `(pool_size × replica_count) < max_connections × 0.8`

Leave 20% headroom for superuser connections and monitoring tools.

## Root Cause Fixes

### Deploy PgBouncer as a connection multiplexer

PgBouncer in transaction-pool mode allows hundreds of application connections to share a small number of actual server connections. Recommended when `replica_count × pool_size > max_connections / 2`.

### Add statement timeout to prevent long-running queries

```sql
ALTER DATABASE <your_database> SET statement_timeout = '30s';
```

Or per-role:

```sql
ALTER ROLE <app_user> SET statement_timeout = '30s';
```

### Add idle-in-transaction timeout

```sql
ALTER DATABASE <your_database> SET idle_in_transaction_session_timeout = '5min';
```

Prevents abandoned transactions from holding connections indefinitely.

### Right-size max_connections

Each connection uses ~5–10 MB. On RDS, `max_connections` is set automatically based on instance memory:

| Instance class | Default max_connections |
|----------------|------------------------|
| db.t3.micro | 34 |
| db.t3.medium | 136 |
| db.r6g.large | 683 |
| db.r6g.xlarge | 1365 |

To increase: upgrade the instance class or use a parameter group override (rarely needed if PgBouncer is in place).

## Monitoring Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| `DatabaseConnections` (CloudWatch RDS) | > 70% of max | > 85% of max |
| `idle in transaction` connections | > 5 | > 20 |
| Active connections > 30 min | > 0 | > 3 |

## Related Runbooks

- `runbooks/postgres/slow-queries.md`
- `runbooks/postgres/vacuum-bloat.md`
- `runbooks/sre-general/pgbouncer-setup.md`
