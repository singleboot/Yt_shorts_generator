"""Clear queue and submit test workflow."""
import httpx
import json

# Try to clear pending queue
r = httpx.post("http://127.0.0.1:8188/queue", json={"clear": True})
print("Clear pending:", r.status_code)

r2 = httpx.post("http://127.0.0.1:8188/queue", json={"clear_pending": True})
print("Clear pending (alt):", r2.status_code)

# Check state
r3 = httpx.get("http://127.0.0.1:8188/queue", timeout=15)
q = r3.json()
running = q.get("queue_running", [])
pending = q.get("queue_pending", [])
print(f"Running: {len(running)}")
for item in running:
    print(f"  {item[1]}")
print(f"Pending: {len(pending)}")
for item in pending:
    print(f"  {item[1]}")
