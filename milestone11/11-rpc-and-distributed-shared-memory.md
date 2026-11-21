# Milestone 11 — RPC and Distributed Shared Memory

**System stage S11:** services talk through a typed call abstraction (not hand-written HTTP), and nodes share named state through a directory-based DSM.

| Brief deliverable | Where |
|---|---|
| RPC implementation | `system/rpc/framework.py` (client stub → network → server stub, 3 call semantics, reply cache, accounting); `system/rpc/rest_server.py` (the same service as RPC-over-JSON, plain REST and NDJSON stream); `system/rpc/grpc_server.py` + `monitor.proto` (gRPC / protobuf) |
| Distributed memory / state mechanism | `system/dsm/node.py` — object-granularity DSM, home-node directory, MSI-style states, `MODE=strong` (write-invalidate) or `eventual` (write-update, last-writer-wins), distributed lock, atomic add |
| Communication benchmarks, consistency analysis | `python -m system.experiments.m11_rpc_dsm` → `results/m11_rpc_benchmark.csv`, `m11_call_semantics.csv`, `m11_dsm_consistency.csv`, `m11_dsm_synchronization.csv` |

## A — RPC benchmark (8 concurrent clients, loopback)
| payload | REST/JSON | RPC framework (JSON) | gRPC/protobuf |
|---|---|---|---|
| small `get_site` | 1.53 ms, 938 calls/s, req 21 B / resp 82 B | 1.74 ms, 876/s, 89 B / 102 B | **0.52 ms, 3,252/s**, 13 B / 43 B |
| 100 readings | 2.38 ms, 705/s, 21.2 kB | 2.02 ms, 713/s, 21.3 kB | **0.63 ms, 3,400/s**, 7.8 kB |
| 5,000 readings | 22.1 ms, 78/s, **1.07 MB** | 21.2 ms, 72/s, 1.07 MB | **2.12 ms, 825/s, 395 kB** |
| stream 10,000 readings | 138 ms (NDJSON) | 50 ms (one JSON array) | 681 ms (server stream, jitter 114 ms) |

*Reading.* gRPC is 3× faster for small calls and 10× for batches and sends 2.7× fewer bytes (protobuf vs JSON). The RPC framework over JSON costs ≈ 0.2 ms (≈ 14 %) more than raw REST for small calls (envelope, id, reply bookkeeping) and nothing measurable for large ones – the price of retries and call semantics. **gRPC server-streaming was the slowest** for 10,000 small messages: the synchronous Python gRPC server pays a per-message cost, so streaming is only attractive when messages are few and large, or with an async server – we report this rather than hide it.

## B — call semantics under 30 % reply loss (200 non-idempotent `increment` calls)
| semantics | calls returned OK | server executions | duplicates | retries | verdict |
|---|---|---|---|---|---|
| maybe | 129 / 200 | 200 | 0 | 0 | 71 calls report failure although they were executed – caller cannot know |
| at-least-once | 200 / 200 | **298** | **98** | 98 | counter over-counts by 49 % |
| at-most-once | 200 / 200 | **200** | 0 | 71 | 71 retries answered from the reply cache |

Only at-most-once (retry + server-side dedup by request id) gives the behaviour a monitoring counter needs; its cost is the reply cache (memory) and a lookup per request.

## C — DSM consistency vs cost
| operation | strong (write-invalidate) | eventual (write-update) |
|---|---|---|
| read, local hit | 1.84 ms | 2.78 ms (includes background update traffic) |
| read, miss via home | 5.82 ms, 2.2 msgs | 2.98 ms |
| write, no other sharer | 1.65 ms | 5.27 ms |
| write, 1 / 2 / 3 sharers | 5.13 / 6.23 / 7.31 ms, **1 / 2 / 3 invalidations** | 3.9 / 4.3 / 4.2 ms (flat) |
| **stale reads** (300 writes, 600 immediate remote reads) | **0 %** | **10 %** (60 / 600) |
| time until all nodes see a new value | 11.3 ms | 6.2 ms |
| 95 % read / 5 % write workload | 803 ops/s, 0.29 msg/op | 938 ops/s, 0.18 msg/op |
| 50 / 50 workload | 480 ops/s, 1.11 msg/op | 404 ops/s, 1.50 msg/op |

Strong consistency costs one invalidation round per remote sharer on every write (write latency grows linearly with sharers, 1.65 → 7.3 ms) and buys 0 % stale reads. Eventual consistency makes reads local and writes flat but 10 % of immediate reads are stale for a few ms, and under write-heavy load it sends **more** messages (1.5 vs 1.1 per op) because every write is pushed to every peer. Rule of thumb confirmed: write-invalidate for write-sharing-light data, write-update/eventual for read-mostly data that tolerates staleness (e.g. site thresholds); the crossover is near 50 % writes. Note that in `eventual` mode the "local hit" and "write with 0 sharers" rows include update messages from earlier operations still in flight – the message columns for that mode measure the whole protocol, not one call.

## D — synchronisation (4 nodes, 160 increments of one shared counter)
| style | final value | lost updates | wall | messages / increment |
|---|---|---|---|---|
| plain read-modify-write | **26** | **134 (84 %)** | 0.53 s | 1.1 |
| distributed lock | 160 | 0 | 2.33 s | 4.5 |
| atomic add at the home node | 160 | 0 | **0.32 s** | **0.8** |

Even a *sequentially consistent* memory does not make read-then-write atomic; correct sharing needs a primitive. Moving the update to the data (atomic add at the home) is both the fastest and the cheapest (7× faster than the lock, 5.6× fewer messages).

## Failure-driven engineering log (week 11)
| Question | Answer |
|---|---|
| What changed? | RPC framework with three call semantics, REST and gRPC servers, DSM with two coherence modes and sync primitives. |
| What failed? | (1) At-least-once calls over-counted. (2) Plain read-modify-write on strongly consistent DSM lost 84 % of updates. (3) gRPC streaming was 5× slower than NDJSON. |
| Why? | (1) Lost replies cause retries of executed calls. (2) Coherence orders individual reads and writes, not read-then-write pairs. (3) Per-message overhead of the synchronous Python gRPC server. |
| How fixed? | (1) Server reply cache keyed by request id → at-most-once. (2) Lock and atomic-add primitives. (3) Not "fixed": reported; recommended batching or an async server. |
| Alternative considered | Page-granularity DSM with false sharing; consensus-backed (Raft) state instead of DSM; HTTP/2 REST. |
| What was learned? | Retries need idempotence or dedup; consistency models do not compose into atomicity; protocol choice must be measured per payload shape. |

## Limitations
Loopback (no real network latency, so the benefit of gRPC's smaller messages is understated); DSM nodes are not failure-tolerant (a crashed home loses its directory) – failure handling belongs to the replicated store of M7; reply cache is unbounded in time (size-bounded only).
