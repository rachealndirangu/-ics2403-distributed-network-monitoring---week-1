# Milestone 8 — Distributed System Models

**System stage S8:** which architecture fits a telecom monitoring workload? Five models are run on the *same* workload and scored.

| Brief deliverable | Where |
|---|---|
| Model comparison | `results/m08_reference.csv`, `m08_load_sweep.csv`, `m08_scalability.csv`, `m08_reliability.csv` |
| Simulation/experimental results | `system/models/simulator.py` (seeded discrete-event simulator) + `system/experiments/m08_models.py`; live cross-check from M3 (`results/m03_*.csv`) |
| Architectural justification | § Decision below, `results/m08_decision_matrix.csv` |

Run: `python -m system.experiments.m08_models` (≈ 40 s). **Fully deterministic**: two consecutive runs give byte-identical CSVs (the one timing measurement is pinned, see below).

## The five models (as simulated)
| Model | Meaning here |
|---|---|
| host-based | all analysis jobs are shipped to ONE central host (4 cores) |
| workstation | every site analyses its own jobs on its own 1-core machine; nothing shared |
| server-based | sites are clients of dedicated servers (2 servers × 2 cores at 24 sites; fixed site→server assignment) |
| processor-pool | 5 identical processors, a dispatcher sends each job to the least-loaded *up* processor |
| integrated | edge nodes pre-aggregate locally (10 % of the job's CPU; data shrinks to 10 %), the reduced work goes to a processor pool with replicated storage — **the architecture of this project** |

Workload: 24 sites (a few "hot" ones with 4× the rate), Poisson arrivals, a job = 1 000 telemetry rows to scan for anomalies. `load = 1.0` keeps a 4-core host ≈ 85 % busy. WAN 50 Mbit/s. Seeds 2403…2407 (5 runs per cell; 95 % CI in the CSVs). Cost = 1 unit per core-hour of simulated time + 0.09 per GB of WAN traffic.

**Calibration — what is measured, what is assumed.** The per-row cost of the real anomaly detector was *measured* on this machine: 4.0–4.4 µs/row across runs. The simulation uses the pinned value **4.0 µs/row** (`PINNED_US_PER_ROW`): the failure simulations are chaotic and run-to-run timing noise otherwise changed their results (see log). The production detector is *assumed* to be 40× heavier (`HEAVY = 40`) → 160 µs/row = 160 ms CPU per 1 000-row job. Network and cost figures are assumptions too. Every conclusion below is therefore conditional on those parameters.

## Results

**Reference load (load = 1.0, 24 sites, 600 s simulated)**

| model | throughput (jobs/s) | mean latency | p95 | compute utilisation | cores (compute / total) | WAN (GB) | cost units |
|---|---|---|---|---|---|---|---|
| host-based | 21.22 | 0.333 s | 0.582 | 0.85 | 4 / 4 | 4.84 | 1.10 |
| workstation | 21.22 | **0.187 s** | 0.316 | 0.14 | 24 / 24 | 0.00 | 4.00 |
| server-based | 21.21 | 0.452 s | 0.933 | 0.85 | 4 / 4 | 4.84 | 1.10 |
| processor-pool | 21.22 | 0.269 s | 0.388 | 0.68 | 5 / 5 | 4.84 | 1.27 |
| integrated | 21.22 | 0.203 s | 0.309 | 0.61 | 5 / 29 | **0.48** | 4.88 |

**Load sweep (completion % / mean latency)**

| load | host-based | server-based | processor-pool | workstation | integrated |
|---|---|---|---|---|---|
| 1.0 | 100 / 0.33 s | 99.9 / 0.45 s | 100 / 0.27 s | 100 / 0.19 s | 100 / 0.20 s |
| 1.2 | 97.7 / 6.6 s | 97.6 / 7.2 s | 100 / 0.31 s | 100 / 0.20 s | 100 / 0.22 s |
| 1.5 | **78.4 / 64 s** | **78.4 / 64 s** | 97.8 / 6.7 s | 100 / 0.21 s | 99.9 / 0.34 s |

**Scalability (sites 12 → 192; hardware of server/pool/integrated scaled with sites, host fixed at 4 cores)**
host-based completion: 100 → 100 → **58.8 → 29.4 → 14.7 %** at 12/24/48/96/192 sites (throughput capped at 25 jobs/s, latency 123 → 256 s). All other models keep ≥ 99.9 % completion; throughput grows linearly (10.6 → 170 jobs/s). Mean latency stays flat: integrated 0.19–0.20 s, workstation 0.19 s, pool 0.24–0.27 s, server-based 0.45 s.

**Reliability (node MTBF 600 s / 300 s, MTTR 60 s, 1 800 s horizon)**

| model | completion % @600 | mean lat @600 | p99 @600 | completion % @300 | mean lat @300 | p99 @300 |
|---|---|---|---|---|---|---|
| host-based | 95.6 | 17.9 s | 126 s | 93.3 | 118 s | 196 s |
| workstation | 99.6 | 7.3 s | 154 s | 98.8 | 14.6 s | 195 s |
| server-based | 98.9 | 18.5 s | 99 s | 93.1 | 92 s | 233 s |
| processor-pool | 100 | 0.99 s | 11.3 s | 99.8 | 4.3 s | 51 s |
| integrated | **100** | **0.44 s** | **4.3 s** | **99.98** | **2.3 s** | **38 s** |

Models that can re-route (pool, integrated) absorb node loss; models with a fixed site→node mapping (server-based, workstation) park the jobs of a dead node until it returns.

## Decision (weighted matrix; criteria min-max normalised 0–1)
Criteria: latency (p95), throughput at load 1.5, utilisation, scalability (p95 at 96 sites), reliability (p99 at MTBF 600), cost. Four weightings (balanced, cost-driven, latency-driven, reliability-driven; weights in the code) × **two cost models**, because the answer depends on what "cost" means:

* **Cost model A — every core is priced.** The integrated model needs 24 edge cores in addition to the pool, so it is the most expensive (4.88 units; score 0).
* **Cost model B — hardware the sites already own is free** (the workstation model's 24 machines and the integrated model's 24 edge nodes already exist at telecom sites; only dedicated servers are paid for).

| cost model | weighting | host | workstation | server | pool | integrated | winner (runner-up) |
|---|---|---|---|---|---|---|---|
| A | balanced | 0.399 | 0.583 | 0.523 | **0.920** | 0.816 | **processor-pool** (integrated) |
| A | cost-driven | 0.675 | 0.392 | 0.737 | **0.908** | 0.533 | **processor-pool** (server-based) |
| A | latency-driven | 0.412 | 0.669 | 0.373 | **0.914** | 0.883 | **processor-pool** (integrated) |
| A | reliability-driven | 0.289 | 0.422 | 0.516 | **0.940** | 0.883 | **processor-pool** (integrated) |
| B | balanced | 0.269 | 0.698 | 0.393 | 0.776 | **0.862** | **integrated** (pool) |
| B | cost-driven | 0.326 | **0.699** | 0.388 | 0.525 | 0.655 | **workstation** (integrated) |
| B | latency-driven | 0.325 | 0.746 | 0.286 | 0.818 | **0.914** | **integrated** (pool) |
| B | reliability-driven | 0.202 | 0.499 | 0.428 | 0.844 | **0.914** | **integrated** (pool) |

**What this does and does not show.**
* Under cost model A the **processor pool wins all four weightings** — the integrated design is consistently second. Under cost model B the **integrated model wins three of four** (workstation wins when cost dominates, because its hardware is then free and it has no WAN).
* The integrated model is the best on latency, throughput, scalability and reliability in every run; it loses only when its edge hardware is charged as new. **The choice of the integrated architecture is therefore a statement that the edge nodes exist at the sites (B) or that the WAN and latency matter more than the extra cores — not an unconditional ranking.** The processor pool is the strongest alternative and is also what the "core" tier of the final system is.
* We report both cost models rather than choose the convenient one: the first version of this experiment (see log) produced "integrated wins" through a scoring error, and the corrected result is less flattering.

## Cross-check against live measurements (M3)
The simulator claims the integrated design cuts upper-tier/WAN traffic ≈ 10× but does **not** improve latency when the WAN is free. The live system agrees: flat collector (≈ host-based) vs tiered-1-gateway (≈ integrated), 20 agents, `results/m03_scalability.csv`: upper-tier messages **500 → 50 (10×)**, mean latency 23.3 → 24.4 ms (**slightly worse**: the extra hop costs ≈ 1 ms on loopback where there is no WAN to save). The qualitative claim has independent support; the quantitative latency/throughput/reliability figures above are *simulated* and depend on `HEAVY` and the network assumptions.

## Hypotheses
| Hypothesis | Outcome |
|---|---|
| H1 at the reference load all models serve the offered load; they differ in latency and hardware | **supported** (all 21.2 jobs/s; mean latency 0.19–0.45 s; 4–29 cores) |
| H2 under growing load the host saturates first; pool and integrated degrade last | **supported** (host 78 % completion at load 1.5; integrated 99.9 %; pool 97.8 %) |
| H3 with node failures only models that can re-route keep latency low | **supported** (pool/integrated ≤ 4.3 s mean at MTBF 300; host 118 s, server-based 92 s) |
| H4 integrated cuts WAN ≈ 10× and keeps latency near the workstation model | **supported** (WAN 4.84 → 0.48 GB; 0.203 s vs 0.187 s) — at 29 cores vs 24 for the workstation model |
| (added after review) H5 integrated is the best overall fit | **conditional**: true if site-owned hardware is free (3 of 4 weightings), false if every core is priced (pool wins all 4) |

## Failure-driven engineering log (week 8)
| Question | Answer |
|---|---|
| What changed? | Seeded discrete-event simulator with five models, a node failure process, a weighted decision matrix. |
| What failed? | (1) Completion percentages were computed against *expected* arrivals, so saturated models looked better than they were. (2) The calibration print and saved summary mixed units (`cpu_ms_per_job = 0.2` instead of ≈ 160). (3) **The cost criterion added raw WAN gigabytes to `cost_units`, which already contains WAN cost at 0.09/GB — WAN was counted ≈ 11× too heavily.** That produced the "integrated wins 3 of 4, workstation when cost-driven" result I first documented; it was an artefact. (4) Two runs of the same experiment gave different reliability numbers. |
| Why? | (1) wrong denominator; (2) a missing ×1000; (3) double counting; (4) the measured µs/row differed by a few percent between runs and the failure simulation amplifies small differences. |
| How fixed? | (1) simulator counts actual arrivals; (2) units fixed in code and saved JSON; (3) cost = `cost_units` only, and a second explicit cost model B added so the dependence on what is "owned" is visible rather than hidden; (4) calibration pinned at 4.0 µs/row (live value still printed, warns if > 25 % away); two runs now produce identical files. |
| Alternative considered | Keep the first result because it matched the architecture we had already chosen — rejected: the corrected matrix is reported as is. |
| What was learned? | A decision matrix is only as honest as its criteria definitions — review each criterion, not just the weights; chaotic simulations need pinned inputs; "best architecture" depends on who pays for the edge hardware. |

## Limits (honest)
Simulated, not measured, for four of the five models; `HEAVY = 40`, WAN speed and the cost units are assumptions; 5 seeds per cell; the cost-B assumption (edge hardware already exists) is plausible for a telecom operator but is an assumption.
