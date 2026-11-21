# Milestone 5 — Distributed Transactions

**System stage S5:** capacity reallocation between resource managers (participants) is an atomic distributed transaction: *Prepare → (Pre-commit) → Commit/Abort → Completion*.

| Brief deliverable | Where |
|---|---|
| Transaction subsystem | `system/txn/coordinator.py` (2PC + 3PC, decision log, retry thread, restart recovery), `system/txn/participant.py` (SQLite ledger, strict 2PL, forced vote log, termination protocol) |
| Failure experiments | `python -m system.experiments.m05_transactions` → `results/m05_coordinator_crash.csv`, `m05_participant_recovery.csv`, `m05_atomicity_isolation.csv`, `m05_availability_timeline.csv` |
| Recovery mechanism | §Recovery |
| Consistency analysis | §Consistency |

## Model
Workload: move Mbps of quota between sites held by different participants; every transaction is zero-sum, so **total quota over all participants is the invariant** (3,400,020 in the runs).
ACID: *Atomicity* — all operations applied in one SQLite transaction on commit or none; *Consistency* — a quota can never go negative (violation ⇒ vote NO at prepare); *Isolation* — strict 2PL, per-account locks taken at prepare and held to completion; *Durability* — the vote is forced to disk (`synchronous=FULL`) before it is returned, the coordinator forces its decision before telling anyone (the commit point).
Evaluation metrics requested by the brief: transaction latency, throughput, failure behaviour, consistency, availability.

## Recovery
* **Coordinator restart:** decision logged but undelivered → re-send; 2PC with no logged decision → ABORT (presumed abort; nobody can have committed); 3PC with no decision → collect participant states and apply the termination rule.
* **Participant restart:** in-doubt (PREPARED) transactions get their locks back from the log, then ask the coordinator; if it is down, ask peers (cooperative termination).
* **3PC termination rule:** any peer COMMITTED/PRECOMMITTED ⇒ commit; any ABORTED or all only PREPARED ⇒ abort. Non-blocking under fail-stop crashes without partitions.

## Results
**A — latency/throughput (clean runs).** (`results/m05_latency_throughput.csv`; every run kept the invariant, 0 aborts.)

| participants | clients | 2PC tps / mean ms / p95 | 3PC tps / mean ms / p95 | 3PC cost |
|---|---|---|---|---|
| 2 | 1 | 88.9 / 11.3 / 14.4 | 59.0 / 17.0 / 20.7 | +51 % latency |
| 3 | 1 | 76.8 / 13.0 / 15.6 | 45.8 / 21.8 / 26.9 | +68 % |
| 4 | 1 | 60.2 / 16.6 / 21.2 | 34.5 / 29.0 / 35.3 | +74 % |
| 3 | 16 | 101.9 / 154.3 / 179.4 | 69.8 / 224.6 / 280.6 | +46 % |

Latency grows with participants (more votes to collect) and with concurrency (queueing on the coordinator and on participant locks); throughput saturates around 100–135 tps (2PC) on this host. 3PC's extra round trip costs +46…+74 % latency, matching H1 (predicted +25–60 %; the single-client cases exceed it, probably because the extra phase adds another forced log write — we did not isolate this).

**B — atomicity and isolation.**

| case | result |
|---|---|
| no protocol, one resource manager down, 20 transfers | **200 Mbps of quota destroyed** (total 3,400,020 → 3,399,820): invariant broken |
| 2PC, same failure | 20/20 aborted, 0 lost, no locks left |
| 3PC, same failure | 20/20 aborted, 0 lost |
| 2PC, parallel prepare, 16 clients, one hot account | **9 of 240 committed**, 231 lock-timeout aborts, 0.6 tps (invariant held, service useless) |
| 2PC, **ordered prepare**, same load | 240/240 committed, 103 tps, mean latency 134 ms |
| 3PC, ordered prepare, same load | 239/240 committed, 64.5 tps |

**C — coordinator crash at each step (participants stay up; 2 reps).**

| protocol | crash point | resolved without coordinator? | participants blocked | locks held | recovery after coordinator restart |
|---|---|---|---|---|---|
| 2PC | after prepare (votes in, no decision) | **no** | > 9 s (until restart) | 3 | 1.18 s → ABORT |
| 2PC | after decision logged | **no** | > 9 s | 3 | 0.64–0.68 s → COMMIT |
| 3PC | after prepare | yes | ≈ 1.96 s | 3 (released) | 0.31 s → ABORT |
| 3PC | mid-precommit / after precommit / after decision | yes | ≈ 1.95–2.06 s | 3 (released) | 0.31 s → COMMIT |

All 12 runs ended with all participants agreeing and the invariant intact. **2PC blocks, 3PC does not** (H2 supported); the ≈ 2 s for 3PC is dominated by the participants' in-doubt timer (`INDOUBT_AFTER_S` = 1.5 s) plus one termination round, not by protocol rounds.

**D — participant crash while in-doubt.** Participant p2 killed after voting: on restart it finds 1 in-doubt transaction, restores 0 locks when the coordinator is alive and resolves it by asking the coordinator (1.5 s); when the coordinator is *also* down it restores 1 lock and resolves by asking a peer (1.7 s 2PC / 1.9 s 3PC). Final state COMMITTED, invariant held in all four cases.

**E — availability.** A participant is down for seconds 4–7 of 12. Committed share per second drops from ≈ 1.0 to **0.00** for both protocols and returns to ≈ 0.95 within 2 s of restart (2PC) / ≈ 0.9 (3PC). H4 supported: atomic commit over all participants has *no* availability advantage; 3PC buys non-blocking recovery, not availability.

## Consistency analysis
The invariant held in every scenario that used a protocol and broke in the one that did not. The only non-ACID observation is *liveness*, not safety: the hot-account case below.

## Failure-driven engineering log (week 5)
| Question | Answer |
|---|---|
| What changed? | Coordinator, participants, decision/vote logs, termination protocols, fault-point injection. |
| What failed? | 16 clients on one hot account: only 9 of 240 transactions committed (231 lock timeouts) although safety held. |
| Why? | **Distributed deadlock**: two transactions prepared in parallel took the same account lock on different participants in opposite order, so each waited for the other; bounded lock waits turned the deadlock into timeouts instead of progress. |
| How fixed? | *Ordered prepare*: the coordinator contacts participants in a fixed global order (resource ordering ⇒ no cycle). Throughput 0.6 → 103 tps, 0 timeouts. Also rewrote the in-doubt experiment so it really crashes both coordinator and participant (first version never exercised lock recovery). |
| Alternative considered | Wait-for-graph deadlock detection across participants (more machinery; see M6 for the single-node version); optimistic concurrency with validation at commit. |
| What was learned? | "Timeouts make deadlock impossible" is false — they make it *expensive*. Ordering resources is the cheapest prevention. 3PC's non-blocking property costs ~+50 % latency and only holds without partitions. |

## Limitations
Fail-stop crashes only (3PC is unsafe under partitions — we do not claim otherwise); one coordinator (no coordinator replication — a real system would run the coordinator on a consensus group); SQLite on one disk, so "durability" is measured as fsync-ed WAL, not multi-machine replication.
