"""Authored jade-traveler volume seeds; transport never infers height from RGB.

These coordinates are a documented interpretation of actual 256px color poses
and the clay studies. A different character requires its own seed geometry.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
import yaml
from h3_character_studio import geometry, normals


def ellipse(name, coords, slope=.55, colors=None, metallic=False, yaw=0):
    result = dict(id=name, kind="ellipsoid", ellipse=coords, slope=slope, yaw=yaw,
                  metallic=metallic)
    if colors: result["palette_colors"] = colors
    return result


def tube(name, points, radius, slope=.6, colors=None, metallic=False):
    result = dict(id=name, kind="tube", points=points, radius=radius, slope=slope,
                  braid=False, metallic=metallic)
    if colors: result["palette_colors"] = colors
    return result


def seed(direction, palette):
    hair = [c for c in palette if max(c) < 125 and c[0] >= c[1]-5]
    skin = [c for c in palette if c[0] > 150 and c[1] > 85 and c[0] > c[1]*1.075 and c[1] > c[2]*1.06]
    metal = [c for c in palette if min(c) >= 85 and c[0] >= c[1]-1 and max(c)-min(c) <= 48]
    jade = [c for c in palette if c[1] > c[0]+4 and c[1] > c[2]-8 and min(c) > 70]
    if not hair or not skin or not metal or not jade:
        raise ValueError("The shared palette lacks the authored material groups")
    if direction == "down":
        shapes = [dict(id="cloth-base", kind="plane", points=[[1,1],[254,1],[254,254],[1,254]], normal=[0,0,1])]
        shapes += [ellipse("skirt-volume",[126,153,42,32],.36),
            tube("skirt-left-pleat",[[110,125],[104,155],[99,178]],8,.4),
            tube("skirt-middle-pleat",[[128,125],[124,155],[121,181]],8,.4),
            tube("skirt-right-pleat",[[141,125],[148,154],[153,179]],8,.4),
            tube("left-leg",[[119,182],[118,198],[117,213]],7,.5),
            ellipse("left-boot",[117,215,7,8],.5),
            tube("right-leg",[[130,183],[132,205],[131,231]],8,.5),
            ellipse("right-boot",[132,233,9,6],.5),
            ellipse("torso",[127,110,17,20],.38),
            tube("left-sleeve",[[99,110],[97,122],[89,135]],9,.45),
            tube("right-sleeve",[[155,112],[159,123],[166,136]],9,.45),
            ellipse("capelet-left",[111,95,20,16],.35),
            ellipse("capelet-right",[143,96,20,16],.35),
            ellipse("satchel",[107,135,12,15],.45),
            tube("strap",[[137,82],[124,108],[111,131]],2.5,.35),
            ellipse("head-hair",[126,48,23,23],.5,colors=hair),
            tube("left-ponytail",[[99,27],[94,55],[81,80],[85,101]],10,.55,colors=hair),
            tube("right-ponytail",[[150,27],[153,56],[168,82],[169,99]],10,.55,colors=hair),
            ellipse("face",[127,65,19,16],.4,colors=skin),
            ellipse("neck",[127,83,5,6],.4,colors=skin),
            ellipse("left-hand",[88,145,6,8],.5,colors=skin),
            ellipse("right-hand",[168,146,6,8],.5,colors=skin)]
        for name,coords in [("left-jade-leaf",[104,41,3,5]),("right-jade-leaf",[151,41,3,5]),
            ("waist-jade",[127,140,3,4])]:
            shapes.append(ellipse(name,coords,.4,colors=jade))
        for name,coords in [("left-hair-cuff",[106,32,5,5]),("right-hair-cuff",[148,32,5,5]),
            ("cape-brooch",[129,86,4,4]),("left-wrist",[90,136,6,4]),("right-wrist",[165,137,6,4]),
            ("satchel-clasp",[108,136,4,4]),("waist-ornament",[127,127,8,4]),
            ("left-boot-buckle",[118,201,4,3]),("right-boot-buckle",[131,217,5,3])]:
            shapes.append(ellipse(name,coords,.55,colors=metal,metallic=True))
        for i,x in enumerate([122,127,132]):
            shapes.append(tube(f"waist-pendant-{i}",[[x,130],[x,141]],2,.5,colors=metal,metallic=True))
        return shapes
    if direction == "left":
        shapes = [dict(id="cloth-base", kind="plane", points=[[1,1],[254,1],[254,254],[1,254]], normal=[0,0,1])]
        shapes += [ellipse("skirt-volume",[137,153,42,33],.38),
            tube("skirt-left-pleat",[[116,126],[109,151],[107,181]],8,.42),
            tube("skirt-middle-pleat",[[130,125],[131,153],[131,184]],8,.42),
            tube("skirt-right-pleat",[[147,127],[157,151],[168,177]],8,.42),
            tube("near-leg",[[122,183],[114,207],[104,230]],8,.5),
            ellipse("near-boot",[104,232,17,7],.45),
            tube("far-leg",[[145,181],[151,199],[154,218]],7,.5),
            ellipse("far-boot",[154,221,12,7],.45),
            ellipse("torso",[128,110,17,20],.38),
            tube("near-sleeve",[[107,110],[95,122],[88,132]],9,.45),
            tube("far-sleeve",[[151,113],[158,128],[166,140]],9,.45),
            ellipse("capelet",[131,96,30,18],.35),
            ellipse("occluded-satchel",[107,137,6,15],.45),
            tube("strap",[[117,88],[113,112],[106,136]],2.5,.35),
            ellipse("head-hair",[130,52,24,29],.5,colors=hair),
            tube("near-ponytail",[[157,38],[165,70],[181,91],[180,110]],10,.55,colors=hair),
            tube("far-ponytail",[[118,30],[110,57],[98,81],[92,94]],8,.55,colors=hair),
            ellipse("face",[125,67,15,15],.4,colors=skin,yaw=-.12),
            ellipse("neck",[124,83,5,6],.4,colors=skin),
            ellipse("near-hand",[80,142,6,8],.5,colors=skin),
            ellipse("far-hand",[172,151,6,8],.5,colors=skin)]
        for name,coords in [("near-jade-leaf",[157,55,3,5]),("far-jade-leaf",[102,52,3,4]),
            ("waist-jade-a",[115,138,2,3]),("waist-jade-b",[120,143,2,3]),("waist-jade-c",[125,139,2,3])]:
            shapes.append(ellipse(name,coords,.4,colors=jade))
        for name,coords in [("near-hair-cuff",[152,43,5,6]),("far-hair-cuff",[120,32,6,4]),
            ("cape-brooch",[121,93,4,4]),("strap-buckle",[113,113,3,3]),
            ("near-wrist",[89,130,5,4]),("far-wrist",[166,142,5,4]),
            ("waist-ornament",[121,129,9,4]),("near-boot-buckle",[112,223,4,4]),
            ("far-boot-buckle",[158,209,4,4])]:
            shapes.append(ellipse(name,coords,.55,colors=metal,metallic=True))
        for i,x in enumerate([115,120,125]):
            shapes.append(tube(f"waist-pendant-{i}",[[x,131],[x,142]],2,.5,colors=metal,metallic=True))
        return shapes
    if direction == "up":
        shapes = [dict(id="cloth-base", kind="plane", points=[[1,1],[254,1],[254,254],[1,254]], normal=[0,0,1])]
        shapes += [ellipse("back-skirt",[126,153,43,34],.36),
            tube("back-left-pleat",[[112,120],[105,153],[98,179]],8,.42),
            tube("back-middle-pleat",[[127,120],[127,154],[126,183]],8,.42),
            tube("back-right-pleat",[[141,123],[151,152],[155,177]],8,.42),
            tube("left-leg",[[116,180],[117,204],[119,224]],8,.5),
            ellipse("left-boot",[119,226,8,7],.45),
            tube("right-leg",[[134,182],[135,208],[138,233]],8,.5),
            ellipse("right-boot",[139,235,9,6],.45),
            ellipse("back-torso",[128,107,21,22],.36),
            tube("left-sleeve",[[97,110],[91,125],[85,136]],9,.45),
            tube("right-sleeve",[[155,111],[163,125],[168,138]],9,.45),
            ellipse("back-capelet",[127,95,30,16],.35),
            ellipse("satchel",[148,136,12,14],.45),
            tube("back-strap",[[113,84],[127,109],[145,133]],2.5,.35),
            ellipse("back-head-hair",[126,49,25,27],.5,colors=hair),
            tube("left-ponytail",[[99,29],[94,58],[81,84],[84,101]],10,.55,colors=hair),
            tube("right-ponytail",[[151,29],[157,59],[171,86],[170,103]],10,.55,colors=hair),
            ellipse("back-neck",[127,76,5,5],.4,colors=skin),
            ellipse("left-hand",[80,146,6,8],.5,colors=skin),
            ellipse("right-hand",[170,146,6,8],.5,colors=skin)]
        for name,coords in [("left-jade-leaf",[105,47,3,5]),("right-jade-leaf",[148,47,3,5])]:
            shapes.append(ellipse(name,coords,.4,colors=jade))
        for name,coords in [("left-hair-cuff",[111,34,5,5]),("right-hair-cuff",[142,34,5,5]),
            ("left-wrist",[84,133,5,4]),("right-wrist",[166,136,5,4]),
            ("back-strap-buckle",[125,105,3,3]),("satchel-clasp",[155,138,4,5]),
            ("left-boot-buckle",[117,216,4,4]),("right-boot-buckle",[141,216,4,4])]:
            shapes.append(ellipse(name,coords,.55,colors=metal,metallic=True))
        return shapes
    if direction != "right":
        raise ValueError("This seed currently records the reviewed right direction only")
    shapes = [dict(id="cloth-base", kind="plane", points=[[1,1],[254,1],[254,254],[1,254]], normal=[0,0,1])]
    shapes += [ellipse("skirt-volume",[129,151,34,33],.42),
        tube("skirt-left-pleat",[[117,119],[108,150],[97,173]],7,.45),
        tube("skirt-middle-pleat",[[127,121],[124,152],[119,181]],7,.48),
        tube("skirt-right-pleat",[[138,122],[143,151],[150,179]],7,.45),
        tube("far-leg",[[112,182],[104,205],[96,222]],6,.55),
        ellipse("far-boot",[96,224,8,7],.5),
        tube("near-leg",[[139,185],[151,209],[163,230]],7,.55),
        ellipse("near-boot",[168,232,14,6],.5),
        ellipse("torso",[131,110,15,19],.42),
        tube("near-sleeve",[[115,107],[104,122],[94,137]],8,.5),
        tube("far-sleeve",[[148,106],[159,123],[167,138]],6,.5),
        ellipse("capelet",[132,98,25,14],.4),
        ellipse("satchel",[106,135,13,15],.5),
        tube("strap",[[140,87],[127,108],[108,129]],2.5,.35),
        ellipse("head-hair",[127,52,24,28],.55,colors=hair),
        tube("near-ponytail",[[107,30],[99,58],[84,78],[75,97]],9,.6,colors=hair),
        tube("far-ponytail",[[141,32],[148,57],[154,81],[166,94]],6,.6,colors=hair),
        ellipse("face",[136,67,12,13],.5,colors=skin,yaw=.12),
        ellipse("neck",[137,83,4,7],.45,colors=skin),
        ellipse("near-hand",[87,149,5,8],.55,colors=skin),
        ellipse("far-hand",[175,148,5,6],.55,colors=skin)]
    for name,coords in [("near-jade-leaf",[106,43,2,4]),("far-jade-leaf",[149,58,2,3]),
        ("waist-jade-a",[129,132,2,3]),("waist-jade-b",[133,137,2,3]),("waist-jade-c",[137,134,2,3])]:
        shapes.append(ellipse(name,coords,.5,colors=jade))
    for name,coords in [("near-hair-cuff",[107,33,3.5,6]),("far-hair-cuff",[142,34,3,3]),
        ("cape-brooch",[141,89,3.5,4]),("strap-buckle",[130,106,3,3]),
        ("near-wrist-cuff",[92,136,5,3]),("far-wrist-cuff",[169,137,4,3]),
        ("satchel-clasp",[103,138,3,4]),("waist-ornament",[132,125,8,3]),
        ("far-boot-buckle",[96,210,3,3]),("near-boot-buckle",[158,219,3,3])]:
        shapes.append(ellipse(name,coords,.6,colors=metal,metallic=True))
    for i,x in enumerate([129,133,137]):
        shapes.append(tube(f"waist-pendant-{i}",[[x,127],[x,137]],2,.6,colors=metal,metallic=True))
    return shapes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("animation",type=Path)
    parser.add_argument("--direction",choices=["down","up","left","right"],required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError("Authored geometry exists; choose a new revision")
    manifest=json.loads((args.animation/"animation.json").read_text())
    colors=[np.asarray(Image.open(args.animation/f["path"]).convert("RGBA")) for f in manifest["frames"]]
    initial=seed(args.direction,manifest["palette_rgb"])
    forward,backward=geometry.optical_flow(colors)
    transported=normals.transport({0:initial},forward,backward)
    keys=sorted(set([0,len(colors)//4,len(colors)//2,3*len(colors)//4,len(colors)-1]))
    data=dict(schema_version=1,direction=args.direction,method="authored semantic frame-0 seed, cyclic bidirectional correspondence; review and correct keyposes",
        guide_policy="clay guide is an interpretation aid only; no guide pixels or diffuse height inference",
        keyframes={i:transported[i] for i in keys})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(yaml.safe_dump(data,sort_keys=False))
    print("Saved",len(keys),"editable pose anchors",len(initial),"semantic volumes")


if __name__=="__main__":main()
