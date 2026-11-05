# Reproducibility record

A second researcher should be able to re-run every experiment. This file records what the results were produced on, what is exactly reproducible, and what is only statistically reproducible.

## One command
```bash
pip install -r requirements.txt -r requirements-system.txt --break-system-packages   # or a venv
bash scripts/run_all_experiments.sh        # ≈ 2.5–3 h on a 2-vCPU machine; run NOTHING else at the same time
```
The experiments measure *time*, so they must run **one at a time on an otherwise idle machine**; running two together (or doing heavy work meanwhile) changes the results. The capstone is resumable (`results/m12_capstone_raw.csv` is appended per trial; delete it for a clean run).

## Hardware and operating system (where the reported numbers come from)
| Item | Value |
|---|---|
| Machine | cloud micro-VM (Firecracker), **2 vCPU** Intel Xeon @ 2.10 GHz, 8 GB RAM (8,214,984 kB) |
| OS / kernel | Linux 6.18.44-fc-v236 |
| Disk | VM-local, ephemeral |
| Network topology | **single host, loopback only** (127.0.0.1). Every "node" is an OS process; "links" are loopback TCP. Bandwidth, CPU, memory, failure and cross-traffic are emulated (see below). No real WAN, no multi-host run. |
| Containers | **none used** for any reported number (no Docker daemon on the machine). `docker-compose.system.yml` and `docs/run_with_docker.md` describe the container deployment; it was not executed. |

## Language, frameworks, versions
Python **3.13.18**; flask 3.0.3, werkzeug 3.1.9, requests 2.34.2, psutil 6.0.0, grpcio 1.85.1, protobuf 7.36.1, confluent-kafka 2.16.1 (client library; **no broker was run**), minio 7.2.20 (client library; **no MinIO server was run**), pytest 9.1.1, pandas 3.0.5, matplotlib 3.11.2, numpy 2.5.3. SQLite (stdlib) in WAL mode; the DFS, the bus stand-in (`LocalBus`) and the object-store stand-in (`LocalStore`) are in this repository.

## Dataset / workload
`python data/generate_dataset.py` → `data/telemetry_120k.csv`: **120 000 rows × 17 columns**, 24 cell sites in 6 regions (Nairobi, Mombasa, Kisumu, Nakuru, Eldoret, Nyeri), 1 785 anomalous rows (1.49 %), **seed 2403**, 17 days of timestamps.
**sha256 = `7e81ca812c2965b14346808d5907c42e4da813984574af5bbae794a41f95e691`** — regenerating the file on the reference machine produced a byte-identical file (checked with `cmp`). The generator prints the hash; it must match.

## Random seeds
| Use | Seed |
|---|---|
| dataset | 2403 |
| chaos / failure-injection RNG (capstone, M7) | 2403 |
| discrete-event simulator (M8) | 2403 … 2407 (five runs per cell) |
| process-controller `random` policy (M10) | `seed=rep` per repetition |
Everything else is deterministic code; **timing is not** (see below).

## What is exactly reproducible, what is not
| Result | Reproducible? |
|---|---|
| Dataset | **bit-for-bit** |
| M8 simulator tables (`results/m08_*.csv`) | **bit-for-bit** (seeds fixed; the one measured parameter, µs/row, is pinned at 4.0; two consecutive runs gave identical checksums) |
| Counts and correctness outcomes (rows stored, lost, duplicated; chunks lost; which policy wins; 0 vs non-0 errors) | **exactly**, up to the stated assumptions |
| Latencies, throughputs, speed-ups, MTTR, CPU %, memory | **statistically**: expect the same ordering and roughly the same ratios, not the same digits. Run-to-run variation on this 2-vCPU host is ≈ ±10 % for short trials (see the ±sd in the tables; n = 2–3 per cell). A machine with more cores will move the unconstrained-link results (baseline vs proposed) and the memory/CPU cliffs. |

