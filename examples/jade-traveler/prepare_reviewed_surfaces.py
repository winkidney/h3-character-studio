"""Propose source-bound face/neck and silver pixel ownership for visual review.

Proposal files are deliberately not approved. Review every frame overlay before
changing review_status. No convex hull may silently flood other body surfaces.
"""
import argparse,copy,json
from pathlib import Path
import cv2,numpy as np
from PIL import Image
from h3_character_studio import core,geometry,normals,materials

def skin_pixels(color):
    r,g,b=np.moveaxis(color[...,:3].astype(int),2,0)
    return (color[...,3]>0)&(r>140)&(r-g>18)&(g-b>5)&(g>75)

def propose(animation,retained,direction,output):
    output.mkdir(parents=True,exist_ok=False);(output/'materials').mkdir();(output/'geometry').mkdir()
    data=json.loads((animation/'animation.json').read_text());poses=[]
    for i,row in enumerate(data['frames']):
        color=np.asarray(Image.open(animation/row['path']).convert('RGBA'))
        src=retained/'editable'/f'{i:05d}';shapes=copy.deepcopy(json.loads((src/'geometry.json').read_text())['shapes'])
        # Connected neutral-color islands do not establish jewelry identity.
        shapes=[s for s in shapes if not s['id'].startswith('silver-island') and s['id']!='nose-volume']
        skin=skin_pixels(color);face=next((s for s in shapes if s['id']=='face'),None)
        if face:
            fx,fy,rx,ry=face['ellipse']
            cap=int(round(fy+ry*.36))
            frontal=skin&(geometry.YY>=55)&(geometry.YY<=cap)
            frontal&=(geometry.XX>=fx+2) if direction=='right' else ((geometry.XX<=fx-2) if direction=='left' else (abs(geometry.XX-fx)<8))
            yy,xx=np.where(frontal);jaw=int(yy.max()) if len(yy) else int(fy+ry*.65)
            own=skin&normals.polygon(face.get('surface_region',[[fx-rx,fy-ry],[fx+rx,fy-ry],[fx+rx,fy+ry],[fx-rx,fy+ry]]))&(geometry.YY<=jaw)
            # Include ink/eyes only inside the actual eyes band. Other visible
            # hair, cloth and holes never inherit the cheek surface by a hull.
            eye_band=(geometry.YY>=jaw-17)&(geometry.YY<=jaw-10)&(abs(geometry.XX-fx)<rx*.85)&(color[...,3]>0)
            eye_band&=(color[...,:3].max(-1)-color[...,:3].min(-1)<45)&(color[...,1]>140)
            own|=eye_band
            yy,xx=np.where(own);face['pixel_region']=np.stack([xx,yy],-1).tolist()
            face['points']=[[1,1],[254,1],[254,254],[1,254]]
            face['kind']='plane';face['normal']=[.14 if direction=='right' else (-.14 if direction=='left' else .04),.025,1]
            for k in ['surface_region','palette_colors','clip_polygon','slope']:face.pop(k,None)
            poses.append(dict(frame=i,jaw_bottom=jaw,face_pixels=int(own.sum()),nose_volume=False))
            neck=next((s for s in shapes if s['id']=='neck'),None)
            if neck:
                side=-1 if direction=='right' else (1 if direction=='left' else 0)
                neck_x=fx+side*4
                rgb=color[...,:3].astype(int)
                warm=(rgb[...,0]-rgb[...,1]>30)&(rgb[...,0]-rgb[...,2]>60)
                nc=skin&warm&~own&(geometry.YY>jaw)&(geometry.YY<=jaw+10)&(abs(geometry.XX-neck_x)<=4)
                ny,nx=np.where(nc)
                if not len(nx):
                    shapes.remove(neck)
                    neck=None
                if neck is not None:neck['pixel_region']=np.stack([nx,ny],-1).tolist()
                if neck is not None:neck['points']=[[1,1],[254,1],[254,254],[1,254]];neck['kind']='plane';neck['normal']=[.08 if direction=='right' else (-.08 if direction=='left' else .025),-.05,1]
                if neck is not None:
                    for k in ['palette_colors','surface_region','clip_polygon','slope']:neck.pop(k,None)
        body=[s for s in shapes if not s.get('metallic')]
        _,body_labels,_=normals.render(color,body)
        protected={};surfaces={}
        for idx,shape in enumerate(body,1):
            ident=shape['id']
            if ident in ['face','neck','back-neck'] or 'hand' in ident:
                # An arm envelope is not a skin annotation. Only actual warm
                # skin pixels are reserved, except the explicitly owned face.
                mask=(body_labels==idx)&(skin if ident!='face' else True)
                y,x=np.where(mask);protected[ident]=np.stack([x,y],-1).tolist()
                if ident in ['face','neck','back-neck']:surfaces[ident]=protected[ident]
        reserved=np.zeros((256,256),bool)
        for v in protected.values():reserved|=materials.pixels(v)
        regions={};used=np.zeros((256,256),bool)
        for shape in shapes:
            if not shape.get('metallic'):continue
            _,_,proposal=normals.render(color,[shape])
            rgb=color[...,:3].astype(int);neutral=(rgb.max(-1)-rgb.min(-1)<40)&(rgb[...,0]>105)
            proposal&=~reserved&~used&neutral
            used|=proposal;y,x=np.where(proposal);regions[shape['id']]=np.stack([x,y],-1).tolist()
        core.write_json(output/'materials'/f'{i:05d}.json',dict(schema_version=1,frame=i,source_sha256=row['sha256'],
            review_status='proposal',reviewed_by=None,regions=regions,protected_regions=protected,surface_regions=surfaces,
            annotation_method='per-frame exact pixels, proposal from retained named ornament geometry; requires visual review'))
        core.write_json(output/'geometry'/f'{i:05d}/geometry.json',dict(frame=i,shapes=shapes))
        overlay=color.copy();overlay[used,:3]=[0,225,255];overlay[reserved,:3]=(overlay[reserved,:3].astype(float)*.65+[89,0,0]).clip(0,255).astype(np.uint8)
        Image.fromarray(overlay).save(output/f'{i:05d}-overlay.png')
    core.write_json(output/'surface-review.json',dict(direction=direction,frames=poses,source_animation_sha256=core.digest(animation/'animation.json'),status='proposal'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('animation',type=Path);p.add_argument('retained_normals',type=Path);p.add_argument('--direction',required=True,choices=['down','up','left','right']);p.add_argument('--output',required=True,type=Path);a=p.parse_args();propose(a.animation,a.retained_normals,a.direction,a.output)
