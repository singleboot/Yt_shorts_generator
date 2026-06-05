"""Wait and check."""
import time
import httpx

time.sleep(60)
r = httpx.get("http://127.0.0.1:8188/internal/logs?max_lines=20", timeout=15)
print("--- Last log lines ---")
print(r.text[-1500:])
r2 = httpx.get("http://127.0.0.1:8188/queue", timeout=15)
q = r2.json()
running = q.get("queue_running", [])
pending = q.get("queue_pending", [])
print(f"\nQueue: running={len(running)}, pending={len(pending)}")
for item in running:
    print(f"  RUN: {item[1]}")
for item in pending:
    print(f"  PEND: {item[1]}")
r3 = httpx.get("http://127.0.0.1:8188/system_stats", timeout=15)
for dev in r3.json().get("devices", []):
    v = dev.get("vram_total", 0) - dev.get("vram_free", 0)
    t = dev.get("vram_total", 0)
    print(f"GPU: {v/1024**3:.1f}GB/{t/1024**3:.1f}GB")
