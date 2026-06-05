"""Inspect official workflow nodes properly."""
import json

data = json.load(open("test_workflow.json"))
nodes = data["nodes"]
print(f"Nodes: {len(nodes)}")
for n in nodes:
    cls = n.get("type", "")
    nid = n.get("id")
    title = n.get("title", "")
    widgets = n.get("widgets_values", [])
    print(f"  [{nid}] {cls} ({title}) widgets: {widgets[:6]}")
