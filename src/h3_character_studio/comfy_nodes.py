"""Only reference preparation and lossless raw output run inside ComfyUI."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from . import core
from .recipe import identifier


class H3CharacterReference:
    CATEGORY = "H3 Character Studio"
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "prepare"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",), "mask": ("MASK",),
            "background": ("STRING", {"default": "#ff00ff"}),
            "width": ("INT", {"default": 768, "min": 256, "max": 2048, "step": 32}),
            "height": ("INT", {"default": 768, "min": 256, "max": 2048, "step": 32})}}

    def prepare(self, images, mask, background, width, height):
        import torch
        image = Image.fromarray(np.rint(images[0].detach().cpu().numpy() * 255).clip(0, 255).astype(np.uint8))
        alpha = Image.fromarray(np.rint((1 - mask[0].detach().cpu().numpy()).clip(0, 1) * 255).astype(np.uint8))
        image.putalpha(alpha.resize(image.size, Image.Resampling.NEAREST))
        scale = min(width / image.width, height / image.height)
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.NEAREST)
        result = Image.new("RGBA", (width, height), (*core.rgb(background), 255))
        result.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
        return (torch.from_numpy(np.asarray(result.convert("RGB")).astype(np.float32) / 255)[None],)


class H3CharacterRawFrames:
    CATEGORY = "H3 Character Studio"
    RETURN_TYPES = ("STRING",)
    FUNCTION = "save"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",), "run_id": ("STRING", {"default": "character-right-001"}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 60.0}),
            "expected_frames": ("INT", {"default": 56, "min": 22, "max": 260})},
            "hidden": {"prompt": "PROMPT"}}

    def save(self, images, run_id, fps, expected_frames, prompt=None):
        import folder_paths
        target = Path(folder_paths.get_output_directory()) / "h3-character" / identifier(run_id)
        # Never overwrite outputs or accept a frame count silently rounded by H3.
        target.mkdir(parents=True, exist_ok=False)
        core.write_json(target / "request.json", dict(prompt=prompt, fps=fps, expected_frames=expected_frames))
        if len(images) != expected_frames:
            raise ValueError("H3 frame count changed; output retained for diagnosis")
        raw = target / "raw"
        raw.mkdir()
        records = []
        for index, frame in enumerate(images):
            image = Image.fromarray(np.rint(frame.detach().cpu().numpy() * 255).clip(0, 255).astype(np.uint8))
            path = raw / f"{index:05d}.png"
            image.save(path)
            records.append(dict(path=str(path.relative_to(target)), sha256=core.digest(path), index=index))
        core.write_json(target / "raw.json", dict(schema_version=1, fps=fps, frames=records,
                                                 generation_complete=True, visual_approval="pending"))
        # Free generation weights before the separate ToonOut worker is launched.
        import comfy.model_management
        comfy.model_management.unload_all_models()
        import gc
        gc.collect()
        comfy.model_management.soft_empty_cache()
        return {"ui": {"text": [str(target)]}, "result": (str(target),)}


NODE_CLASS_MAPPINGS = {"H3CharacterReference": H3CharacterReference, "H3CharacterRawFrames": H3CharacterRawFrames}
NODE_DISPLAY_NAME_MAPPINGS = {k: k for k in NODE_CLASS_MAPPINGS}
