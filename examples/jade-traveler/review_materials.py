"""Build a color/vector/mask/clay contact sheet for actual selected poses."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from h3_character_studio.geometry import unit

p = argparse.ArgumentParser()
p.add_argument("animation", type=Path)
p.add_argument("normals", type=Path)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
manifest = json.loads((a.animation / "animation.json").read_text())
keys = sorted(set([0, len(manifest["frames"])//4, 11, len(manifest["frames"])//2,
    3*len(manifest["frames"])//4, len(manifest["frames"])-1]))
sheet = Image.new("RGB", (256*len(keys), 4*276), "#303238")
d = ImageDraw.Draw(sheet)
light = unit(np.array([-.6, .5, .8], np.float32))
for x,index in enumerate(keys):
    color = Image.open(a.animation / manifest["frames"][index]["path"]).convert("RGBA")
    normal = Image.open(a.normals / "frames" / f"{index:05d}.png").convert("RGBA")
    mask = Image.open(a.normals / "masks" / f"{index:05d}.png").convert("RGBA")
    data = np.asarray(normal)
    vectors = unit(data[..., :3].astype(np.float32)/255*2-1)
    gray = ((np.clip((vectors*light).sum(-1),0,1)*.65+.2)*255).astype(np.uint8)
    clay = Image.fromarray(np.dstack([gray,gray,gray,data[...,3]]))
    for y,(label,im) in enumerate(zip(["color","vector","metal","clay"],[color,normal,mask,clay])):
        sheet.paste(im,(x*256,y*276),im)
        d.text((x*256+4,y*276+258),f"{label} frame {index}",fill="white")
a.output.parent.mkdir(parents=True,exist_ok=True)
sheet.save(a.output)
