import asyncio
from pathlib import Path
from app.services.audio import AudioService

async def test():
    svc = AudioService()
    voices = await svc.list_voices()
    print("Found total voices:", len(voices))
    print("Kokoro voices listed:")
    for v in voices:
        if "kokoro" in v["id"]:
            print(f" - {v['name']} ({v['id']})")
            
    text = "This is a local Kokoro high-quality synthesis test."
    out_path = Path("backend/test_kokoro_svc.mp3")
    print(f"\nGenerating voiceover using 'kokoro-af_sarah' into {out_path}...")
    
    success = await svc.generate_voiceover(text, "kokoro-af_sarah", out_path)
    if success and out_path.exists():
        print(f"Success! File size: {out_path.stat().st_size} bytes")
        json_path = out_path.with_suffix(".json")
        if json_path.exists():
            print("Found json word boundaries:")
            print(json_path.read_text())
    else:
        print("Generation failed!")

if __name__ == "__main__":
    asyncio.run(test())
