# Distributed Network Monitoring System — Technical Report
**ICS 2403 Distributed Computing · Theme 2 · Telecommunication & Information Engineering**
Repository: `rachealndirangu/-ics2403-distributed-network-monitoring---week-1` (branch `complete-system`)

> **How to read this report.** It follows the 30 sections required by brief §11.3. Each section is short and points to the milestone document (`docs/milestones/NN-*.md`) and the result files that hold the evidence. All numbers are from `results/`; the capstone tables are generated from the raw trial data (`results/m12_tables.md`). What was *not* done or *not* measured is stated in §28.

---

## 1. Introduction
A telecom operator watches thousands of cell sites. Each site emits telemetry (latency, jitter, CPU, memory, bandwidth, packet loss) every few seconds; the operator needs the data collected reliably, anomalies found quickly, and the history stored durably — while nodes crash, links saturate and load grows. This project builds that system as a sequence of twelve distributed-computing milestones and evaluates the finished system against the simple design it started from.

The finished system is `Users/Devices → Edge → Telecom Core → Cloud → Distributed Storage` (§7). It is built, measured and — where the measurements were unflattering — reported as such.

## 2. Problem Statement
Design, implement and evaluate a distributed network-monitoring system that (a) ingests ≥ 100 000 telemetry rows from many sources, (b) keeps working through node crashes, message loss and overload, (c) hides distribution from applications where that is worth its cost, and (d) can be shown — by experiment, not assertion — to improve on a flat collector in at least one meaningful respect.

## 3. Research Questions
| # | Question | Answered in |
|---|---|---|
| RQ1 | How much of the end-to-end cost is communication, and how does it scale with message size, batching and link bandwidth? | §10, §22, §27 |
| RQ2 | Which coordination mechanisms (election, ordering, commit, locking) keep the system correct under failure, and what do they cost? | §9, §11, §12 |
| RQ3 | What availability and recovery time does replication buy, against which faults? | §13, §14, §23 |
| RQ4 | Which of the five distributed-system models fits a telecom monitoring workload, and how sensitive is that choice to cost? | §6, M8 |
| RQ5 | What does hiding location, replication, migration and failure cost? | §15–§18, M9 |
| RQ6 | Does the tiered architecture with an edge-side improvement beat a flat collector — where, by how much, and where not? | §26, §27 |

## 4. System Requirements
**Functional.** FR1 ingest a 120 000-row dataset from several edge nodes; FR2 detect anomalies per site; FR3 store all rows durably and exactly once per `record_id`; FR4 archive to a distributed file system and an object store; FR5 keep serving when a node dies; FR6 expose naming, process management, RPC and shared state as services.
**Non-functional.** NFR1 availability under crashes; NFR2 bounded recovery time; NFR3 correctness (no lost or corrupt rows); NFR4 measurable latency/throughput/jitter, CPU/memory/bandwidth; NFR5 reproducibility (`docs/reproducibility.md`).
**Lecturer's additions.** ≥ 100 000-row dataset ✔ (120 000, `data/`); Kafka (or Hadoop/Hive) between edge node and core ✔ in code and compose, measured on a stand-in (§28); a Power BI file with 2–4 charts — specified and previewed, `.pbix` to be assembled in Power BI Desktop (`powerbi/`).

