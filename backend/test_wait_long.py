"""Wait 8 minutes and check."""
import time
import httpx

print("Waiting 8 minutes for full pipeline...")
time.sleep(480)
r = httpx.get("http://127.0.0.1:8188/queue", timeout=15)
q = r.json()
print(f"\nQueue: running={len(q.get('queue_running', []))}, pending={len(q.get('queue_pending', []))}")
for item in q.get("queue_running", []):
    print(f"  RUN: {item[1]}")
for item in q.get("queue_pending", []):
    print(f"  PEND: {item[1]}")

r2 = httpx.get("http://127.0.0.1:8188/internal/logs?max_lines=15", timeout=15)
print("\n--- Last log lines ---")
print(r2.text[-2000:])
