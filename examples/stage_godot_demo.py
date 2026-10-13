"""Adopt a verified bundle in a recorded temporary hd-2d-godot copy only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from h3_character_studio import core, delivery


def main():
    p = argparse.ArgumentParser()
    p.add_argument("bundle", type=Path)
    p.add_argument("--project", required=True, type=Path)
    a = p.parse_args()
    project = a.project.resolve()
    if not (project / "demo-source.json").is_file() or (project / ".git").exists():
        raise ValueError("Require a recorded temporary copy with demo-source.json and no .git")
    delivery.verify(a.bundle)
    definition = json.loads((a.bundle / "character/character.json").read_text())
    identifier = definition["id"]
    color_root = f"assets/characters/{identifier}/v1/"
    normal_root = f"assets/character-normals/{identifier}/v1/"
    replacements = {
        "scripts/character_animation.gd": ("assets/characters/crescent-traveler/v1/", color_root),
        "scripts/pixel_actor.gd": ("assets/characters/crescent-traveler/v1/", color_root),
        "scripts/ancient_canal/actor.gd": ("assets/ancient-canal/character-normals/v1/", normal_root),
    }
    originals = {}
    for name, (old, _) in replacements.items():
        text = (project / name).read_text()
        if old not in text:
            raise ValueError("Expected original protagonist path in " + name)
        originals[name] = text
    if (project / color_root).exists() or (project / normal_root).exists():
        raise ValueError("Use a fresh temporary copy; do not overwrite existing character assets")
    shutil.copytree(a.bundle / "character", project / color_root)
    normal_definition = json.loads((a.bundle / "normals/manifest.json").read_text())
    # Keep editable source layers in the bundle. Godot imports runtime atlases
    # only, avoiding thousands of unused authoring textures in the game.
    for name in normal_definition["directions"]:
        target = project / normal_root / name
        target.mkdir(parents=True)
        for filename in ("atlas.png", "mask-atlas.png"):
            shutil.copy2(a.bundle / "normals" / name / filename, target / filename)
    for name, row in normal_definition["directions"].items():
        color = json.loads((project / color_root / name / "animation.json").read_text())
        row.update(atlas=normal_root+name+"/atlas.png", mask_atlas=normal_root+name+"/mask-atlas.png",
            source_atlas=color_root+name+"/"+color["atlas"], duration_ms=sum(f["duration_ms"] for f in color["frames"]),
            pivot=color["pivot"], frames=[dict(region=f["region"], duration_ms=f["duration_ms"],
                source_path=color_root+name+"/"+f["path"], source_index=f["source"]["raw_frame"])
                for f in color["frames"]])
        row.pop("manifest", None)
    core.write_json(project / normal_root / "manifest.json", normal_definition)
    for name,(old,new) in replacements.items():
        (project / name).write_text(originals[name].replace(old,new))
    core.write_json(project / "h3-character-adoption.json", dict(character_id=identifier,
        bundle_manifest_sha256=core.digest(a.bundle / "SHA256SUMS.json"),
        temporary_copy=True, modified_scripts=list(replacements),
        original_script_sha256={name:hashlib.sha256(text.encode()).hexdigest() for name,text in originals.items()}))
    print("Staged", identifier, "in recorded temporary project", project)


if __name__ == "__main__":
    main()
