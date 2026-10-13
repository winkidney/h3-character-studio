"""Editable semantic geometry transported through an animation loop."""
import copy
import json
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageDraw
import yaml
from . import core, geometry
from .extraction import check_bundle
from .recipe import identifier


def warp(shapes, flow):
    result = copy.deepcopy(shapes)
    for shape in result:
        if "pixel_region" in shape:
            raise ValueError("Exact pixel regions require explicit per-frame geometry edits")
        if "ellipse" in shape:
            shape["ellipse"][:2] = (np.asarray(shape["ellipse"][:2]) + geometry.sample_flow(flow, shape["ellipse"][:2])).tolist()
        if "points" in shape:
            shape["points"] = [(np.asarray(point) + geometry.sample_flow(flow, point)).tolist() for point in shape["points"]]
        for name in ("clip_polygon", "surface_region"):
            if name in shape:
                shape[name] = [(np.asarray(point) + geometry.sample_flow(flow, point)).tolist() for point in shape[name]]
    return result


def interpolate(a, b, weight):
    if len(a) != len(b) or [(s["id"], s["kind"]) for s in a] != [(s["id"], s["kind"]) for s in b]:
        raise ValueError("Key poses must share ordered shape IDs and kinds; use per-frame edits for topology changes")
    result = copy.deepcopy(a)
    for shape, other in zip(result, b):
        for name in ("ellipse", "points", "clip_polygon", "surface_region"):
            if (name in shape) != (name in other):
                raise ValueError("Corresponding shapes must share coordinate fields")
            if name in shape:
                x, y = np.asarray(shape[name]), np.asarray(other[name])
                if x.shape != y.shape:
                    raise ValueError("Corresponding shape coordinates must share a topology")
                shape[name] = ((1 - weight) * x + weight * y).round(4).tolist()
        defaults = dict(slope=.65 if shape["kind"] == "ellipsoid" else .72,
                        yaw=0, coverage=1, normal=[0, 0, 1])
        for name in ("radius", "slope", "yaw", "coverage", "normal"):
            if name in shape or name in other:
                x = np.asarray(shape.get(name, defaults.get(name)), dtype=float)
                y = np.asarray(other.get(name, defaults.get(name)), dtype=float)
                if x.shape != y.shape or not np.isfinite(x).all() or not np.isfinite(y).all():
                    raise ValueError("Corresponding surface parameters must be finite and compatible")
                value = (1 - weight) * x + weight * y
                if name == "normal":
                    if value.shape != (3,) or np.linalg.norm(value) < 1e-6:
                        raise ValueError("Interpolated plane normal is undefined")
                    value = geometry.unit(value)
                shape[name] = value.round(6).tolist()
    return result


def transport(keys, forward, backward):
    """Bidirectional propagation between authored anchors, including the loop seam."""
    count = len(forward)
    anchors = sorted(keys)
    if not anchors or anchors[0] != 0 or anchors[-1] >= count:
        raise ValueError("Author frame 0 and keyposes inside the selected animation")
    result = [None] * count
    for position, start in enumerate(anchors):
        end = anchors[(position + 1) % len(anchors)]
        span = (end - start) % count or count
        front, back = [copy.deepcopy(keys[start])], [None] * (span + 1)
        back[span] = copy.deepcopy(keys[end])
        for offset in range(1, span + 1):
            front.append(warp(front[-1], forward[(start + offset - 1) % count]))
        for offset in reversed(range(span)):
            back[offset] = warp(back[offset + 1], backward[(start + offset) % count])
        for offset in range(span):
            index = (start + offset) % count
            result[index] = copy.deepcopy(keys[start]) if offset == 0 else interpolate(front[offset], back[offset], offset / span)
    return result


