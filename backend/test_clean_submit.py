"""Clean state and submit."""
import httpx
import json
import time

# Interrupt and clear
httpx.post("http://127.0.0.1:8188/interrupt", timeout=10)
time.sleep(2)
httpx.post("http://127.0.0.1:8188/queue", json={"clear": True})
httpx.post("http://127.0.0.1:8188/free", json={"unload_models": True, "free_memory": True})

time.sleep(5)
r = httpx.get("http://127.0.0.1:8188/queue", timeout=15)
q = r.json()
running = q.get("queue_running", [])
pending = q.get("queue_pending", [])
print(f"Queue: running={len(running)}, pending={len(pending)}")

wf = json.load(open("app/workflows/video_t2v_ltx.json"))
r2 = httpx.post("http://127.0.0.1:8188/prompt", json={"prompt": wf})
print("Submit:", r2.status_code)
body = r2.json()
if "prompt_id" in body:
    pid = body["prompt_id"]
    print(f"  prompt_id: {pid}")
else:
    print(json.dumps(body, indent=2)[:1000])
