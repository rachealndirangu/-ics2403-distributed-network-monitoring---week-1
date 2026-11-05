# ICS 2403 — Distributed Network Monitoring System (Theme 2)

A telecom-style network-monitoring system built over 12 weekly milestones, from three polling agents (Week 1) to an
edge → log → replicated core → cloud → distributed-storage pipeline, measured against its own Week-1/2 baseline.

```
Users / Devices ──► Edge gateway ──► partitioned log (Kafka interface) ──► Telecom core (3 replicas, Bully leader) ──► Cloud digest ──► Distributed storage (DFS R=3 + object store)
```

## Where everything is
| What | Where |
|---|---|
| 12 milestone write-ups (deliverables, hypotheses, results, weekly failure log) | `docs/milestones/01-…` to `12-…` |
| Failure-driven engineering log (all weeks side by side) | `docs/engineering-log.md` |
| 30-section technical report | `docs/technical-report.md` |
| Conference-style paper (existing ≠ implementation ≠ contribution) | `docs/research-paper.md` |
| Oral-defence preparation, Parts A–G | `docs/oral-defense.md` |
| Reproducibility record (hardware, versions, seeds, commands) | `docs/reproducibility.md` |
| Architecture and docker deployment | `docs/architecture.md`, `docs/run_with_docker.md` |
| System code | `system/` (core, edge, cloud, storage, replication, transparency, procman, rpc, dsm, experiments, scripts) |
| Dataset generator and the 120,000-row dataset | `data/generate_dataset.py`, `data/telemetry_120k.csv` |
| Raw and summarised results of every experiment | `results/` |
| Power BI model, queries, DAX measures, 4 chart previews | `powerbi/` |
| Tests (14 unit + 12 integration) | `tests/` |

## Quick start
```bash
pip install -r requirements.txt -r requirements-system.txt --break-system-packages
python data/generate_dataset.py                 # 120,000 rows; sha256 must be 7e81ca81…95e691
python -m pytest tests -q                       # ≈ 3 min, starts real processes on ports 23000+
python -m system.scripts.demo_failure           # kill the leader mid-stream; see detection, recovery, restoration (≈ 25 s)
bash scripts/run_all_experiments.sh             # every experiment, ≈ 2.5–3 h on 2 vCPUs, run nothing else meanwhile
```

## Lecturer's requirements
| Requirement | Delivered |
|---|---|
| 100,000+ row dataset | 120,000 rows × 17 columns, 24 cell sites, seed 2403, byte-reproducible |
| Kafka (or Hadoop/Hive) between edge and core | `system/edge` → log → `system/core`, Kafka client interface (`KafkaBus`) with `docker-compose.system.yml`; **measurements ran on a file-backed stand-in with the same producer/consumer/offset semantics (`LocalBus`) — no broker was run** |
| Distributed storage / Hadoop-style | HDFS-style DFS (namenode, datanodes, checksums, re-replication) + object-store archive |
| Power BI file with 2–4 charts | 4 charts specified in `powerbi/` (Power Query, DAX, layout) and previewed as PNG. **The `.pbix` binary was not created** (Power BI Desktop is Windows-only); open `powerbi/README.md` and build it in ≈ 10 minutes |

## Headline results (single 2-vCPU host, loopback; bandwidth, CPU, memory and failures are emulated)
* **Improvement** (adaptive site-affine coalescing + zlib on the edge→core link): bytes on the link 44.5 → 6.1 MB (7.3×); time to deliver 120,000 rows is 3.6–5.9× shorter than the flat baseline at ≤ 25 Mbit/s (crossover ≈ 130 Mbit/s).
* **Availability** at 6 / 12 / 20 crashes per minute: flat baseline 84.8 / 77.6 / 63.7 %, tiered system 100 %; no rows lost in any system.
* **Failover:** leader crash detected in ≈ 0.8 s, new leader resumes from the committed offset, 120,000 of 120,000 rows stored.
* **Negative results, kept:** on an unconstrained link the baseline is ≈ 2.8× faster and uses ≈ 6× less memory; the tiered system collapses under a 256 MB address-space cap; more replicas add no throughput.

## Honest limits
Single host and loopback network; n = 2–3 repetitions per cell (wide confidence intervals); Kafka and MinIO stand-ins; Docker deployment written but not executed; no `.pbix`; the M8 "best architecture" depends on who pays for edge hardware (both cost models are reported). Details: `docs/reproducibility.md`, "Limits" of `docs/milestones/12-capstone.md`.

---

# Week 1 — Distributed OS Foundation (the original prototype, unchanged)

Theme 2: Distributed Network Monitoring System — ICS 2403.

Three agent nodes (`edge-node-a`, `edge-node-b`, `core-node`) each read local
CPU/memory/network stats every 2 seconds and push them to a central
`collector` node over HTTP. This is the minimal skeleton the rest of the
12-week system builds on.

## Run it

Requires Docker and Docker Compose.

```bash
docker compose up --build
```

Then, in another terminal, check the collector's view of the system:

```bash
curl http://localhost:5000/status | python3 -m json.tool
```

You should see all three node IDs under `known_nodes`, each with its latest
CPU/memory/network reading. Watch the terminal running `docker compose up`
to see each agent's reports and the collector receiving them live.

Stop everything with `Ctrl+C`, then `docker compose down`.

## Try a failure (a preview of Week 7)

```bash
docker compose stop edge-node-a
```

Watch `collector`'s log — it simply stops hearing from `edge-node-a`, but
`edge-node-b` and `core-node` keep reporting normally. `GET /status` will
keep showing `edge-node-a`'s *last known* reading, which is exactly the kind
of stale-data problem Week 7 (fault tolerance) and Week 9 (failure
transparency) are meant to address.

## Files

| File | Role |
| --- | --- |
| `agent.py` | Runs on every monitored node; reads local stats, pushes to the collector |
| `collector.py` | Runs on the central node; receives reports, exposes `/status` |
| `Dockerfile` | One shared image for both roles (agent vs. collector chosen via `command:`) |
| `docker-compose.yml` | Defines the 4 nodes and the network they share |
| `requirements.txt` | `flask`, `psutil`, `requests` |

## Reproducibility

- **OS (tested)**: Ubuntu 24.04 (host), `python:3.11-slim` (containers)
- **Language**: Python 3.11
- **Frameworks/libraries**: Flask 3.0.3, psutil 6.0.0, requests 2.32.3 (pinned in `requirements.txt`)
- **Network topology**: single Docker bridge network (`monitor-net`), 4 containers
- **Configuration**: all node identity/config passed via environment variables in `docker-compose.yml` — no code changes needed to add a node, just another service block
- **Workload**: each agent reports every `REPORT_INTERVAL` seconds (default 2s); no external load generator yet — that arrives in Week 2

A second person should be able to clone this folder and run `docker compose up --build`
with no other setup.
