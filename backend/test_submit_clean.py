"""Submit my t2v workflow with clean state."""
import asyncio
import httpx
import json


async def main():
    async with httpx.AsyncClient(timeout=15.0) as c:
        r = await c.get("http://127.0.0.1:8188/queue", timeout=15)
        q = r.json()
        running = q.get("queue_running", [])
        pending = q.get("queue_pending", [])
        print(f"Queue: running={len(running)}, pending={len(pending)}")
        for item in running:
            print(f"  RUN: {item[1]}")
        for item in pending:
            print(f"  PEND: {item[1]}")

        wf = json.load(open("app/workflows/video_t2v_ltx.json"))
        r2 = await c.post("http://127.0.0.1:8188/prompt", json={"prompt": wf})
        body = r2.json()
        if "prompt_id" in body:
            print(f"Submitted! prompt_id: {body['prompt_id']}")
        else:
            print("Error:")
            print(json.dumps(body, indent=2)[:1500])


asyncio.run(main())
