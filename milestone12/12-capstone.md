# Milestone 12 — Distributed File System and Telecom Capstone

**System stage S12:** `Users / Devices → Edge → Telecom Core → Cloud → Distributed Storage`, evaluated against a baseline across nine factors and three groups of metrics.

| Brief deliverable / requirement | Where |
|---|---|
| Fully working distributed system integrating the course concepts | `system/` (see `docs/architecture.md`); `scripts/run_all_experiments.sh`; `tests/` (26 tests) |
| Distributed storage (NFS/HDFS-style, cloud storage) | `system/storage/` (namenode, datanode, client), `system/cloud/archiver.py`, `system/common/objstore.py` (MinIO / local stand-in) |
| Edge nodes, core services, cloud services | `system/edge/`, `system/core/`, `system/cloud/` |
| Containerised services | `Dockerfile.system`, `docker-compose.system.yml`, `docs/run_with_docker.md` (**not executed here — no Docker daemon**) |
| Lecturer: 100 000+ row dataset | `data/telemetry_120k.csv` (120 000 rows, 24 sites, seed 2403, sha256 `7e81ca81…95e691`) |
| Lecturer: Kafka between edge and core | `system/common/bus.py`: `KafkaBus` (confluent-kafka) **and** `LocalBus` (file-backed log, same interface). **All measurements below ran on `LocalBus`**; the Kafka code path and compose file are written but unexecuted (see Limits). |
| Lecturer: Power BI file with 2–4 charts | `powerbi/` (4-chart report definition: Power Query + DAX + layout; preview images). The `.pbix` itself must be assembled in Power BI Desktop (`powerbi/README.md`) — it cannot be produced on Linux. |
| Capstone: vary nodes, users, bandwidth, CPU, memory, network load, failure rate, request rate, data volume | `system/experiments/m12_capstone.py` — 253 trials, all nine factors |
| Capstone: measure latency / throughput / jitter, CPU / memory / bandwidth, availability / MTTR / failure rate, consistency / scalability / coordination overhead | raw: `results/m12_capstone_raw.csv`; summary: `results/m12_capstone_summary.csv`; tables: `results/m12_tables.md`; coordination: `results/m12_coordination.csv` |
| Baseline vs proposed, ≥ 1 meaningful improvement | three systems compared below; improvement = adaptive site-affine coalescing + zlib on the edge→core link |

Run: `python -m system.experiments.m12_storage` (≈ 10 min), `python -m system.experiments.m12_capstone` (≈ 2.5 h, resumable), `python -m system.experiments.m12_analyze`, `python -m system.experiments.m12_tables`, `python -m system.experiments.m12_coordination` (3.5 min).

# Part 1 — The distributed-storage tier

HDFS-style file system (`system/storage/`): a **namenode** (namespace, chunk → replica map, chunk-ID allocation, heartbeats, re-replication, orphan GC) and **datanodes** (chunk store on local disk, per-chunk SHA-256 verified on every read). The client splits files into chunks, pipelines each chunk to R datanodes, fails over between replicas on read, and verifies checksums. The archiver consumes `core.processed` from the bus and writes gzip-CSV objects (`telemetry/site=…/date=…/p*-o*.csv.gz`) to **both** the DFS and the object store.

**A — throughput vs chunk size and replication (24 MB file, 5 datanodes, 3 reps; MB/s)**

| chunk | R=1 write | R=2 write | R=3 write | R=1 read | R=3 read |
|---|---|---|---|---|---|
| 256 KB | 58.5 | 29.7 | 19.1 | 85.9 | 89.8 |
| 1 MB | 122.9 | 60.1 | 39.2 | 169.7 | 165.7 |
| 4 MB | **143.8** | 81.2 | 56.8 | 201.8 | **205.4** |

Write throughput falls with the replication factor (every byte is written R times: 256 KB chunks give 1 : 0.51 : 0.33 — almost exactly 1/R; 4 MB chunks 1 : 0.56 : 0.40); read throughput does not change with R. Larger chunks amortise per-chunk namenode round trips: 4 MB vs 256 KB is 2.5× on writes and 2.3× on reads.

**B — datanode failures (16 chunks of 512 KB, 5 datanodes, 2 reps, dead-after 3 s)**

