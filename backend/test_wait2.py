"""Wait and check."""
import time
import httpx

time.sleep(120)
r = httpx.get("http://127.0.0.1:8188/internal/logs?max_lines=15", timeout=15)
print(r.text[-1500:])
r2 = httpx.get("http://127.0.0.1:8188/queue", timeout=15)
q = r2.json()
print(f"\nQueue: running={len(q.get('queue_running', []))}, pending={len(q.get('queue_pending', []))}")
for item in q.get("queue_running", []):
    print(f"  RUN: {item[1]}")
for item in q.get("queue_pending", []):
    print(f"  PEND: {item[1]}")
