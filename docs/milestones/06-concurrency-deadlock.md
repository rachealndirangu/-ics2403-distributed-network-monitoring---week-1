# Milestone 6 — Concurrency and Deadlock Management

**System stage S6:** several concurrent services share resources (quota pools, links, locks) through a resource manager that can show — and handle — races, deadlock, starvation and contention.

| Brief deliverable | Where |
|---|---|
| Concurrent distributed implementation | `system/concurrency/lockmgr.py` (resource manager), `system/concurrency/service.py` (HTTP service; clients are separate processes/threads) |
| Deadlock experiment | `python -m system.experiments.m06_concurrency` → `results/m06_deadlock.csv` |
| Detection / recovery mechanism | `policy="detect"` (wait-for-graph cycle detection + youngest-victim abort + retry) and prevention policies `ordered`, `wait-die` |
| Resource-allocation graph P<sub>i</sub> → R<sub>j</sub> | `results/m06_rag_*.dot` / `.png` (request edge P→R, assignment edge R→P), wait-for dumps `m06_wait_for_*.txt` |
| Resource-utilisation analysis | `results/m06_utilization.csv` |

## Model
Processes P<sub>i</sub> request resources R<sub>j</sub> (capacity = number of identical units; 1 = mutex). The manager keeps request edges P→R and assignment edges R→P and derives the wait-for graph P→P'. A cycle in the wait-for graph is a deadlock when all resources have one unit (Coffman: mutual exclusion, hold-and-wait, no pre-emption, circular wait).
Policies: `none` (wait forever), *timeout-only* (client gives up after 2.5 s), `detect` (detector thread every 0.2 s; victim = youngest in the cycle, its `acquire` raises `Deadlock`, caller releases and retries), `ordered` (prevention: refuse a request ranking below one already held ⇒ no circular wait), `wait-die` (prevention: younger requester facing an older holder dies and restarts with its **original** timestamp ⇒ cannot starve). Fairness: FIFO queue vs barging.

## Results
**A — race condition (8 clients × 100 increments).**
| mode | final value (expected 800) | lost updates |
|---|---|---|
| no mutual exclusion | 311 | **489 (61.1 %)** |
| mutex via lock manager | 800 | 0 (wall time 0.96 s → 1.55 s: the price of exclusion) |

**B — deadlock: 4 services in a circle (P<sub>i</sub> holds R<sub>i</sub>, wants R<sub>i+1</sub>), 20 jobs, 3 reps.**
| policy | jobs completed | wall time | deadlocks detected / victims | notes |
|---|---|---|---|---|
| none (wait forever) | **1, 0, 0 of 20** | 30 s (cut off) | 0 | permanent deadlock; only the client time-out ended the run |
| timeout-only (2.5 s) | 3, **20**, 3 of 20 | 10.3 / 6.1 / 10.3 s | 0 | outcome is luck — timeouts break one cycle but the retries re-deadlock |
| detect + recover | 20/20 in all 3 | **1.27 s** | 1 / 1 | cycle found in 0.14–0.15 s; 1 victim restarted |
| ordered (prevention) | 20/20 | **1.10 s** | 0 | no cycle can form; 0 restarts; utilisation 0.68 |
| wait-die (prevention) | 20/20 | 1.21 s | 0 / 29 dies | 29 restarts are the price of never forming a cycle |

The RAG of the stuck run (`m06_rag_none__wait_forever.png`) shows the 4-cycle P0→R1→P1→R2→P2→R3→P3→R0→P0; after recovery (`m06_rag_detect_recover.png`) the victim's edges are gone.

**C — starvation.** A request for the whole 4-unit pool against a stream of 1-unit requests: with *barging* the large request was **never granted in 6 s (3/3 reps starved)**; with FIFO it was granted after ≈ 0.1 s (about one hold time).

**D — contention (4-unit pool, 20 ms hold; analytic bound 200 req/s).**
| clients | throughput/s | mean wait (ms) | p95 wait (ms) | utilisation |
|---|---|---|---|---|
| 1 | 33.3 | 2.2 | 2.6 | 0.19 |
| 2 | 63.6 | 2.8 | 3.9 | 0.36 |
| 4 | 130.2 | 2.5 | 4.5 | 0.74 |
| 8 | 170.9 | 18.4 | 21.0 | 0.94 |
| 16 | 170.9 | 64.1 | 68.3 | 0.96 |
Throughput rises almost linearly to 4 clients (= capacity) then flattens at **171/s, 85 % of the 200/s bound** (the remainder is service overhead per request); past saturation extra clients only add waiting time (×3.5 from 8 to 16 clients). Utilisation of the pool approaches 0.96 — contention costs latency, not capacity.

## Analysis — which handling to use?
Prevention by ordering was fastest and simplest *when the order is known in advance* (it is: resources are ranked by id). Detection is the right tool when requests are dynamic — it costs a detector thread and one victim restart (0.14 s to find, 1.27 s total). Timeouts alone are not a deadlock strategy. Wait-die trades restarts (29) for never needing a graph.

## Failure-driven engineering log (week 6)
| Question | Answer |
|---|---|
| What changed? | Lock/resource manager with four deadlock policies, RAG export, fairness switch, service wrapper. |
| What failed? | The first deadlock experiment showed policy "none" *completing* its jobs. |
| Why? | The client's request time-out silently broke the cycle (abort → retry), so "no handling" looked fine. |
| How fixed? | Split into "none (wait forever)" (client timeout 30 s) and "timeout-only (2.5 s)"; both now show their real behaviour. |
| Alternative considered | Banker's algorithm (needs maximum demand declared up-front, unrealistic for monitoring services); pre-emption (unsafe for stateful resources). |
| What was learned? | An experiment must not contain a hidden recovery mechanism; prevention and detection have different cost profiles (restarts vs detector latency); starvation needs a *fairness* policy, not more capacity. |

## Limitations
Single-resource-manager deadlock handling (the distributed case is solved only by ordering in M5); the detector runs centrally; 20-job workload.
