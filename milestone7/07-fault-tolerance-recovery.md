# Milestone 7 — Fault Tolerance and Recovery

**System stage S7:** the state store is replicated; failures are injected on purpose, detected, masked by failover, and healed.

| Brief deliverable | Where |
|---|---|
| Fault-injection framework | `system/common/faults.py` (installed in every service: `POST /fault`) + process-level crash/pause in `system/scripts/cluster.py` |
| Recovery mechanism | `system/replication/replica.py` (versioned KV, hinted handoff, anti-entropy), `system/replication/client.py` (quorum W/R, failure detector, failover, read repair, optional majority vote) |
| Availability analysis, recovery-time analysis, failure comparison | `python -m system.experiments.m07_fault_tolerance` → `results/m07_fault_injection_raw.csv`, `m07_failure_comparison.csv` |

## Fault model (brief: crash, communication, omission, node, service; Byzantine where appropriate)
| Fault | How it is injected on replica r1 (5 s of a 12 s run) |
|---|---|
| crash | SIGKILL, restarted at repair time |
| node failure (hang) | SIGSTOP / SIGCONT: process exists but is frozen |
| omission | 50 % of requests accepted but never answered |
| communication | traffic from the client dropped/held (`blocked_from`) – a partition seen from r1 |
| service failure | process up, every request gets HTTP 503 |
| application error | 50 % of requests answered with HTTP 500 |
| Byzantine | r1 answers with plausible but wrong values |

## Mechanisms
* **Failure detection:** client-side timeouts + suspicion after 2 consecutive failures, retry-after probing (`suspect_after=2`, `retry_after=1.0 s`). Measured detection time: crash 0.02 s, service-down 0.02 s, app-error 0.14 s, communication 0.61 s, node-hang 0.92 s, omission 1.28 s (bounded by the 0.6 s request timeout × 2).
* **Replication:** N=3, write quorum W=2, read quorum R=2 (W+R>N ⇒ read sees latest write); versions per key.
* **Failover:** the client simply uses the remaining healthy replicas — no election needed for a leaderless quorum store.
* **Recovery:** hinted handoff (writes missed by a suspected replica are replayed when it returns), read repair, and background anti-entropy (digest comparison every 0.5 s). A restarted replica was fully caught up after 0–0.23 s.
* **Majority vote (Byzantine):** read from R replicas and accept a value only if a strict majority agree.

Metrics: Availability = T<sub>uptime</sub>/T<sub>total</sub> where a 50 ms probe window is "up" if the write *and* the read complete; MTTR = mean length of an outage episode (consecutive failed probes); correctness = reads returning the value just written.

## Results (2 reps per cell; full table in `m07_failure_comparison.csv`)
**Availability (%)**

| fault | single instance | replicated N=3 (W2 R2) | + vote, N=3 (R=3) | + vote, **N=4** (W3 R3) |
|---|---|---|---|---|
| crash | 56.6 | **100** | 56.7 | **100** |
| node hang | 94.6 | **100** | 84.9 | **100** |
| omission | 93.9 | **100** | 91.7 | **100** |
| communication | 93.6 | **100** | 83.9 | **100** |
| service down | 58.5 | **100** | 58.3 | **100** |
| application error | 68.1 | **100** | 67.1 | **100** |
| Byzantine | 100 | 100 | 100 | 100 |

**MTTR (s):** single 5.2 (crash) / 4.8 / 1.8 / 5.4 / 4.9 / 0.14 for crash / hang / omission / communication / service-down / app-error; replicated and N=4-vote **0.0** in every case (no outage episode: the client never waits for repair); N=3-vote equals the single instance for crash/service-down because voting over all 3 replicas needs all 3 alive.

**Correctness under Byzantine r1:** single **58.3 %**, plain quorum **75.8 %**, vote N=3 **100 %**, vote N=4 **100 %**. For all crash-type faults correctness was 100 % everywhere (stale data is never returned thanks to W+R>N).

## Analysis
* **H1 (single instance ≈ 58 % under crash/down) — supported**: 56.6 % ≈ 7/12 (outage 5 of 12 s); replicated holds 100 %.
* **H2 (failover bounded by detection, not repair) — supported and stronger**: with a leaderless quorum client the *observed* MTTR is 0 because the surviving quorum answers while the failure detector is still deciding; detection time (0.02–1.28 s) only shows up as latency of a few probes.
* **H3 (only voting protects against Byzantine replies) — supported**: plain quorum returned wrong data 24 % of the time because it trusts the highest version number and a Byzantine replica can claim one.
* **A design lesson we did not predict:** voting with N=3 buys Byzantine tolerance *at the cost of crash tolerance* (availability 56.7 % under crash) because it needs all three replicas. Tolerating one crash **and** one Byzantine replica needs N ≥ 3f+1 = 4 with R=3 – confirmed experimentally (100 %/100 %). Cost: 33 % more storage and a W=3 write path.

## Failure-driven engineering log (week 7)
| Question | Answer |
|---|---|
| What changed? | Fault injector in all services, replicated KV with quorum client, failure detector, hinted handoff / read repair / anti-entropy. |
| What failed? | Majority-vote reads on 3 replicas dropped availability to 57 % under a plain crash. |
| Why? | The vote was defined over R=3 of N=3 replicas; one dead replica means no majority can be formed from the required 3 answers. |
| How fixed? | Added the N=4, W=3, R=3 configuration (3f+1); kept N=3 vote in the results as the documented counter-example. |
| Alternative considered | Reading from all and voting among whoever answers (weakens safety: with 2 answers a single liar plus one honest tie); full PBFT (out of scope). |
| What was learned? | Crash tolerance and Byzantine tolerance are different budgets; the fault you design for decides N. |

## Limitations
One client observer; 2 repetitions (the cells are deterministic enough that variation is tiny, but the CI is not computed); "communication" fault is one-directional and from one caller; no network partition between replicas.
