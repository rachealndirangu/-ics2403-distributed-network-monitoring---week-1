# Final architecture (Milestone 12) — Distributed Network Monitoring System

```
 Users / IoT / Telecom devices         24 cell sites, 6 regions, 120,000 telemetry rows (seed 2403)
            │  HTTP  (agent reports /metrics, dataset chunks /bulk)
            ▼
 ┌────────── Distributed EDGE layer ─────────────────────────────────────────────────┐
 │ edge nodes A,B (replayers/agents) → edge gateway: validate · batch · back-pressure │
 │ ADAPTIVE site-affine coalescing + zlib (the proposed improvement) · naming client   │
 └───────────────────────────────┬────────────────────────────────────────────────────┘
                                 │  topic edge.telemetry  (Kafka / LocalBus: partitioned by site, durable, replayable)
                                 ▼
 ┌────────── Distributed processing + COORDINATION layer ────────────────────────────┐
 │ 3 core replicas · Bully leader election · heartbeat · Lamport stamps                │
 │ only the leader consumes; offsets committed after persist (at-least-once)           │
 └───────────────────────────────┬────────────────────────────────────────────────────┘
        TRANSACTION & STATE layer │  per-replica SQLite (idempotent on record_id) · txn/ (2PC/3PC) for quota moves ·
        replicated quorum KV (replication/) · DSM (dsm/) · locks (concurrency/)
                                 ▼
 ┌────────── Telecom CORE ─── anomaly detection (analytics) · alerts · digest ────────┐
 └───────────────────────────────┬────────────────────────────────────────────────────┘
                                 │  topic core.processed ; HTTP digest
                                 ▼
 ┌────────── CLOUD ── fleet analytics (cloud/service) · archiver (cloud/archiver) ────┐
 └───────────────────────────────┬────────────────────────────────────────────────────┘
                                 ▼
 ┌────────── Distributed STORAGE ── HDFS-style DFS (namenode + datanodes, 3 replicas, checksums, re-replication)
 │                                  + S3-style object store (MinIO)   → gzip-CSV objects  telemetry/site=…/date=…/p*-o*.csv.gz
 └─────────────────────────────────────────────────────────────────────────────────────
 Cross-cutting: naming (naming/: static · broadcast · name server · hierarchical prefix resolver with referrals)
                process management (procman/: create · locate · schedule · coordinate · terminate)
                RPC (rpc/: stub/skeleton, 3 call semantics, REST, gRPC)   transparency (transparency/: logical resources)
                fault injection (common/faults.py)   monitoring & evaluation (experiments/, results/, powerbi/)
```

## How each brief layer / milestone is realised
| Brief layer | Milestone | Code | Key measured result |
|---|---|---|---|
| Distributed OS | 1 | `agent.py`, `collector.py`, `system/scripts/cluster.py` | nodes = processes with enforced CPU/memory envelopes (`results/m01_*`) |
| Processing | 2 | `edge/analytics.py`, `baseline/collector.py` | data-local distribution 1.6× on 2 CPUs; shipping data 0.7× |
| Architecture | 3 | `edge/gateway.py`, `core/`, `cloud/` | 10× fewer messages at the core; 2 gateways: 0 failures at 400 agents |
| Algorithms | 4 | `core/service.py`, `common/lamport.py` | failover ≈ 1.05–1.3 × heartbeat interval; wall-clock ordering violated 33.6 %, Lamport 0 % |
| Transactions | 5 | `txn/` | 2PC blocks, 3PC does not (+46…74 % latency); ordered prepare 0.6 → 103 tps |
| Concurrency | 6 | `concurrency/` | detect+recover 20/20 in 1.27 s; barging starves, FIFO 0.1 s |
| Fault tolerance | 7 | `common/faults.py`, `replication/` | availability 56.6 % → 100 %; vote needs N=4 for crash+Byzantine |
| (System models) | 8 | `models/simulator.py` | integrated model wins 3 of 4 weightings if site-owned edge hardware is free; processor-pool wins all 4 if every core is priced |
| Transparency | 9 | `transparency/` | layer overhead 1.7× read / 1.9× write (3.75× if the placement is looked up on every call); failure transparency 100 % vs 57 %; 4-phase migration 0 lost writes vs ≈ 6 % for naive |
| Naming | 10 | `naming/`, `procman/` | prefix table + cache 0.004 ms; least-loaded 20–25 % faster than round-robin with a slow node |
| Communication | 11 | `rpc/`, `dsm/` | gRPC 3–10× faster; at-most-once exact; DSM strong 0 % stale vs eventual 10 % |
| Distributed storage | 12 | `storage/`, `cloud/archiver.py` | 120,000/120,000 ids in DFS **and** object store, also after an archiver crash |

## Baseline vs proposed (brief §6)
*Baseline:* flat collector (Week 1/2): agents/edge nodes → one process → SQLite.
*Proposed:* the tiered system above. *Proposed improvement:* adaptive site-affine coalescing + zlib on the edge→core link (`edge/gateway.py: ADAPTIVE, COMPRESS`). Results: `docs/milestones/12-capstone.md`.

## Deployment
Compose (`docker-compose.system.yml`, real Kafka/MinIO — see `docs/run_with_docker.md` for what was and was not executed) or local processes (`system/scripts/cluster.py`) – identical service modules in both.
