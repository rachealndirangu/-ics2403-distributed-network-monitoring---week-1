# Running the full stack with Docker (real Kafka, MinIO, HDFS-style DFS)

> **Status, stated plainly:** the development machine for this project had no Docker daemon, so the *compose file and the `KafkaBus` /
> `MinioStore` code paths were not executed here*. Everything else (all experiments and tests) ran against the in-repo stand-ins:
> `LocalBus` (a file-backed, partitioned, offset-committing log with the same producer/consumer interface as Kafka) and `LocalStore`
> (a directory with the MinIO interface). If something fails on a first Docker run, the likeliest places are the Kafka client
> settings in `system/common/bus.py` (`KafkaProducerWrapper`/`KafkaConsumerWrapper`) and MinIO start-up timing in `system/common/objstore.py`.
> The lecturer's requirement "Kafka between edge and core" is implemented in code and compose; its *measured* behaviour comes from the stand-in.

## Run
```bash
docker compose -f docker-compose.system.yml up --build -d
docker compose -f docker-compose.system.yml logs -f replayer-a replayer-b     # 2 edge nodes stream 2 x 60,000 rows
python -m system.scripts.verify_docker --expect 120000                          # waits until DFS + MinIO both hold all 120,000 ids
docker compose -f docker-compose.system.yml down -v
```
Baseline for comparison: `docker compose -f docker-compose.system.yml --profile baseline up baseline-collector` and point a replayer at `http://localhost:5100`.

## Capacity variables on Docker
The capstone sweeps emulate the variables locally (CPU affinity, `RLIMIT_AS`, a throttled link, cross-traffic threads, kill/restart chaos). On Docker the same variables map to: `cpus:` / `mem_limit:` (cgroups), `tc qdisc add dev eth0 root tbf rate 25mbit burst 32kbit latency 400ms` inside the gateway container (bandwidth), `docker kill` / `docker start` (failure rate), replayer `--rate` (request rate). To reproduce a sweep against Docker, replace the `Cluster` start-up in `system/experiments/m12_capstone.py::trial` by the compose services; the driver, probes and metrics are unchanged.

## Ports
gateway 5000, cloud 5002, archiver 5003, Kafka 9092, MinIO 9000/9001 (console), baseline collector 5100 (profile `baseline`). Core and DFS ports are internal to the compose network.