| R | datanodes killed back-to-back | reads during failure | chunks lost | re-replications | namenode detects after | fully replicated after | final read |
|---|---|---|---|---|---|---|---|
| 3 | 1 | all OK | 0 | 10 | 2.4 s | 3.1 s | correct |
| 3 | 2 | all OK | **0** | 20 | 2.6 s | 4.1 s | correct |
| 2 | 1 | all OK | 0 | 7 | 2.4 s | 3.3 s | correct |
| 2 | 2 | 1 read failed | **4 of 16 (25 %)** | 6 | 2.8 s | never | **incorrect** |

With R=3 two simultaneous datanode losses lose nothing and the file heals in ≈ 4 s; with R=2 the same double failure loses the 4 chunks that lived only on the two dead nodes — the replication factor is a loss-tolerance of R−1 simultaneous failures, measured.

**C — bit rot.** 20 corruption injections (the first replica of a chunk, round-robin over the file's 8 chunks; earlier corruptions stay in place), each followed by a full read of the file: **all 20 reads returned correct data (0 corrupt bytes reached the application)**; 19 of them recorded a checksum failure and a failover to another replica (in one read no failover was recorded — we did not investigate whether the client simply tried a healthy replica first).

**D — end to end (the full 120 000 rows: edge → bus → core → `core.processed` → archiver → DFS + object store)**

| scenario | distinct record_ids in object store | in DFS | rows lost | objects (store / DFS) | archive complete | lag after core finished |
|---|---|---|---|---|---|---|
| archiver runs to completion | **120 000 / 120 000** | **120 000** | 0 | 523 / 523 | 17.2 s | 14.2 s |
| archiver killed at 8.1 s (≈ 50 %) and restarted | **120 000 / 120 000** | **120 000** | 0 | 526 / 526 | 17.4 s | 14.2 s |

The archive path is *at-least-once*: after the crash the restarted archiver re-read from its last committed offset and rewrote a few objects (526 instead of 523 objects); de-duplicated on `record_id` the stored set equals the dataset in both stores. The DFS ended with 0 under-replicated chunks.

# Part 2 — Capstone: baseline vs proposed vs improved

## The three systems (same dataset, same driver, same host)
| system | design |
|---|---|
| **baseline-flat** | the Week-1/2 design: clients POST straight to **one** collector (validate + SQLite). No bus, no replicas, no election. |
| **proposed** | the final architecture: edge gateway → partitioned log (Kafka interface) → 3 core replicas (Bully-elected leader consumes; offsets committed after persist) → cloud digest. Fixed 100 rows per message, uncompressed. |
| **proposed+improved** | the same, plus the **improvement**: *adaptive site-affine coalescing* (rows of the same site are merged into larger messages when a backlog exists, bounded wait `COALESCE_MS`) and *zlib compression* of the merged batches on the bandwidth-limited edge→core link. |

## Method
One-factor-at-a-time sweeps around a centre point (60 000 rows, 4 users, unlimited rate, no bandwidth cap, 3 cores, 2 CPUs, no memory cap, no cross-traffic, no failures), except the bandwidth sweep (full 120 000 rows). 2–3 repetitions per cell (3 for bandwidth, failure rate and transport; 2 elsewhere) → 253 trials; each trial starts a fresh cluster. Tables show mean ±sd over repetitions (full table with 95 % CIs: `results/m12_capstone_summary.csv`).

| factor | levels | how it is varied (all emulated, all local — see Limits) |
|---|---|---|
| nodes | 1, 2, 3, 5 core replicas | process count |
| users | 1, 2, 4, 8, 16 | concurrent client threads |
| bandwidth | unlimited, 100, 25, 10, 5 Mbit/s | token-bucket shared by all senders on the edge→core link (baseline gets the same cap) |
| CPU | 2 CPUs / 1 CPU / 1 CPU + busy-loop | `sched_setaffinity` on core/collector processes (+ a competing spin process) |
| memory | unlimited / 256 / 160 / 128 MB | `RLIMIT_AS` on core/collector processes |
| network load | 0, 2, 8, 16 | cross-traffic threads posting 32 KB reports at the entry point |
| failure rate | 0, 6, 12, 20 crashes/min | core/collector SIGKILL, restarted after 1 s (4 000 rows/s paced) |
| request rate | 2 k, 5 k, 10 k, 20 k rows/s, unlimited | global pacing |
| data volume | 10 k, 30 k, 60 k, 120 k rows | rows sent |

Metrics — **performance:** request latency (mean/p95/p99), jitter (stdev and RFC-3550-style mean |Δ|), ingest and end-to-end throughput; **resources:** CPU %, resident memory, bytes on the link; **reliability:** ingest availability (a 1-row write probe every 100 ms), failed-request %, MTTR (crash → writes accepted again), rows lost; **consistency:** stored record_ids are compared with the dataset (lost / duplicate); **scalability:** nodes, users and volume sweeps; **coordination overhead:** Part 3.

## Results by factor

### Bandwidth — where the improvement matters
**time to deliver all 120,000 rows (s)**

| level | baseline | proposed | improved |
|---|---|---|---|
| unlimited | 0.98 ±0.04 | 2.72 ±0.29 | 2.76 ±0.38 |
| 100 | 3.61 | 6.38 ±0.12 | 2.92 ±0.31 |
| 25 | 14.29 | 17.35 ±0.22 | 4.03 ±0.35 |
| 10 | 35.65 ±0.01 | 39.13 ±0.24 | 7.80 ±0.87 |
| 5 | 71.26 ±0.01 | 75.84 ±0.25 | 11.99 ±0.29 |

**bytes on the edge→core link (MB)**

| level | baseline | proposed | improved |
|---|---|---|---|
| unlimited | 44.5 | 45.1 | 6.1 ±0.0 |
| 100 | 44.5 | 45.1 | 6.1 ±0.0 |
| 25 | 44.5 | 45.2 | 6.1 ±0.0 |
| 10 | 44.5 | 45.3 | 6.1 ±0.0 |
| 5 | 44.5 | 45.5 | 6.1 ±0.0 |

**total CPU-seconds of the core/collector processes (mean CPU % × time)**

| level | baseline | proposed | improved |
|---|---|---|---|
| unlimited | 0.84 | 3.38 | 2.70 |
| 100 | 0.84 | 4.32 | 2.88 |
| 25 | 1.24 | 5.67 | 3.03 |
| 10 | 1.82 | 7.92 | 3.50 |
| 5 | 2.87 | 12.39 | 4.00 |

Speed-up of *improved* over *baseline*: **0.36×** (unlimited), **1.24×** (100 Mbit/s), **3.55×** (25), **4.57×** (10), **5.94×** (5). Over the *unimproved proposed* system: 0.99× / 2.19× / 4.31× / 5.02× / 6.33×. Bytes on the link fall **7.3×** (44.5 → 6.1 MB; zlib ≈ 6.6:1 on this telemetry, plus fewer headers from larger messages) and the improved system also needs **less total CPU** than the unimproved one at every bandwidth (e.g. 4.0 vs 12.4 CPU-seconds at 5 Mbit/s; larger messages mean fewer per-message costs).

**Crossover.** Below ≈ 130 Mbit/s the improved system beats the baseline: the baseline's time is ≈ 356 Mbit ÷ bandwidth (44.5 MB), the improved system's is bounded by its ≈ 2.7 s processing floor, and the two lines meet at ≈ 130 Mbit/s (model); measured points bracket it (improved already 1.24× faster at 100, 0.36× at unlimited). On an unconstrained link the baseline is simply fastest: it has the fewest hops.

### Failure rate — where the architecture matters
**ingest availability % (100 ms write probe)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 0 | 100.0 | 100.0 | 100.0 |
| 6 | 84.8 ±0.4 | 100.0 | 100.0 |
| 12 | 77.6 ±0.4 | 100.0 | 100.0 |
| 20 | 63.7 ±0.2 | 100.0 | 100.0 |

**failed requests %**

| level | baseline | proposed | improved |
|---|---|---|---|
| 0 | 0.00 | 0.00 | 0.00 |
| 6 | 23.08 | 0.00 | 0.00 |
| 12 | 31.03 | 0.00 | 0.00 |
| 20 | 42.86 | 0.00 | 0.00 |

**MTTR (s): crash → accepting writes again**

| level | baseline | proposed | improved |
|---|---|---|---|
| 0 | – | – | – |
| 6 | 1.23 | 0.69 ±0.01 | 0.70 ±0.02 |
| 12 | 1.21 ±0.02 | 0.88 ±0.01 | 0.89 ±0.02 |
| 20 | 1.23 ±0.04 | 0.76 ±0.10 | 0.77 ±0.05 |

**rows lost**

| level | baseline | proposed | improved |
|---|---|---|---|
| 0 | 0 | 0 | 0 |
| 6 | 0 | 0 | 0 |
| 12 | 0 | 0 | 0 |
| 20 | 0 | 0 | 0 |

Under crashes the flat collector is down for its restart time each time (1.2 s MTTR): availability falls to 84.8 / 77.6 / **63.7 %** at 6 / 12 / 20 crashes per minute and 23–43 % of request *attempts* fail (the driver retries until success, so no rows are lost — the cost is *availability and latency*, not data). The proposed and improved systems keep accepting writes **100 %** of the time at every crash rate: the edge gateway and the log absorb data while the leader is replaced; the price is a processing pause of 0.7–0.9 s per crash (MTTR column: time until processing resumes). Total delivery time at 4 000 rows/s is the same for all three (≈ 15 s, bounded by the pacing).

**Transport under crashes (proposed, 12 crashes/min, 3 reps)**

| transport | complete (s) | p95 latency (ms) | availability % | MTTR (s) | rows lost | core CPU % |
|---|---|---|---|---|---|---|
| bus (Kafka interface) | 15.04 | 11.7 | 100 | 0.89 | 0 | 13.6 |
| direct HTTP | 15.04 | 10.3 | 100 | 0.93 | 0 | 29.6 |

Both transports meet the same availability/MTTR at this (paced) load; the bus mode uses about half the core CPU. CPU readings in chaos trials are noisy (processes restart while being sampled), so only the order of magnitude should be read from them.

### Users (concurrency, scalability of clients)
**request latency p95 (ms)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 1 | 13.3 ±1.4 | 19.6 ±1.4 | 13.2 ±0.0 |
| 2 | 27.4 ±1.0 | 24.5 ±0.9 | 23.9 ±0.0 |
| 4 | 49.6 ±3.5 | 48.4 ±6.6 | 46.0 ±0.6 |
| 8 | 87.0 ±6.7 | 79.5 ±6.6 | 68.6 ±0.2 |
| 16 | 159.4 ±3.9 | 125.9 ±12.2 | 126.2 ±0.5 |

**jitter, RFC-3550 style (ms)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 1 | 1.84 ±0.23 | 3.90 ±0.63 | 2.38 ±0.59 |
| 2 | 3.26 ±0.23 | 5.39 ±1.27 | 5.14 ±0.23 |
| 4 | 4.94 ±1.03 | 9.86 ±0.26 | 11.66 ±0.43 |
| 8 | 6.71 ±0.10 | 11.59 ±0.63 | 12.03 ±0.51 |
| 16 | 7.75 ±0.95 | 12.32 ±0.81 | 10.45 ±2.26 |

**end-to-end throughput (rows/s)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 1 | 123,933 ±501 | 44,222 ±5,341 | 33,562 ±6,501 |
| 2 | 130,103 ±1,587 | 43,396 ±6,470 | 40,792 ±10,110 |
| 4 | 119,850 ±7,294 | 40,806 ±10,281 | 33,957 ±19,921 |
| 8 | 109,844 ±5,343 | 37,278 ±3,246 | 50,218 ±333 |
| 16 | 113,716 ±1,884 | 40,008 ±506 | 48,908 ±1,218 |

Latency grows ≈ linearly with users for all systems (single shared host): p95 13 → 159 ms (baseline) and 13–20 → 126 ms (proposed/improved) from 1 to 16 users. Jitter grows 3–4× from 1 to 16 users; the proposed systems have roughly 1.6–2.1× the jitter of the baseline (extra hops). End-to-end throughput stays flat (baseline ≈ 110–130 k rows/s, proposed ≈ 37–44 k, improved 34–50 k): the host, not the client count, is the limit.

### Nodes (core replicas)
**end-to-end throughput (rows/s)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 1 | – | 40,592 ±927 | 43,256 ±11,057 |
| 2 | – | 40,664 ±677 | 37,672 ±14,688 |
| 3 | – | 37,014 ±4,454 | 39,112 ±16,893 |
| 5 | – | 39,018 ±1,220 | 44,138 ±6,131 |

**resident memory (MB)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 1 | – | 223 | 204 |
| 2 | – | 272 | 251 |
| 3 | – | 319 | 298 |
| 5 | – | 407 | 390 |

Throughput does **not** scale with replicas (≈ 37–44 k rows/s from 1 to 5): only the leader consumes, and all replicas share two CPUs. Memory grows ≈ 45 MB per replica (223 → 407 MB). The extra replicas buy fault tolerance, not throughput (confirmed hypothesis H4); their cost is Part 3.

### CPU
**end-to-end throughput (rows/s)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 2 CPUs | 115,543 ±1,643 | 41,008 ±411 | 39,424 ±12,463 |
| 1 CPU | 138,406 ±827 | 37,568 ±3,989 | 42,041 ±10,727 |
| 1 CPU shared with busy-loop | 93,760 ±8,268 | 26,079 ±2,357 | 33,331 ±7,577 |

Restricting to one CPU does not hurt anyone much (the load generator and the services were already sharing 2 CPUs); a competing busy-loop costs throughput relative to two free CPUs: baseline 116 → 94 k rows/s (−19 %), proposed 41 → 26 k (−36 %), improved 39 → 33 k (−15 %) — the improved system degrades least, the unimproved proposed system most.

### Memory — a cliff, not a slope
**time to complete 60,000 rows (s)**

| level | baseline | proposed | improved |
|---|---|---|---|
| unlimited | 0.5 ±0.0 | 1.5 ±0.0 | 1.9 ±0.9 |
| 256 | 0.5 | 91.8 ±0.6 | 1.3 ±0.2 |
| 160 | 0.8 ±0.3 | 91.2 ±0.8 | 46.9 ±63.5 |
| 128 | 0.6 ±0.0 | 92.2 ±1.6 | 91.0 ±0.4 |

**rows lost**

| level | baseline | proposed | improved |
|---|---|---|---|
| unlimited | 0 | 0 | 0 |
| 256 | 0 | 0 | 0 |
| 160 | 0 | 21,290 ±4,299 | 0 |
| 128 | 0 | 41,934 ±4,687 | 7,458 ±10,547 |

The baseline is unaffected down to 128 MB (it is a 50 MB process). The **proposed system collapses at every cap, even 256 MB**: 60 000 rows take 91 s instead of 1.5 s, and at 160 / 128 MB 21 k / 42 k rows had not been stored when the trial's 90-second deadline expired (the experiment does not wait longer, so we cannot say whether they would eventually have been stored). The improved system tolerates 256 MB, becomes erratic at 160 MB (one of two trials collapsed: 46.9 ±63.5 s) and takes ≈ 91 s at 128 MB (7 458 ±10 547 rows unstored at the deadline). The cap is `RLIMIT_AS` (address space, not RSS), and the Kafka-style client plus thread stacks reserve a lot of address space; the cause of the slowdown was not isolated further (an untested explanation, not a finding). **This is the proposed design's weakest axis:** all its service processes together (gateway, 3 cores, cloud) hold ≈ 6× the resident memory of the single baseline collector (≈ 320 MB vs ≈ 50 MB).

### Network load (cross-traffic at the entry point)
**request latency p95 (ms)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 0 | 46.8 ±4.6 | 43.2 ±6.3 | 46.2 ±2.1 |
| 2 | 53.4 ±6.8 | 54.0 ±3.3 | 50.5 ±8.5 |
| 8 | 61.3 ±2.6 | 68.1 ±1.8 | 69.0 ±4.5 |
| 16 | 75.9 ±3.3 | 99.5 ±0.5 | 99.9 ±20.6 |

**time to complete (s)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 0 | 0.51 ±0.05 | 1.22 ±0.04 | 1.75 ±0.35 |
| 2 | 0.60 ±0.04 | 2.30 ±0.24 | 3.33 ±0.60 |
| 8 | 0.80 ±0.03 | 2.54 ±0.21 | 3.96 ±1.60 |
| 16 | 0.99 ±0.04 | 3.10 ±0.36 | 4.71 ±1.71 |

Cross-traffic degrades everyone: p95 latency at 16 noise threads is 76 ms (baseline) vs ≈ 100 ms (proposed/improved); completion time grows ≈ 1.9× (baseline), 2.5× (proposed) and 2.7× (improved) from 0 to 16 noise threads. The improved system is *not* better here (its advantage is bytes on a constrained link, and the noise competes for the entry point, not for the edge→core link). Wire-byte comparisons are not reported for this sweep: the proposed systems' link counter also counts the noise bytes, the baseline's does not.

### Request rate and data volume
**time to complete (s)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 2000 | 29.54 ±0.01 | 29.81 | 30.70 ±0.18 |
| 5000 | 11.83 | 12.23 ±0.18 | 12.88 ±0.36 |
| 10000 | 5.93 ±0.01 | 6.21 ±0.02 | 6.20 |
| 20000 | 2.98 | 3.38 ±0.18 | 4.28 ±0.38 |
| 0 | 0.59 ±0.09 | 1.65 ±0.18 | 1.57 ±0.18 |

**time to complete (s)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 10000 | 0.10 ±0.01 | 0.47 ±0.18 | 0.98 ±0.16 |
| 30000 | 0.23 ±0.01 | 0.74 | 0.89 ±0.21 |
| 60000 | 0.50 ±0.01 | 1.47 ±0.04 | 1.83 ±0.21 |
| 120000 | 0.98 ±0.02 | 2.77 ±0.02 | 2.66 ±0.40 |

**bytes on the link (MB)**

| level | baseline | proposed | improved |
|---|---|---|---|
| 10000 | 3.70 | 3.75 | 0.54 |
| 30000 | 11.11 | 11.26 | 1.63 |
| 60000 | 22.23 | 22.53 | 3.17 ±0.01 |
| 120000 | 44.50 | 45.09 | 6.11 |

At paced rates (2 k–20 k rows/s) completion time is set by the pacing and the three systems are within 4 % (2 k rows/s) to 44 % (20 k rows/s: 4.28 s vs 2.98 s for improved vs baseline) of each other. Unpaced, the baseline's per-row cost is lowest (0.59 s vs 1.65 s). Time grows linearly with volume for all systems (10 k → 120 k rows = ≈ ×10 for each); the fixed overhead of the pipeline shows at 10 k rows (0.47 / 0.98 s vs 0.10 s). Bytes on the link scale linearly (and are 7.3× smaller for the improved system).

# Part 3 — Coordination overhead (replicas agreeing on a leader)

Message counters from the core replicas (`results/m12_coordination.csv`; 2 reps; heartbeat 0.5 s; 20 s steady state after replaying 60 000 rows):

| replicas N | heartbeats/s, whole cluster | theory (N−1)/0.5 s | election messages after a leader crash | elections started | bound N² | crash → new leader agreed | leader returns: takeover time / messages |
|---|---|---|---|---|---|---|---|
| 1 | 0 | 0 | – | – | 1 | – | – |
| 2 | 1.95 | 2 | 1 | 1 | 4 | 0.59 s | 1.75 s / 1 |
| 3 | 3.95 | 4 | 2 | 1 | 9 | 0.78–0.84 s | 1.74 s / 2 |
| 5 | 7.7 | 8 | 7 and 19 (two reps) | 2 and 4 | 25 | 0.54–0.60 s | 1.72 s / 4 |

Heartbeat traffic is linear in N (measured within 4 % of theory). Election cost is small for N ≤ 3 (1–2 messages) and varies with timing at N = 5: when several replicas notice the dead leader in the same instant they start overlapping elections (4 in one run, 19 of the 25 worst-case messages); the leader change is nevertheless agreed in ≈ 0.6 s. When the old leader (highest id) restarts, it bullies its way back in ≈ 1.7 s. Combined with the *nodes* sweep above — no throughput gain — the coordination bill is real but small (a few messages per second); the replicas are paid for in memory (≈ 45 MB each), not in network.

# Hypotheses (written before running; outcomes after)
| # | Hypothesis | Outcome |
|---|---|---|
| H1 | On an unconstrained link the improvement costs CPU and gives no throughput gain; baseline is fastest | **partly refuted**: baseline is fastest (0.98 s vs 2.7 s) and the improvement gives no gain (0.99×) — but the improvement does **not** cost extra CPU: it uses *less* CPU-seconds than the unimproved proposed system (2.7 vs 3.4 s unconstrained), because coalescing saves more per-message work than zlib costs |
| H2 | Under a constrained link (≤ 25 Mbit/s) compression cuts bytes ~4–6× and end-to-end time by a similar factor; below the crossover the improved system beats both | **supported** (bytes 7.3× fewer; time 3.6–5.9× less than baseline, 4.3–6.3× less than proposed; crossover ≈ 130 Mbit/s) |
| H3 | Under crashes the flat collector loses availability in proportion to downtime; the proposed system keeps accepting data and loses nothing, at the price of a processing pause | **supported** (63.7 % vs 100 % at 20 crashes/min; 0 rows lost in all systems; pause 0.7–0.9 s). The baseline does not lose *rows* either because its clients retry — what it loses is availability |
| H4 | More replicas do not raise throughput on 2 CPUs but raise coordination overhead | **supported** (flat 37–44 k rows/s; heartbeats linear in N; memory +45 MB per replica) |
| H5 (added) | The proposed system is at least as fast as the baseline | **refuted** at every unconstrained setting: the baseline is ≈ 2.8× faster at most settings (up to 10× at 10 k rows where pipeline start-up dominates) because it has no bus, no replication and no election. The proposed architecture buys availability under failure, and — with the improvement — speed on constrained links. |

# What the evidence supports, and what it does not
* **Supported:** (1) under a constrained edge→core link (≤ 25 Mbit/s) the improved system is 3.6–5.9× faster than the baseline, with 7.3× fewer bytes and less CPU than the unimproved proposed system; (2) under crashes the tiered system's availability is 100 % vs 64–85 % for the flat collector; (3) storage survives datanode loss (R=3), bit rot and an archiver crash with 0 lost rows.
* **Not supported / costs:** on an unconstrained link the tiered system is ≈ 2.8× *slower* than the flat collector and holds ≈ 6× the memory; the memory cliff (collapse at 256 MB for the proposed system) is a real weakness; adding replicas does not add throughput.
* **Consequence for the architecture choice:** the tiered design is justified by availability and by constrained links, not by raw speed. A deployment with an abundant link and rare failures would be better served by the baseline.

# Failure-driven engineering log (week 12)
| Question | Answer |
|---|---|
| What changed? | DFS (namenode/datanodes/checksums/re-replication), archiver to DFS + object store, adaptive coalescing + zlib, the capstone harness (driver, shared emulated link, cross-traffic, probe, chaos, sampler), coordination measurements. |
| What failed? | (1) **DFS reads failed with "chunk unavailable"** on larger files. (2) **Heal time showed 0.0 s.** (3) **Capstone trials aborted: "cloud/core exited early".** (4) The first capstone run was lost when the VM restarted. (5) The coordination experiment first reported *negative* election-message counts. (6) A cost/WAN scoring error (see M8). |
| Why? | (1) the namenode's orphan GC treated chunks of a file still being written as orphans and deleted them; (2) the timer started before the namenode had noticed the death, so "under-replicated = 0" was trivially true; (3) service ports 37 000+ lie inside Linux's ephemeral range (32 768–60 999) and collided with client sockets; (4) no checkpointing; (5) the "before" count included the killed leader's counters and "after" did not. |
| How fixed? | (1) pending-chunk grace period (`PENDING_TTL_S`) + regression test; (2) wait until the victim is declared dead, then until `under_replicated == 0`, and report both times; (3) ports moved to 20 000–25 000; (4) trials append to the raw CSV and the sweep is resumable (`done_keys()`); (5) compare survivors only. |
| Alternative considered | For (3) disable the ephemeral range via sysctl — rejected: not reproducible on someone else's machine. |
| What was learned? | A garbage collector needs a notion of "not yet committed"; measure a recovery from the moment the failure is *observed*, not injected; long experiments must be resumable; port allocation is part of the experiment design. |

# Limits (honest)
* **Single 2-vCPU host, loopback network.** Users, load generator, edge, core, cloud and storage compete for the same CPUs. Bandwidth, CPU, memory, failure and cross-traffic are *emulated* (token bucket, affinity, `RLIMIT_AS`, SIGKILL, threads); real WAN latency, packet loss and multi-host effects are not measured.
* **Kafka:** measured on `LocalBus`, a durable, partitioned, offset-committing log with Kafka's producer/consumer interface — not on a Kafka broker. `KafkaBus` and the compose file are unexecuted (`docs/run_with_docker.md`). The MinIO path is likewise the local stand-in.
* **Power BI:** the report is specified (queries, measures, layout, previews) but the `.pbix` was not built.
* **Statistics:** n = 2–3 per cell; CIs are wide (see `results/m12_capstone_summary.csv`); several differences (e.g. nodes sweep, CPU sweep) are inside the noise and are described as such.
* **CPU readings** during crash trials are unreliable (restarting processes); memory-cap results are for address-space limits, not cgroup limits.
* Rows are "lost" in a trial only if not stored by the trial's deadline (90 s); the experiment does not establish eventual loss.
