# Oral defence — preparation sheet (Parts A–G)

One page per part: what you will be asked, the short answer, and where the evidence is. Every number below is taken from a file in `results/` (named in brackets); if a number here and a file disagree, the file wins and this sheet is wrong.

Architecture to be able to draw from memory:

```
Users / Devices ──► Edge gateway ──► partitioned log (Kafka interface) ──► Telecom core (3 replicas, Bully leader) ──► Cloud digest
                    (buffer, coalesce,         ▲ offsets committed after persist       │                               │
                     compress)                 └──── new leader resumes from offset ◄──┘                               ▼
                                                                                                         Distributed storage (DFS R=3 + object store)
```

---

## Part A — Theory (what is a distributed system, and why these choices)

| Question | Answer in one breath |
|---|---|
| Why is this a *distributed* system and not a big server? | Cell sites are geographically spread; each produces data locally; the failure of one component must not stop the rest. No shared memory, no global clock, partial failure. |
| What are the eight fallacies and which one bit you? | The network is reliable / latency is zero / bandwidth is infinite … Bandwidth: the Week-12 sweep shows the flat design takes 71 s at 5 Mbit/s vs 12 s improved. Reliable network: the retry that duplicated an in-flight chunk (week 4). |
| Which transparencies do you provide? | Access, location, migration, replication, failure (M9). Failure transparency 100 % vs ≈ 57 % without it [`m09_failure_transparency.csv`]. |
| CAP — where are you? | The quorum store (M7) chooses consistency over availability when a quorum is unreachable (W+R>N); the ingest path chooses availability (edge buffers, log accepts) and is eventually consistent. |
| Why not a monolith? | Measured: the monolith (baseline) is ≈ 2.8× *faster* when the link is unconstrained [`m12_headline.csv`]. We pay for the distribution with speed and buy availability under failure (100 % vs 64–85 %). Say this yourself before the examiner does. |

## Part B — Architecture rationale

| Layer | What it does | Why it exists (evidence) |
|---|---|---|
| Edge gateway | buffers, coalesces per site, compresses (the improvement) | the only layer that sees the constrained link; 7.3× fewer bytes (44.5 → 6.1 MB) |
| Log (Kafka interface) | durable, partitioned, offset-committing queue between edge and core | decouples producers from consumers; the edge is acked only after append, so a core crash cannot lose an acknowledged chunk (M4) |
| Core replicas | persist, elect a leader, serve queries | leader failover ≈ 0.8 s, 0 rows lost |
| Cloud digest | per-site summaries, anomalies | keeps wide-area traffic small |
| Distributed storage | DFS (chunks, R=3, checksums, re-replication) + object store | R=3 loses 0 chunks with 2 datanode kills; R=2 loses 4 of 16 [`m12_storage_summary.json`] |

**Kafka, honestly.** The code talks to a `Bus` interface with two implementations: `KafkaBus` (confluent-kafka) and `LocalBus` (file-backed partitioned log, same producer/consumer/offset semantics). **All reported numbers use `LocalBus`**, because the build machine had no Docker daemon. `docker-compose.system.yml` starts a real broker; run it with `docs/run_with_docker.md`. Say "the interface and semantics are Kafka's; the broker's replication and rebalancing were not measured". Do not say "we measured Kafka".

## Part C — Algorithms (be able to derive each on the board)

| Algorithm | Core idea | Cost / bound | Evidence |
|---|---|---|---|
| Bully election | on timeout send ELECTION to higher ids; no answer ⇒ COORDINATOR | ≤ N² messages worst case, N−1 best | 0 split-brain samples in 24 runs [`m04_summary.json`]; measured 1–2 messages at N≤3 [`m12_coordination.csv`] |
| Lamport clocks | `t = max(t, t_msg)+1` | O(1) per message | ±3 s skew: wall-clock order wrong in 33.6 % of traces, Lamport 0 % |
| 2PC / 3PC | prepare → decide → commit; 3PC adds pre-commit to remove the blocking window | 2PC: 3N messages, blocks if coordinator dies in doubt | in-doubt experiment [`m05_coordinator_crash.csv`] |
| Ordered prepare | take participants in one global order | prevents distributed deadlock | 9/240 committed → 240/240, 0.6 → 103 tps |
| Deadlock policies | detect (wait-for cycle) / ordered / wait-die / none | detect+recover 1.27 s, ordered 1.10 s, none = stuck | [`m06_deadlock.csv`] |
| Quorum replication | W + R > N ⇒ read and write sets intersect | N=3,W=R=2 tolerates 1 crash; N=4,W=R=3 tolerates 1 Byzantine + crash (3f+1) | Byzantine correctness 58.3 % single, 75.8 % quorum, 100 % vote |
| Tombstones | a delete is a versioned write | prevents anti-entropy from resurrecting a key | regression test in `tests/test_integration.py` |
| Naming | static / broadcast / name server / hierarchical prefix | broadcast O(N) messages; hierarchy O(depth) | [`m10_*.csv`] |
| Adaptive coalescing | per-site buffers flushed at backlog-scaled row target or 100 ms | fewer, larger messages ⇒ less per-message CPU | improved uses *less* CPU than unimproved (2.7 vs 3.4 CPU-s) |

