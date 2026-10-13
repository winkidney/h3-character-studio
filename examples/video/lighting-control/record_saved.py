"""Record four-direction GPU PNGs using the explicitly saved UI selection."""
import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import shutil
import subprocess
from PIL import Image
from serve import HERE, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot-project", type=Path, required=True)
    parser.add_argument("--selection", type=Path, default=Path("output/lighting-control/selected.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--playback-scale", type=float, help="Explicit user-requested recording speed override")
    args = parser.parse_args()
    project, source, output = args.godot_project.resolve(), args.selection.resolve(), args.output.resolve()
    selection = json.loads(source.read_text())
    if selection.get("schema") != "h3-cardinal-lighting/v1":
        parser.error("需要调参界面保存的选择文件")
    selection["params"] = validate(selection["params"])
    if args.playback_scale is not None:
        selection["source_saved_params"] = selection["params"].copy()
        selection["params"] = validate(dict(selection["params"], playback_scale=args.playback_scale))
        selection["recording_overrides"] = dict(playback_scale=args.playback_scale)
    output.mkdir(parents=True, exist_ok=False)
    # Freeze a receipt before launching, even if the user saves again during recording.
    frozen = output / "selected.json"
    frozen.write_text(json.dumps(selection, ensure_ascii=False, indent=2) + "\n")
    target = project / "tools/lighting-control"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("cardinal_scene.gd", "record.gd"):
        shutil.copyfile(HERE / name, target / name)
    spec = importlib.util.spec_from_file_location("godot_project_adapter", project / "tools/project.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    env = adapter.desktop_environment()
    env.update(XDG_DATA_HOME=str(output / "user-data"), XDG_CONFIG_HOME=str(output / "config"),
               XDG_CACHE_HOME=str(output / "cache"))
    # MovieWriter fixes its dimensions before SceneTree initialization. Runtime
    # window sizing alone does not set the writer's output resolution.
    project_file = project / "project.godot"
    original = project_file.read_bytes()
    configured = original.decode()
    for key, value in [("viewport_width", 1920), ("viewport_height", 1080),
                       ("window_width_override", 1920), ("window_height_override", 1080)]:
        configured = re.sub(r"(size/" + key + r"=)\d+", lambda m: m[1] + str(value), configured)
    try:
        project_file.write_text(configured)
        with (output / "render.log").open("w") as log:
            result = subprocess.run([adapter.engine(), "--path", str(project), "--display-driver", "x11",
                "--position", "10000,10000", "--resolution", "1920x1080", "--audio-driver", "Dummy",
                "--write-movie", str(output / "raw.png"), "--fixed-fps", "30",
                "--script", "res://tools/lighting-control/record.gd", "--", "--ignore-user-settings",
                "--lighting-params=" + str(frozen), "--jade-output=" + str(output)],
                cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=480)
    finally:
        project_file.write_bytes(original)
    if result.returncode:
        raise RuntimeError((output / "render.log").read_text()[-2000:])
    recipe = json.loads((output / "shot-recipe.json").read_text())
    if recipe["params"] != selection["params"]:
        raise RuntimeError("实际录制参数与保存参数不符")
    expected = round(selection["params"]["direction_seconds"] * 30) * 4
    if len(recipe["trajectory"]) != expected or any(row["animation_frame"] != row["clay_animation_frame"] for row in recipe["trajectory"]):
        raise RuntimeError("双视口帧同步或录制长度不符")
    recipe["saved_selection_sha256"] = hashlib.sha256(frozen.read_bytes()).hexdigest()
    recipe["source_start_frame"] = len(list(output.glob("raw*.png"))) - (expected + 15)
    recipe["source_frames"] = expected
    for png in output.glob("raw*.png"):
        with Image.open(png) as image:
            if image.size != (1920, 1080):
                raise RuntimeError("MovieWriter 未按原生 1080p 录制")
    recipe["original_project_restored"] = project_file.read_bytes() == original
    (output / "shot-recipe.json").write_text(json.dumps(recipe, ensure_ascii=False, indent=2) + "\n")
    print("SAVED_LIGHTING_CAPTURE_VALIDATED", output, "frames=", expected)


if __name__ == "__main__":
    main()
