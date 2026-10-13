"""Private runtime, fixed upstream sources and verified model references."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

import yaml
from . import core
from .workflow import COMFY_REVISION, NODE_REVISION, DATA

SOURCES = {
    "comfyui": ("https://github.com/Comfy-Org/ComfyUI.git", COMFY_REVISION),
    "birefnet": ("https://github.com/lldacing/ComfyUI_BiRefNet_ll.git", NODE_REVISION),
}


def models():
    return json.loads((DATA / "models.lock.json").read_text())["models"]


def verify_models(root, overrides=None):
    overrides = overrides or {}
    unknown = set(overrides) - {row["id"] for row in models()}
    if unknown:
        raise ValueError("Unknown model IDs: " + str(sorted(unknown)))
    result = {}
    for row in models():
        path = Path(overrides.get(row["id"], Path(root) / row["file"])).expanduser().resolve(strict=True)
        if path.stat().st_size != row["size"] or core.digest(path) != row["sha256"]:
            raise ValueError("Model bytes or SHA-256 mismatch: " + row["id"])
        result[row["id"]] = str(path)
    return result


def download_models(root):
    root = Path(root).absolute()
    for row in models():
        path = root / row["file"]
        if path.exists():
            if path.stat().st_size != row["size"] or core.digest(path) != row["sha256"]:
                raise ValueError("Existing model changed; inspect without overwriting: " + str(path))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".part")
        if partial.exists():
            raise ValueError("Partial download retained; move it aside before retrying: " + str(partial))
        url = f'https://huggingface.co/{row["repo"]}/resolve/{row["revision"]}/{row["file"]}'
        # Original ToonOut weight resides at the repository root.
        print("Downloading", row["id"], row["size"], "bytes", flush=True)
        with urllib.request.urlopen(url, timeout=120) as response, partial.open("xb") as stream:
            shutil.copyfileobj(response, stream, 8 * 1024 * 1024)
        if partial.stat().st_size != row["size"] or core.digest(partial) != row["sha256"]:
            raise ValueError("Downloaded model failed verification; .part retained")
        partial.replace(path)
    return verify_models(root)


def checkout(path, url, revision):
    path = Path(path)
    if path.exists():
        current = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
        changed = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip()
        if current != revision or changed:
            raise ValueError("Source checkout differs; use a new runtime directory")
        return
    subprocess.run(["git", "clone", "--no-checkout", "--filter=blob:none", url, str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "checkout", "--detach", revision], check=True)


def prepare(runtime, models_root, overrides=None, *, install_gpu=False, source_caches=None, wheelhouse=None):
    runtime = Path(runtime).absolute()
    if (runtime / "runtime.json").exists():
        raise ValueError("Runtime exists; use doctor, or prepare a new directory")
    references = verify_models(models_root, overrides)
    runtime.mkdir(parents=True, exist_ok=True)
    source_caches = source_caches or {}
    for name, (url, revision) in SOURCES.items():
        destination = runtime / "sources" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if name in source_caches and not destination.exists():
            # Independent object database; no alternates, worktree edits or copied venv.
            subprocess.run(["git", "clone", "--no-hardlinks", "--no-checkout", str(Path(source_caches[name]).absolute()), str(destination)], check=True)
            subprocess.run(["git", "-C", str(destination), "remote", "set-url", "origin", url], check=True)
            subprocess.run(["git", "-C", str(destination), "checkout", "--detach", revision], check=True)
        checkout(destination, url, revision)
    python = runtime / "venv/bin/python"
    if install_gpu:
        subprocess.run([sys.executable, "-m", "venv", str(runtime / "venv")], check=True)
        pip = [str(python), "-m", "pip", "install", "--require-hashes", "--cache-dir", str(runtime / "cache/pip")]
        if wheelhouse:
            pip.extend(["--no-index", "--find-links", str(Path(wheelhouse).absolute())])
        else:
            pip.extend(["--extra-index-url", "https://download.pytorch.org/whl/cu130"])
        subprocess.run(pip + ["-r", str(DATA / "h3-linux-python312-cu130.lock")], check=True)
        # Caller provides the same built wheel in a separate explicit command.
    for name in ("data/custom_nodes/H3CharacterStudio", "input", "output", "temp", "user"):
        (runtime / name).mkdir(parents=True, exist_ok=True)
    (runtime / "data/custom_nodes/H3CharacterStudio/__init__.py").write_text(
        "from h3_character_studio.comfy_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS\n")
    paths = {}
    for row in models():
        if row["subdir"] != "toonout":
            paths[row["id"]] = {row["subdir"]: str(Path(references[row["id"]]).parent)}
    (runtime / "models.yaml").write_text(yaml.safe_dump(paths))
    (runtime / "launch.py").write_text("import runpy, sys\nsource = " + repr(str(runtime / "sources/comfyui")) +
        "\nsys.path.insert(0, source)\nsys.argv[0] = source + '/main.py'\nrunpy.run_path(sys.argv[0], run_name='__main__')\n")
    record = dict(schema_version=1, python=str(python), sources={name: str(runtime / "sources" / name) for name in SOURCES},
                  models=references, gpu_dependencies_installed=install_gpu, inference_verified=False)
    core.write_json(runtime / "runtime.json", record)
    return record


def launch(runtime, port=8197, python=None):
    runtime = Path(runtime).absolute()
    if not (runtime / "runtime.json").exists():
        raise ValueError("Prepare this runtime first")
    record = json.loads((runtime / "runtime.json").read_text())
    executable = str(Path(python).absolute()) if python else record["python"]
    command = [executable, "-I", str(runtime / "launch.py"), "--listen", "127.0.0.1", "--port", str(port),
        "--base-directory", str(runtime / "data"), "--input-directory", str(runtime / "input"),
        "--output-directory", str(runtime / "output"), "--temp-directory", str(runtime / "temp"),
        "--user-directory", str(runtime / "user"), "--database-url", "sqlite:///" + str(runtime / "user/comfyui.db"),
        "--extra-model-paths-config", str(runtime / "models.yaml"), "--disable-auto-launch",
        "--disable-all-custom-nodes", "--whitelist-custom-nodes", "H3CharacterStudio", "--preview-method", "none",
        "--lowvram", "--reserve-vram", "1", "--fast-disk", "--disable-pinned-memory", "--cache-none"]
    return subprocess.call(command)