Expected whiteboard question: **"Why does W+R>N guarantee you read the latest write?"** — any W-set and any R-set must share at least one replica when W+R>N; that replica holds the highest version, and the reader picks the highest version.

## Part D — Live demo (run in this order, ≈ 5 minutes)

```bash
pip install -r requirements.txt -r requirements-system.txt --break-system-packages
python data/generate_dataset.py            # 120,000 rows, prints sha256 (must start 7e81ca81…)
python -m pytest tests -q                  # 26 tests, ≈ 3 min  (skip live if short of time; show last run)
python -m system.scripts.demo_failure      # Part E (≈ 25 s)
python powerbi/make_preview.py             # regenerates the four Power BI chart previews
```
Show on screen: `data/telemetry_120k.csv` row count, the architecture diagram, `results/m12_headline.csv`, the four charts in `powerbi/preview/`. Docker alternative: `docker compose -f docker-compose.system.yml up` (not executed on the build machine — say so if asked).

## Part E — Failure → Detection → Recovery → Service restoration

Run: `python -m system.scripts.demo_failure`. A real run produced:

```
[ 2.19s] stack up: 3 core replicas, leader = core3; streaming 120,000 rows at 6,000 rows/s
[10.12s] FAILURE    : SIGKILL core3 (the leader) with 48,000 rows stored
[10.90s] DETECTION  : survivors stopped hearing core3 (+0.78 s) and started an election
[10.90s] RECOVERY   : new leader = core2 agreed by all survivors (+0.78 s)
[11.09s] RECOVERY   : new leader is consuming the log again from the committed offset (+0.97 s after the crash)
[22.30s] RESTORATION: stream finished; distinct record_ids stored = 120,000 of 120,000  (lost: 0; duplicate copies across replicas: 0)
[24.01s] RETURN     : core3 restarted; as the highest id it bullies its way back to leadership in 1.40 s
```
Narrate the four stages:
1. **Failure** — SIGKILL, no graceful shutdown, mid-stream.
2. **Detection** — survivors miss heartbeats (interval 0.5 s, limit 2 misses) → ≈ 0.8 s.
3. **Recovery** — Bully election; the new leader reads the committed offset and resumes from there. Rows between the last commit and the crash are re-read (at-least-once) and de-duplicated by `record_id` on write (idempotent).
4. **Restoration** — every `record_id` in the dataset is stored once: 120,000 of 120,000.

What the demo does not show: a crashed *edge* node, a network partition, disk loss. If asked, point to M7 (fault injection) and M12 DFS (datanode loss, bit rot).

## Part F — Defending the numbers

Know three things about every number: **what was varied, what was held fixed, what could be wrong**. All on one 2-vCPU host over loopback; bandwidth/CPU/memory/failures are emulated.

