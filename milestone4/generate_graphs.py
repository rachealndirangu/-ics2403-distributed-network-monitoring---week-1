import matplotlib.pyplot as plt 
import matplotlib.pyplot as plt

# 1. Throughput vs. Node Count Graph
nodes = [1, 2, 3, 4, 6]
throughput = [100, 220, 310, 430, 600]

plt.figure(figsize=(6, 4))
plt.plot(nodes, throughput, marker='o', color='b', linewidth=2)
plt.title('Throughput vs. Node Count')
plt.xlabel('Number of Active Nodes')
plt.ylabel('Throughput (metrics/sec)')
plt.grid(True)
plt.tight_layout()
plt.savefig('throughput_vs_nodes.png')
plt.close()

# 2. Latency vs. Node Count Graph
latency = [2.1, 2.5, 3.8, 5.2, 8.1]

plt.figure(figsize=(6, 4))
plt.plot(nodes, latency, marker='s', color='r', linewidth=2)
plt.title('Latency vs. Node Count')
plt.xlabel('Number of Active Nodes')
plt.ylabel('Average Latency (ms)')
plt.grid(True)
plt.tight_layout()
plt.savefig('latency_vs_nodes.png')
plt.close()

# 3. Recovery Latency vs. Failure Type Graph
failure_types = ['Follower Crash', 'Leader Crash', 'Network Partition']
recovery_time = [0.2, 1.8, 2.5]

plt.figure(figsize=(6, 4))
plt.bar(failure_types, recovery_time, color=['green', 'orange', 'red'])
plt.title('Recovery Latency vs. Failure Type')
plt.xlabel('Failure Scenario')
plt.ylabel('Recovery Time (seconds)')
plt.grid(axis='y')
plt.tight_layout()
plt.savefig('recovery_vs_failure.png')
plt.close()

print("Graphs generated successfully!")