## Configuration and experimental parameters
| Experiment | Command | Key parameters | Approx. time |
|---|---|---|---|
| M1 | `python -m system.experiments.m01_foundation` | CPU test 2.5 s × 3 reps; memory cap `RLIMIT_AS` 96 MB; 300 requests per payload size | 1 min |
| M2–M7, M11 | `python -m system.experiments.m0N_*` / `m11_rpc_dsm` | see each milestone document's "Results" header | see `scripts/run_all_experiments.sh` |
| M8 | `python -m system.experiments.m08_models` | 24 sites, load 0.5–1.5, 12–192 sites, MTBF 600/300 s, MTTR 60 s, horizon 600/1 800 s, `HEAVY`=40, pinned 4.0 µs/row, WAN 50 Mbit/s, cost 1/core-hour + 0.09/GB | 40 s |
| M9 | `python -m system.experiments.m09_transparency` | placement TTL 0.5 s; migration settle 2.2 × TTL per phase; 4 namespaces, 12 s of load, 2 reps | 2 min |
| M10 | `python -m system.experiments.m10_naming_procman` (parts `a c d e f`) | 24 names / 6 zones; 100 000-name table; 4 node agents (1 slow ×3), cap 1, 3 reps per policy; kill at 2 s | ≈ 10 min |
| M12 storage | `python -m system.experiments.m12_storage` | 24 MB file, chunks 256 KB–4 MB, R 1–3, 5 datanodes, dead-after 3 s (10 s in part A), 120 000-row archive run | ≈ 10 min |
| M12 capstone | `python -m system.experiments.m12_capstone <sweeps>` | nine sweeps, centre point 60 000 rows / 4 users / 3 cores / 2 CPUs; 3 reps (bandwidth, failure rate, transport) or 2; 253 trials; ports 20 000+100·(k mod 20) | ≈ 2.5 h |
| M12 coordination | `python -m system.experiments.m12_coordination` | N = 1, 2, 3, 5; heartbeat 0.5 s; 60 000 rows; 2 reps | 3.5 min |
| Analysis | `m12_analyze`, `m12_tables`, `powerbi/make_preview.py` | — | seconds |
| Tests | `python -m pytest tests -q` | 26 tests (unit + integration; they start real processes on ports 23 000+) | ≈ 3 min |

### How the capstone variables are emulated
| Variable | Mechanism | Not the same as |
|---|---|---|
| bandwidth | token bucket on the edge→core sender (baseline: on the client uplink) | a real link with latency, loss and queues |
| CPU | `sched_setaffinity` on core/collector processes; a competing spin loop for "contended" | cgroup CPU shares / a different CPU model |
| memory | `RLIMIT_AS` (address space) | cgroup memory limits (RSS) |
| network load | threads POSTing 32 KB reports to the entry point | competing traffic on a shared link |
| failure rate | SIGKILL of a core/collector, restart after 1 s | node loss, partitions, disk loss |
| request rate | global pacing in the driver | independent clients |

## Known sources of non-determinism
Process scheduling on 2 vCPUs; the load generator and every service share the CPUs; Python hash randomisation is not relevant to results; the Linux ephemeral port range (32 768–60 999) must not overlap service ports (every experiment and test uses ports between 20 000 and 32 100 for this reason: capstone 20 000–22 000, M3 22 000+, tests 23 000+, M4 24 000+, coordination 25 000+, M5 26 000+, storage 27 000+, M7 28 000+, M9 29 000+, M10 30 000+, M11 31 000+, M1 32 000+); leftover processes from an interrupted run can hold ports — check `pgrep -f system.` before starting.

## Stand-ins (stated again, because they matter)
`LocalBus` replaces Kafka and `LocalStore` replaces MinIO in every measurement. They implement the same producer/consumer and object interfaces (partitions, consumer offsets, commit-after-persist; put/get/list), so the *system* code path is the same, but broker-specific behaviour (replication, rebalancing, network latency) is not measured.
