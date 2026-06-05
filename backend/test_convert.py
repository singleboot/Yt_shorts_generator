"""Convert official UI workflow to API format."""
import json

# Load the 2.0 t2v distilled workflow
ui_workflow = json.load(open("test_workflow.json"))
nodes = ui_workflow["nodes"]
links = ui_workflow.get("links", [])

# Build link lookup
link_map = {}
for link in links:
    if len(link) >= 4:
        lid, src_node, src_slot, dst_slot = link[0], link[1], link[2], link[3]
        link_map[lid] = (src_node, src_slot)

# Find each node by id and type
nodes_by_id = {n["id"]: n for n in nodes}

# Build a simpler API workflow
# Required nodes:
# 1. CheckpointLoaderSimple - load model
# 2. LTXVGemmaCLIPModelLoader - load text encoder
# 3. CLIPTextEncode (positive) - prompt
# 4. CLIPTextEncode (negative) - negative
# 5. EmptyLTXVLatentVideo - latent
# 6. LTXVConditioning - conditioning with frame_rate
# 7. KSampler - sample
# 8. LTXVTiledVAEDecode - tiled decode
# 9. CreateVideo - create video
# 10. SaveVideo - save

# Use distilled LoRA approach: skip distilled, use full model
# This is a simple distilled-like workflow

# Let me just list every LTX node we need and their inputs
ltx_nodes = {}
for n in nodes:
    if "ltx" in n.get("type", "").lower() or "ltx" in n.get("title", "").lower():
        ltx_nodes[n["id"]] = {
            "type": n.get("type"),
            "title": n.get("title", ""),
            "inputs": n.get("inputs", []),
            "widgets": n.get("widgets_values", []),
        }

print(json.dumps(ltx_nodes, indent=2)[:5000])
