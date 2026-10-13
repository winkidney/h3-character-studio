"""H3 graph based on the accepted AssetWorkbench 56-frame workflow."""
import copy
import json
from pathlib import Path

DATA = Path(__file__).with_name("data")
COMFY_REVISION = "a8686f2b33fc540f137df50c0f0719953830a5e7"
NODE_REVISION = "5443a2aa16cfbd98bb2f7dcc8bdcb70439e08529"


def graph(image, run_id, settings, prompt, seed):
    g = copy.deepcopy(json.loads((DATA / "h3.api.json").read_text()))
    g["1"]["inputs"]["image"] = image
    g["2"]["class_type"] = "H3CharacterReference"
    g["2"]["inputs"].update(background="#ff00ff", width=settings["width"], height=settings["height"])
    g["6"]["inputs"].update(prompt=prompt, width=settings["width"], height=settings["height"], length=settings["frames"])
    g["8"]["inputs"]["steps"] = settings["steps"]
    g["10"]["inputs"]["noise_seed"] = seed
    guides = sorted(set(settings.get("extra_guide_frames", []) +
                        ([settings["mid_guide_frame"]] if settings["mid_guide_frame"] != -1 else [])))
    conditioning = ["6", 0]
    for index, frame in enumerate(guides, 17):
        key = str(index)
        g[key] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": conditioning, "latent": ["6", 1], "vae": ["5", 0],
            "image": ["2", 0], "frame_idx": frame}}
        conditioning = [key, 0]
    g["7"]["inputs"]["conditioning"] = conditioning
    del g["14"]
    g["15"] = {"class_type": "H3CharacterRawFrames", "inputs": {
        "images": ["12", 0], "run_id": run_id, "fps": settings["fps"], "expected_frames": settings["frames"]}}
    return g


def api_to_ui(prompt, info):
    """Serialize with live object_info; input widgets follow the pinned server order."""
    nodes, links, lookup = [], [], {}
    for order, (key, value) in enumerate(prompt.items()):
        schema = info[value["class_type"]]
        widgets = []
        for name, field in {**schema["input"].get("required", {}), **schema["input"].get("optional", {})}.items():
            val = value["inputs"].get(name)
            if val is None or isinstance(val, list):
                continue
            widgets.append(val)
            if len(field) > 1 and field[1].get("control_after_generate"):
                widgets.append("fixed")
        node = dict(id=int(key), type=value["class_type"], pos=[order % 4 * 350, order // 4 * 340],
                    size=[320, 260], flags={}, order=order, mode=0, inputs=[],
                    outputs=[dict(name=t, type=t, links=[]) for t in schema["output"]],
                    properties={"Node name for S&R": value["class_type"]}, widgets_values=widgets)
        nodes.append(node)
        lookup[key] = node
    for key, value in prompt.items():
        for name, val in value["inputs"].items():
            if not isinstance(val, list):
                continue
            source, slot = val
            typ = lookup[source]["outputs"][slot]["type"]
            number = len(links) + 1
            target_slot = len(lookup[key]["inputs"])
            lookup[key]["inputs"].append(dict(name=name, type=typ, link=number))
            lookup[source]["outputs"][slot]["links"].append(number)
            links.append([number, int(source), slot, int(key), target_slot, typ])
    return dict(version=0.4, last_node_id=max(n["id"] for n in nodes), last_link_id=len(links),
                nodes=nodes, links=links, groups=[], config={}, extra={"comfy_revision": COMFY_REVISION})
