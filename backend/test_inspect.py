"""Inspect the official LTX 2.3 workflow."""
import json

data = json.load(open("test_workflow.json"))
print(f"Total nodes: {len(data)}")
for k, v in data.items():
    cls = v.get("class_type")
    title = v.get("_meta", {}).get("title", "")
    inputs = v.get("inputs", {})
    in_keys = list(inputs.keys())[:6]
    print(f"  [{k}] {cls} ({title}) - inputs: {in_keys}")
