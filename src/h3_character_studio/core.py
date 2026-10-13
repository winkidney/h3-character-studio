"""Portable, deterministic pixel processing. No torch, model or UI dependencies."""
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import zlib

import numpy as np
from PIL import Image, ImageColor

VERSION = 1
DIRECTIONS = {"down": 0, "left": 1, "right": 2, "up": 3}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement keeps an interrupted UI save from destroying an edit.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False, suffix=".tmp") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        temp = Path(stream.name)
    temp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_png(image):
    """RGBA8 PNG with fixed filter/stored DEFLATE blocks, independent of zlib builds.

    Pillow wheels can encode identical pixels differently across platforms. Export
    hashes are part of the portable manifest, so use deterministic framing here.
    Raw generation candidates keep Pillow's smaller compressed PNG originals.
    """
    image = image.convert("RGBA")
    pixels = image.tobytes()
    stride = image.width * 4
    raw = b"".join(b"\x00" + pixels[y*stride:(y+1)*stride] for y in range(image.height))
    blocks = []
    for start in range(0, len(raw), 65535):
        block = raw[start:start+65535]
        last = start + len(block) == len(raw)
        blocks.append(struct.pack("<BHH", int(last), len(block), len(block) ^ 0xffff) + block)
    stream = b"\x78\x01" + b"".join(blocks) + struct.pack(">I", zlib.adler32(raw) & 0xffffffff)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", stream) + chunk(b"IEND", b"")


def contained(root, relative):
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Asset paths must be relative and cannot contain '..'")
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError("Asset path escapes the bundle")
    return result


def rgb(value):
    if isinstance(value, str):
        return ImageColor.getrgb(value)
    if len(value) != 3 or any(not 0 <= int(v) <= 255 for v in value):
        raise ValueError("Expected an RGB color")
    return tuple(int(v) for v in value)


