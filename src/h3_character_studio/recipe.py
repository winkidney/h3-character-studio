"""Explicit character inputs; one reference and prompt per direction."""
import math
from pathlib import Path
import re

from PIL import Image
import yaml
from . import core

DIRECTIONS = ("down", "up", "left", "right")
DEFAULTS = dict(width=768, height=768, frames=56, fps=24.0, steps=40,
                seed=41, mid_guide_frame=27, palette_size=96, pivot=[128, 240])


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise ValueError("IDs must contain 1..80 letters, numbers, underscores or hyphens")
    return value


def load(path):
    path = Path(path).resolve(strict=True)
    spec = yaml.safe_load(path.read_text())
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("Expected character YAML schema_version: 1")
    identifier(spec.get("id"))
    settings = dict(DEFAULTS, **spec.get("settings", {}))
    for name in ("width", "height"):
        if type(settings[name]) is not int or not 256 <= settings[name] <= 2048 or settings[name] % 32:
            raise ValueError("H3 width and height must be multiples of 32 in 256..2048")
    if settings["width"] != settings["height"]:
        raise ValueError("Character masters use a square canvas")
    count = settings["frames"]
    if type(count) is not int or count < 22 or count > 260 or (count - 5) % 17:
        raise ValueError("H3 length must be 17k+5, from 22 through 260")
    if type(settings["fps"]) not in (int, float) or not math.isfinite(settings["fps"]) or not 1 <= settings["fps"] <= 60:
        raise ValueError("FPS must be finite and in 1..60")
    if type(settings["steps"]) is not int or not 1 <= settings["steps"] <= 100:
        raise ValueError("Steps must be an integer in 1..100")
    pivot = settings["pivot"]
    if not isinstance(pivot, list) or len(pivot) != 2 or any(type(x) is not int or not 0 <= x < 256 for x in pivot):
        raise ValueError("Pivot must be two integer pixels in the 256 canvas")
    guide = settings["mid_guide_frame"]
    if type(guide) is not int or (guide != -1 and not 0 < guide < count - 1):
        raise ValueError("Middle guide must be -1 or strictly between endpoint frames")
    extra_guides = settings.get("extra_guide_frames", [])
    if not isinstance(extra_guides, list) or len(extra_guides) > 8 or any(type(g) is not int or not 0 < g < count-1 for g in extra_guides) or len(set(extra_guides)) != len(extra_guides):
        raise ValueError("Extra guides must be up to 8 unique interior frame integers")
    if type(settings["seed"]) is not int or not 0 <= settings["seed"] < 2**64:
        raise ValueError("Seed must be an unsigned 64-bit integer")
    if type(settings["palette_size"]) is not int or not 1 <= settings["palette_size"] <= 256:
        raise ValueError("Palette size must be an integer in 1..256")
    directions = spec.get("directions")
    if not isinstance(directions, dict) or set(directions) != set(DIRECTIONS):
        raise ValueError("Provide independent down, up, left and right masters and prompts")
    references = {}
    for name, row in directions.items():
        if not isinstance(row, dict):
            raise ValueError("Each direction must be a mapping")
        master = core.contained(path.parent, row["master"])
        with Image.open(master) as image:
            if image.mode != "RGBA" or image.width != image.height or image.width < 256 or not image.getbbox():
                raise ValueError("Masters must be nonempty square RGBA PNGs at least 256 pixels")
        if row.get("prompt_file"):
            prompt_path = core.contained(path.parent, row["prompt_file"])
            prompt = prompt_path.read_text().strip()
        else:
            prompt = row.get("prompt", "").strip()
        if not prompt:
            raise ValueError("Each direction needs a nonempty prompt or prompt_file")
        references[name] = dict(master=master, master_sha256=core.digest(master), prompt=prompt,
                                seed=row.get("seed", settings["seed"]))
        if type(references[name]["seed"]) is not int or not 0 <= references[name]["seed"] < 2**64:
            raise ValueError("Direction seed must be an unsigned 64-bit integer")
    return spec, settings, references
