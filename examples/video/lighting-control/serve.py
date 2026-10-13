"""Loopback-only controls for actual Godot rendering and explicit saved selections."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
DEFAULTS = dict(energy=.7, ambient=0., normal_strength=.8, normals_enabled=True,
                silver_enabled=True, color="#ffffff", horizontal_extent=1.6,
                vertical_extent=1.6, front_offset=1.3, range=8., playback_scale=.46875,
                direction_seconds=6., direction=0, auto_cycle=False, paused=False, frame=11)
BOUNDS = dict(energy=(0, 4), ambient=(0, .5), normal_strength=(0, 2),
              horizontal_extent=(.2, 3), vertical_extent=(.2, 3), front_offset=(.3, 4),
              range=(3, 12), playback_scale=(.1, 1.5), direction_seconds=(2, 12),
              direction=(0, 3), frame=(0, 26))


def validate(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        raise ValueError("参数字段不完整")
    result = {}
    for key, default in DEFAULTS.items():
        item = value[key]
        if isinstance(default, bool):
            if not isinstance(item, bool):
                raise ValueError(key + " 必须为开关")
        elif key == "color":
            if not isinstance(item, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", item):
                raise ValueError("灯光颜色无效")
            item = item.lower()
        else:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError(key + " 必须为有限数值")
            low, high = BOUNDS[key]
            if not low <= item <= high:
                raise ValueError(key + " 超出范围")
            if key in ("direction", "frame") and item != int(item):
                raise ValueError(key + " 必须为整数")
            item = int(item) if key in ("direction", "frame") else float(item)
        result[key] = item
    return result


def atomic_json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def read_json(path, fallback=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


class Studio:
    def __init__(self, state, port):
        self.state, self.port = state, port
        self.lock = threading.Lock()
        self.frames = {}
        state.mkdir(parents=True, exist_ok=True)
        saved = read_json(state / "selected.json")
        values = validate(saved["params"]) if saved else DEFAULTS.copy()
        self.current = dict(revision=int(time.time() * 1000), params=values)
        atomic_json(state / "current.json", self.current)

    def preview(self, params):
        with self.lock:
            self.current = dict(revision=self.current["revision"] + 1, params=validate(params))
            atomic_json(self.state / "current.json", self.current)
            return self.current

    def save(self, params, revision, sequence):
        with self.lock:
            params = validate(params)
            if revision != self.current["revision"] or params != self.current["params"]:
                raise ValueError("参数已变动，请等待预览更新后再保存")
            frame = read_json(self.state / "rendered.json")
            # Match the image the client displayed, rather than saving a later animation pose.
            shown = self.frames.get(sequence)
            if not frame or not shown or shown[0]["revision"] != revision or shown[0]["params"] != params:
                raise ValueError("请等待新参数的实际渲染画面显示后再保存")
            receipt, png = shown
            digest = hashlib.sha256(png).hexdigest()
            stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + str(time.time_ns())[-6:]
            snapshot = self.state / ("selection-" + stamp + ".png")
            snapshot.write_bytes(png)
            result = dict(schema="h3-cardinal-lighting/v1", saved_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                          revision=revision, params=params, scope="four-direction-lighting",
                          snapshot=snapshot.name, snapshot_sha256=digest, rendered=receipt,
                          recording=dict(script="examples/video/lighting-control/record.gd", fps=30,
                                         animation_continues=True, direction_order=["上方", "下方", "左侧", "右侧"]),
                          note="暂停、固定帧和单向选择用于预览，正式录像按四向连续慢步执行")
            atomic_json(self.state / ("selection-" + stamp + ".json"), result)
            atomic_json(self.state / "selected.json", result)
            return result

    def image(self):
        with self.lock:
            receipt = read_json(self.state / "rendered.json")
            if not receipt:
                return None
            png = (self.state / receipt["image"]).read_bytes()
            # The producer replaces a double buffer atomically. Recheck its sequence.
            if read_json(self.state / "rendered.json")["sequence"] != receipt["sequence"]:
                return None
            self.frames[receipt["sequence"]] = (receipt, png)
            for seq in sorted(self.frames)[:-24]:
                del self.frames[seq]
            return receipt, png

def handler(studio):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, value, code=200, content_type="application/json", headers=None):
            data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (headers or {}).items():
                self.send_header(k, str(v))
            self.end_headers()
            try:
                self.wfile.write(data)
            except BrokenPipeError:
                pass

        def trusted(self):
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{studio.port}", f"localhost:{studio.port}"}
            return host in allowed and self.headers.get("Origin", "http://" + host) == "http://" + host

        def do_GET(self):
            if not self.trusted():
                return self.respond({"error": "仅允许本机同源访问"}, 403)
            path = urlsplit(self.path).path
            if path == "/":
                return self.respond((HERE / "index.html").read_bytes(), content_type="text/html; charset=utf-8")
            if path == "/font.ttf":
                return self.respond((HERE.parent / "fonts/zlabs-pixel-12px-m-cn.ttf").read_bytes(), content_type="font/ttf")
            if path == "/api/status":
                return self.respond(dict(current=studio.current, rendered=read_json(studio.state / "rendered.json"),
                                         selected=read_json(studio.state / "selected.json"), defaults=DEFAULTS))
            if path == "/api/frame":
                frame = studio.image()
                if not frame:
                    return self.respond({"error": "渲染准备中"}, 503)
                receipt, png = frame
                return self.respond(png, content_type="image/png", headers={"X-Revision": receipt["revision"],
                    "X-Sequence": receipt["sequence"], "X-Direction": receipt["direction"],
                    "X-Animation-Frame": receipt["animation_frame"], "X-Renderer": receipt["renderer"]})
            if path == "/api/selected":
                return self.respond(read_json(studio.state / "selected.json", {}))
            return self.respond({"error": "未找到"}, 404)

        def do_POST(self):
            if not self.trusted():
                return self.respond({"error": "仅允许本机同源保存"}, 403)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("请求大小无效")
                data = json.loads(self.rfile.read(size))
                if self.path == "/api/preview":
                    return self.respond(studio.preview(data["params"]))
                if self.path == "/api/save":
                    return self.respond(studio.save(data["params"], data["revision"], data["sequence"]))
                return self.respond({"error": "未找到"}, 404)
            except (ValueError, KeyError, TypeError) as exc:
                return self.respond({"error": str(exc)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot-project", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=Path("output/lighting-control"))
    parser.add_argument("--port", type=int, default=18793)
    args = parser.parse_args()
    project, state = args.godot_project.resolve(), args.state.resolve()
    if not (project / "tools/project.py").exists():
        parser.error("需要已准备的隔离 hd-2d Godot 项目及 tools/project.py")
    spec = importlib.util.spec_from_file_location("godot_project_adapter", project / "tools/project.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    target = project / "tools/lighting-control"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("cardinal_scene.gd", "preview.gd", "record.gd"):
        shutil.copyfile(HERE / name, target / name)
    studio = Studio(state, args.port)
    # Discard a previous process's frame status, keeping all user-saved selections.
    (state / "rendered.json").unlink(missing_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(studio))
    env = adapter.desktop_environment()
    env.update(XDG_DATA_HOME=str(state / "user-data"), XDG_CONFIG_HOME=str(state / "config"),
               XDG_CACHE_HOME=str(state / "cache"))
    with (state / "render.log").open("w") as log:
        renderer = subprocess.Popen([adapter.engine(), "--path", str(project), "--display-driver", "x11",
            "--position", "10000,10000", "--resolution", "1920x1080", "--audio-driver", "Dummy",
            "--script", "res://tools/lighting-control/preview.gd", "--", "--ignore-user-settings",
            "--lighting-state=" + str(state)], cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT)
        print(f"LIGHTING_CONTROL_READY http://127.0.0.1:{args.port} saved={state / 'selected.json'}", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            renderer.terminate()
            renderer.wait(timeout=10)


if __name__ == "__main__":
    main()
