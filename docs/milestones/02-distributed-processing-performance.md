# Milestone 2 — Distributed Processing and Performance

**System stage S2:** the Week-1 prototype now ingests the 120,000-row dataset from several edge nodes and distributes the analytics over workers, with every metric the brief lists measured.

| Brief deliverable | Where |
|---|---|
| Distributed processing implementation | `system/edge/replayer.py` (edge nodes stream their sites), `system/baseline/collector.py` (flat collector), `system/edge/analytics.py` (per-site anomaly detector, `run_partitioned*`) |
| Performance measurements | `results/m02_throughput_raw.csv`, `m02_throughput_summary.csv`, `m02_compute_scaling.csv`, `m02_summary.json` |
| Load-distribution analysis | Jain index per run (§Results A) and the sites→workers partition (§Results B) |
| Bottleneck analysis | §Analysis |

Run: `python -m system.experiments.m02_performance`

## Method (Hypothesis → Design → Implementation → Measurement → Analysis → Conclusion)
**Hypothesis.** Spreading the edge work over more nodes raises aggregate throughput until the single flat collector saturates; latency then grows while throughput flattens. Distributed anomaly detection speeds up with workers until the host's cores run out.

**Design.** *Part A* — independent variable: edge nodes N ∈ {1, 2, 4}, each streaming its share of the sites. Controlled: 30,000 dataset rows, chunk 500, same collector, same host, same dataset (seed 2403). Dependent: throughput = completed rows / time, latency = T_response − T_request, jitter = stdev of latency, request loss = failed / attempted, collector CPU and RSS, Jain fairness of the load. 3 repetitions per point; 95 % CI. An extra run injects 5 % request errors to prove the loss metric measures what it claims. *Part B* — anomaly detection over all 120,000 rows with k ∈ {1, 2, 4} workers in three modes: *cold* (rows pickled to freshly started workers), *warm* (pre-started pool, rows still shipped), *data-local* (each worker already holds its sites, only site ids go out, as on a real edge node).

## Results
**A — ingest (flat collector).**

| nodes | throughput rows/s (±95 % CI) | latency mean / p95 (ms) | jitter (ms) | collector CPU | collector RSS | Jain |
|---|---|---|---|---|---|---|
| 1 | 72,926 ± 4,652 | 6.85 / 8.35 | 2.34 | 59.7 % | 39 MB | 1.00 |
| 2 | 92,576 ± 7,236 | 10.58 / 15.72 | 3.68 | 73.2 % | 41 MB | 1.00 |
| 4 | 88,502 ± 3,864 | 21.69 / 36.80 | 7.81 | 75.3 % | 43 MB | 1.00 |

Packet/request loss: 0 % in all clean runs. With 5 % injected errors the measured request loss was 5.00 %, 1.67 % and 3.33 % (3 runs of only 60 requests each, so the spread is sampling noise) and the corresponding rows were not stored (28,500–29,500 of 30,000).

**B — distributed analytics (120,000 rows, 2-CPU host).**

| workers | cold wall (s) / speed-up | warm | data-local |
|---|---|---|---|
| 1 | 0.551 / 1.00 | – | 0.548 / 1.01 |
| 2 | 0.768 / 0.71 | 0.644 / 0.86 | **0.344 / 1.60** |
| 4 | 0.715 / 0.77 | 0.554 / 0.99 | 0.383 / 1.44 |

Detector quality (same for every mode): precision 0.994, recall 0.849, F1 0.916 against the `is_anomaly` label.

## Analysis
* **Bottleneck.** Throughput rises from 1→2 nodes (+27 %) and then falls slightly at 4: the collector is at 73–75 % CPU of one core (Flask + SQLite commit on one process) and the 2-CPU host is shared with the load generators. Latency and jitter keep growing with N (queueing at the collector) — the classic single-server saturation curve. This is exactly the motivation for Milestone 3.
* **Distribution only pays when data stays local.** Shipping rows to workers (cold/warm) is *slower* than one process (0.71–0.99×) because pickling 120,000 dicts costs more than the 4 µs/row detection itself. Moving the computation to the data (data-local) gives 1.6× on 2 workers; 4 workers on 2 CPUs are oversubscribed (1.44×). The honest claim is "speed-up limited by min(workers, CPUs) and by data movement", not "linear scaling".
* **Load distribution.** Jain index 1.0: sites are assigned round-robin and every site has 5,000 rows, so work is perfectly even; real heterogeneity is handled in Milestone 10 (scheduling).

## Conclusion
H1 is supported for ingest (saturation at ≈ 90 k rows/s, latency ×3 from 1→4 nodes). H2 is supported only for the data-local mode; the naive "ship the data" distribution is a net loss. Both findings change later design: tiers aggregate at the edge (M3) and analytics run where the data lives (M10).

## Failure-driven engineering log (week 2)
| Question | Answer |
|---|---|
| What changed? | Flat collector with bulk ingest, dataset replayer, partitioned analytics, metric library (throughput, latency, jitter, loss, CPU/RSS, Jain). |
| What failed? | Distributing the detector over 2 and 4 worker processes made it *slower* than 1 process (0.71×, 0.77×). |
| Why? | Process start-up and pickling 120,000 row dicts dominated the 0.55 s of useful work. |
| How fixed? | Separated cold / warm / data-local modes so the cost of each is visible; data-local workers hold their sites and receive only site ids. |
| Alternative considered | Threads (blocked by the GIL for CPU-bound work); shared-memory arrays (more code, same lesson). |
| What was learned? | Move computation to data; report speed-up against the right baseline and be explicit about the CPU count. |

## Limitations
2-CPU sandbox, so scale-out beyond 2 workers is oversubscribed; load generators share the CPUs with the collector; N=3 repetitions → CIs are wide.
