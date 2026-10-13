"""Reduce broad curvature; separate articulated surfaces with editable vector layers.
The authoring bias is applied into painted layers, not an implicit geometry field.
"""
import argparse,json,copy,shutil
from pathlib import Path
import numpy as np
from PIL import Image
from h3_character_studio import core,geometry,normals

def adjustment(ident,side):
    factor=1.0;bias=[0.,0.,0.]
    if ident=='textile-envelope':factor=.45;bias=[side*.10,0,0]
    elif ident=='cape-surface':factor=.45;bias=[side*.12,.08,0]
    elif ident=='skirt-surface':factor=.45;bias=[side*.05,-.04,0]
    elif ident=='head-hair':factor=.45;bias=[side*.04,.02,0]
    elif ident in ['near-ponytail','far-ponytail']:factor=.45;bias=[side*(.12 if ident.startswith('near') else -.10),-.02,0]
    elif ident.startswith('crown-strand-'):factor=.6;bias=[(int(ident.rsplit('-',1)[1])-2)*.045,.025,0]
    elif 'ponytail-strand' in ident:factor=.65;bias=[side*(.08 if ident.startswith('near') else -.08),0,0]
    elif ident.startswith('skirt-fold-'):factor=.6;bias=[(int(ident.rsplit('-',1)[1])-2)*.055,-.025,0]
    elif ident.startswith('cape-drape-'):factor=.65;bias=[side*.04,.03,0]
    elif 'sleeve' in ident:factor=.55;bias=[side*(.20 if 'near' in ident else -.14),.025,0]
    elif 'hand' in ident:factor=.55;bias=[side*(.10 if 'near' in ident else -.10),-.03,0]
    elif ident in ['far-leg','near-leg'] or 'calf-correction' in ident:factor=.7;bias=[side*(.08 if 'near' in ident else -.08),0,0]
    elif ident=='face':factor=.72
    return factor,bias

def refine(bundle,output,materials_root=None):
    output.mkdir(parents=True,exist_ok=False)
    records={}
    for direction in ['down','up','left','right']:
        source=bundle/'normals'/direction
        annotations=Path(materials_root)/direction if materials_root else source/'material-annotations'
        if not annotations.is_dir():raise ValueError('Review source-bound per-frame materials before refining: '+direction)
        painted=output/(direction+'-layers');painted.mkdir()
        side=-1 if direction=='left' else 1
        data=json.loads((source/'manifest.json').read_text());changes=[]
        rendered_annotations=output/(direction+'-materials');rendered_annotations.mkdir()
        for i in range(len(data['frames'])):
            src=source/'editable'/f'{i:05d}';dst=painted/f'{i:05d}';dst.mkdir()
            shapes=copy.deepcopy(json.loads((src/'geometry.json').read_text())['shapes']);biases=[]
            for shape in shapes:
                factor,bias=adjustment(shape['id'],side) if not shape.get('metallic') else (1,[0,0,0])
                if 'slope' in shape:shape['slope']*=factor
                biases.append(bias)
            annotation=json.loads((annotations/f'{i:05d}.json').read_text())
            names={s['id'] for s in shapes}
            if any(points for name,points in annotation['regions'].items() if name not in names):raise ValueError('Retained geometry lost an owned ornament')
            annotation['regions']={name:points for name,points in annotation['regions'].items() if name in names}
            core.write_json(rendered_annotations/f'{i:05d}.json',annotation)
            color=np.asarray(Image.open(bundle/'character'/direction/'frames'/f'{i:05d}.png').convert('RGBA'))
            vectors,labels,metal=normals.render(color,shapes)
            # All coverage and ornaments remain identical to the reviewed v6.
            expected=np.asarray(Image.open(src/'labels.png'));assert np.array_equal(labels,expected)
            for idx,(shape,bias) in enumerate(zip(shapes,biases),1):
                n=geometry.unit(vectors+np.asarray(bias,dtype=np.float32))
                if shape.get('metallic'):
                    original=np.asarray(Image.open(src/(shape['id']+'.png')).convert('RGBA'))
                    Image.fromarray(original).save(dst/(shape['id']+'.png'))
                else:
                    Image.fromarray(normals.encoded(n,np.where(labels==idx,color[...,3],0).astype(np.uint8))).save(dst/(shape['id']+'.png'))
            core.write_json(dst/'geometry.json',dict(frame=i,shapes=shapes))
            core.write_json(dst/'surface-orientations.json',dict(frame=i,shapes={s['id']:dict(curvature_factor=adjustment(s['id'],side)[0],painted_vector_bias=b) for s,b in zip(shapes,biases) if not s.get('metallic')}))
        target=output/direction
        normals.build(bundle/'character'/direction,source/'geometry.yaml',target,painted_layers=painted,material_annotations=rendered_annotations)
        for record in painted.glob('*/surface-orientations.json'):
            shutil.copy2(record,target/'editable'/record.parent.name/record.name)
        records[direction]=normals.verify(bundle/'character'/direction,target)
        for i in range(len(data['frames'])):
            old=np.asarray(Image.open(source/'masks'/f'{i:05d}.png'))
            new=np.asarray(Image.open(target/'masks'/f'{i:05d}.png'));assert np.array_equal(old,new)
            metal=old[...,0]>127
            before=np.asarray(Image.open(source/'frames'/f'{i:05d}.png'))[..., :3].astype(np.float32)/127.5-1
            after=np.asarray(Image.open(target/'frames'/f'{i:05d}.png'))[..., :3].astype(np.float32)/127.5-1
            angle=np.degrees(np.arccos(np.clip((geometry.unit(before)[metal]*geometry.unit(after)[metal]).sum(-1),-1,1)))
            assert not len(angle) or angle.max()<1.0
    core.write_json(output/'validation.json',dict(directions=records,metal_coverage_unchanged=True,metal_vector_angle_max_degrees=1,source_color_unchanged=True,large_volume_boost=False,artistic_approval='pending'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('bundle',type=Path);p.add_argument('output',type=Path);p.add_argument('--materials-root',type=Path);a=p.parse_args();refine(a.bundle,a.output,a.materials_root)