| Metric | Value | Source | Caveat to volunteer |
|---|---|---|---|
| Throughput, flat collector, bulk ingest | 73 k rows/s (1 node), 93 k (2 nodes), 88 k (4 nodes) | [`m02_summary.json`] | 2 CPUs ⇒ no gain beyond 2 workers |
| Latency (dataset, per request) | mean 21.4 ms, p95 26.5 ms | `powerbi/preview/numbers.txt` | dataset field, not a live measurement |
| Jitter | 4.25 ms (dataset) | same | RFC-3550-style mean |Δ| also reported for live trials |
| Time to deliver 120 k rows @ 5 Mbit/s | 71.3 s baseline, 75.8 s proposed, **12.0 s improved** (5.94×) | [`m12_headline.csv`] | n = 3; link is a token bucket, not a real WAN |
| Bytes on link | 44.5 → 6.1 MB (7.3×) | same | zlib ratio is specific to this telemetry |
| CPU-seconds @ unlimited | baseline 0.84, proposed 3.38, improved 2.70 | [`m12_tables.md`] | derived = mean CPU % × time |
| Memory | ≈ 45 MB per core replica; proposed collapses at ≤ 256 MB cap (92 s) | [`m12_capstone_summary.csv`] | `RLIMIT_AS` (address space), not cgroup RSS; cause of the cliff not isolated |
| Availability @ 6 / 12 / 20 crashes/min | baseline 84.8 / 77.6 / 63.7 %, proposed 100 % | [`m12_headline.csv`] | 100 ms write probe; 100 % means *writes accepted*, processing pauses 0.7–0.9 s |
| MTTR | 0.78–0.97 s (leader), 5.2 s (single replica without failover) | [`m12_coordination.csv`], [`m07_summary.json`] | restart delay emulated at 1 s |
| Failure rate / data loss | 0 rows lost in all systems; baseline retries until success | `m12_headline.csv` | loss is "not stored by the 90 s deadline" |
| Scalability | nodes 1→5: throughput flat (37–44 k rows/s); users 1→16: flat | `m12_tables.md` | CPU-bound host; says nothing about a many-core machine |
| Consistency | stored ids = dataset ids, 0 lost, 0 duplicated | `stored_ids()` in `m12_capstone.py` | checked per trial |
| Coordination overhead | heartbeats ∝ N (3.95/s at N=3, theory 4); election 1–2 messages at N≤3, up to 19 at N=5 | [`m12_coordination.csv`] | N=5 varies with timing, n = 2 |

**Confidence intervals:** n = 2–3 per cell, so CIs are wide. Say: "ordering and ratios are reproducible; the digits are not" (`docs/reproducibility.md`).

## Part G — "What has your system contributed beyond the baseline?"

Say it in this order (30 seconds):

1. **The baseline** is the Week-1/2 design: clients → one collector. Fast, simple, 100 % available only while that process lives.
2. **The proposed architecture** adds an edge tier, a durable log, replicated cores with leader election, and distributed storage. Measured benefit: **availability 100 % vs 64–85 %** at 6–20 crashes/min, zero rows lost, storage that survives two datanode kills.
3. **The improvement** — adaptive site-affine coalescing + zlib on the edge→core link: **7.3× fewer bytes, 3.6–5.9× faster than the baseline at ≤ 25 Mbit/s**, and *lower* CPU than the unimproved system.
4. **What it costs** (volunteer it): ≈ 2.8× slower on an unconstrained link, ≈ 6× the memory, a memory cliff under a 256 MB cap, no throughput gain from more replicas. Crossover ≈ 130 Mbit/s.
5. **Therefore:** the tiered design is justified by availability and constrained links, not by speed. On a fat link with rare failures, keep the baseline.

Distinguish the three things the brief insists on: **existing** = Kafka, Bully, 2PC, quorums, HDFS-style DFS (all published); **implementation** = our code and harness; **contribution** = the adaptive coalescing + compression policy and the measured crossover/availability trade-off.

### Likely follow-up questions
| Question | Answer |
|---|---|
| "Was it really Kafka?" | Interface and semantics, yes; broker, no. `LocalBus` in all measurements. |
| "Where is the `.pbix`?" | Not created — Power BI Desktop is Windows-only. `powerbi/README.md` has the data model, the DAX measures, the 4 chart specs; `powerbi/preview/` shows the charts rendered from the same data. Import `data/telemetry_120k.csv` and follow the README (≈ 10 min). |
| "Why was your first M8 result wrong?" | The cost criterion double-counted WAN traffic; the corrected matrix depends on the cost model, so both are reported (`docs/milestones/08-*.md`). |
| "What would you do with more time?" | Run on 3+ machines with `tc netem`; real Kafka; isolate the memory cliff; more repetitions. |
| "What was your worst bug?" | Deletes were resurrected by anti-entropy (12 copies after migration). Fixed with versioned tombstones + regression test. |
