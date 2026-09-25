# Week 1 — Distributed OS Foundation

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
