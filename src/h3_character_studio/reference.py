"""One-time master layout preparation; animation frames never recenter."""
from pathlib import Path
import numpy as np
from PIL import Image
from . import core


def normalize(source, output, *, root_x, size=768, height=648, ground=720):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError("Prepared master exists; choose a new output")
    image = Image.open(source).convert("RGBA")
    alpha = np.asarray(image.getchannel("A"))
    ys, xs = np.where(alpha >= 128)
    if not len(ys) or not 0 <= root_x < image.width or not 0 < height <= ground < size:
        raise ValueError("Nonempty master and valid explicit layout required")
    scale = height / (ys.max() + 1 - ys.min())
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.NEAREST)
    offset = (round(size / 2 - root_x * scale), round(ground - (ys.max() + 1) * scale))
    result = Image.new("RGBA", (size, size))
    result.paste(resized, offset)
    pixels = np.asarray(result.getchannel("A"))
    # Low-alpha edge noise from the source is retained, never used as an anchor.
    if (pixels[0] >= 128).any() or (pixels[-1] >= 128).any() or (pixels[:, 0] >= 128).any() or (pixels[:, -1] >= 128).any():
        raise ValueError("Prepared visible silhouette touches an edge")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    record = dict(schema_version=1, source_sha256=core.digest(source), output_sha256=core.digest(output),
        source_size=list(image.size), source_solid_bbox=[int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)],
        source_root_x=root_x, scale=float(scale), offset=list(offset), size=[size, size],
        character_height=height, ground=ground, resize="nearest", alpha_anchor_threshold=128,
        per_animation_frame_recentering=False)
    core.write_json(output.with_suffix(".layout.json"), record)
    return record
