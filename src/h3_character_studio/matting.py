"""ToonOut inference and RGB recovery extracted from AssetWorkbench."""
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image
NODE_REVISION = "5443a2aa16cfbd98bb2f7dcc8bdcb70439e08529"

def predictor(model_name, resolution, device, dtype, *, models, node_source=None, comfy_source=None):
    models = Path(models)
    if model_name == 'u2netp':
        import onnxruntime as ort
        if device != 'cpu' or resolution != 320 or dtype != 'float32':
            raise ValueError('Pinned U2-NetP ONNX supports CPU, fixed 320 input and float32 only; do not silently ignore settings')
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        session = ort.InferenceSession(str(models / 'u2netp.onnx'), options, providers=['CPUExecutionProvider'])
        def predict(images):
            results = []
            for image in images:
                a = np.asarray(image.convert('RGB').resize((320, 320), Image.Resampling.LANCZOS)).astype(np.float32)
                a /= max(float(a.max()), 1e-6)
                a = ((a - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]).transpose(2, 0, 1)[None].astype(np.float32)
                result = session.run(None, {session.get_inputs()[0].name: a})[0][0, 0]
                result = (result - result.min()) / max(float(result.max() - result.min()), 1e-8)
                results.append(np.asarray(Image.fromarray(result).resize(image.size, Image.Resampling.BILINEAR)).clip(0, 1))
            return results
        return predict
    if node_source is None or comfy_source is None:
        raise ValueError('BiRefNet requires explicit node_source and comfy_source directories')
    import torch
    from torchvision import transforms
    from safetensors.torch import load_file
    revision = subprocess.check_output(['git', '-C', str(node_source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != NODE_REVISION:
        raise ValueError('BiRefNet source revision mismatch')
    sys.path.insert(0, str(node_source))
    # The existing node's Config imports ComfyUI folder_paths for optional weights.
    sys.path.insert(0, str(comfy_source))
    from birefnet.models.birefnet import BiRefNet
    torch.set_num_threads(4)
    torch.manual_seed(11)
    torch.backends.cudnn.benchmark = False
    torch.set_float32_matmul_precision('highest')
    model = BiRefNet(bb_pretrained=False, bb_index=3 if model_name == 'lite' else 6)
    if model_name == 'lite':
        state = load_file(str(models / 'birefnet-lite.safetensors'))
    else:
        state = torch.load(models / 'toonout.pth', map_location='cpu', weights_only=True)
        state = {key.removeprefix('module.').removeprefix('_orig_mod.'): value for key, value in state.items()}
    model.load_state_dict(state, strict=True)
    del state
    td = torch.float16 if dtype == 'float16' else torch.float32
    model.to(device=device, dtype=td).eval()
    transform = transforms.Compose([transforms.Resize((resolution, resolution)), transforms.ToTensor(),
                                    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    def predict(images):
        with torch.inference_mode():
            value = torch.stack([transform(im.convert('RGB')) for im in images]).to(device=device, dtype=td)
            masks = model(value)[-1].sigmoid().float()
            masks = torch.nn.functional.interpolate(masks, size=images[0].size[::-1], mode='bilinear', align_corners=False)
            return masks[:, 0].cpu().numpy().clip(0, 1)
    return predict

def recover(image, alpha, method='ml', regularization=1e-5, n_small=10, n_big=2):
    rgb = np.asarray(image.convert('RGB')).astype(np.float64) / 255
    if method == 'none':
        return rgb
    if method != 'ml':
        raise ValueError('Unknown recovery method')
    from pymatting import estimate_foreground_ml
    return estimate_foreground_ml(rgb, alpha.astype(np.float64), regularization=regularization,
                                  n_small_iterations=n_small, n_big_iterations=n_big).clip(0, 1)


def key_pixels(rgb, key, *, hue_degrees=24, saturation=0.30, minimum_value=0.045):
    """Recognize a known solid chroma background, including dark spill pixels.

    Hue and saturation rather than brightness catch background trapped in hair
    holes. Call before palette mapping, which otherwise hides these pixels.
    """
    import cv2
    value = np.asarray(rgb, np.float32)
    if value.max() > 1: value = value / 255
    hsv = cv2.cvtColor(value, cv2.COLOR_RGB2HSV)
    target = cv2.cvtColor(np.asarray(key, np.float32).reshape(1, 1, 3), cv2.COLOR_RGB2HSV)[0, 0]
    distance = np.abs(hsv[..., 0] - target[0])
    distance = np.minimum(distance, 360 - distance)
    return (distance <= hue_degrees) & (hsv[..., 1] >= saturation) & (hsv[..., 2] >= minimum_value)


def background_prior(image, alpha, *, protected_palette=()):
    """Fuse a verified saturated solid-background prior with the neural matte.

    No blanket erosion, hole filling or frame-specific coordinate patch. If the
    approved character palette contains the key hue, fail instead of deleting
    an intended purple garment. Non-chroma backgrounds retain neural matting.
    """
    rgb = np.asarray(image.convert('RGB'), np.float32) / 255
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    key = np.median(border, axis=0)
    import cv2
    hsv = cv2.cvtColor(key.reshape(1, 1, 3), cv2.COLOR_RGB2HSV)[0, 0]
    magenta_distance=min(abs(float(hsv[0])-300),360-abs(float(hsv[0])-300))
    if hsv[1] < .65 or hsv[2] < .5 or magenta_distance > 35:
        return np.asarray(alpha).copy(), dict(mode='neural-only', background_prior_verified=False)
    border_mask = key_pixels(border.reshape(1, -1, 3), key, hue_degrees=35)
    if float(border_mask.mean()) < .98:
        raise ValueError('Chroma background is not uniform at the canvas boundary')
    # H3 reference compositing specifies magenta. Keep its detection hue fixed
    # across frames; a generated warmer backdrop must not eat plum garments.
    nominal=np.array([1.,0.,1.],np.float32)
    if protected_palette:
        palette = np.asarray(protected_palette, np.float32).reshape(1, -1, 3) / 255
        if key_pixels(palette, nominal, hue_degrees=35).any():
            raise ValueError('Character palette overlaps the chroma key; use a different background')
    reject = key_pixels(rgb, nominal, hue_degrees=35)
    result = np.asarray(alpha, np.float64).copy()
    removed = int(((result >= .5) & reject).sum())
    result[reject] = 0
    return result, dict(mode='neural-plus-verified-chroma', background_prior_verified=True,
                        background_rgb=np.rint(key*255).astype(int).tolist(), detection_rgb=[255,0,255],
                        removed_background_pixels=removed, key_hue_tolerance_degrees=35,
                        no_blanket_erosion=True)


def validate_foreground(image, alpha, foreground, *, key=None):
    """Reject surviving key pixels before quantization can disguise contamination."""
    visible = np.asarray(alpha) >= .5
    report = dict(opaque_pixels=int(visible.sum()), checked_before_palette=True)
    if key is not None:
        key = np.array([1.,0.,1.],np.float32)
        raw_bad = key_pixels(np.asarray(image.convert('RGB')), key, hue_degrees=35) & visible
        recovered_bad = key_pixels(np.asarray(foreground), key, saturation=.08) & visible
        report.update(raw_background_in_foreground=int(raw_bad.sum()),
                      recovered_key_spill_pixels=int(recovered_bad.sum()))
        if raw_bad.any() or recovered_bad.any():
            raise ValueError('Background color survived foreground extraction before palette mapping: '+str(report))
    return report


def recover_chroma_edges(image, alpha, foreground, *, key, palette):
    """Resolve key-colored edge spill against the existing shared character palette.

    Fit the *raw composite* C=aF+(1-a)B. Nearest clean interior color disambiguates
    similar palette rays; never erode all edges or paint a frame-specific patch.
    """
    import cv2
    rgb=np.asarray(image.convert('RGB'),np.float64)/255
    fg=np.asarray(foreground,np.float64)
    if fg.max()>1:fg=fg/255
    a=np.asarray(alpha,np.float64).copy()
    bg=np.asarray(key,np.float64)/255
    colors=np.asarray(palette,np.float64)/255
    # On opaque pixels F=C. Do not let regularized recovery tint interior art.
    nominal=np.array([1.,0.,1.],np.float32)
    raw_spill=key_pixels(rgb,nominal,hue_degrees=28,saturation=.06,minimum_value=.03)
    fg=fg.copy()
    opaque=(a>=.995)&~raw_spill
    fg[opaque]=rgb[opaque]
    quantized=np.rint(fg*255).astype(np.uint8)
    spill=(key_pixels(fg,nominal,hue_degrees=28,saturation=.06,minimum_value=.03)
           | key_pixels(quantized,nominal,saturation=.08))&(a>0)
    clean=(a>=.95)&~spill
    if not clean.any():raise ValueError('No clean interior pixels for edge-color recovery')
    distance,nearest=cv2.distanceTransformWithLabels((~clean).astype(np.uint8),cv2.DIST_L2,5,labelType=cv2.DIST_LABEL_PIXEL)
    lookup=np.zeros((int(nearest.max())+1,2),np.int32)
    cy,cx=np.where(clean);lookup[nearest[cy,cx]]=np.stack([cy,cx],axis=-1)
    indices=np.moveaxis(lookup[nearest],-1,0)
    repaired=fg.copy();unknown=0;removed=0;fallback_pixels=[]
    yy,xx=np.where(spill)
    delta=colors-bg
    denom=np.maximum((delta*delta).sum(-1),1e-8)
    for start in range(0,len(xx),4096):
        y,x=yy[start:start+4096],xx[start:start+4096]
        observed=rgb[y,x]-bg
        weights=np.clip(observed@delta.T/denom,0,1)
        fitted=bg+weights[...,None]*delta[None]
        error=((fitted-rgb[y,x,None])**2).sum(-1)
        local=fg[indices[0,y,x],indices[1,y,x]]
        cost=error+.01*((colors[None]-local[:,None])**2).sum(-1)+.002*(weights-a[y,x,None])**2
        choice=cost.argmin(-1);n=np.arange(len(y))
        scale=rgb.shape[1]/256
        unresolved=(distance[y,x]>8*scale)|((distance[y,x]>3*scale)&(error[n,choice]>.01))
        unknown+=int(unresolved.sum())
        if unresolved.any():
            points=[dict(x=int(px),y=int(py),raw_rgb=np.rint(rgb[py,px]*255).astype(int).tolist(),fit_error=float(err),interior_distance=float(dist)) for px,py,err,dist in zip(x[unresolved],y[unresolved],error[n,choice][unresolved],distance[y,x][unresolved])]
            raise ValueError('Ambiguous edge spill requires review: '+str(points[:12]))
        reliable=error[n,choice]<=.04
        a[y[reliable],x[reliable]]=weights[n,choice][reliable]
        repaired[y[reliable],x[reliable]]=colors[choice][reliable]
        # Generative fringes are not always physically valid composites. With
        # a nearby reliable interior, suppress the key chroma while preserving
        # luminance and the neural geometry; do not invent an alpha from a bad fit.
        cy,cx=y[~reliable],x[~reliable]
        if len(cx):
            original=fg[cy,cx];clean_color=original.copy()
            excess=np.maximum(np.minimum(original[:,0],original[:,2])-original[:,1],0)
            clean_color[:,0]-=excess;clean_color[:,2]-=excess
            luma=np.array([.2126,.7152,.0722])
            clean_color+=((original-clean_color)@luma)[:,None]
            repaired[cy,cx]=clean_color.clip(0,1)
            fallback_pixels.extend([dict(x=int(px),y=int(py),fit_error=float(e)) for px,py,e in zip(cx,cy,error[n,choice][~reliable])])
        removed+=int((a[y,x]<.5).sum())
    return repaired,a,dict(despilled_pixels=len(xx),removed_subthreshold_edge_pixels=removed,
                           mode='raw-composite-fit-to-shared-palette',background_not_palette_mapped=True,
                           luminance_preserving_fallback_pixels=fallback_pixels,visual_review_required=bool(fallback_pixels))
