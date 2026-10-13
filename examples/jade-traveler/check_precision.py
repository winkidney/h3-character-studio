"""Check frame pairing and material-interior temporal vectors, as for the red actor.

The measured thresholds are production review gates, not an artistic accuracy
score. Label stability, reciprocal flow consistency and one-pixel erosion keep
newly exposed boundaries out of the temporal measurement.
"""
import argparse,json
from pathlib import Path
import cv2,numpy as np
from PIL import Image
from h3_character_studio import core,geometry,normals


def family(shape):
    ident=shape['id']
    if shape.get('fallback'): return 0
    if shape.get('metallic'): return 6
    if 'ponytail' in ident: return 3
    if 'hair' in ident or 'crown-strand' in ident: return 2
    if ident in ['face','neck','back-neck','nose-volume'] or 'hand' in ident: return 1
    if 'skirt' in ident or 'pleat' in ident: return 5
    if any(s in ident for s in ['-leg','-boot','calf-correction','foot-correction']):return 7
    return 4


def check(animation,normal_root):
    paired=normals.verify(animation,normal_root)
    data=json.loads((animation/'animation.json').read_text())
    colors=[];vectors=[];labels=[]
    for i,row in enumerate(data['frames']):
        color=np.asarray(Image.open(animation/row['path']).convert('RGBA'))
        normal=np.asarray(Image.open(normal_root/'frames'/f'{i:05d}.png').convert('RGBA'))
        raw=np.asarray(Image.open(normal_root/'editable'/f'{i:05d}/labels.png'))
        shapes=json.loads((normal_root/'editable'/f'{i:05d}/geometry.json').read_text())['shapes']
        lookup=np.array([0]+[family(s) for s in shapes],dtype=np.uint8)
        colors.append(color);vectors.append(geometry.unit(normal[...,:3].astype(np.float32)/127.5-1));labels.append(lookup[raw])
    motion=np.load(normal_root/'motion.npz');forward=motion['forward'].astype(np.float32);backward=motion['backward'].astype(np.float32)
    rows=[]
    for i,flow in enumerate(forward):
        nxt=(i+1)%len(colors);mx=geometry.XX+flow[...,0];my=geometry.YY+flow[...,1]
        opposite=cv2.remap(backward[i],mx,my,cv2.INTER_LINEAR)
        consistent=np.linalg.norm(flow+opposite,axis=-1)<1.5
        alpha=cv2.remap(colors[nxt][...,3],mx,my,cv2.INTER_NEAREST)
        next_labels=cv2.remap(labels[nxt],mx,my,cv2.INTER_NEAREST)
        interior=(labels[i]==next_labels)&(labels[i]>0)&(alpha>127)&(colors[i][...,3]>127)&consistent
        interior=cv2.erode(interior.astype(np.uint8),np.ones((3,3),np.uint8))>0
        target=geometry.unit(cv2.remap(vectors[nxt],mx,my,cv2.INTER_LINEAR))
        angle=np.degrees(np.arccos(np.clip((vectors[i]*target).sum(-1),-1,1)))[interior]
        if len(angle)<400:raise ValueError('Insufficient reciprocal material-interior correspondence')
        rows.append(dict(frame=i,samples=len(angle),mean_degrees=float(angle.mean()),p95_degrees=float(np.quantile(angle,.95))))
    result=dict(pairing=paired,transitions=rows,loop_seam=rows[-1],
        max_transition_mean=max(r['mean_degrees'] for r in rows),
        method='same material family, reciprocal flow<1.5px,3x3 erosion, linear vector sampling; red actor method',
        artistic_approval='pending')
    result['passed']=result['max_transition_mean']<12 and result['loop_seam']['mean_degrees']<8
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('animation',type=Path);p.add_argument('normals',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=check(a.animation,a.normals);core.write_json(a.output,result)
    print(json.dumps({k:result[k] for k in ['passed','max_transition_mean','loop_seam','artistic_approval']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
