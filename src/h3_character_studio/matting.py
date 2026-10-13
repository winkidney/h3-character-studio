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