## 5. Literature Review
The design choices follow established work; none of it is reproduced here beyond what was implemented.
* **Foundations.** Tanenbaum & van Steen, *Distributed Systems: Principles and Paradigms*; Coulouris, Dollimore, Kindberg & Blair, *Distributed Systems: Concepts and Design* — the system models (host, workstation, server, pool, integrated), transparency taxonomy, naming and RPC semantics.
* **Time and order.** Lamport, "Time, Clocks, and the Ordering of Events in a Distributed System" (CACM, 1978) → logical clocks (§9).
* **Election.** Garcia-Molina, "Elections in a Distributed Computing System" (IEEE Trans. Computers, 1982) → Bully algorithm (§9).
* **Commit.** Gray, "Notes on Database Operating Systems" (1978); Skeen, "Nonblocking Commit Protocols" (SIGMOD 1981); Gray & Lamport, "Consensus on Transaction Commit" (ACM TODS, 2006) → 2PC/3PC (§11).
* **Deadlock.** Coffman, Elphick & Shoshani, "System Deadlocks" (ACM Computing Surveys, 1971) → four conditions, prevention vs detection (§12).
* **Replication and Byzantine faults.** DeCandia et al., "Dynamo" (SOSP 2007) → quorum, hinted handoff, read repair, anti-entropy; Lamport, Shostak & Pease, "The Byzantine Generals Problem" (ACM TOPLAS, 1982) → N ≥ 3f+1 (§14). Ongaro & Ousterhout, "In Search of an Understandable Consensus Algorithm" (USENIX ATC 2014) is the consensus alternative we did **not** implement (§29).
* **Logs and storage.** Kreps, Narkhede & Rao, "Kafka: a Distributed Messaging System for Log Processing" (NetDB 2011); Ghemawat, Gobioff & Leung, "The Google File System" (SOSP 2003); Shvachko et al., "The Hadoop Distributed File System" (MSST 2010) → §10, §19.
* **RPC, DSM, naming.** Birrell & Nelson, "Implementing Remote Procedure Calls" (ACM TOCS, 1984); Li & Hudak, "Memory Coherence in Shared Virtual Memory Systems" (ACM TOCS, 1989); Mockapetris, RFC 1034/1035 (DNS) → §15–§18.
* **Metrics.** Jain, Chiu & Hawe, "A Quantitative Measure of Fairness and Discrimination" (DEC TR-301, 1984) → fairness index; Schulzrinne et al., RFC 3550 → the jitter estimator.

*(Bibliographic details are given as author, title, venue, year; verify page numbers before submitting.)*

## 6. Distributed System Model
* **Nodes and processes:** OS processes on one host (§28); each has its own address space, SQLite file or directory, and a fixed port. A node is *crash-recovery*: it may be killed (SIGKILL) and restarted, keeping its durable state.
* **Network:** loopback TCP/HTTP — reliable and fast, so message loss, delay and partitions are *injected* (`system/common/faults.py`: drop, delay, 5xx, hang, Byzantine replies) rather than occurring.
* **Timing:** partially synchronous — no clock synchronisation is assumed (clock skew is injected and handled with Lamport clocks, M4); failure detection uses timeouts and therefore can be wrong (a slow node looks dead).
* **Failures considered:** crash, omission, hang, communication, service-down, application error, Byzantine replies (§13).
* **Architectural model (M8).** The five models were simulated on the same workload: host-based, workstation, server-based, processor pool, integrated. With every core priced the **processor pool** wins all four weightings; with site-owned edge hardware free the **integrated** model wins three of four (workstation wins when cost dominates) (`docs/milestones/08-*.md`). The built system is the integrated model: edge pre-aggregation and a pool of core replicas.

## 7. System Architecture
```
Users / IoT / telecom devices ─► EDGE (agents, replayers → gateway: validate · batch · back-pressure · [coalesce + zlib])
   ─► log (Kafka interface; partitioned by site) ─► COORDINATION + PROCESSING (3 core replicas, Bully leader, Lamport stamps)
   ─► TRANSACTION & STATE (per-replica SQLite, 2PC/3PC quota moves, quorum KV, DSM, locks) ─► TELECOM CORE (anomaly detection, alerts)
   ─► CLOUD (fleet digest, archiver) ─► DISTRIBUTED STORAGE (HDFS-style DFS + S3-style object store)
   cross-cutting: naming · process management · RPC · transparency · fault injection · monitoring/evaluation
```
Details, service table and milestone-to-code map: `docs/architecture.md`, `docs/milestones/03-*.md`. Styles evaluated in M3: client–server (the baseline), multi-tier (the backbone), SOA (HTTP contracts), microservices (independent failure domains, kept coarse because each hop costs latency).

## 8. Mathematical Model
Notation: *n* replicas/nodes, *B* link bandwidth, *S* bytes to transfer, *f* crashes per minute, *d* downtime per crash, *a* availability of one replica.

**Link-bound vs CPU-bound delivery (§27).** `T(B) ≈ max(T_cpu, 8·S/B)`. The baseline sends *S₀* = 44.5 MB (120 000 rows) so `T₀(B) ≈ 356 Mbit / B` once the link binds (measured 14.3 s at 25 Mbit/s, 35.7 s at 10, 71.3 s at 5). The improved system sends *S₁* = 6.1 MB but has a processing floor *T_cpu* ≈ 2.7 s. They cross at `B* = 8·S₀ / T_cpu ≈ 356 / 2.76 ≈ 130 Mbit/s`; measured: 1.24× faster at 100 Mbit/s, 0.36× at unlimited.

