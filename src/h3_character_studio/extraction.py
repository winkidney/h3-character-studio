"""H3 lossless frames -> ToonOut -> shared palette -> native 256px sprites."""
import json
import os
from pathlib import Path
import time

import numpy as np
from PIL import Image
from PIL import ImageDraw
from . import core, matting

TOONOUT_SHA256 = "8c7f8a0bc24400f4caade76622f75ff22ca1e93e169add9d2b70093e2487fbe5"


def palette(master, output, count=96):
    output = Path(output)
    if output.exists():
        raise ValueError("Palette exists; choose a new path")
    if not 1 <= count <= 256:
        raise ValueError("Palette size must be 1..256")
    image = Image.open(master).convert("RGBA")
    colors = core._palette_for([core.remove_background(image, None)], count)
    core.write_json(output, dict(schema_version=1, palette_rgb=colors, source_sha256=core.digest(master),
                                alpha_reference_threshold=128))
    return colors


def check_bundle(directory):
    directory = Path(directory)
    data = json.loads((directory / "animation.json").read_text())
    if data["size"] != [256, 256] or not data["frames"]:
        raise ValueError("Expected a native 256px animation")
    atlas = np.asarray(Image.open(core.contained(directory, data["atlas"])).convert("RGBA"))
    for row in data["frames"]:
        path = core.contained(directory, row["path"])
        if core.digest(path) != row["sha256"]:
            raise ValueError("Frame digest mismatch")
        image = np.asarray(Image.open(path).convert("RGBA"))
        if image.shape != (256, 256, 4) or set(np.unique(image[..., 3])) - {0, 255} or not image[..., 3].any():
            raise ValueError("Invalid frame size, alpha or empty silhouette")
        if image[0, :, 3].any() or image[-1, :, 3].any() or image[:, 0, 3].any() or image[:, -1, 3].any():
            raise ValueError("Visible silhouette touches the canvas boundary")
        x, y, width, height = row["region"]
        if not np.array_equal(atlas[y:y+height, x:x+width], image):
            raise ValueError("Atlas slice mismatch")
        if row["duration_ms"] <= 0:
            raise ValueError("Invalid frame duration")
    return dict(frame_count=len(data["frames"]), size=data["size"], pivot=data["pivot"],
                duration_ms=sum(row["duration_ms"] for row in data["frames"]),
                exact_atlas=True, binary_alpha=True, visual_approval="pending")


def extract(raw, output, palette_path, *, runtime=None, prepared_rgba=False, fps=None, pivot=(128, 240)):
    raw, output = Path(raw), Path(output)
    raw_manifest = json.loads((raw / "raw.json").read_text())
    fps = fps or raw_manifest["fps"]
    files = [core.contained(raw, row["path"]) for row in raw_manifest["frames"]]
    for path, row in zip(files, raw_manifest["frames"]):
        if core.digest(path) != row["sha256"]:
            raise ValueError("Raw frame changed")
    if not files or not 1 <= fps <= 60 or len(pivot) != 2 or any(type(x) is not int or not 0 <= x < 256 for x in pivot):
        raise ValueError("Invalid raw sequence, FPS or pivot")
    colors = json.loads(Path(palette_path).read_text())["palette_rgb"]
    if not 1 <= len(colors) <= 256:
        raise ValueError("Shared palette requires 1..256 colors")
    colors = [core.rgb(c) for c in colors]
    output.mkdir(parents=True, exist_ok=False)
    (output / "palette.json").write_bytes(Path(palette_path).read_bytes())
    core.write_json(output / "request.json", dict(raw_sha256=core.digest(raw / "raw.json"),
        palette_sha256=core.digest(palette_path), fps=fps, pivot=list(pivot),
        mode="prepared-rgba" if prepared_rgba else "toonout", output_size=256))
    record = dict(status="processing", visual_approval="pending")
    core.write_json(output / "result.json", record)
    start = time.monotonic()
    try:
        images = []
        if prepared_rgba:
            for path in files:
                with Image.open(path) as image:
                    if image.mode != "RGBA" or set(np.unique(np.asarray(image)[..., 3])) - {0, 255}:
                        raise ValueError("Prepared input requires hard-alpha RGBA, no implicit matting")
                    images.append(image.copy())
        else:
            if runtime is None:
                raise ValueError("ToonOut requires a prepared runtime")
            backend = json.loads((Path(runtime) / "runtime.json").read_text())
            model = Path(backend["models"]["toonout"])
            if core.digest(model) != TOONOUT_SHA256:
                raise ValueError("ToonOut model digest mismatch")
            os.environ.setdefault("NUMBA_NUM_THREADS", "4")
            os.environ.setdefault("OMP_NUM_THREADS", "4")
            predict = matting.predictor("toonout", 1024, "cuda", "float32", models=model.parent,
                node_source=backend["sources"]["birefnet"], comfy_source=backend["sources"]["comfyui"])
            for folder in ("soft-mask", "foreground", "rgba-soft", "rgba-hard"):
                (output / folder).mkdir()
            for index, path in enumerate(files):
                image = Image.open(path).convert("RGB")
                mask = predict([image])[0]
                alpha16 = np.rint(mask * 65535).astype(np.uint16)
                Image.fromarray(alpha16).save(output / "soft-mask" / f"{index:05d}.png")
                alpha = alpha16.astype(np.float64) / 65535
                foreground = np.rint(matting.recover(image, alpha) * 255).astype(np.uint8)
                Image.fromarray(foreground).save(output / "foreground" / f"{index:05d}.png")
                soft = np.dstack((foreground, np.rint(alpha * 255).astype(np.uint8)))
                soft[soft[..., 3] == 0, :3] = 0
                Image.fromarray(soft).save(output / "rgba-soft" / f"{index:05d}.png")
                hard = np.dstack((foreground, (alpha >= 0.5).astype(np.uint8) * 255))
                hard[hard[..., 3] == 0, :3] = 0
                Image.fromarray(hard).save(output / "rgba-hard" / f"{index:05d}.png")
                images.append(Image.fromarray(hard))
                print("ToonOut", index + 1, "/", len(files), flush=True)
        if len({image.size for image in images}) != 1 or images[0].width != images[0].height or images[0].width < 256:
            raise ValueError("Raw frames must share a square canvas at least 256 pixels")
        candidate = output / "candidate"
        core.save_candidate(candidate, images, fps=fps, sources=[dict(raw_frame=i) for i in range(len(images))],
            provenance=dict(source_manifest_sha256=core.digest(raw / "raw.json"), mode="prepared-rgba" if prepared_rgba else "toonout"))
        frames, report = core.process(candidate, core.load_edit(candidate), canvas=(256, 256), pivot=pivot,
                                      palette=colors, background=None)
        core.export_frames(frames, report, output / "pixel-256")
        record.update(status="extracted", checks=check_bundle(output / "pixel-256"), seconds=time.monotonic() - start)
    except Exception as error:
        record.update(status="failed", error=str(error), seconds=time.monotonic() - start)
        raise
    finally:
        core.write_json(output / "result.json", record)
    return record