def polygon(points):
    coordinates = np.asarray(points, dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[1] != 2 or len(coordinates) < 3 or not np.isfinite(coordinates).all():
        raise ValueError("A surface polygon needs at least three finite 2D points")
    canvas = Image.new("L", (256, 256))
    ImageDraw.Draw(canvas).polygon([tuple(p) for p in points], fill=255)
    return np.asarray(canvas) > 0


def render(color, shapes):
    visible = color[..., 3] > 0
    vectors = np.zeros((256, 256, 3), np.float32)
    vectors[..., 2] = 1
    labels = np.zeros((256, 256), np.uint8)
    metallic = np.zeros((256, 256), bool)
    if not shapes or len(shapes) > 254 or len({s["id"] for s in shapes}) != len(shapes):
        raise ValueError("Use 1..254 uniquely named semantic shapes")
    for index, shape in enumerate(shapes, 1):
        identifier(shape["id"])
        for name in ("ellipse", "points", "clip_polygon", "surface_region", "normal", "radius", "slope", "yaw", "coverage"):
            if name in shape and not np.isfinite(np.asarray(shape[name], dtype=float)).all():
                raise ValueError("Geometry coordinates and parameters must be finite")
        kind = shape["kind"]
        if kind == "ellipsoid":
            if min(shape["ellipse"][2:]) <= 0:
                raise ValueError("Ellipsoid radii must be positive")
            mask = geometry.ellipse_region(shape["ellipse"], shape.get("coverage", 1.0))
            normal = geometry.ellipsoid(shape["ellipse"], slope=shape.get("slope", 0.65), yaw=shape.get("yaw", 0))
            # The semantic visible garment can extend beyond the analytic
            # ellipse. Its explicit region gets the same surface field, rather
            # than falling silently back to a screen-facing plane.
            if "surface_region" in shape:
                mask = polygon(shape["surface_region"])
        elif kind == "tube":
            if len(shape["points"]) < 2 or shape["radius"] <= 0:
                raise ValueError("A tube needs two points and a positive radius")
            mask, normal = geometry.tube_geometry(shape["points"], shape["radius"],
                amplitude=shape.get("slope", 0.72), braid=shape.get("braid", False))
        elif kind == "plane":
            mask = polygon(shape["points"])
            vector = np.asarray(shape.get("normal", [0, 0, 1]), np.float32)
            if vector.shape != (3,) or not np.isfinite(vector).all() or np.linalg.norm(vector) < 1e-6:
                raise ValueError("Plane normal must be a finite nonzero vector")
            normal = np.broadcast_to(geometry.unit(vector), vectors.shape)
        else:
            raise ValueError("Geometry kind must be ellipsoid, tube or plane")
        if "pixel_region" in shape:
            # Fine material islands need exact per-frame coverage. A bounding
            # ellipse must not turn adjacent embroidery or jade into metal.
            points = np.asarray(shape["pixel_region"], dtype=float)
            if (points.ndim != 2 or points.shape[1] != 2 or not len(points)
                    or not np.isfinite(points).all() or np.any(points != np.rint(points))
                    or np.any(points < 0) or np.any(points > 255)):
                raise ValueError("Pixel regions need integer coordinates inside the256px canvas")
            points = points.astype(int)
            mask = np.zeros((256, 256), bool)
            mask[points[:, 1], points[:, 0]] = True
        if "clip_polygon" in shape:
            mask &= polygon(shape["clip_polygon"])
        if shape.get("palette_colors"):
            # Semantic material selection only. RGB never defines surface slopes.
            allowed = np.asarray([core.rgb(c) for c in shape["palette_colors"]], np.uint8)
            mask &= (color[..., :3, None] == allowed.T[None, None]).all(axis=2).any(axis=2)
        mask &= visible
        vectors[mask] = normal[mask]
        labels[mask] = index
        metallic[mask] = bool(shape.get("metallic", False))
    return geometry.unit(vectors), labels, metallic


def encoded(normal, alpha):
    pixels = np.dstack((np.rint(np.clip(normal * 0.5 + 0.5, 0, 1) * 255).astype(np.uint8), alpha))
    pixels[alpha == 0, :3] = [128, 128, 255]
    return pixels


def build(animation, geometry_path, output, *, edits=None, painted_layers=None, material_annotations=None):
    animation, output = Path(animation), Path(output)
    check_bundle(animation)
    manifest = json.loads((animation / "animation.json").read_text())
    spec = yaml.safe_load(Path(geometry_path).read_text())
    if spec.get("schema_version") != 1 or not isinstance(spec.get("keyframes"), dict):
        raise ValueError("Geometry YAML requires schema_version: 1 and keyframes")
    keys = {int(key): value for key, value in spec["keyframes"].items()}
    colors = [np.asarray(Image.open(core.contained(animation, row["path"])).convert("RGBA")) for row in manifest["frames"]]
    # Validate keypose geometry before creating outputs.
    for key, value in keys.items():
        if not 0 <= key < len(colors):
            raise ValueError("Keypose frame outside selected animation")
        render(colors[key], value)
    forward, backward = geometry.optical_flow(colors)
    # Explicit per-frame edits are authoritative, including topology changes
    # such as a newly exposed fold or a different boot silhouette. They must
    # not first pass through automatic keypose interpolation.
    per_frame_source = Path(edits or painted_layers) if (edits or painted_layers) else None
    rigs = [None] * len(colors) if per_frame_source else transport(keys, forward, backward)
    output.mkdir(parents=True, exist_ok=False)
    (output / "geometry.yaml").write_bytes(Path(geometry_path).read_bytes())
    np.savez_compressed(output / "motion.npz", forward=np.asarray(forward).astype(np.float16),
                        backward=np.asarray(backward).astype(np.float16))
    source_atlas = Image.open(core.contained(animation, manifest["atlas"])).convert("RGBA")
    normal_atlas = Image.new("RGBA", source_atlas.size, (128, 128, 255, 0))
    mask_atlas = Image.new("RGBA", source_atlas.size)
    records, unlabelled, fallback, normals, masks = [], [], [], [], []
    material_checks = []
    for index, (color, shapes, row) in enumerate(zip(colors, rigs, manifest["frames"])):
        if per_frame_source:
            shapes = json.loads((per_frame_source / f"{index:05d}/geometry.json").read_text())["shapes"]
        from . import materials
        shapes, material_check = materials.constrain(shapes, color, row["sha256"], index, material_annotations)
        material_checks.append(material_check)
        normal, labels, metal = render(color, shapes)
        edit_dir = output / "editable" / f"{index:05d}"
        edit_dir.mkdir(parents=True)
        core.write_json(edit_dir / "geometry.json", dict(frame=index, shapes=shapes))
        if painted_layers:
            # Explicit previous editable layers are recomposed without regeneration.
            combined = np.zeros_like(normal)
            coverage = np.zeros((256, 256), np.uint16)
            for layer_index, shape in enumerate(shapes, 1):
                path = Path(painted_layers) / f"{index:05d}" / (shape["id"] + ".png")
                pixels = np.asarray(Image.open(path).convert("RGBA"))
                expected = labels == layer_index
                if not np.array_equal(pixels[..., 3] > 0, expected):
                    raise ValueError("Edited normal layer coverage changed")
                vectors = pixels[..., :3].astype(np.float32) / 255 * 2 - 1
                combined[expected] = geometry.unit(vectors)[expected]
                coverage += expected
            combined[coverage == 0] = [0, 0, 1]
            normal = combined
        alpha = color[..., 3]
        pixels = encoded(normal, alpha)
        mask = np.dstack((np.repeat((metal.astype(np.uint8) * 255)[..., None], 3, axis=2), alpha))
        masks.append(mask); normals.append(pixels)
        Image.fromarray(labels).save(edit_dir / "labels.png")
        for layer_index, shape in enumerate(shapes, 1):
            # Editable sparse layers use lossless compression; runtime PNGs below
            # retain canonical bytes. Thousands of empty layer pixels need not
            # become gigabytes of uncompressed authoring data.
            Image.fromarray(encoded(normal, np.where(labels == layer_index, alpha, 0).astype(np.uint8))).save(
                core.contained(edit_dir, shape["id"] + ".png"))
        frame_path = output / "frames" / f"{index:05d}.png"
        mask_path = output / "masks" / f"{index:05d}.png"
        frame_path.parent.mkdir(exist_ok=True); mask_path.parent.mkdir(exist_ok=True)
        frame_path.write_bytes(core.canonical_png(Image.fromarray(pixels)))
        mask_path.write_bytes(core.canonical_png(Image.fromarray(mask)))
        x, y, width, height = row["region"]
        normal_atlas.paste(Image.fromarray(pixels), (x, y)); mask_atlas.paste(Image.fromarray(mask), (x, y))
        unlabelled.append(int(((alpha > 0) & (labels == 0)).sum()))
        fallback_labels = [i for i, shape in enumerate(shapes, 1) if shape.get("fallback", False)]
        fallback.append(int(((alpha > 0) & np.isin(labels, fallback_labels)).sum()))
        records.append(dict(index=index, path=str(frame_path.relative_to(output)), sha256=core.digest(frame_path),
            mask_path=str(mask_path.relative_to(output)), mask_sha256=core.digest(mask_path),
            source_path=row["path"], source_sha256=row["sha256"], region=row["region"], duration_ms=row["duration_ms"]))
    (output / "atlas.png").write_bytes(core.canonical_png(normal_atlas))
    (output / "mask-atlas.png").write_bytes(core.canonical_png(mask_atlas))
    data = dict(schema_version=1, size=[256, 256], pivot=manifest["pivot"], atlas="atlas.png", mask_atlas="mask-atlas.png",
        atlas_sha256=core.digest(output / "atlas.png"), mask_atlas_sha256=core.digest(output / "mask-atlas.png"),
        source_manifest_sha256=core.digest(animation / "animation.json"), frames=records,
        coordinates="X right, Y up, Z toward viewer; RGB=(normal+1)/2; linear vector data",
        visual_approval="pending", unlabelled_pixels=unlabelled, fallback_pixels=fallback)
    core.write_json(output / "manifest.json", data)
    # Clay review keeps albedo entirely out of the lighting calculation.
    light = geometry.unit(np.array([-.6, .5, .8], np.float32))
    review = []
    for pixels in normals:
        vectors = geometry.unit(pixels[..., :3].astype(np.float32) / 255 * 2 - 1)
        brightness = (np.clip((vectors * light).sum(-1), 0, 1) * .65 + .2) * 255
        review.append(Image.fromarray(np.dstack((np.repeat(brightness[..., None], 3, axis=2).astype(np.uint8), pixels[..., 3]))))
    review[0].save(output / "clay.webp", save_all=True, append_images=review[1:],
                   duration=[r["duration_ms"] for r in records], loop=0, lossless=True)
    transitions = []
    for i, pixels in enumerate(normals):
        next_i = (i + 1) % len(normals)
        flow = backward[i]
        old = pixels[..., :3].astype(np.float32) / 255 * 2 - 1
        transported = cv2.remap(old, geometry.XX + flow[..., 0], geometry.YY + flow[..., 1], cv2.INTER_NEAREST)
        previous_alpha = cv2.remap(pixels[..., 3], geometry.XX + flow[..., 0], geometry.YY + flow[..., 1], cv2.INTER_NEAREST)
        current = normals[next_i][..., :3].astype(np.float32) / 255 * 2 - 1
        visible = (previous_alpha > 0) & (normals[next_i][..., 3] > 0)
        angle = np.degrees(np.arccos(np.clip((geometry.unit(transported) * geometry.unit(current)).sum(-1), -1, 1)))
        transitions.append(dict(source=i, target=next_i, loop_seam=next_i == 0,
            common_pixels=int(visible.sum()), p95_angle_degrees=float(np.percentile(angle[visible], 95)) if visible.any() else None))
    validation = verify(animation, output)
    core.write_json(output / "material-ownership.json", dict(frames=material_checks, transported_materials_are_proposals=True))
    validation.update(material_annotations_verified=True, unlabelled_pixels=unlabelled, fallback_pixels=fallback,
                      geometry_coverage_complete=not any(unlabelled) and not any(fallback),
                      transitions=transitions, temporal_metrics_are_review_hints=True, visual_approval="pending")
    core.write_json(output / "validation.json", validation)
    return validation


def verify(animation, output):
    animation, output = Path(animation), Path(output)
    check_bundle(animation)
    color = json.loads((animation / "animation.json").read_text())
    normal = json.loads((output / "manifest.json").read_text())
    if core.digest(animation / "animation.json") != normal["source_manifest_sha256"] or len(color["frames"]) != len(normal["frames"]):
        raise ValueError("Normal and color sequences disagree")
    atlases = [np.asarray(Image.open(output / name).convert("RGBA")) for name in ("atlas.png", "mask-atlas.png")]
    with Image.open(core.contained(animation, color["atlas"])) as source_atlas:
        source_size = source_atlas.size
    if any(list(a.shape[:2][::-1]) != list(source_size) for a in atlases):
        raise ValueError("Paired atlas size differs")
    for key in ("atlas", "mask_atlas"):
        if core.digest(output / normal[key]) != normal[key + "_sha256"]:
            raise ValueError("Normal atlas digest changed")
    max_error = 0.0
    for c, n in zip(color["frames"], normal["frames"]):
        if c["duration_ms"] != n["duration_ms"] or c["region"] != n["region"] or c["sha256"] != n["source_sha256"]:
            raise ValueError("Frame timing, region or source changed")
        alpha = np.asarray(Image.open(core.contained(animation, c["path"])).convert("RGBA"))[..., 3]
        for key, atlas in zip(("path", "mask_path"), atlases):
            path = core.contained(output, n[key])
            digest_key = "sha256" if key == "path" else "mask_sha256"
            if core.digest(path) != n[digest_key]:
                raise ValueError("Paired frame digest changed")
            pixels = np.asarray(Image.open(path).convert("RGBA"))
            if pixels.shape != (256, 256, 4) or not np.array_equal(alpha, pixels[..., 3]):
                raise ValueError("Normal/mask alpha differs from color")
            x, y, width, height = c["region"]
            if not np.array_equal(pixels, atlas[y:y+height, x:x+width]):
                raise ValueError("Normal/mask atlas region differs")
            if key == "path":
                length = np.linalg.norm(pixels[alpha > 0, :3].astype(np.float32) / 255 * 2 - 1, axis=1)
                max_error = max(max_error, float(np.max(np.abs(length - 1))))
            elif set(np.unique(pixels[..., :3])) - {0, 255}:
                raise ValueError("Material mask must be binary")
    if max_error > 0.014:
        raise ValueError("Normal unit-vector error exceeds RGBA8 rounding tolerance")
    return dict(frame_count=len(color["frames"]), exact_alpha=True, exact_atlas=True,
                immutable_color=True, max_unit_vector_error=max_error, visual_approval="pending")
