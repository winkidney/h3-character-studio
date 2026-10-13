"""Single submission with frozen references and recoverable ComfyUI history."""
import json
from pathlib import Path
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import core, recipe, workflow


def request(url, endpoint, data=None):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("This workflow connects to a local ComfyUI instance")
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url.rstrip("/") + endpoint, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def upload(url, path, name):
    token = uuid.uuid4().hex
    header = (f'--{token}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
              'Content-Type: image/png\r\n\r\n').encode()
    body = header + Path(path).read_bytes() + f"\r\n--{token}--\r\n".encode()
    # Validate the endpoint before issuing a multipart upload.
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Only local ComfyUI uploads are supported")
    req = urllib.request.Request(url.rstrip("/") + "/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={token}"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.load(response)
    return (data.get("subfolder", "") + "/" + data["name"]).lstrip("/")


def prepare(path, direction, output, url):
    spec, settings, references = recipe.load(path)
    if direction not in recipe.DIRECTIONS:
        raise ValueError("Unknown direction")
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    reference = references[direction]
    shutil.copy2(reference["master"], output / "master.png")
    (output / "character.yaml").write_bytes(Path(path).read_bytes())
    (output / "prompt.txt").write_text(reference["prompt"] + "\n")
    identifier = f'{spec["id"]}-{direction}-{uuid.uuid4().hex[:12]}'
    state = dict(schema_version=1, run_id=identifier, character_id=spec["id"], direction=direction,
                 status="preparing", url=url, settings=settings, seed=reference["seed"],
                 master_sha256=core.digest(output / "master.png"),
                 client_id=str(uuid.uuid4()), submission_attempts=0, visual_approval="pending")
    core.write_json(output / "job.json", state)
    info = request(url, "/object_info")
    graph = workflow.graph("pending.png", identifier, settings, reference["prompt"], reference["seed"])
    missing = {n["class_type"] for n in graph.values()} - set(info)
    if missing:
        raise ValueError("Required ComfyUI nodes missing: " + str(sorted(missing)))
    name = upload(url, output / "master.png", identifier + ".png")
    graph["1"]["inputs"]["image"] = name
    core.write_json(output / "object_info.json", info)
    core.write_json(output / "workflow.api.json", graph)
    core.write_json(output / "workflow.json", workflow.api_to_ui(graph, info))
    state.update(status="prepared", graph_sha256=core.digest(output / "workflow.api.json"),
                 prompt_sha256=core.digest(output / "prompt.txt"))
    core.write_json(output / "job.json", state)
    return state


def submit(output):
    output = Path(output)
    state = json.loads((output / "job.json").read_text())
    if state["status"] != "prepared" or state["submission_attempts"]:
        raise ValueError("This run already attempted submission; resume instead")
    for file, key in (("master.png", "master_sha256"), ("workflow.api.json", "graph_sha256"), ("prompt.txt", "prompt_sha256")):
        if core.digest(output / file) != state[key]:
            raise ValueError("Frozen run input changed: " + file)
    # Persist uncertainty BEFORE network I/O. A lost response never causes retry.
    state.update(status="submission_unknown", submission_attempts=1)
    core.write_json(output / "job.json", state)
    graph = json.loads((output / "workflow.api.json").read_text())
    try:
        response = request(state["url"], "/prompt", dict(prompt=graph, client_id=state["client_id"],
                            extra_data={"h3_character_run_id": state["run_id"]}))
        if response.get("node_errors") or "prompt_id" not in response:
            state.update(status="rejected", response=response)
        else:
            state.update(status="queued", prompt_id=response["prompt_id"])
    except urllib.error.HTTPError as error:
        if error.code == 400:
            state.update(status="rejected", error=error.read().decode(errors="replace"))
        else:
            state["error"] = str(error)
    except (OSError, ValueError) as error:
        state["error"] = str(error)
    core.write_json(output / "job.json", state)
    return state


def find_submission(state, queue, history):
    for item in queue.get("queue_running", []) + queue.get("queue_pending", []):
        if len(item) > 3 and item[3].get("h3_character_run_id") == state["run_id"]:
            return item[1]
    for key, item in history.items():
        prompt = item.get("prompt", [])
        if len(prompt) > 3 and prompt[3].get("h3_character_run_id") == state["run_id"]:
            return key
    return None


def follow(output, seconds=30):
    output = Path(output)
    state = json.loads((output / "job.json").read_text())
    if state["status"] in ("prepared", "preparing", "rejected"):
        return state
    deadline = time.monotonic() + seconds
    while True:
        if not state.get("prompt_id"):
            found = find_submission(state, request(state["url"], "/queue"), request(state["url"], "/history"))
            if not found:
                # History may have been pruned or the server restarted. Preserve unknown.
                return state
            state["prompt_id"] = found
        history = request(state["url"], "/history/" + state["prompt_id"])
        if state["prompt_id"] in history:
            item = history[state["prompt_id"]]
            core.write_json(output / "history.json", item)
            status = item.get("status", {})
            if status.get("status_str") == "error":
                state.update(status="failed", error=status.get("messages", []))
            elif status.get("completed"):
                state.update(status="generated", outputs=item.get("outputs", {}))
        core.write_json(output / "job.json", state)
        if state["status"] in ("generated", "failed") or time.monotonic() >= deadline:
            return state
        time.sleep(min(2, max(0, deadline - time.monotonic())))
