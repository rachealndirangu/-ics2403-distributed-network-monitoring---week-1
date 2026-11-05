# Adaptive Coalescing and Compression on the Edge-to-Core Link of a Tiered Telecom Monitoring System: Where It Helps and What a Tiered Design Costs

**[Student name(s)] · ICS 2403 Distributed Computing · Telecommunication & Information Engineering**

## Abstract
Network-monitoring pipelines commonly replace a single flat collector with an edge–core–cloud hierarchy joined by a durable log. We built such a system (edge gateway → partitioned log → three Bully-coordinated core replicas → cloud → HDFS-style storage) and compared it with the flat collector it replaces, over 253 controlled trials that vary nine factors (nodes, users, bandwidth, CPU, memory, network load, failure rate, request rate, data volume) on a 120 000-row telemetry dataset. We propose one change to the tiered design — **adaptive site-affine coalescing of rows into larger messages plus zlib compression on the edge→core link** — and show that, when the link is constrained (≤ 25 Mbit/s), it delivers the dataset **3.6–5.9× faster than the flat collector** and 4.3–6.3× faster than the unmodified tiered system, sending **7.3× fewer bytes** and using *less* CPU than the unmodified tiered system. We also report what the evidence does **not** support: on an unconstrained link the tiered design is ≈ 2.8× slower than the flat collector and holds ≈ 6× the memory, it collapses under a 256 MB address-space cap, and extra core replicas add no throughput; its benefit is availability (100 % vs 64 % at 20 crashes per minute). All results come from one 2-vCPU host with emulated bandwidth, CPU, memory and failures, and from a file-backed stand-in for the Kafka log; we state what that does and does not license.

**Keywords:** distributed monitoring, edge computing, telemetry batching, compression, availability, Kafka, replication.

---

## I. Existing Method ≠ Our Implementation ≠ Our Contribution
The three are kept apart throughout.

| | What it is | Source | Status here |
|---|---|---|---|
| **Existing method** | (a) A flat collector: clients push to one server that validates and stores. (b) Tiered monitoring: edge aggregation, a durable partitioned log (the role Kafka plays), replicated stateful processors with leader election, replicated distributed storage. (c) Batching and compression of telemetry in general. | Standard practice and literature (§VIII) | **Not claimed as ours** |
| **Our implementation** | A working version of (a) and (b) written from scratch for the course: Flask services, SQLite, a Bully election, Lamport clocks, a `Kafka`-interface log (measured on a file-backed implementation), an HDFS-style DFS, plus the test and measurement harness. | `system/`, `tests/` | **Engineering work; the baseline and the "proposed" system of §V** |
| **Proposed contribution** | **Adaptive site-affine coalescing + zlib compression on the edge→core link**, bounded by a wait limit, switched on by backlog; and its *measured operating envelope* — where it wins, where it does not, and the cost of the tiered design it is added to. | `system/edge/gateway.py` (`ADAPTIVE`, `COMPRESS`, `COALESCE_MS`); evidence: `results/m12_*` | **Our claim, tested in §VI** |

We do **not** claim a new election algorithm, a new storage system, or that batching or compression is new. The claim is narrower: for *this* telemetry on a *constrained* edge→core link, coalescing rows *by site* under backlog and compressing the result is a large, measured win that costs no extra CPU relative to the unmodified tiered pipeline, and the same measurements bound where it is useless.

## II. Introduction
Operators monitor thousands of cell sites; each emits small, frequent readings. The naive design — every probe posts to one collector — is simple and fast, but the collector is a single point of failure and a single bottleneck. Hierarchical designs add edge gateways and a durable log to decouple producers from consumers and replicate the processors. Two questions are rarely answered with data from the same system: *what does the hierarchy cost* when everything is healthy, and *when does an edge-side optimisation repay it?* We answer both for one system. Contributions: (1) the proposed coalescing-plus-compression improvement; (2) a controlled comparison of flat, tiered and improved tiered systems over nine factors, including negative results; (3) the engineering lessons — a stale cached name that tripled recovery time, a delete resurrected by anti-entropy, a decision matrix that double-counted a cost — that affected the evaluation's validity (`docs/engineering-log.md`).

## III. Our Implementation (the systems compared)
All three systems ingest the same 120 000-row seeded telemetry set (24 sites, 1.49 % anomalous) through the same client driver.

