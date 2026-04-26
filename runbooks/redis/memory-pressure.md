# Redis — Memory Pressure and Key Eviction

## Overview

Redis is an in-memory store. When `used_memory` approaches `maxmemory`, Redis either starts evicting keys (if an eviction policy is set) or rejects write commands with `OOM command not allowed` errors. Both outcomes degrade application behaviour.

**Common causes:**
- Cache miss amplification — clients caching large or unbounded payloads
- Missing TTLs on keys — data accumulates indefinitely
- Sudden traffic spike increasing the working set size
- Memory leak in application (e.g., accumulating lists/sets without trimming)
- `maxmemory` set too low for current workload

## Diagnosis

### 1. Check memory usage

```bash
redis-cli -h <host> -p <port> INFO memory
```

Key fields:
- `used_memory_human` — current RSS
- `maxmemory_human` — configured cap (0 = no limit)
- `mem_fragmentation_ratio` — >1.5 suggests fragmentation; <1 means memory is swapping
- `used_memory_peak_human` — high-water mark

### 2. Check eviction stats

```bash
redis-cli -h <host> -p <port> INFO stats | grep evicted
# evicted_keys: cumulative evictions since start
```

High `evicted_keys` means the working set exceeds `maxmemory` and data is being silently dropped.

### 3. Identify largest key consumers

```bash
# Top 10 keys by memory (use on a replica, not primary — it's slow)
redis-cli --bigkeys

# Sample key sizes (safer for production)
redis-cli -h <host> MEMORY USAGE <key>
```

### 4. Check current eviction policy

```bash
redis-cli -h <host> CONFIG GET maxmemory-policy
```

Common policies and implications:

| Policy | Behaviour |
|--------|-----------|
| `noeviction` | Rejects writes when full — apps see OOM errors |
| `allkeys-lru` | Evicts least-recently-used keys across all keyspaces |
| `volatile-lru` | Evicts LRU keys that have a TTL set |
| `allkeys-lfu` | Evicts least-frequently-used (Redis 4+) |

### 5. Check for keys without TTL

```bash
# Count keys with no expiry (sample-based, safe for prod)
redis-cli -h <host> INFO keyspace
# Look for keys= vs expires= ratio per DB
```

## Immediate Mitigation

### Free memory without data loss

```bash
# Force a memory defrag cycle (Redis 4+)
redis-cli -h <host> MEMORY PURGE

# If fragmentation ratio > 1.5, enable active defrag
redis-cli -h <host> CONFIG SET activedefrag yes
redis-cli -h <host> CONFIG SET active-defrag-ignore-bytes 100mb
redis-cli -h <host> CONFIG SET active-defrag-threshold-lower 10
```

### Increase maxmemory temporarily

```bash
redis-cli -h <host> CONFIG SET maxmemory 4gb
```

Update the Terraform / Helm value to make this permanent after the incident.

### Flush non-critical cache data

Only if the instance is a pure cache (no persistent state):

```bash
# Flush a specific database (DB 1 = cache tier by convention)
redis-cli -h <host> SELECT 1
redis-cli -h <host> FLUSHDB ASYNC
```

Never run `FLUSHALL` without confirming all databases are pure cache.

## Root Cause Fixes

### Add TTLs to keys missing expiry

Application-side fix — search for `SET` calls without `EX`/`PX`/`EXAT` options and add appropriate TTLs.

```python
# Before (no expiry — key lives forever)
redis.set("session:abc123", data)

# After
redis.set("session:abc123", data, ex=3600)  # 1 hour TTL
```

### Cap list / sorted-set sizes

Use `LTRIM` after `LPUSH` to keep lists bounded:

```bash
LPUSH mylist value
LTRIM mylist 0 999   # keep newest 1000 items
```

### Right-size the instance

If `used_memory` consistently exceeds 70% of `maxmemory`, upgrade the instance class (ElastiCache: change node type). Target steady-state usage at 50–60% to absorb traffic spikes.

## Monitoring Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| `used_memory` / `maxmemory` | > 70% | > 85% |
| `evicted_keys` rate | > 0/min | > 100/min |
| `rejected_connections` | > 0 | > 10 |

## Related Runbooks

- `runbooks/redis/replication-lag.md`
- `runbooks/redis/slow-commands.md`
