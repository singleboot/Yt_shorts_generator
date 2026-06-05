"""Monitor workflow status."""
import httpx
import json
import sys
import time

pid = sys.argv[1] if len(sys.argv) > 1 else "4a8ffd79-47d5-44fd-af65-da7570af1194"

with httpx.Client(timeout=15.0) as c:
    for i in range(40):
        time.sleep(5)
        r = c.get(f"http://127.0.0.1:8188/history/{pid}")
        if r.status_code == 200:
            data = r.json()
            if pid in data:
                entry = data[pid]
                status = entry.get("status", {})
                completed = status.get("completed", False)
                status_str = status.get("status_str", "?")
                print(f"Tick {i}: completed={completed}, str={status_str}")
                if completed:
                    if status.get("messages"):
                        for m in status["messages"]:
                            if m[0] == "execution_error":
                                print("ERROR:", json.dumps(m[1], indent=2)[:2000])
                            elif m[0] == "execution_success":
                                print("SUCCESS at", m[1].get("timestamp"))
                    if "outputs" in entry:
                        print("Outputs:", json.dumps(entry["outputs"], indent=2)[:2000])
                    break
            else:
                print(f"Tick {i}: not in history")
        else:
            print(f"Tick {i}: HTTP {r.status_code}")
