import asyncio
import json
import os

HOST = "0.0.0.0"
PORT = int(os.getenv("CLOUD_PORT", "9000"))

async def handle_core_stream(reader, writer):
    """Handles incoming telemetry forwarded by the Core Leader node."""
    peer_addr = writer.get_extra_info('peername')
    print(f"[Cloud Server] Received connection from Core Leader at {peer_addr}")
    
    while True:
        data = await reader.readline()
        if not data:
            break
        try:
            payload = json.loads(data.decode().strip())
            leader_id = payload.get("leader_id")
            lamport_clock = payload.get("lamport_clock")
            telemetry = payload.get("telemetry")
            
            print(f"[CLOUD STORAGE | Leader: Node {leader_id} | Lamport Clock: {lamport_clock}] "
                  f"Stored Telemetry from {telemetry.get('node_id')}: "
                  f"CPU={telemetry.get('cpu_utilization')}% | BW={telemetry.get('bandwidth_mbps')}Mbps")
        except json.JSONDecodeError:
            print("[Cloud Server] Received malformed JSON packet.")

    writer.close()
    await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_core_stream, HOST, PORT)
    print(f"[Cloud Server] Central Cloud Storage operational on port {PORT}...")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())