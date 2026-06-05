"""Check ComfyUI state."""
import httpx
import json

r = httpx.get("http://127.0.0.1:8188/internal/logs?max_lines=15", timeout=15)
print(r.text[-1500:])

print("\n=== Queue ===")
r2 = httpx.get("http://127.0.0.1:8188/queue", timeout=15)
q = r2.json()
running = q.get("queue_running", [])
pending = q.get("queue_pending", [])
print(f"Running: {len(running)}")
for item in running:
    print(f"  {item[1]}")
print(f"Pending: {len(pending)}")
for item in pending:
    print(f"  {item[1]}")

print("\n=== VRAM ===")
r3 = httpx.get("http://127.0.0.1:8188/system_stats", timeout=15)
for dev in r3.json().get("devices", []):
    v = dev.get("vram_total", 0) - dev.get("vram_free", 0)
    t = dev.get("vram_total", 0)
    print(f"GPU: {v/1024**3:.1f}GB/{t/1024**3:.1f}GB")
