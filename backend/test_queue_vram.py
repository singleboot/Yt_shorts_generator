"""Check queue and VRAM."""
import httpx
import json

r = httpx.get("http://127.0.0.1:8188/queue", timeout=15)
q = r.json()
print("Running:", len(q.get("queue_running", [])))
print("Pending:", len(q.get("queue_pending", [])))

r2 = httpx.get("http://127.0.0.1:8188/system_stats", timeout=15)
stats = r2.json()
for dev in stats.get("devices", []):
    name = dev.get("name")
    vram_total = dev.get("vram_total", 0)
    vram_free = dev.get("vram_free", 0)
    vram_used = vram_total - vram_free
    print(f"GPU {name}: {vram_used/1024**3:.1f}GB used of {vram_total/1024**3:.1f}GB")
