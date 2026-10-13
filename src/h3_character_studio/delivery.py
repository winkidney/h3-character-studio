"""Portable Godot-shaped character bundle; game adoption remains explicit."""
import json
from pathlib import Path
import shutil

import yaml
from . import core, normals
from .recipe import DIRECTIONS, identifier
from .extraction import check_bundle


def assemble(spec_path, output):
    spec_path, output = Path(spec_path).absolute(), Path(output)
    spec = yaml.safe_load(spec_path.read_text())
    if spec.get("schema_version") != 1 or set(spec.get("directions", {})) != set(DIRECTIONS):
        raise ValueError("Delivery needs schema_version: 1 and all four directions")
    identifier(spec["id"])
    rows, palette, pivot = {}, None, None
    for direction, row in spec["directions"].items():
        color = core.contained(spec_path.parent, row["animation"])
        normal = core.contained(spec_path.parent, row["normals"])
        check_bundle(color); normals.verify(color, normal)
        manifest = json.loads((color / "animation.json").read_text())
        idle = row["idle_frame"]
        if type(idle) is not int or not 0 <= idle < len(manifest["frames"]):
            raise ValueError("Choose an idle frame inside each direction")
        if palette is not None and (manifest["palette_rgb"] != palette or manifest["pivot"] != pivot):
            raise ValueError("Four directions must share a palette and pivot")
        palette, pivot = manifest["palette_rgb"], manifest["pivot"]
        rows[direction] = color, normal, idle
    output.mkdir(parents=True, exist_ok=False)
    definition = dict(schema_version=1, id=spec["id"], version="v1", default_direction="right", size=[256, 256],
        pivot=pivot, pixel_size=spec.get("pixel_size", 0.009), directions={},
        stationary_behavior="Hold the explicitly selected frame; no generated idle animation.", visual_approval="pending")
    normal_definition = dict(schema_version=1, size=[256, 256], pivot=pivot, frame_count=0, directions={}, visual_approval="pending")
    for direction, (color, normal, idle) in rows.items():
        shutil.copytree(color, output / "character" / direction)
        shutil.copytree(normal, output / "normals" / direction)
        definition["directions"][direction] = dict(manifest=f"{direction}/animation.json", idle_frame=idle, generation="independent-H3")
        n = json.loads((normal / "manifest.json").read_text())
        normal_definition["directions"][direction] = dict(manifest=f"{direction}/manifest.json", atlas=f"{direction}/atlas.png", mask_atlas=f"{direction}/mask-atlas.png", idle_frame=idle)
        normal_definition["frame_count"] += len(n["frames"])
    core.write_json(output / "character/character.json", definition)
    core.write_json(output / "normals/manifest.json", normal_definition)
    core.write_json(output / "SHA256SUMS.json", dict(files=[dict(path=str(p.relative_to(output)), sha256=core.digest(p))
        for p in sorted(output.rglob("*")) if p.is_file()]))
    return dict(output=str(output), id=spec["id"], frame_count=normal_definition["frame_count"], visual_approval="pending")


def verify(bundle):
    bundle = Path(bundle)
    manifest = json.loads((bundle / "SHA256SUMS.json").read_text())
    expected = {row["path"] for row in manifest["files"]}
    actual = {str(p.relative_to(bundle)) for p in bundle.rglob("*") if p.is_file()} - {"SHA256SUMS.json"}
    if actual != expected:
        raise ValueError("Bundle file list changed")
    for row in manifest["files"]:
        if core.digest(core.contained(bundle, row["path"])) != row["sha256"]:
            raise ValueError("Bundle file digest changed")
    for direction in DIRECTIONS:
        normals.verify(bundle / "character" / direction, bundle / "normals" / direction)
    return dict(verified_files=len(expected), four_directions=True, visual_approval="pending")
