"""Check key LTX 2.x node schemas."""
import asyncio
import httpx
import json


async def main():
    async with httpx.AsyncClient(timeout=15.0) as c:
        for node in ["CreateVideo", "SaveVideo", "LTXVTiledVAEDecode", "LTXVEmptyLatentAudio", "LTXVAudioVAEEncode", "LTXVAudioVAEDecode"]:
            r = await c.get(f"http://127.0.0.1:8188/object_info/{node}")
            if r.status_code == 200:
                data = r.json()
                info = data.get(node, {})
                print(f"\n=== {node} ===")
                print(f"  Output: {info.get('output')}")
                req = info.get("input", {}).get("required", {})
                opt = info.get("input", {}).get("optional", {})
                print(f"  Required keys: {list(req.keys())}")
                print(f"  Optional keys: {list(opt.keys())}")


asyncio.run(main())