**Availability of the flat collector under crashes.** Downtime fraction `1 − A = f·d/60`. With *d* ≈ 1.2 s (1 s restart delay + start-up) the model predicts A = 88 %, 76 %, 60 % at *f* = 6, 12, 20; measured 84.8 %, 77.6 %, 63.7 % (±4 points: the probe's sampling and in-flight requests are not modelled).

**Replicated availability.** With a quorum of *W = R = ⌈(n+1)/2⌉* replicas, the service is up when at least that many are up: for n = 3, `A = 3a² − 2a³` (a = 0.95 → 0.993). With one injected crash in a 12 s run the measured availability was 100 % vs 56.6 % for a single instance (M7). Strong read-your-writes holds iff `W + R > n`.

**Byzantine + crash budget.** Majority voting over R replicas masks `⌊(R−1)/2⌋` wrong answers but needs all R replicas alive, so with N = R = 3 one crash removes availability (measured 56.7 %, the counter-example in M7). For one crash *and* one Byzantine replica the working configuration was **N = 4, W = R = 3** (the 3f+1 rule with f = 1), confirmed at 100 % availability and 100 % correctness. We make no claim beyond f = 1.

**Queueing at the collector (M2).** Throughput saturates at the service rate μ of the single process; for an M/M/1 view `W = 1/(μ − λ)`, so latency grows without bound as λ → μ. Measured: 73–93 k rows/s service rate, latency 6.9 → 21.7 ms as clients go 1 → 4.

**Election cost (M4, M12).** Heartbeats: `(n − 1)/τ` messages/s for interval τ (measured 1.95, 3.95, 7.7 per s for n = 2, 3, 5 at τ = 0.5 s vs theory 2, 4, 8). Bully elections: O(n) best case, O(n²) worst case (bound 4, 9, 25); observed 1, 2 and 7–19 messages after a leader crash for n = 2, 3, 5.

**Commit cost.** 2PC: 3 message rounds (prepare, vote, decide); 3PC adds pre-commit: 5 rounds. Measured latency +46…+74 % (M5).

**Fairness.** Jain index `J = (Σxᵢ)² / (n·Σxᵢ²)` ∈ [1/n, 1]; 1.00 in M2 (even assignment).

**Jitter.** Both the sample standard deviation of latency and the RFC 3550 estimator `J ← J + (|Dᵢ| − J)/16` over successive latency differences are reported.

## 9. Distributed Algorithms
| Algorithm | Where | Result |
|---|---|---|
| **Bully election** + heartbeats (miss limit 2) | `core/service.py` | exactly one leader in 0 split-brain samples; failover ≈ 1.05–1.3 × the heartbeat interval (0.33 s at 0.25 s … 2.09 s at 2 s); worst-case messages grow ≈ quadratically but stay under n² |
| **Lamport clocks** | `common/lamport.py` | with ±3 s skew wall-clock ordering violated causality in 33.6 % of 113 traces, Lamport ordering in 0 % |
| **Leader-only consumption, commit-after-persist, idempotent insert** | `core/service.py` | leader crash during a 120 000-row stream: 0 rows lost; 0–2 416 duplicate rows across replicas (de-duplicated on `record_id`) |
| **Quorum replication, hinted handoff, read repair, anti-entropy** | `replication/` | M7, §14 |
| **2PC / 3PC** with ordered prepare | `txn/` | §11 |
| **Wait-for-graph deadlock detection**, ordered locking, wait-die | `concurrency/` | §12 |
| **4-phase migration** | `transparency/layer.py` | 0 lost writes vs ≈ 6 % for naive copy-then-switch |
| **Namenode re-replication, checksummed chunks** | `storage/` | §19 |

## 10. Communication Architecture
* **Edge → core:** a partitioned, durable, replayable log (topic `edge.telemetry`, partition = site). The gateway acknowledges an edge request only after the append; consumers commit offsets after persisting (at-least-once). This is the Kafka role; `KafkaBus` (confluent-kafka) and `LocalBus` share one interface. **All measurements ran on `LocalBus`.**
* **Core → cloud → storage:** HTTP digest to the cloud, topic `core.processed` to the archiver, which writes gzip-CSV objects to the DFS and the object store.
* **Control plane:** HTTP/JSON between services; RPC framework with three call semantics, REST and gRPC servers (§17).
* **Costs (M1, M11):** ≈ 1.6 ms fixed per HTTP message on loopback, ≈ 2× for 1 MB; gRPC/protobuf 3× faster for small calls, 10× for batches, 2.7× fewer bytes than JSON; batching 100 rows/message ≈ 1.4× throughput of 10 rows/message (M3).

## 11. Transaction Management (M5)
Quota moves between sites held by different participants are zero-sum transactions; the total quota (3 400 020) is the invariant. ACID: atomic (one SQLite transaction per participant), consistent (no negative quota → vote NO), isolated (strict 2PL, locks taken at prepare), durable (`synchronous=FULL`, decision forced before it is sent).
* Without a protocol and one resource manager down, 20 transfers **destroyed 200 Mbps of quota**; with 2PC or 3PC 20/20 aborted and nothing was lost.
* **2PC blocks, 3PC does not:** coordinator crash after prepare leaves 2PC participants blocked until restart (> 9 s, 3 locks held); 3PC participants resolve in ≈ 2 s via the termination rule. Cost of 3PC: +46…+74 % latency.
* **Distributed deadlock** (parallel prepare, 16 clients, hot account): 9 of 240 committed. **Ordered prepare** → 240/240 at 103 tps (0.6 → 103 tps).
* Participant crash while in-doubt: recovers its locks from the log and resolves via the coordinator (1.5 s) or a peer (1.7–1.9 s); invariant held in all cases.

## 12. Concurrency Management (M6)
Lock manager with a resource-allocation graph (`results/m06_rag_*.png`) and policies none / timeout / **detect** / **ordered** / **wait-die**. Race without mutual exclusion lost 61 % of updates (489 of 800). Four services in a circular wait: "none" completed 0–1 of 20; timeout-only 3, 20, 3 (luck); **detect+recover 20/20 in 1.27 s** (cycle found in 0.14 s); **ordered 20/20 in 1.10 s**; wait-die 20/20 in 1.21 s with 29 restarts. Barging starved a whole-pool request (never granted in 6 s, 3/3), FIFO granted it in ≈ 0.1 s. A 4-unit pool saturates at 171 req/s (85 % of the 200 req/s bound).

## 13. Fault Model
Crash (SIGKILL), hang (SIGSTOP), omission (50 % of requests never answered), communication (traffic dropped/held), service failure (HTTP 503), application error (HTTP 500), Byzantine (plausible wrong values), disk-level corruption of stored chunks, and — in the capstone — repeated core crashes at 0–20 per minute, memory caps, cross-traffic, constrained bandwidth. Injection: `common/faults.py` (`POST /fault`) and process-level control in `scripts/cluster.py`.

## 14. Fault-Tolerance Mechanism (M7)
Failure detection by timeouts with suspicion after 2 consecutive failures (detection time 0.02 s for crash/503 … 1.28 s for omission); replication N=3, W=R=2; failover by the client; recovery by hinted handoff, read repair and 0.5 s anti-entropy (restarted replica caught up in 0–0.23 s); majority vote for Byzantine replies.
Availability (%): single instance 56.6 (crash), 94.6 (hang), 93.9 (omission), 93.6 (communication), 58.5 (service down), 68.1 (app error); **replicated 100 in every case**. Byzantine correctness: single 58.3 %, plain quorum 75.8 %, vote 100 %. Design lesson: a vote over N=3 sacrifices crash tolerance (56.7 %); tolerating one crash **and** one Byzantine replica needs **N=4, W=R=3** (100 %/100 %).
**Where it matters at system level:** 100 % ingest availability for the tiered system at 6–20 crashes/min vs 84.8 → 63.7 % for the flat collector (§23).

## 15. Naming Architecture (M10)
`Name → Name Resolution → Resource Location` with four schemes (`naming/`): static map, broadcast, central name server, hierarchical prefix resolver (DNS-style referrals, prefix table, answer cache).
Resolution (8 nodes): static 0 ms; broadcast 9.4 ms / 8 messages (31.3 ms / 24 messages at 24 nodes); central 0.025 ms (98 % cache hits); prefix cold 5.1 ms / 3 messages; prefix table 1.7 ms / 1 message; prefix table + cache **0.004 ms**. Table size barely matters (100 000 names: 1.7 ms). After a resource moves: static map stale forever; TTL cache stale for exactly the TTL (1.01 s, 5.01 s; 14 %, 71 % stale answers). Naming-service failure: central down → 0 % for central clients; root down → 0 % for cold prefix clients but 100 % with a prefix table; one regional server down → that region only (83 %).

## 16. Process Management (M10)
`Create → Locate → Schedule → Coordinate → Terminate` (`procman/`): node agents spawn worker processes registered in the name service; a controller schedules (round-robin / random / least-loaded), coordinates with a barrier and re-schedules on node death. With one slow node: least-loaded 10.9 s vs round-robin 13.6 s vs random 14.7 s (20–26 % faster). Node killed mid-job: 24/24 workers completed; recovery 10 s vs a 9.4 s control **after** fixing a stale name binding that had made it 62 s (§25).

## 17. RPC Architecture (M11)
Client → client stub → network → server stub → server (`rpc/`). Call semantics under 30 % reply loss, 200 non-idempotent increments: *maybe* — 71 calls reported failure though executed; *at-least-once* — counter over-counted by 49 %; ***at-most-once* (request-id reply cache) — exact**. gRPC vs REST: 0.52 vs 1.53 ms (small), 2.1 vs 22.1 ms (5 000 readings), 395 kB vs 1.07 MB; gRPC server-streaming was the slowest for 10 000 tiny messages (681 ms vs 50–138 ms) — reported, not fixed.

## 18. Distributed Memory / State (M11, M9)
Object-granularity DSM with home-node directory, MSI-style states, **strong** (write-invalidate) and **eventual** (write-update) modes, distributed lock and atomic add (`dsm/`). Strong: 0 % stale reads, write latency 1.65 → 7.3 ms with 0 → 3 sharers; eventual: flat 3.9–4.3 ms, **10 %** stale immediate reads, more messages under write-heavy load (1.5 vs 1.1 per op). Plain read-modify-write lost **84 %** of updates even on the strong memory; lock: exact but 4.5 messages/increment; **atomic add at the home: exact, 7× faster, 5.6× fewer messages**. The transparency layer (M9) presents replicated state as logical resources: 1.7× read / 1.9× write overhead, 100 % availability vs 57 % under a replica crash.

## 19. Distributed Storage (M12)
HDFS-style DFS: namenode (namespace, chunk map, heartbeats, re-replication, orphan GC with a pending-chunk grace period), datanodes (per-chunk SHA-256 verified on read), pipelined replication. Write throughput ∝ 1/R (256 KB chunks: 58.5 / 29.7 / 19.1 MB/s for R = 1/2/3), reads unaffected (≈ 90 MB/s at 256 KB, 205 MB/s at 4 MB). R=3 loses **0 chunks** with two simultaneous datanode losses and heals in ≈ 4 s; R=2 loses 4 of 16. 20 corruption injections → 0 corrupt reads. End-to-end: **120 000 / 120 000 ids in both the DFS and the object store**, also when the archiver is killed at ≈ 50 % and restarted.

## 20. Implementation
Python 3.13; Flask services, SQLite (WAL), `requests`, gRPC, confluent-kafka (client only), psutil. 57 Python modules under `system/` (40 services/libraries + 17 experiment drivers and helpers) (see `docs/architecture.md`), 26 tests (`tests/`: unit + integration with real processes), experiment drivers `system/experiments/m01…m12_*`, Power BI definition under `powerbi/`. The harness (`scripts/cluster.py`) starts, kills, pauses and restarts processes, pins CPUs and caps memory so that a laptop can emulate a multi-node deployment. Reproduction: `docs/reproducibility.md`.

## 21. Experimental Methodology
Hypothesis → design → implementation → measurement → analysis → conclusion for every milestone; hypotheses are written in the experiment's docstring **before** running, and outcomes are recorded as supported / refuted / conditional (including refuted ones — H5 of M12, and H1 of M12 which turned out to be partly wrong). One-factor-at-a-time sweeps around a centre point; 2–3 repetitions per cell (253 capstone trials), mean ± sd and 95 % CI; every failure experiment has a no-failure control. Metrics: latency (mean/p95/p99), jitter (sd and RFC 3550), throughput, CPU, memory, bytes, availability (100 ms write probe), MTTR, request failure rate, rows lost/duplicated, coordination messages. Datasets: seeded and hash-checked.

## 22. Performance Evaluation
* **Processing (M2):** distributing the detector by shipping rows is *slower* (0.71–0.99×); moving computation to the data gives 1.6× on 2 workers (4 workers on 2 CPUs: 1.44×). The flat collector saturates at ≈ 73–93 k rows/s, latency 6.9 → 21.7 ms from 1 to 4 clients.
* **Architecture (M3):** tiering cuts messages reaching the upper tier 10× (500 → 50) and keeps 400 agents healthy with two gateways (0 failures, p99 486 ms vs 3.1 s flat); a single gateway is slightly *worse* than flat at low load.
* **Capstone, unconstrained link:** the baseline delivers 120 000 rows in 0.98 s; proposed 2.72 s; improved 2.76 s — **the baseline is ≈ 2.8× faster** when bandwidth is free. With 4 clients p95 latency is 45 / 44 / 42 ms (baseline / proposed / improved); jitter 4.9 / 9.9 / 11.7 ms.
* **Users:** p95 latency 13 → 159 ms (baseline) and 13–20 → 126 ms (tiered) from 1 to 16 users; throughput flat (host-limited).
* **Request rate, data volume:** paced rates leave the three systems within 4–44 %; time grows linearly with volume.

## 23. Reliability Evaluation
| crashes/min | availability % baseline | proposed | improved | request attempts failing (baseline) | MTTR baseline / proposed |
|---|---|---|---|---|---|
| 0 | 100 | 100 | 100 | 0 | – |
| 6 | 84.8 | 100 | 100 | 23.1 % | 1.23 s / 0.69 s |
| 12 | 77.6 | 100 | 100 | 31.0 % | 1.21 s / 0.88 s |
| 20 | 63.7 | 100 | 100 | 42.9 % | 1.23 s / 0.76 s |
No rows were lost by any system (the driver retries); the flat collector's cost is availability and latency. Transport under 12 crashes/min: bus and direct HTTP both 100 % available, 0 rows lost. Storage: §19. Consistency: stored `record_id`s verified against the dataset in every capstone trial.

## 24. Scalability Evaluation
* **Clients:** latency linear in users on a shared host; throughput flat (§22).
* **Replicas:** throughput does not scale with core replicas (37–44 k rows/s for 1–5); memory +≈ 45 MB per replica; heartbeats grow linearly; elections stay cheap for n ≤ 3 (1–2 messages) and vary (7–19) at n = 5.
* **Sites (simulated, M8):** flat host collapses (completion 100 → 14.7 % from 24 to 192 sites); integrated/pool/workstation keep ≥ 99.9 %, throughput 10.6 → 170 jobs/s linearly.
* **Names:** a 100 000-name server answers in 1.7 ms. **Data volume:** linear.
* **Honest limit:** all live scalability results come from one 2-vCPU host, so they show *where the architecture stops scaling*, not how it would scale on separate machines.

## 25. Failure Analysis
Every failure found during development is in `docs/engineering-log.md`; the ones that changed the design: the HTTP-retry design that could lose an in-flight chunk (→ durable log); distributed deadlock in 2PC (→ ordered prepare); the vote that needed N=4 (→ 3f+1); the resurrected delete (→ tombstones); the stale cached name that stretched a node-failure recovery from ≈ 10 s to 62 s (→ invalidate on re-placement); the orphan GC that deleted live chunks (→ pending grace); the ephemeral-port collision (→ ports < 32 768). **Failures of the evaluation itself** (also logged): a migration test that could not detect lost writes, a decision matrix that double-counted WAN cost and flattered the chosen architecture, a failure experiment with no control, a run that never executed because the CLI ignored its second argument.
**Capstone failure boundaries:** memory caps — the proposed system collapses at every cap down to 256 MB (60 000 rows in ≈ 91 s instead of 1.5 s), the improved one at 160 MB; cross-traffic raises p95 latency ≈ 2.2× at 16 threads for the tiered systems vs 1.6× for the baseline.

## 26. Baseline Comparison
| Dimension | Baseline (flat collector) | Proposed (tiered) | Improved |
|---|---|---|---|
| Unconstrained link, 120 000 rows | **0.98 s** | 2.72 s | 2.76 s |
| 25 Mbit/s link | 14.29 s | 17.35 s | **4.03 s** |
| 5 Mbit/s link | 71.26 s | 75.84 s | **11.99 s** |
| Bytes on the link | 44.5 MB | 45.1 MB | **6.1 MB** |
| Total CPU-seconds (5 Mbit/s) | **2.87** | 12.39 | 4.00 |
| Ingest availability at 20 crashes/min | 63.7 % | **100 %** | **100 %** |
| Resident memory (all service processes) | **≈ 50 MB** | ≈ 320 MB | ≈ 300 MB |
| Memory cap 256 MB (60 000 rows) | **0.5 s** | 91.8 s | 1.3 s |
| Single points of failure | collector | none for ingest | none for ingest |
The baseline wins on raw speed, CPU and memory; the tiered system wins on availability; the improvement wins on constrained links. None of the three dominates.

## 27. Proposed Improvement
**Adaptive site-affine coalescing + zlib on the edge→core link** (`edge/gateway.py`, `ADAPTIVE`, `COMPRESS`, `COALESCE_MS`). Rows of the same site are merged into larger messages when a backlog exists (bounded wait), and batches are compressed.
*Evidence:* at ≤ 25 Mbit/s it delivers 120 000 rows **3.6× / 4.6× / 5.9×** faster than the baseline (25 / 10 / 5 Mbit/s) and 4.3× / 5.0× / 6.3× faster than the unimproved tiered system; bytes on the link fall 7.3× (compression ratio 6.6:1); it uses *less* CPU than the unimproved tiered system at every bandwidth (e.g. 4.0 vs 12.4 CPU-s at 5 Mbit/s). *Where it does not help:* unconstrained link (0.36× of baseline, equal to unimproved), cross-traffic at the entry point, memory-starved cores. Crossover ≈ 130 Mbit/s (§8). This is the contribution that is *supported by experimental evidence*; the architecture's availability advantage (§23) is a property of the tiered design, not of the improvement.

## 28. Limitations
1. **One 2-vCPU host, loopback network.** Everything competes for the same two CPUs; WAN latency, loss and multi-host effects are absent. Bandwidth, CPU, memory, failure and cross-traffic are *emulated*.
2. **Kafka and MinIO were not run.** Measurements use `LocalBus`/`LocalStore`; `KafkaBus`, `MinioStore`, `docker-compose.system.yml` are written but unexecuted (no Docker daemon) — `docs/run_with_docker.md` lists what to check first.
3. **No `.pbix`.** Power BI Desktop is Windows-only; the report is specified in `powerbi/` (Power Query, DAX measures, layout, preview images).
4. **Small samples:** n = 2–3 per cell; many differences (nodes, CPU sweeps) are within noise and are described as such.
5. **M8 is simulated** for four of five models and rests on stated assumptions (`HEAVY` = 40, WAN speed, unit costs); its conclusion depends on whether edge hardware is priced.
6. **Memory results** are for address-space limits (`RLIMIT_AS`), the cause of the proposed system's collapse was not isolated; **CPU readings** in crash trials are unreliable.
7. **Consensus** is not implemented (Bully assumes reliable failure detection; a partition could create two leaders); exactly-once processing is not provided (at-least-once + idempotent insert).
8. **Security** (authentication, encryption, authorisation) is out of scope.

## 29. Future Work
Run the compose stack against a real Kafka broker and MinIO and repeat the bandwidth/failure sweeps there (`tc` for bandwidth, `docker kill` for failures); multi-host deployment; replace Bully by Raft; transactional offset+write for exactly-once; find and fix the proposed system's memory cliff; async gRPC server and batching for streaming; erasure-coded storage; real operator telemetry; a closed-loop controller that switches coalescing/compression on measured bandwidth; build and publish the `.pbix`.

## 30. Conclusion
A twelve-milestone distributed monitoring system was built, tested (26 tests) and measured (253 capstone trials plus per-milestone experiments), and it behaves as the theory predicts where the theory is clear: 2PC blocks and 3PC does not, a vote needs 3f+1, anti-entropy resurrects naive deletes, caches decide recovery time, replication tolerates R−1 losses. Against a flat collector the tiered architecture is **not faster** (≈ 2.8× slower and ≈ 6× the memory on an unconstrained link) but is **available** (100 % vs 64 % at 20 crashes/min), and with the proposed adaptive-coalescing-plus-compression improvement it is **3.6–5.9× faster on constrained links** while sending 7.3× fewer bytes. The honest summary is a trade-off, supported by evidence, with its limits — one small host, emulated variables, stand-in Kafka — stated rather than hidden.