* **baseline-flat.** Clients POST chunks to one collector (validate + SQLite). No log, replicas or election.
* **proposed.** Edge gateway → partitioned durable log (partition = site; offsets committed after persistence; at-least-once) → 3 core replicas, one Bully-elected leader consuming (heartbeat 0.5 s; Lamport stamps) → idempotent per-replica SQLite (`INSERT OR IGNORE` on `record_id`) → cloud digest; archiver → DFS (namenode + datanodes, R = 3, per-chunk SHA-256) and object store. Messages carry a fixed 100 rows, uncompressed.
* **proposed + improved.** As above with the contribution of §IV.

Supporting subsystems (tested, measured in their own milestone reports): quorum-replicated store with hinted handoff / read repair / anti-entropy and majority-vote reads, 2PC/3PC with ordered prepare, lock manager with deadlock detection, hierarchical naming, process scheduling, RPC with at-most-once semantics, DSM, a transparency layer with 4-phase live migration.

## IV. Proposed Contribution
**Observation.** Telemetry rows arrive time-ordered across sites, so a fixed-size message mixes sites and carries per-row field names and repeated site metadata; each message also costs ≈ 1.6 ms of fixed overhead (measured). Rows of one site are highly repetitive.

**Mechanism.** (1) *Site-affine coalescing.* The gateway buffers rows per site and emits a message when the site's buffer is large enough **or** its oldest row has waited `COALESCE_MS` (100 ms): the message size adapts to backlog (large under load, small when idle, so latency stays bounded). (2) *Compression.* Each coalesced batch is serialised as compact JSON and compressed with zlib at **level 1** (fastest; the bytes counted on the link are the compressed bytes) before it crosses the edge→core link; the core decompresses before persisting. The per-site row target grows with the outbox backlog (`adaptive_state.rows_per_msg`).

**Hypothesis (written before the experiments).** Under a constrained link (≤ 25 Mbit/s) the system is link-bound; bytes saved translate into time saved, and below a crossover bandwidth *B\** the improved system beats both others. On an unconstrained link it brings no gain. Predicted crossover: `B* = 8·S₀ / T_floor`, with *S₀* the bytes the baseline sends and *T_floor* the improved system's processing floor.

## V. Experimental Setup
**Platform.** One cloud VM, 2 vCPU Intel Xeon 2.1 GHz, 8 GB, Linux 6.18; Python 3.13; loopback network; every service an OS process. Details: `docs/reproducibility.md`.
**Stand-ins (important).** The log is a file-backed, partitioned, offset-committing implementation with Kafka's producer/consumer interface (`LocalBus`); a Kafka broker was not run. Object storage is a directory with the MinIO interface. Bandwidth is a token bucket (the baseline gets the same cap on its client uplink); CPU is `sched_setaffinity` plus a competing spin loop; memory is `RLIMIT_AS`; failures are SIGKILL + restart after 1 s; network load is threads posting 32 KB reports.
**Design.** One-factor-at-a-time sweeps around a centre point (60 000 rows, 4 users, 3 core replicas, 2 CPUs, no caps, no failures), bandwidth sweep with the full 120 000 rows. Factors: nodes (1, 2, 3, 5), users (1–16), bandwidth (unlimited, 100, 25, 10, 5 Mbit/s), CPU (2, 1, 1 + contention), memory (unlimited, 256, 160, 128 MB), network load (0–16 threads), failure rate (0, 6, 12, 20 crashes/min), request rate (2 k–unlimited rows/s), data volume (10 k–120 k rows). 2–3 repetitions per cell; 253 trials. Metrics: request latency (mean/p95/p99), jitter (stdev and RFC 3550), throughput, CPU, memory, bytes on the link, availability (a 1-row write probe every 100 ms), MTTR, request failure rate, rows lost/duplicated (verified against the dataset), coordination messages.

## VI. Results
(Mean ±sd; full tables: `results/m12_tables.md`.)

**A. Constrained link — the contribution.**

