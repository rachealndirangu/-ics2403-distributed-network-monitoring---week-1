import asyncio
import json
import random
import time
import argparse

parser = argparse.ArgumentParser(description="Edge Telemetry Agent")
parser.add_argument("--edge-id", type=str, default="Edge_01")
parser.add_argument("--core-host", type=str, default="core-aggregator-1")
parser.add_argument("--core-port", type=int, default=8001)
args = parser.parse_args()

async def collect_telemetry():
    """Simulates edge telecom metrics."""
    return {
        "node_id": args.edge_id,
        "timestamp": time.time(),
        "cpu_utilization": round(random.uniform(15.0, 98.0), 2),
        "bandwidth_mbps": round(random.uniform(50.0, 1000.0), 2),
        "packet_loss_pct": round(random.uniform(0.0, 6.0), 2),
        "jitter_ms": round(random.uniform(0.5, 30.0), 2)
    }

async def stream_to_core():
    print(f"[{args.edge_id}] Connecting to Core Aggregator at {args.core_host}:{args.core_port}...")
    while True:
        try:
            reader, writer = await asyncio.open_connection(args.core_host, args.core_port)
            print(f"[{args.edge_id}] Connected! Streaming telemetry...")
            while True:
                data = await collect_telemetry()
                payload = json.dumps(data) + "\n"
                writer.write(payload.encode())
                await writer.drain()
                await asyncio.sleep(2)
        except (ConnectionRefusedError, OSError):
            print(f"[{args.edge_id}] Core unavailable. Retrying in 3 seconds...")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(stream_to_core())