# Milestone 4 — Distributed Algorithms and Coordination

**System stage S4:** the core is now a replica group with a single active member (Bully leader election), events are ordered by logical clocks, and the edge→core link is a durable log so a leader change loses nothing.

| Brief deliverable | Where |
|---|---|
| Distributed algorithm implementation | `system/core/service.py` (Bully election, heartbeats, leader-only consumption), `system/common/lamport.py` (Lamport + vector clocks), `system/edge/gateway.py` (stamps/forwards clocks) |
| Algorithm analysis, complexity analysis | §Algorithms and §Complexity below |
| Experimental results | `python -m system.experiments.m04_coordination` → `results/m04_*.csv` |

## Algorithms
**Bully election.** Nodes have ids 1..n. A node that detects leader silence (`HEARTBEAT_MISS_LIMIT` = 2 consecutive missed pings) sends ELECTION to all higher ids; if none answers OK it declares itself leader (COORDINATOR to all); a node that gets an OK waits for the COORDINATOR. The highest live id always wins. Safety: at most one node believes it is leader when links are reliable (checked by sampling every core's `/leader` every 100 ms: **0 split-brain samples in 24 election runs**).
**Leader-only consumption.** Only the leader polls the log (consumer group); followers stay warm. Offsets are committed *after* persisting → at-least-once; the SQLite `PRIMARY KEY(record_id)` + `INSERT OR IGNORE` makes processing idempotent per replica.
**Lamport clock.** `send: t←t+1`; `receive: t←max(t, m)+1`. Guarantees `a→b ⇒ L(a)<L(b)`; the converse does not hold (we do not claim concurrency detection from it; `VectorClock` is provided for that).

## Complexity
| Quantity | Theory | Measured (mean of 3) |
|---|---|---|
| Election messages, best case (highest id fails last / lowest id starts) | O(n) | re-election 1 msg at n=2, 4 at n=3 |
| Election messages, worst case (lowest id starts) | O(n²) (bound n²: 4, 9, 16, 25, 36) | start-up storm 2.3 / 9.3 / 18.3 / 30.7 / 49 messages for n = 2…6 — grows ≈ quadratically but stays under the bound |
| Heartbeat overhead (steady state) | n−1 messages per interval from the leader → O(n) | 0.83 / 1.72 / 2.56 / 3.67 / 4.72 msg/s for n = 2…6 at 1 s interval (≈ n−1) |
| Failover delay | ≈ detection timeout + election round | 0.33 s / 0.60 s / 1.08 s / 2.09 s for heartbeat 0.25 / 0.5 / 1 / 2 s (n=4) |
| Per-message cost trade | shorter heartbeat → faster failover, more traffic | 0.25 s: 11.5 msg/s overhead vs 2 s: 1.17 msg/s |

Re-election message counts vary run to run (1–17 at n≥4) because several nodes can time out simultaneously and each starts its own election (an election storm); `STARTUP_DELAY` lets peers come up before the first election.

## Experiments (Hypothesis → Design → Measurement)
* **A/B — election vs n and heartbeat.** H: failover ≈ heartbeat interval, messages grow superlinearly with n. n ∈ 2…6 at hb = 1 s; n = 4 with hb ∈ {0.25, 0.5, 2} s; 3 reps; leader SIGKILLed. Result: table above. H supported.
* **C — logical vs physical clocks.** Three agents report through the gateway with wall-clock offsets 0 / +3 s / −3 s (`SKEW_SECONDS`); the leader core checks, for each trace, whether ordering by the agents' wall-clock timestamps agrees with ordering by Lamport timestamps and with the true arrival causality. Result: with no skew both orderings are right (112 traces, 0 violations); with ±3 s skew **33.6 % of 113 traces violate causality when ordered by wall-clock time, 0 % when ordered by Lamport timestamps**.
* **D — leader crash during a 120,000-row stream.**

| scenario | rows stored / sent | lost | duplicate rows across replicas | completion |
|---|---|---|---|---|
| control (no failure) | 120,000 / 120,000 | 0 | 0 | 2.7 s |
| leader crash at ≈ 35 % (rep 1) | 120,000 / 120,000 | 0 | 2,416 | 3.0 s |
| rep 2 | 120,000 / 120,000 | 0 | 84 | 2.9 s |
| rep 3 | 120,000 / 120,000 | 0 | 0 | 2.9 s |

  Consistency: **no row is lost**, but because offsets are committed after persisting, the rows between the last commit and the crash are re-processed by the new leader and exist in two replicas' databases (84–2,416 duplicates). Downstream consumers (archiver, queries) de-duplicate by `record_id`; exactly-once would need a transactional offset+write, listed as future work.

## Failure-driven engineering log (week 4)
| Question | Answer |
|---|---|
| What changed? | Replica group + Bully election + heartbeats + Lamport stamps + durable log between edge and core. |
| What failed? | (1) Early re-election message counts came out *negative*. (2) The Week-4 design (gateway retries to the current leader over HTTP) can lose or duplicate a chunk that was in flight when the leader died; this is why the log was introduced. |
| Why? | (1) The killed leader's counters were in the "before" snapshot but not in "after". (2) An HTTP request acknowledged by the dying leader but not yet persisted is unrecoverable by the sender; with a log the sender's acknowledgement means 'appended', and consumption is replayable. |
| How fixed? | (1) Take both snapshots on the surviving nodes only. (2) Replaced the retry design by the log: the edge is acknowledged only after the log append; the new leader resumes from the committed offset. |
| Alternative considered | Raft/consensus (O(n) per decision, no election storms) — more code than the coursework scope, listed under future work; ring election (O(n) but slower detection). |
| What was learned? | Election cost is dominated by simultaneous timeouts, not by the algorithm's best case; at-least-once + idempotent writes is the cheap way to a consistent store. |

## Limitations
Single host, so "partitions" are simulated by killing processes; Bully assumes reliable links and synchronous timeouts (a paused leader that wakes up would briefly disagree — see M7's SIGSTOP experiment).