| link (Mbit/s) | baseline (s) | proposed (s) | improved (s) | improved vs baseline | improved vs proposed |
|---|---|---|---|---|---|
| unlimited | 0.98 ±0.04 | 2.72 ±0.29 | 2.76 ±0.38 | 0.36× | 0.99× |
| 100 | 3.61 | 6.38 ±0.12 | 2.92 ±0.31 | 1.24× | 2.19× |
| 25 | 14.29 | 17.35 ±0.22 | 4.03 ±0.35 | **3.55×** | **4.31×** |
| 10 | 35.65 ±0.01 | 39.13 ±0.24 | 7.80 ±0.87 | **4.57×** | **5.02×** |
| 5 | 71.26 ±0.01 | 75.84 ±0.25 | 11.99 ±0.29 | **5.94×** | **6.33×** |

Bytes on the link: 44.5 MB (baseline), 45.1–45.5 MB (proposed), **6.1 MB** (improved): 7.3× fewer (zlib 6.6:1 plus fewer headers). Total CPU-seconds of the core/collector processes: baseline 0.84–2.87, proposed 3.38–12.39, **improved 2.70–4.00** — the improvement *lowers* CPU relative to the unmodified tiered system at every bandwidth (fewer, larger messages save more per-message work than compression costs). The measured crossover lies between 100 Mbit/s and unlimited; the model gives `B* ≈ 356 Mbit / 2.76 s ≈ 130 Mbit/s`, consistent with the data.

**B. Failures — what the tiered design buys.**

| crashes/min | availability baseline | proposed / improved | request attempts failing (baseline) | MTTR baseline | MTTR tiered |
|---|---|---|---|---|---|
| 6 | 84.8 % | 100 % | 23.1 % | 1.23 s | 0.69 s |
| 12 | 77.6 % | 100 % | 31.0 % | 1.21 s | 0.88 s |
| 20 | 63.7 % | 100 % | 42.9 % | 1.23 s | 0.76 s |

No rows were lost by any system (the driver retries); the flat collector's loss is *availability*. The availability model `1 − f·d/60` with d = 1.2 s predicts 88 / 76 / 60 %.

**C. What the evidence does not support.**
* *Unconstrained link:* the baseline is ≈ 2.8× faster (0.98 vs 2.72 s for 120 000 rows) and needs ≈ 1/6 of the memory (≈ 50 vs ≈ 320 MB resident across all service processes).
* *Memory:* the unmodified tiered system needs ≈ 91 s instead of 1.5 s for 60 000 rows at *every* cap down to 256 MB and leaves 21 k / 42 k rows unstored at 160 / 128 MB when the 90 s trial deadline expires; the improved system survives 256 MB, is erratic at 160 MB and slow at 128 MB; the baseline is unaffected. The cause was not isolated.
* *Replicas:* 1 → 5 core replicas leaves throughput flat (37–44 k rows/s); memory grows ≈ 45 MB per replica; heartbeats grow linearly ((n−1)/τ: 1.95, 3.95, 7.7 per s for n = 2, 3, 5); a leader crash costs 1–19 election messages and 0.5–0.8 s to a new leader.
* *Network load:* with 16 cross-traffic threads p95 latency rises 1.6× (baseline) vs ≈ 2.2× (tiered); the improvement does not help (its advantage is bytes on the *link*).
* *Users, request rate, volume:* no meaningful differences between improved and unmodified tiered systems; both are slower than the baseline per row.

**D. Storage and correctness.** 120 000/120 000 distinct `record_id`s in both the DFS and the object store, also after the archiver is killed at ≈ 50 % and restarted (at-least-once; de-duplicated on id); R = 3 loses no chunk with two simultaneous datanode failures (R = 2 loses 4/16); 20 injected bit-rot cases returned 0 corrupt reads.

## VII. Discussion and Threats to Validity
**Reading the result.** The improvement is a bandwidth optimisation; it should be deployed only where the edge→core link is the bottleneck (here ≲ 100 Mbit/s for this payload). The tiered design is justified by availability, not speed; a deployment with a fat link and rare crashes would do better with the flat collector. The two claims are separable and the evidence for each is separate.
**Threats.** (1) *Single host:* load generator, edge, core, cloud and storage share two CPUs — absolute numbers are not transferable; ratios under a binding link (set by bytes and bandwidth) are the most transferable result, ratios under unconstrained load the least. (2) *Emulated variables:* real links add latency, loss and queueing that a token bucket does not; `RLIMIT_AS` is not a cgroup limit. (3) *Stand-in log:* Kafka's broker replication, rebalancing and network path are not exercised; the system code path is the same. (4) *Sample size:* n = 2–3, so ± values are rough; effects reported as differences are the ones far outside the noise (bandwidth, failure rate), while node/CPU sweeps are within it and are not interpreted. (5) *One dataset* (synthetic, seeded, with injected anomalies); compression ratios depend on the data. (6) *Sampling bias in our own tooling:* during the project several of our own experiments produced misleading results (an overwrite that hid lost writes, a double-counted cost, a failure experiment with no control, a stale cached name); each was found and corrected and is logged; there may be others.

