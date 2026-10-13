"""Derive optional shader response masks from reviewed per-frame semantic geometry.
R: hair, G: cloth, B: waist silver. Source color, normal and metal maps are immutable.
"""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image
from h3_character_studio import normals,core

def build(bundle,destination):
    destination.mkdir(parents=True,exist_ok=False)
    report={}
    for direction in ['down','up','left','right']:
        normal_root=bundle/'normals'/direction
        data=json.loads((normal_root/'manifest.json').read_text())
        target=destination/direction;target.mkdir()
        atlas_size=Image.open(normal_root/'atlas.png').size
        atlas=Image.new('RGBA',atlas_size)
        records=[]
        for i,frame in enumerate(data['frames']):
            edit=normal_root/'editable'/f'{i:05d}'
            shapes=json.loads((edit/'geometry.json').read_text())['shapes']
            labels=np.asarray(Image.open(edit/'labels.png'))
            color=np.asarray(Image.open(bundle/'character'/direction/'frames'/f'{i:05d}.png').convert('RGBA'))
            metal=np.asarray(Image.open(normal_root/'masks'/f'{i:05d}.png').convert('RGBA'))[...,0]>127
            response=np.zeros((256,256,4),np.uint8);response[...,3]=color[...,3]
            for idx,shape in enumerate(shapes,1):
                ident=shape['id']
                if shape.get('fallback') or shape.get('metallic'):continue
                if any(key in ident for key in ['hair','ponytail','crown-strand']):response[...,0][labels==idx]=255
                elif any(key in ident for key in ['textile','skirt','pleat','cape','sleeve']):response[...,1][labels==idx]=255
            # Recover reviewed waist coverage even where small metal islands
            # overwrite semantic labels. Intersect with the final silver mask.
            waist=[s for s in shapes if s['id'].startswith('waist-') and s.get('metallic')]
            if waist:
                _,_,coverage=normals.render(color,waist)
                response[...,2][(coverage>0)&metal]=255
            assert not np.any((response[...,:2]>0)&metal[...,None])
            assert not np.any((response[...,2]>0)&~metal)
            im=Image.fromarray(response);path=target/f'{i:05d}.png';im.save(path)
            x,y,w,h=frame['region'];assert (w,h)==(256,256)
            atlas.paste(im,(x,y))
            records.append(dict(frame=i,region=frame['region'],hair_pixels=int((response[...,0]>0).sum()),cloth_pixels=int((response[...,1]>0).sum()),waist_pixels=int((response[...,2]>0).sum())))
        atlas.save(target/'atlas.png');report[direction]=dict(frames=records,atlas_sha256=core.digest(target/'atlas.png'))
    (destination/'manifest.json').write_text(json.dumps(dict(channels=['hair','cloth','waist-silver','source-alpha'],directions=report,source_colors_changed=False),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bundle',type=Path);p.add_argument('output',type=Path);a=p.parse_args();build(a.bundle,a.output)
