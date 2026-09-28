import asyncio
import json
import os
import argparse

# Global state for Lamport Clock and Leader Election
lamport_clock = 0
current_leader = None

parser = argparse.ArgumentParser(description="Core Aggregator Node")
parser.add_argument("--node-id", type=int, required=True, help="Numeric Node ID for Bully Election")
parser.add_argument("--listen-port", type=int, default=8001)
parser.add_argument("--peers", type=str, default="", help="Comma-separated host:port list of peers")
args = parser.parse_args()

NODE_ID = args.node_id
LISTEN_PORT = args.listen_port
PEER_LIST = [p.strip() for p in args.peers.split(",") if p.strip()]

def tick_clock():
    global lamport_clock
    lamport_clock += 1
    return lamport_clock

def update_clock(received_clock):
    global lamport_clock
    lamport_clock = max(lamport_clock, received_clock) + 1
    return lamport_clock

async def handle_edge_data(reader, writer):
    """Receives telemetry from Edge agents."""
    peer_addr = writer.get_extra_info('peername')
    print(f"[Node {NODE_ID}] Edge connection established from {peer_addr}")
    while True:
        data = await reader.readline()
        if not data:
            break
        clock = tick_clock()
        message = json.loads(data.decode().strip())
        print(f"[Node {NODE_ID} | Lamport Clock: {clock}] Received Edge Telemetry: {message}")
        
        # Forward data to Cloud Server if this node is the Leader
        if current_leader == NODE_ID:
            await forward_to_cloud(message)

    writer.close()
    await writer.wait_closed()

async def forward_to_cloud(data):
    """Sends aggregated telemetry to the Cloud Tier."""
    try:
        cloud_host = os.getenv("CLOUD_HOST", "cloud-server")
        cloud_port = int(os.getenv("CLOUD_PORT", "9000"))
        reader, writer = await asyncio.open_connection(cloud_host, cloud_port)
        payload = json.dumps({"leader_id": NODE_ID, "lamport_clock": lamport_clock, "telemetry": data}) + "\n"
        writer.write(payload.encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        print(f"[Node {NODE_ID} | Leader] Successfully forwarded payload to Cloud.")
    except Exception as e:
        print(f"[Node {NODE_ID}] Failed to forward to Cloud: {e}")

async def start_bully_election():
    """Bully Leader Election Algorithm implementation."""
    global current_leader
    clock = tick_clock()
    print(f"\n[Node {NODE_ID} | Lamport Clock: {clock}] Starting Bully Election...")
    
    higher_nodes_exist = False
    for peer in PEER_LIST:
        try:
            host, port = peer.split(":")
            peer_id = int(host.split("_")[-1]) if "_" in host else int(host.split("-")[-1])
            if peer_id > NODE_ID:
                higher_nodes_exist = True
                reader, writer = await asyncio.open_connection(host, int(port))
                election_msg = json.dumps({"type": "ELECTION", "sender": NODE_ID, "clock": lamport_clock}) + "\n"
                writer.write(election_msg.encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()
        except Exception:
            pass

    if not higher_nodes_exist:
        current_leader = NODE_ID
        print(f"[Node {NODE_ID} | Lamport Clock: {lamport_clock}] *** ELECTION WON! Declaring self as LEADER ***\n")
        await announce_victory()

async def announce_victory():
    """Announce to all lower ID peers that this node is the Leader."""
    for peer in PEER_LIST:
        try:
            host, port = peer.split(":")
            reader, writer = await asyncio.open_connection(host, int(port))
            coord_msg = json.dumps({"type": "COORDINATOR", "leader": NODE_ID, "clock": lamport_clock}) + "\n"
            writer.write(coord_msg.encode())
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

async def handle_peer_messages(reader, writer):
    """Handles messages between Core Aggregator peers (Elections, Coordinator updates)."""
    global current_leader
    data = await reader.readline()
    if data:
        msg = json.loads(data.decode().strip())
        update_clock(msg.get("clock", 0))
        
        if msg.get("type") == "ELECTION":
            print(f"[Node {NODE_ID}] Received ELECTION message from Node {msg['sender']}. Triggering own election.")
            asyncio.create_task(start_bully_election())
        elif msg.get("type") == "COORDINATOR":
            current_leader = msg.get("leader")
            print(f"[Node {NODE_ID} | Lamport Clock: {lamport_clock}] NEW LEADER ELECTED: Node {current_leader}")

    writer.close()
    await writer.wait_closed()

async def main():
    server = await asyncio.start_server(handle_edge_data, "0.0.0.0", LISTEN_PORT)
    peer_server = await asyncio.start_server(handle_peer_messages, "0.0.0.0", LISTEN_PORT + 1000)
    print(f"[Node {NODE_ID}] Core Aggregator active on port {LISTEN_PORT} (Peer port {LISTEN_PORT + 1000})")
    
    # Trigger initial election on startup
    await asyncio.sleep(5)
    await start_bully_election()

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())