## VIII. Related Work
Hierarchical, log-based monitoring pipelines follow Kafka (Kreps et al., 2011) and the HDFS/GFS storage lineage (Ghemawat et al., 2003; Shvachko et al., 2010); quorum replication with hinted handoff, read repair and anti-entropy is from Dynamo (DeCandia et al., 2007); leader election is Garcia-Molina's Bully algorithm (1982) and logical time is Lamport (1978); atomic commit follows Gray (1978), Skeen (1981) and Gray & Lamport (2006); Byzantine voting follows Lamport, Shostak & Pease (1982); RPC semantics follow Birrell & Nelson (1984); DSM follows Li & Hudak (1989). Batching and compression of telemetry are standard (and are exposed as producer options in Kafka itself); our contribution is the *site-affine, backlog-adaptive* form, its *bounded wait*, and the *measured envelope* in a system that also contains the alternatives. We did not compare against Kafka's own `linger.ms`/`compression.type` — a natural next experiment on a real broker.

## IX. Conclusion
Adaptive site-affine coalescing with zlib compression makes a tiered monitoring pipeline 3.6–5.9× faster than a flat collector on a constrained link, with 7.3× fewer bytes and lower CPU than the unmodified tiered pipeline; it is useless on a fast link. The tiered pipeline itself is slower, heavier and more memory-fragile than a flat collector, and is worth its cost for availability. Reporting both halves — and the limits of a single emulated host — is the contribution's evidence, not an afterthought.

## References
1. L. Lamport, "Time, Clocks, and the Ordering of Events in a Distributed System," *CACM*, 1978.
2. H. Garcia-Molina, "Elections in a Distributed Computing System," *IEEE Trans. Computers*, 1982.
3. J. Gray, "Notes on Database Operating Systems," 1978.
4. D. Skeen, "Nonblocking Commit Protocols," *SIGMOD*, 1981.
5. J. Gray and L. Lamport, "Consensus on Transaction Commit," *ACM TODS*, 2006.
6. L. Lamport, R. Shostak, M. Pease, "The Byzantine Generals Problem," *ACM TOPLAS*, 1982.
7. G. DeCandia et al., "Dynamo: Amazon's Highly Available Key-value Store," *SOSP*, 2007.
8. S. Ghemawat, H. Gobioff, S.-T. Leung, "The Google File System," *SOSP*, 2003.
9. K. Shvachko et al., "The Hadoop Distributed File System," *MSST*, 2010.
10. J. Kreps, N. Narkhede, J. Rao, "Kafka: a Distributed Messaging System for Log Processing," *NetDB*, 2011.
11. A. Birrell and B. Nelson, "Implementing Remote Procedure Calls," *ACM TOCS*, 1984.
12. K. Li and P. Hudak, "Memory Coherence in Shared Virtual Memory Systems," *ACM TOCS*, 1989.
13. E. Coffman, M. Elphick, A. Shoshani, "System Deadlocks," *ACM Computing Surveys*, 1971.
14. D. Ongaro and J. Ousterhout, "In Search of an Understandable Consensus Algorithm," *USENIX ATC*, 2014.
15. R. Jain, D. Chiu, W. Hawe, "A Quantitative Measure of Fairness and Discrimination for Resource Allocation in Shared Computer Systems," DEC-TR-301, 1984.
16. H. Schulzrinne et al., "RTP: A Transport Protocol for Real-Time Applications," RFC 3550, 2003.
17. P. Mockapetris, "Domain Names — Concepts and Facilities / Implementation and Specification," RFC 1034/1035, 1987.
18. A. Tanenbaum and M. van Steen, *Distributed Systems: Principles and Paradigms*; G. Coulouris et al., *Distributed Systems: Concepts and Design*.

*(Verify full bibliographic details before submission.)*
