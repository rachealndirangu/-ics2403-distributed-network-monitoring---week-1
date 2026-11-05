# Milestone 3 — Distributed Architecture (Edge ↔ Core ↔ Cloud)

**System stage S3:** the flat collector is split into tiers that can be deployed, scaled and failed independently.

| Brief deliverable | Where |
|---|---|
| Architectural design | this file §Architecture; `docs/architecture.md` (final picture) |
| Deployment architecture | `docker-compose.system.yml` (Kafka, MinIO, namenode/datanodes, cloud, archiver, 3 cores, gateway, 2 replayers; `baseline` profile = flat collector), `Dockerfile.system`; local equivalent `system/scripts/cluster.py` |
| Service decomposition | table below |
| Scalability analysis | §Results A |
| Edge-versus-core trade-off analysis | §Results B, C |
| Experiments | `python -m system.experiments.m03_architecture` → `results/m03_*.csv` |

## Architecture styles evaluated (brief: client-server, multi-tier, SOA, microservices)
| Style | What it is in this system | Verdict |
|---|---|---|
| Client–server | Agents → one collector (`system/baseline/collector.py`). Every client talks to the one server. | Simplest; saturates first; single point of failure (kept as the **baseline**). |
| Multi-tier | Edge gateway → Core → Cloud, each tier with its own responsibility and own data store. | Chosen backbone: lets each tier scale and fail independently. |
| Service-oriented | Every capability has an explicit HTTP contract (`/bulk`, `/ingest`, `/leader`, `/readings/count`, `/verify`, …). | Used for all inter-tier calls. |
| Microservices | Each service is its own process/container with its own state (per-core SQLite, namenode metadata, object store). | Used for the services that must fail independently (cores, datanodes, archiver); kept coarse because every extra hop costs latency (M9, M11). |

## Service decomposition
| Service | Tier | Responsibility | State |
|---|---|---|---|
| `edge/agent.py`, `edge/replayer.py` | device/edge | produce telemetry | none |
| `edge/gateway.py` | edge | validate, batch/aggregate, back-pressure (HTTP 429), publish to the log | in-memory outbox |
| message log (Kafka / `LocalBus`) | edge↔core | durable decoupling, per-site partitioning | log |
| `core/service.py` ×3 | core | leader-only consumption (Bully), persist, anomaly check, digest to cloud | SQLite per replica |
| `cloud/service.py`, `cloud/archiver.py` | cloud | fleet digest, archive to storage | – |
| `storage/*`, MinIO | storage | HDFS-style DFS + S3-style object store | files |

## Experimental method
*H1* a single tier saturates first; the tiered design keeps the core's incoming message rate flat. *H2* edge batching cuts core-bound messages ≈ BATCH_SIZE-fold at the price of staleness. *H3* larger dataset messages raise throughput until per-message cost is amortised.
Independent variables: agents N ∈ {20, 100, 400} × design {flat, tiered-1gw, tiered-2gw}; batch size {1, 5, 20, 50}; rows/message {10, 100, 500} × upload order {time, site}. 3 repetitions for A, one pass for B/C. Controlled: host, dataset, report payload, 2-CPU sandbox.

## Results
**A — scalability (mean of 3 reps).**

| agents | design | throughput (reports/s) | latency mean / p95 / p99 (ms) | failed requests (3 reps) | msgs reaching upper tier |
|---|---|---|---|---|---|
| 20 | flat | 816 | 22 / 29 / 32 | 0 | 500 |
| 20 | tiered-1gw | 744 | 25 / 33 / 36 | 0 | 50 |
| 20 | tiered-2gw | 878 | 20 / 41 / 52 | 0 | 50 |
| 100 | flat | 766 | 96 / 145 / 157 | 0 | 2,500 |
| 100 | tiered-1gw | 723 | 115 / 154 / 163 | 0 | 250 |
| 100 | tiered-2gw | 735 | 101 / 239 / 334 | 0 | 250 |
| 400 | flat | 732 | 342 / 1,255 / 3,130 | 5 | 10,000 |
| 400 | tiered-1gw | 651 | 411 / 1,525 / 3,685 | 13 | 1,000 |
| 400 | tiered-2gw | 697 | **157 / 363 / 486** | **0** | 1,000 |

**B — edge aggregation (1,200 reports).** Batch 1 / 5 / 20 / 50 → core messages 1,200 / 240 / 60 / 24 (×1, ×5, ×20, ×50), bytes to the core 677 kB / 474 kB / 431 kB / 339 kB (−50 % at 50), staleness at the core 29 / 36 / 41 / 89 ms.

**C — rows per message (20,000 dataset rows, bus path).**

| upload order | rows/msg cap | messages | avg rows/msg | rows/s | pipeline latency mean (s) |
|---|---|---|---|---|---|
| time | 10 / 100 / 500 | 2,160 / 240 / 240 | 9 / 83 / 83 | 28.6 k / 38.9 k / 40.0 k | 0.171 / 0.107 / 0.089 |
| site | 10 / 100 / 500 | 2,018 / 218 / 54 | 10 / 92 / 370 | 25.3 k / 32.3 k / 38.8 k | 0.163 / 0.071 / 0.083 |

## Analysis — edge versus core trade-off
* **The core is protected, the edge pays.** Tiering cuts what the upper tier must absorb ×10 (500 → 50 messages) and, with two gateways, keeps 400 agents healthy (0 failures, p99 486 ms vs 3.1 s flat). The price is an extra hop: at low load *one* gateway is slightly **worse** than the flat design (744 vs 816 reports/s at 20 agents, 411 vs 342 ms mean latency at 400 agents with 13 failures vs 5) because the single gateway process becomes the new bottleneck. The tiered design only wins once the first tier is itself scaled out — H1 is supported with that qualification.
* **Aggregation trades freshness for load**: ×50 fewer messages, half the bytes, +60 ms staleness. Worth it for monitoring (second-scale tolerance), not for alarms — which is why alarms bypass batching in the gateway.
* **Message size**: throughput rises ~40 % from 10 to ≥100 rows/message and then flattens; batching by site only helps when many consecutive rows of the same site are present (backlog upload), which is the motivation for the *site-affine coalescing* in the M12 improvement.

## Failure-driven engineering log (week 3)
| Question | Answer |
|---|---|
| What changed? | Gateway tier, log between edge and core, core replicas, cloud digest; deployment as compose file. |
| What failed? | (1) The first scalability run used a single repetition and showed a "tiered wins" result that vanished on repeat. (2) Message-size experiment: 100 vs 500 rows/message gave identical numbers. |
| Why? | (1) Run-to-run noise on a 2-CPU host is ±10 %. (2) Rows arrive time-ordered, so each message holds at most the rows of one site in a 500-row chunk (~83), the cap never bites. |
| How fixed? | 3 repetitions and error-type capture (timeouts are results); added site-ordered uploads and 2,000-row chunks. |
| Alternative considered | Peer-to-peer gossip instead of gateways (rejected: no natural place to batch or apply back-pressure). |
| What was learned? | A tier is only an improvement when it is itself scaled; check that the knob you vary can actually take effect. |

## Limitations
Loopback network (no real WAN latency), 2 CPUs shared by load generator and services, one dataset.
