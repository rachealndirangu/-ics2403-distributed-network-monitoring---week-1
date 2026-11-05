# Milestone 1 — Distributed OS Foundation

**System stage S1:** the first distributed prototype. Model: **Nodes + Processes + Resources + Communication.**

| Brief deliverable | Where |
|---|---|
| Initial distributed prototype | `agent.py`, `collector.py`, `docker-compose.yml` (the Week-1 code, unchanged); exercised by `system/experiments/m01_foundation.py` |
| System architecture | this file + `docs/architecture.md` |
| Process model | § Process model below |
| Resource model | § Resource model below |
| Design justification | § Why this design |

Run: `python -m system.experiments.m01_foundation` → `results/m01_prototype_nodes.csv`, `m01_cpu_allocation.csv`, `m01_memory_allocation.csv`, `m01_comm_cost.csv`, `m01_summary.json` (≈ 50 s).

## What the prototype is
Three agent processes (`edge-node-a`, `edge-node-b`, `core-node`) read local CPU / memory / network counters (psutil) every 2 s and POST them to one `collector` process over HTTP. The collector keeps the latest reading per node and serves `GET /status`.

```
 edge-node-a ─┐
 edge-node-b ─┼── HTTP POST /metrics ──►  collector  ──►  GET /status  (known_nodes)
 core-node   ─┘
```

## Nodes, processes, resources, communication
| Concept | In this system |
|---|---|
| **Nodes** | 3 agent nodes (2 edge, 1 core) + 1 collector node. A node = one OS process here (one container under Docker; see `docs/run_with_docker.md`). |
| **Processes** | `agent.py` main loop (sample → report → sleep), `collector.py` Flask server (one handler thread per request). Later milestones add services, workers and a controller. |
| **Resources** | CPU time, resident memory, network bytes per node — the exact quantities the agents report; the collector's table of last-known readings is the shared resource. |
| **Communication** | HTTP/JSON push (agent → collector), request/response, no ordering or delivery guarantee. This choice is revisited in M4 (Lamport clocks), M7 (retries/failover) and M11 (RPC vs REST vs gRPC). |

## Operating-system responsibilities (brief: "identify")
A *network OS* gives each machine its own OS plus networking; a *distributed OS* presents one system image. This prototype is deliberately a **network OS style** system — every node manages its own CPU/memory — and the collector supplies the only global view. The OS-level responsibilities that exist from day one:

| Responsibility | Mechanism in the prototype |
|---|---|
| Process creation | `Cluster.start()` (`system/scripts/cluster.py`) launches each node as an OS process; Docker Compose does the same with containers |
| Process scheduling | local OS scheduler decides; in M10 a controller adds *global* placement (round-robin, random, least-loaded) |
| Resource allocation | CPU pinning (`sched_setaffinity`) and memory caps (`RLIMIT_AS`) — measured below |
| Inter-node communication | HTTP between processes; per-message cost measured below |
| Failure detection | absence of reports (stale `/status`) — deliberately weak, fixed from M7 on |

## Process model
`created → running → (reporting loop) → terminated | crashed`. Creation is `fork/exec` by the harness; termination is SIGTERM (clean) or SIGKILL (crash). There is no migration yet (M9) and no supervisor (M10). Evidence that three nodes register and report: `results/m01_prototype_nodes.csv` — **3/3 nodes registered after 1.01 s**, each with its own CPU and memory reading.

## Resource model
Resources are named, quantified and assignable. The experiment makes the allocation *visible* instead of assumed:

**CPU allocation (SHA-256 loop, 2.5 s per run, 3 reps; 2-vCPU sandbox)**

| CPUs allowed | workers | total hashes/s | per worker |
|---|---|---|---|
| 1 | 1 | 333,149 | 333,149 |
| 1 | 2 | 322,123 | 161,061 |
| 1 | 4 | 327,021 | 81,755 |
| 2 | 1 | 355,521 | 355,521 |
| 2 | 2 | **665,040** | 332,520 |
| 2 | 4 | 656,912 | 164,228 |

Reading: on one CPU, adding workers only *divides* the same capacity (total flat at ≈ 0.33 M/s); with two CPUs two workers double the total (2.0× the one-CPU total). Beyond the core count nothing is gained (4 workers on 2 CPUs: −1 %). This is the quantitative basis for every placement decision later.

**Memory allocation (`RLIMIT_AS` = 96 MB; request a block inside the process):** 32 MB → ok; 64 / 128 / 256 MB → `MemoryError`. The limit counts *virtual* address space, so the interpreter and libraries consume part of the 96 MB: the usable heap is much smaller than the cap. (Lesson used in the M12 memory sweep: a cap that looks generous can be fatal.)

**Communication cost (payload round trip to the REST server, 300 requests per size (60 for 1 MB), loopback)**

| payload | mean (ms) | p95 (ms) | jitter (ms) |
|---|---|---|---|
| 0 B | 1.590 | 1.971 | 0.238 |
| 1 KB | 1.573 | 2.028 | 0.417 |
| 64 KB | 1.704 | 2.245 | 0.337 |
| 1 MB | 3.268 | 3.791 | 0.371 |

A fixed cost of ≈ 1.6–1.7 ms per message dominates up to 64 KB; only at 1 MB does size matter (≈ 2×). Hence *batching* (M12 improvement) pays off long before payload size does.

## Why this design (justification)
* **Simplest thing that exhibits every concept.** Push-based HTTP/JSON, a single collector, local sampling: easy to reason about, easy to break on purpose.
* **Honest about being a network OS.** It does not hide distribution; it exposes it so that M9 (transparency) has something to improve.
* **Known weaknesses are the roadmap.** Single collector (SPOF → M7 replication), no global clock (→ M4), no atomic multi-node updates (→ M5), stale-data on node loss (→ M7/M9).

## Hypothesis → experiment → result
| Hypothesis | Experiment | Result |
|---|---|---|
| H1 Total compute scales with CPUs allowed up to the core count, not with the process count | hash benchmark, 1–4 workers × 1–2 CPUs | supported (2 workers on 2 CPUs: 2.0×; 4 workers: no further gain) |
| H2 A memory cap smaller than the working set is fatal, not slow | `RLIMIT_AS` 96 MB, requests 32–256 MB | supported (allocation fails with `MemoryError`) |
| H3 Per-message overhead, not bytes, dominates small messages | RTT vs payload | supported (1.6–1.7 ms from 0 B to 64 KB) |

## Failure-driven engineering log (week 1)
| Question | Answer |
|---|---|
| What changed? | Added a measurement harness around the Week-1 prototype (it was previously only runnable via Docker). |
| What failed? | First harness run used a payload shape the REST server rejected; the collector's port is hard-coded to 5000, so a second instance cannot run beside it. |
| Why? | The prototype was written to be run once, in a container, with fixed ports. |
| How fixed? | Payloads follow the server's `{"readings": [...]}` schema; the Week-1 collector runs on its fixed port and later services take ports from the harness. |
| Alternative considered | Rewrite the collector with configurable ports — rejected: Week-1 code is kept unchanged as the historical baseline. |
| What was learned? | Resource allocation is observable; "more processes" ≠ "more capacity"; fixed per-message cost motivates batching. |

## Limits
2-vCPU sandbox, loopback network, three nodes: this shows the *mechanics* of allocation, not the behaviour of real telecom hardware.