def save_candidate(directory, images, *, provenance, fps=24, sources=None, effective_size=None):
    directory = Path(directory)
    images = [im.convert("RGBA") for im in images]
    if not images or fps <= 0 or not math.isfinite(fps):
        raise ValueError("A candidate needs frames and a positive frame rate")
    size = images[0].size
    if any(im.size != size for im in images):
        raise ValueError("Frames must share one source canvas")
    if sources is not None and len(sources) != len(images):
        raise ValueError("Source references must match frames")
    if (directory / "candidate.json").exists():
        raise ValueError("Candidates are immutable; use a new directory")
    (directory / "frames").mkdir(parents=True, exist_ok=True)
    records = []
    for i, im in enumerate(images):
        name = f"frames/{i:05}.png"
        im.save(directory / name)
        records.append({"path": name, "sha256": digest(directory / name),
                        "source": sources[i] if sources is not None else {"video_frame": i},
                        "duration_ms": max(1, round((i+1)*1000/fps) - round(i*1000/fps))})
    manifest = {"version": VERSION, "size": list(size), "effective_size": list(effective_size or size),
                "fps": fps, "frames": records, "provenance": provenance,
                "shared_source_anchor": [size[0]//2, min(size[1]-1, round(size[1]*0.875))],
                "anchor_status": "proposed canvas reference; not an automatically detected foot", "alpha": "embedded-in-rgba-png"}
    preview = [im.resize((max(1, round(size[0]*min(1, 256/max(size)))),
                          max(1, round(size[1]*min(1, 256/max(size))))), Image.Resampling.NEAREST)
               for im in images]
    preview[0].save(directory / "preview.webp", format="WEBP", save_all=True,
                    append_images=preview[1:], duration=[r["duration_ms"] for r in records],
                    loop=0, lossless=True, exact=True)
    manifest["preview"] = "preview.webp"
    write_json(directory / "candidate.json", manifest)
    save_edit(directory, make_edit(directory, list(range(len(images))), [r["duration_ms"] for r in records]))
    return directory


def load_candidate(directory, *, verify=True):
    directory = Path(directory)
    data = json.loads((directory / "candidate.json").read_text())
    if data.get("version") != VERSION or not data.get("frames"):
        raise ValueError("Unsupported or empty candidate")
    for frame in data["frames"]:
        path = contained(directory, frame["path"])
        if verify and digest(path) != frame["sha256"]:
            raise ValueError(f"Candidate source was modified: {frame['path']}")
    return data


def validate_edit(manifest, edit):
    indices, durations = edit.get("indices", []), edit.get("durations_ms", [])
    if not indices or len(indices) != len(durations):
        raise ValueError("Select at least one frame with matching durations")
    if any(type(i) is not int or not 0 <= i < len(manifest["frames"]) for i in indices):
        raise ValueError("Selected frame is outside the candidate")
    if any(type(d) is not int or not 1 <= d <= 60000 for d in durations):
        raise ValueError("Frame duration must be 1..60000 integer milliseconds")
    if edit.get("version") != VERSION:
        raise ValueError("Unsupported edit version")
    return edit


def make_edit(directory, indices, durations_ms):
    return validate_edit(load_candidate(directory),
                         {"version": VERSION, "indices": list(indices),
                          "durations_ms": list(durations_ms), "loop": True})


def save_edit(directory, edit):
    validate_edit(load_candidate(directory), edit)
    write_json(Path(directory) / "edit.json", edit)


def load_edit(directory):
    data = json.loads((Path(directory) / "edit.json").read_text())
    return validate_edit(load_candidate(directory), data)


def split_sheet(sheet, direction="down"):
    if sheet.size != (512, 512) or direction not in DIRECTIONS:
        raise ValueError("The locked sprite recipe requires a 512x512, 4x4 sheet and a known direction")
    grid = sheet.convert("RGBA").resize((128, 128), Image.Resampling.NEAREST)
    row = DIRECTIONS[direction]
    frames, sources = [], []
    for col in range(3):  # The fourth cell contains a different action.
        frames.append(grid.crop((col * 32, row * 32, (col + 1) * 32, (row + 1) * 32)))
        sources.append({"cell": [row, col], "source_region": [col * 128, row * 128, 128, 128],
                        "direction": direction})
    return frames, sources


def remove_background(image, background, tolerance=24):
    if not 0 <= tolerance <= 255:
        raise ValueError("Background tolerance must be 0..255")
    a = np.array(image.convert("RGBA"))
    alpha = a[:, :, 3] >= 128
    if background is not None:
        matches = np.max(np.abs(a[:, :, :3].astype(np.int16) - np.array(rgb(background))), axis=2) <= tolerance
        eligible = matches | ~alpha
        h, w = alpha.shape
        visited = np.zeros((h, w), dtype=bool)
        queue = deque()
        for y, x in [(0, x) for x in range(w)] + [(h-1, x) for x in range(w)] + [(y, 0) for y in range(h)] + [(y, w-1) for y in range(h)]:
            if eligible[y, x] and not visited[y, x]:
                visited[y, x] = True
                queue.append((y, x))
        while queue:
            y, x = queue.popleft()
            for ny, nx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
                if 0 <= ny < h and 0 <= nx < w and eligible[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        alpha &= ~visited
    a[:, :, 3] = alpha.astype(np.uint8) * 255
    a[~alpha, :3] = 0
    return Image.fromarray(a)


def _palette_for(frames, count):
    pixels = np.concatenate([a[a[:, :, 3] != 0, :3] for a in map(np.array, frames)])
    if not len(pixels):
        return [(0, 0, 0)]
    colors, frequency = np.unique(pixels, axis=0, return_counts=True)
    if len(colors) <= count:
        return [tuple(map(int, c)) for c in colors]
    # Limit only histogram sample size; same rule on both platforms.
    sample = pixels[::max(1, len(pixels) // 1000000)]
    palette_image = Image.fromarray(sample.reshape((-1, 1, 3))).quantize(
        colors=count, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    entries = palette_image.getpalette()
    used = sorted(index for _, index in palette_image.getcolors())
    return [tuple(entries[i*3:i*3+3]) for i in used]


def process(directory, edit, *, canvas=(128, 128), crop=None, offset=(0, 0), pivot=None,
            background="#00ff00", tolerance=24, palette_size=32, palette=None):
    manifest = load_candidate(directory)
    validate_edit(manifest, edit)
    canvas = tuple(map(int, canvas))
    if len(canvas) != 2 or min(canvas) < 1 or max(canvas) > 2048:
        raise ValueError("Canvas must be 1..2048 pixels")
    if not 1 <= palette_size <= 256:
        raise ValueError("Palette size must be 1..256")
    pivot = list(pivot or (canvas[0] // 2, min(canvas[1]-1, round(canvas[1] * 0.875))))
    if not (0 <= pivot[0] < canvas[0] and 0 <= pivot[1] < canvas[1]):
        raise ValueError("Pivot is outside the shared canvas")
    w, h = manifest["size"]
    x, y, cw, ch = crop or (0, 0, w, h)
    if min(x, y) < 0 or min(cw, ch) <= 0 or x + cw > w or y + ch > h:
        raise ValueError("Crop is outside the source canvas")
    scale = min(canvas[0] / cw, canvas[1] / ch)
    target = (max(1, round(cw * scale)), max(1, round(ch * scale)))
    position = ((canvas[0] - target[0]) // 2 + int(offset[0]),
                (canvas[1] - target[1]) // 2 + int(offset[1]))
    warnings, frames = [], []
    for index in edit["indices"]:
        im = Image.open(contained(directory, manifest["frames"][index]["path"])).convert("RGBA")
        im = remove_background(im, background, tolerance).crop((x, y, x+cw, y+ch))
        im = im.resize(target, Image.Resampling.NEAREST)
        bounds = im.getchannel("A").getbbox()
        if bounds and (bounds[0]+position[0] < 0 or bounds[1]+position[1] < 0 or
                       bounds[2]+position[0] > canvas[0] or bounds[3]+position[1] > canvas[1]):
            warnings.append(f"Frame {index}: visible pixels clipped by canvas offset")
        frame = Image.new("RGBA", canvas)
        frame.paste(im, position)
        frames.append(frame)
    colors = [rgb(c) for c in palette] if palette else _palette_for(frames, palette_size)
    if not 1 <= len(colors) <= 256:
        raise ValueError("Supply 1..256 palette colors")
    # Exact nearest RGB mapping, no per-frame palette and no dithering.
    color_array = np.array(colors, dtype=np.int32)
    for i, im in enumerate(frames):
        a = np.array(im)
        visible = a[:, :, 3] != 0
        pixels = a[visible, :3].astype(np.int32)
        for start in range(0, len(pixels), 4096):
            chunk = pixels[start:start+4096]
            nearest = ((chunk[:, None] - color_array[None]) ** 2).sum(axis=2).argmin(axis=1)
            pixels[start:start+4096] = color_array[nearest]
        a[visible, :3] = pixels.astype(np.uint8)
        a[~visible, :3] = 0
        frames[i] = Image.fromarray(a)
        if not visible.any():
            warnings.append(f"Frame {edit['indices'][i]}: empty silhouette")
    if len(frames) == 1:
        warnings.append("Single-frame selection is static, not animation acceptance")
    report = {"version": VERSION, "canvas": list(canvas), "pivot": pivot,
              "effective_source_size": manifest["effective_size"],
              "source_indices": edit["indices"], "durations_ms": edit["durations_ms"],
              "sources": [manifest["frames"][i]["source"] for i in edit["indices"]],
              "provenance": manifest["provenance"], "loop": bool(edit.get("loop", True)),
              "palette_rgb": [list(c) for c in colors], "warnings": warnings,
              "processing": {"background": background, "tolerance": tolerance, "crop": [x,y,cw,ch],
                             "offset": list(offset), "resize": "nearest", "dither": False},
              "checks": {"binary_alpha": True, "shared_palette": True, "frame_order": True}}
    return frames, report


def export_frames(frames, report, directory):
    directory = Path(directory)
    if (directory / "animation.json").exists():
        raise ValueError("Export exists; choose a new output directory")
    (directory / "frames").mkdir(parents=True, exist_ok=True)
    w, h = frames[0].size
    columns = min(8, len(frames))
    rows = math.ceil(len(frames) / columns)
    atlas = Image.new("RGBA", (columns * (w+2), rows * (h+2)))
    entries = []
    for i, im in enumerate(frames):
        path = f"frames/{i:05}.png"
        (directory / path).write_bytes(canonical_png(im))
        x, y = (i % columns) * (w+2) + 1, (i // columns) * (h+2) + 1
        atlas.paste(im, (x, y))
        bounds = im.getchannel("A").getbbox()
        entries.append({"path": path, "sha256": digest(directory / path), "region": [x,y,w,h],
                        "visible_bounds": list(bounds) if bounds else None,
                        "source": report["sources"][i], "duration_ms": report["durations_ms"][i]})
    (directory / "atlas.png").write_bytes(canonical_png(atlas))
    frames[0].save(directory / "preview.webp", format="WEBP", save_all=True,
                   append_images=frames[1:], duration=report["durations_ms"], loop=0,
                   lossless=True, exact=True)
    data = {"version": VERSION, "size": [w,h], "pivot": report["pivot"], "loop": report["loop"],
            "atlas": "atlas.png", "effective_source_size": report["effective_source_size"],
            "frames": entries, "palette_rgb": report["palette_rgb"]}
    write_json(directory / "animation.json", data)
    write_json(directory / "report.json", report)
    return directory
