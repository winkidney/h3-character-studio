"""Redraw garment volumes with reviewed pose landmarks and per-frame geometry.

Run against a retained original normal revision. Six authored garment poses per
view are independent annotations of the selected source frames. Bidirectional
flow interpolates their shape coordinates and parameters; it does not infer
height from color. Existing boots/skin/hair/jewelry rigs are retained. Every
output frame has its own editable geometry and a correction record.
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np
import cv2
from PIL import Image
import yaml
from h3_character_studio import core, geometry, normals

KEYS = [0, 6, 11, 13, 20, 26]
# The side-view foreground hand crosses the torso during the walk. These
# visible-pose annotations replace the drifting old sleeve/hand correspondence.
HANDS = {
    "right": [[86,150],[106,151],[130,151],[134,149],[119,152],[86,150]],
    "left": [[171,149],[148,150],[122,150],[115,149],[103,146],[170,150]],
}
# waist, five visible hem landmarks, cape center/radii, fold curvature.
# These are 256px source coordinates, not positions copied from the red actor.
POSES = {
    "right": [
        ([130,122], [[86,169],[102,183],[121,186],[141,185],[153,178]], [132,98,26,15], .56),
        ([130,118], [[83,165],[101,179],[120,182],[141,180],[153,173]], [133,94,25,14], .52),
        ([132,119], [[85,167],[105,181],[125,184],[146,181],[156,174]], [134,95,24,15], .50),
        ([132,124], [[87,173],[105,187],[126,190],[147,187],[156,181]], [134,100,25,14], .55),
        ([130,119], [[84,167],[102,181],[122,184],[143,182],[154,175]], [133,95,25,15], .58),
        ([130,122], [[86,170],[103,183],[122,187],[142,185],[154,178]], [132,98,26,15], .56),
    ],
    "left": [
        ([123,121], [[94,174],[108,186],[128,189],[149,183],[164,174]], [128,98,27,15], .56),
        ([123,117], [[93,169],[110,180],[130,183],[150,179],[165,171]], [128,94,26,14], .51),
        ([124,119], [[94,173],[112,182],[132,185],[152,181],[170,172]], [129,96,26,15], .53),
        ([124,123], [[95,176],[112,187],[134,190],[154,185],[172,175]], [129,100,26,15], .58),
        ([123,118], [[93,170],[110,182],[130,185],[152,180],[167,172]], [128,95,26,14], .54),
        ([123,121], [[94,174],[109,186],[129,189],[150,183],[165,174]], [128,98,27,15], .56),
    ],
    "down": [
        ([128,121], [[94,175],[110,186],[129,188],[146,184],[161,174]], [127,98,30,15], .56),
        ([129,117], [[95,168],[111,180],[130,182],[148,179],[162,169]], [128,94,29,15], .52),
        ([129,119], [[94,172],[111,183],[130,185],[148,181],[163,172]], [128,96,30,15], .53),
        ([128,123], [[93,175],[110,187],[128,190],[146,186],[161,175]], [127,100,30,15], .58),
        ([128,118], [[94,170],[110,182],[129,184],[146,182],[160,171]], [127,95,29,14], .54),
        ([128,121], [[94,175],[110,186],[129,188],[146,184],[161,174]], [127,98,30,15], .56),
    ],
    "up": [
        ([126,121], [[88,176],[107,187],[125,191],[146,186],[164,175]], [126,98,30,16], .56),
        ([125,116], [[88,168],[105,179],[124,182],[145,178],[160,167]], [125,93,29,15], .52),
        ([127,119], [[91,171],[109,183],[128,185],[148,181],[165,171]], [127,96,29,15], .54),
        ([126,123], [[89,176],[107,187],[128,191],[149,186],[167,175]], [126,100,29,16], .58),
        ([125,118], [[89,170],[106,182],[126,184],[147,180],[163,169]], [125,95,29,15], .53),
        ([126,121], [[89,176],[108,187],[126,191],[147,186],[165,175]], [126,98,30,16], .56),
    ],
}


def ellipsoid(name, spec, slope, region, **kwargs):
    return dict(id=name, kind="ellipsoid", ellipse=spec, slope=slope,
                surface_region=region, **kwargs)


def garments(pose, direction, key_index, skin):
    waist, hem, cape, slope = pose
    wx, wy = waist
    skirt_region = [[hem[0][0]-8,wy-2],[hem[-1][0]+8,wy-2],
                    [hem[-1][0]+12,198],[hem[0][0]-12,198]]
    cx,cy,rx,ry=cape
    # This field covers the authored visible cloth region even where an ellipse
    # alone would end. Later skin/hair/bag/metal surfaces resolve occlusions.
    out=[ellipsoid("textile-envelope", [wx,wy-4,23,29], .34,
                   [[78,76],[180,76],[180,199],[78,199]], yaw=.06 if direction=="right" else -.06),
         ellipsoid("skirt-surface", [wx,(wy+max(p[1] for p in hem))/2,42,36], .48, skirt_region)]
    for i,(hx,hy) in enumerate(hem):
        root=[wx+(i-2)*5,wy+3+abs(i-2)]
        middle=[root[0]*.43+hx*.57,wy+(hy-wy)*.57]
        out.append(dict(id=f"skirt-fold-{i}",kind="tube",points=[root,middle,[hx,hy]],
                        radius=5.0+(.5 if i==2 else 0),slope=slope,clip_polygon=skirt_region))
    # A broad convex cape plus three thin, concave drape folds. Their positions
    # follow the neck/shoulder form; no albedo brightness becomes geometry.
    cape_region=[[cx-rx-5,cy-ry-7],[cx+rx+5,cy-ry-7],
                 [cx+rx+5,cy+ry+3],[cx-rx-5,cy+ry+3]]
    out.append(ellipsoid("cape-surface",cape,.44,cape_region,yaw=.07 if direction=="right" else -.07))
    for i,sign in enumerate([-1,0,1]):
        root=[cx+sign*3,cy-ry+1]
        end=[cx+sign*(rx*.78),cy+ry*.70]
        middle=[cx+sign*(rx*.36),cy+ry*.12]
        out.append(dict(id=f"cape-drape-{i}",kind="tube",points=[root,middle,end],radius=2.2,
                        slope=-.34 if i==1 else -.42,clip_polygon=cape_region))
    # Hem rolls across all panels. Thin embroidered colors retain cloth normals.
    out.append(dict(id="skirt-rolled-hem",kind="tube",points=hem,radius=2.0,slope=.36,
                    clip_polygon=skirt_region))
    if direction in HANDS:
        hx,hy=HANDS[direction][key_index]
        shoulder=[cx-17 if direction=="right" else cx+16,cy+12]
        elbow=[shoulder[0]*.4+hx*.6,hy-25]
        wrist=[hx,hy-12]
        out.append(dict(id="pose-near-sleeve",kind="tube",points=[shoulder,elbow,wrist],
                        radius=7.5,slope=.56))
        out.append(dict(id="pose-near-hand",kind="ellipsoid",ellipse=[hx,hy,6.5,8],
                        slope=.55,palette_colors=skin))
    return out


def refine_precision(shapes, color, direction):
    """Match the red actor's strand/face/island detail and local corrections.

    Material identity and bounded visible silhouettes locate regions. They do
    not set vector slopes, which remain independently authored geometry.
    """
    records=[]
    head=next(s for s in shapes if s['id'] in ['head-hair','back-head-hair'])
    cx,cy,rx,ry=head['ellipse']
    head['surface_region']=[[cx-rx*1.35,cy-ry*1.4],[cx+rx*1.35,cy-ry*1.4],
                            [cx+rx*1.35,cy+ry*1.2],[cx-rx*1.35,cy+ry*1.2]]
    hair_colors=[c for c in head['palette_colors'] if c[0]>=c[1] or max(c)<30]
    head['palette_colors']=hair_colors
    strands=[]
    paths=[[[cx-rx*.9,cy],[cx-rx*.55,cy-ry*.65],[cx,cy-ry*.85]],
           [[cx-rx*.45,cy-ry*.65],[cx-rx*.2,cy-ry*.1],[cx-rx*.28,cy+ry*.6]],
           [[cx,cy-ry*.8],[cx+rx*.35,cy-ry*.45],[cx+rx*.6,cy+ry*.25]],
           [[cx+rx*.45,cy-ry*.7],[cx+rx*.85,cy-ry*.1],[cx+rx*.88,cy+ry*.6]],
           [[cx-rx*.8,cy-ry*.15],[cx-rx*.65,cy+ry*.4],[cx-rx*.8,cy+ry*.8]]]
    for i,line in enumerate(paths):
        strands.append(dict(id=f'crown-strand-{i}',kind='tube',points=line,radius=4.0,
                            slope=.45,palette_colors=hair_colors,clip_polygon=head['surface_region']))
    insert=shapes.index(head)+1
    shapes[insert:insert]=strands
    # Twin ponytails remain smooth loose hair. Never introduce braid beads.
    for pony in list(shapes):
        if 'ponytail' not in pony['id']:continue
        pony['radius']+=1.5
        pony['palette_colors']=hair_colors
        for j,offset in enumerate([-2.0,2.0]):
            line=[[x+offset,y] for x,y in pony['points']]
            shapes.insert(shapes.index(pony)+1,dict(id=pony['id']+f'-strand-{j}',kind='tube',
                points=line,radius=2.7,slope=.4,palette_colors=hair_colors))
    face=next((s for s in shapes if s['id']=='face'),None)
    visible=color[...,3]>0
    r,g,b=np.moveaxis(color[...,:3].astype(float),2,0)
    identity=visible&(r>140)&(r-g>18)&(g-b>3)&(g>75)
    skin_regions=np.zeros((256,256),bool)
    for shape in shapes:
        if shape['id'] in ['face','neck','back-neck','near-hand','far-hand','left-hand','right-hand','pose-near-hand']:
            skin_regions|=geometry.ellipse_region(shape['ellipse'],1.15)
    if face:
        # Skin-color connected components include neck/cape pixels. Retain the
        # bounded authored face proposal; final facial coverage must come from
        # reviewed per-frame surface ownership. Never add a guessed nose block.
        records.append(dict(feature='face',method='authored proposal; explicit per-frame facial ownership required',nose_volume=False))
    # Follow the re-annotated foreground wrist instead of a stale torso ROI.
    hand=next((s for s in shapes if s['id']=='pose-near-hand'),None)
    cuff=next((s for s in shapes if s['id']=='near-wrist-cuff'),None)
    if hand and cuff:
        hx,hy,_,_=hand['ellipse'];cuff['ellipse'][:2]=[hx,hy-14]
    jade=[s['palette_colors'] for s in shapes if 'jade' in s['id'] and s.get('palette_colors')]
    jade_colors={tuple(c) for group in jade for c in group}
    jade_mask=np.zeros((256,256),bool)
    for c in jade_colors:jade_mask|=(color[...,:3]==c).all(-1)
    silver_identity=visible&((np.maximum.reduce([r,g,b])-np.minimum.reduce([r,g,b]))<48)&(r>108)&~(identity&skin_regions)&~jade_mask
    for shape in shapes:
        if not shape.get('metallic'):continue
        spec=shape['ellipse'] if shape['kind']=='ellipsoid' else None
        if spec is None:continue
        target=silver_identity&geometry.ellipse_region(spec,1.2)
        yy,xx=np.where(target)
        if len(xx)>=3:
            before=spec[:2].copy();shift=np.clip(np.array([np.median(xx),np.median(yy)])-spec[:2],-3,3)
            spec[:2]=(np.array(spec[:2])+shift).round(4).tolist()
            shape['pixel_region']=np.stack([xx,yy],axis=-1).tolist()
            shape.pop('palette_colors',None)
            records.append(dict(feature=shape['id'],before=before,after=spec[:2],pixels=len(xx),method='bounded visible jewelry correction'))
    # Render exact selected material, then give each small silver island its
    # own convex surface. The mask is binary material data, not normal strength.
    _,_,metal=normals.render(color,shapes)
    count,islands,stats,_=cv2.connectedComponentsWithStats(metal.astype(np.uint8),8)
    for i in range(1,count):
        x,y,w,h,area=map(int,stats[i])
        if area<3 or w>16 or h>20:continue
        yy,xx=np.where(islands==i)
        shapes.append(dict(id=f'silver-island-{i}',kind='ellipsoid',
            ellipse=[x+(w-1)/2,y+(h-1)/2,max(2,w*.65),max(2,h*.6)],slope=.68,
            metallic=True,pixel_region=np.stack([xx,yy],axis=-1).tolist()))
    records.append(dict(feature='detail',crown_strands=5,ponytail_substrands=4,metal_islands=count-1,
                        method='separate geometry surfaces and exact semantic regions; no luminance height'))
    return records


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("animation",type=Path)
    p.add_argument("retained_normals",type=Path)
    p.add_argument("--direction",choices=list(POSES),required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): raise ValueError("Choose a new redraw revision")
    normals.verify(a.animation,a.retained_normals)
    manifest=json.loads((a.animation/"animation.json").read_text())
    colors=[np.asarray(Image.open(a.animation/r['path']).convert('RGBA')) for r in manifest['frames']]
    if len(colors)!=27: raise ValueError("This authored example expects the reviewed27-frame clips")
    original=[json.loads((a.retained_normals/'editable'/f'{i:05d}'/'geometry.json').read_text())['shapes'] for i in range(27)]
    skin=next(s['palette_colors'] for s in original[0] if s['id'] in ['near-hand','left-hand'])
    keys={k:garments(pose,a.direction,j,skin) for j,(k,pose) in enumerate(zip(KEYS,POSES[a.direction]))}
    forward,backward=geometry.optical_flow(colors)
    tracked=normals.transport(keys,forward,backward)
    a.output.mkdir(parents=True)
    newkeys={}
    corrections=[]
    old_cloth={'skirt-volume','skirt-left-pleat','skirt-middle-pleat','skirt-right-pleat',
               'back-skirt','back-left-pleat','back-middle-pleat','back-right-pleat','torso','back-torso',
               'capelet','capelet-left','capelet-right','back-capelet'}
    if a.direction in HANDS: old_cloth.update(['near-sleeve','near-hand'])
    for i,(shapes,cloth,color) in enumerate(zip(original,tracked,colors)):
        shapes=copy.deepcopy(shapes)
        for shape in shapes:
            if shape['id']=='cloth-base': shape['fallback']=True
            if shape['id'] in ['near-sleeve','far-sleeve','left-sleeve','right-sleeve']:
                shape['slope']=.56
                shape['radius']=float(shape['radius'])+.8
        shapes=[s for s in shapes if s['id'] not in old_cloth]
        # Keep the retained per-frame boots, skin, hair and ornaments above cloth.
        shapes[1:1]=cloth
        precision_records=refine_precision(shapes,color,a.direction)
        vectors,labels,metal=normals.render(color,shapes)
        old_mask=np.asarray(Image.open(a.retained_normals/'masks'/f'{i:05d}.png'))[...,0]>0
        correction=dict(frame=i,source_raw_frame=manifest['frames'][i]['source']['raw_frame'],
                        authored_keypose=i in keys,method='six garment annotations; bidirectional shape and parameter interpolation; retained per-frame non-cloth geometry')
        correction.update(precision_corrections=precision_records,
                          metal_pixels_added=int((metal&~old_mask).sum()),metal_pixels_removed=int((old_mask&~metal).sum()))
        core.write_json(a.output/'edits'/f'{i:05d}'/'geometry.json',dict(frame=i,shapes=shapes,correction=correction))
        corrections.append(correction)
        if i in keys:newkeys[i]=shapes
    (a.output/'geometry.yaml').write_text(yaml.safe_dump(dict(schema_version=1,direction=a.direction,
        method='precision-redraw-v6: six garment poses, strand surfaces, corrected cheek and fine metal islands',
        keyframes=newkeys),sort_keys=False))
    core.write_json(a.output/'corrections.json',corrections)
    print('Redrew',a.direction,len(colors),'paired poses with precision corrections; immutable color')


if __name__=='__main__':main()
