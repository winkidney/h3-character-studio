"""Frame-bound material ownership. Geometry transport only proposes materials."""
import copy,json
from pathlib import Path
import numpy as np
from . import core


def pixels(points):
    value=np.asarray(points,dtype=float)
    if value.size==0:return np.zeros((256,256),bool)
    if value.ndim!=2 or value.shape[1]!=2 or not np.isfinite(value).all() or np.any(value!=np.rint(value)) or np.any(value<0) or np.any(value>255):
        raise ValueError('Material annotation requires integer256px coordinates')
    value=value.astype(int);mask=np.zeros((256,256),bool);mask[value[:,1],value[:,0]]=True
    if int(mask.sum())!=len(value):raise ValueError('Duplicate material annotation pixels')
    return mask


def constrain(shapes,color,source_sha256,frame,annotations):
    """No material may overwrite an unowned or protected body pixel."""
    metals={s['id']:s for s in shapes if s.get('metallic')}
    facial=any(s['id']=='face' for s in shapes)
    if not metals and not facial and annotations is None:return copy.deepcopy(shapes),dict(frame=frame,metal_pixels=0,annotations_required=False)
    if annotations is None:raise ValueError('Silver requires explicit per-frame material annotations; transported geometry is a proposal')
    path=Path(annotations)/f'{frame:05d}.json'
    record=json.loads(path.read_text())
    if record.get('schema_version')!=1 or record.get('frame')!=frame or record.get('source_sha256')!=source_sha256:
        raise ValueError('Material annotation frame/source fingerprint mismatch')
    if record.get('review_status') not in ['agent-reviewed','user-approved'] or not record.get('reviewed_by'):
        raise ValueError('Material annotation has not been reviewed')
    regions=record.get('regions');protected=record.get('protected_regions')
    if not isinstance(regions,dict) or not isinstance(protected,dict):raise ValueError('Missing material/protected ownership regions')
    reserved=np.zeros((256,256),bool)
    for points in protected.values():reserved|=pixels(points)
    ownership=np.zeros((256,256),bool);out=[copy.deepcopy(s) for s in shapes if not s.get('metallic')]
    visible=color[...,3]>0
    surfaces=record.get('surface_regions',{})
    if facial and 'face' not in surfaces:raise ValueError('Face needs explicit per-frame ownership; skin convex hull is not an anatomical annotation')
    for shape in out:
        if shape['id'] in surfaces:
            owned=pixels(surfaces[shape['id']])
            if np.any(owned&~visible):raise ValueError('Body surface annotation covers transparent background')
            shape['pixel_region']=surfaces[shape['id']]
            for key in ['palette_colors','clip_polygon','surface_region']:shape.pop(key,None)
    for name,points in regions.items():
        if name not in metals:raise ValueError('Unknown annotated ornament '+name)
        mask=pixels(points)
        if np.any(mask&reserved):raise ValueError('Silver annotation overlaps protected body surface '+name)
        if np.any(mask&~visible):raise ValueError('Silver annotation covers transparent background '+name)
        if np.any(mask&ownership):raise ValueError('Two ornaments own the same pixel '+name)
        if not mask.any():continue
        ownership|=mask;shape=copy.deepcopy(metals[name]);shape['pixel_region']=points
        # Exact ownership is authoritative; old bounding/palette proposals must
        # neither expand nor silently clip an approved per-frame annotation.
        for key in ['palette_colors','clip_polygon','surface_region']:shape.pop(key,None)
        out.append(shape)
    return out,dict(frame=frame,source_sha256=source_sha256,annotation_sha256=core.digest(path),
                    review_status=record['review_status'],reviewed_by=record['reviewed_by'],
                    metal_pixels=int(ownership.sum()),protected_pixels=int(reserved.sum()),outside_owned_pixels=0)
