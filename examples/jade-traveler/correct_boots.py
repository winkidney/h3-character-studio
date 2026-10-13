"""Pose-specific boot volumes inside reviewed lower-limb regions.

Color identifies leather only. Silhouette coordinates define geometry; diffuse
brightness never becomes height or a surface slope. Screen-left/right regions
are authoring regions, not anatomical leg identities during an overlap.
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np
from PIL import Image
from h3_character_studio import core


def main():
    p = argparse.ArgumentParser()
    p.add_argument("animation", type=Path)
    p.add_argument("editable", type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    manifest = json.loads((a.animation / "animation.json").read_text())
    leather = [c for c in manifest["palette_rgb"] if max(c) < 165 and c[0] > c[1] and c[1] >= c[2]]
    a.output.mkdir(parents=True, exist_ok=False)
    for index, row in enumerate(manifest["frames"]):
        pixels = np.asarray(Image.open(a.animation / row["path"]).convert("RGBA"))
        semantic = (pixels[..., :3, None] == np.asarray(leather).T).all(axis=2).any(axis=2)
        rig = json.loads((a.editable / f"{index:05d}/geometry.json").read_text())
        shapes = copy.deepcopy(rig["shapes"])
        before_metal = next((i for i, s in enumerate(shapes) if s.get("metallic")), len(shapes))
        additions = []
        for name, low, high in [("screen-left", 30, 128), ("screen-right", 128, 220)]:
            region = semantic & (pixels[..., 3] > 0)
            region[:186] = False
            region[:, :low] = False
            region[:, high:] = False
            ys, xs = np.where(region)
            if len(xs) < 20:
                continue
            points = []
            for y in range(int(ys.min()), int(ys.max()) + 1, 5):
                local_y, local_x = np.where(region[max(186, y-2):y+3])
                if len(local_x):
                    points.append([float(np.median(local_x)), float(y)])
            if len(points) >= 2:
                additions.append(dict(id=name+"-calf-correction", kind="tube", points=points,
                    radius=7, slope=.42, braid=False, palette_colors=leather,
                    clip_polygon=[[low,186],[high-1,186],[high-1,255],[low,255]]))
            foot = region.copy()
            foot[:max(186,int(ys.max())-9)] = False
            fy, fx = np.where(foot)
            additions.append(dict(id=name+"-foot-correction", kind="ellipsoid",
                ellipse=[float((fx.min()+fx.max())/2),float((fy.min()+fy.max())/2),
                    float((fx.max()-fx.min())/2+2),float((fy.max()-fy.min())/2+2)],
                slope=.4, palette_colors=leather,
                clip_polygon=[[low,186],[high-1,186],[high-1,255],[low,255]]))
        shapes[before_metal:before_metal] = additions
        core.write_json(a.output / f"{index:05d}/geometry.json", dict(frame=index, shapes=shapes,
            correction="silhouette-derived lower-limb axes inside authored leather regions"))
    print("Corrected", len(manifest["frames"]), "pose-specific lower-limb rigs")


if __name__ == "__main__":
    main()