def select(source, output, start, stop):
    """Choose a contiguous cycle; no interpolation, frame skipping or retiming."""
    source, output = Path(source), Path(output)
    check_bundle(source)
    manifest = json.loads((source / "animation.json").read_text())
    if not 0 <= start < stop <= len(manifest["frames"]) or stop - start < 2:
        raise ValueError("Use a contiguous interval [start, stop) containing at least two frames")
    images = [Image.open(core.contained(source, row["path"])).convert("RGBA") for row in manifest["frames"]]
    output.mkdir(parents=True, exist_ok=False)
    candidate = output / "candidate"
    fps = 1000 * len(images) / sum(row["duration_ms"] for row in manifest["frames"])
    core.save_candidate(candidate, images, fps=fps, sources=[dict(raw_frame=row.get("source", {}).get("raw_frame", i))
        for i, row in enumerate(manifest["frames"])], provenance=dict(selection_from_sha256=core.digest(source / "animation.json")))
    edit = core.make_edit(candidate, list(range(start, stop)), [row["duration_ms"] for row in manifest["frames"][start:stop]])
    frames, report = core.process(candidate, edit, canvas=(256, 256), pivot=manifest["pivot"],
                                  palette=manifest["palette_rgb"], background=None)
    core.export_frames(frames, report, output / "pixel-256")
    core.write_json(output / "selection.json", dict(interval=[start, stop], frame_skipping=False,
        interpolation=False, retiming=False, visual_approval="pending"))
    return check_bundle(output / "pixel-256")


def review(animation, output):
    animation, output = Path(animation), Path(output)
    check_bundle(animation)
    manifest = json.loads((animation / "animation.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    columns = min(8, len(manifest["frames"]))
    rows = (len(manifest["frames"]) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 256, rows * 280), (42, 44, 49))
    draw = ImageDraw.Draw(sheet)
    frames = []
    for i, row in enumerate(manifest["frames"]):
        image = Image.open(core.contained(animation, row["path"])).convert("RGBA")
        frames.append(np.asarray(image))
        x, y = i % columns * 256, i // columns * 280
        sheet.paste(image, (x, y), image)
        draw.text((x + 8, y + 260), f'{i}   raw {row.get("source", {}).get("raw_frame", i)}   {row["duration_ms"]}ms', fill="white")
    sheet.save(output / "contact.png")
    pairs = [dict(source=i, target=(i+1) % len(frames), loop_seam=i == len(frames)-1,
        mean_rgba_difference=float(np.abs(frames[i].astype(float) - frames[(i+1) % len(frames)]).mean()))
        for i in range(len(frames))]
    core.write_json(output / "review.json", dict(transitions=pairs, visual_approval="pending",
        metric_scope="Raw pixel differences are review hints; motion and foot contact require visual review."))
    return dict(contact=str(output / "contact.png"), preview=str(animation / "preview.webp"), visual_approval="pending")
