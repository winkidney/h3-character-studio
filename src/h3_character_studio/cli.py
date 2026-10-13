"""Standalone command line without AssetWorkbench or game-repository imports."""
import argparse
import json
from pathlib import Path
import sys

import yaml
from . import __version__, core, delivery, extraction, generation, normals, recipe, setup, reference


def parser():
    p = argparse.ArgumentParser(prog="h3-character")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("validate"); q.add_argument("character", type=Path)
    q = sub.add_parser("normalize-master"); q.add_argument("source", type=Path)
    q.add_argument("--output", required=True, type=Path); q.add_argument("--root-x", required=True, type=float)
    q = sub.add_parser("download-models"); q.add_argument("--models-dir", required=True, type=Path)
    q = sub.add_parser("prepare-runtime")
    q.add_argument("--runtime", required=True, type=Path); q.add_argument("--models-dir", required=True, type=Path)
    q.add_argument("--model-files", type=Path, help="YAML map of model ID to existing file path")
    q.add_argument("--source-caches", type=Path, help="YAML map of comfyui/birefnet to local clean Git source cache")
    q.add_argument("--install-gpu", action="store_true")
    q.add_argument("--wheelhouse", type=Path, help="Offline hashed GPU dependency wheels")
    q = sub.add_parser("serve"); q.add_argument("--runtime", required=True, type=Path)
    q.add_argument("--port", type=int, default=8197); q.add_argument("--python", type=Path)
    q = sub.add_parser("doctor"); q.add_argument("--runtime", required=True, type=Path)
    q.add_argument("--url", default="http://127.0.0.1:8197"); q.add_argument("--verify-models", action="store_true")
    q = sub.add_parser("prepare")
    q.add_argument("character", type=Path); q.add_argument("--direction", choices=recipe.DIRECTIONS, required=True)
    q.add_argument("--output", required=True, type=Path); q.add_argument("--url", default="http://127.0.0.1:8197")
    for command in ("run", "resume"):
        q = sub.add_parser(command); q.add_argument("directory", type=Path)
        q.add_argument("--observe-seconds", type=int, default=30)
    q = sub.add_parser("palette"); q.add_argument("master", type=Path)
    q.add_argument("--output", required=True, type=Path); q.add_argument("--colors", type=int, default=96)
    q = sub.add_parser("extract"); q.add_argument("raw", type=Path)
    q.add_argument("--output", required=True, type=Path); q.add_argument("--palette", required=True, type=Path)
    q.add_argument("--runtime", type=Path); q.add_argument("--prepared-rgba", action="store_true")
    q.add_argument("--pivot", type=int, nargs=2, default=[128, 240])
    q = sub.add_parser("select"); q.add_argument("animation", type=Path)
    q.add_argument("--output", required=True, type=Path); q.add_argument("--start", required=True, type=int)
    q.add_argument("--stop", required=True, type=int)
    q = sub.add_parser("review"); q.add_argument("animation", type=Path); q.add_argument("--output", required=True, type=Path)
    q = sub.add_parser("normals"); q.add_argument("animation", type=Path)
    q.add_argument("--geometry", required=True, type=Path); q.add_argument("--output", required=True, type=Path)
    q.add_argument("--edits", type=Path); q.add_argument("--painted-layers", type=Path); q.add_argument("--materials", type=Path, help="Reviewed per-frame material ownership JSON")
    q = sub.add_parser("verify-normals"); q.add_argument("animation", type=Path); q.add_argument("normals", type=Path)
    q = sub.add_parser("assemble"); q.add_argument("spec", type=Path); q.add_argument("--output", required=True, type=Path)
    q = sub.add_parser("verify"); q.add_argument("bundle", type=Path)
    return p


def execute(args):
    c = args.command
    if c == "normalize-master": return reference.normalize(args.source, args.output, root_x=args.root_x)
    if c == "validate":
        spec, settings, references = recipe.load(args.character)
        return dict(id=spec["id"], settings=settings, references={k: v["master_sha256"] for k, v in references.items()})
    if c == "download-models": return setup.download_models(args.models_dir)
    if c == "prepare-runtime":
        overrides = yaml.safe_load(args.model_files.read_text()) if args.model_files else None
        caches = yaml.safe_load(args.source_caches.read_text()) if args.source_caches else None
        return setup.prepare(args.runtime, args.models_dir, overrides, install_gpu=args.install_gpu, source_caches=caches, wheelhouse=args.wheelhouse)
    if c == "serve":
        if not 1024 <= args.port <= 65535: raise ValueError("Use an unprivileged port")
        return dict(exit_code=setup.launch(args.runtime, args.port, args.python))
    if c == "doctor":
        runtime = json.loads((args.runtime / "runtime.json").read_text())
        info = generation.request(args.url, "/object_info")
        required = {"H3CharacterRawFrames", "H3CharacterReference", "MiniMaxH3ImageToVideo", "MiniMaxH3AddGuide"}
        missing = sorted(required - set(info))
        if missing: raise ValueError("Required nodes missing: " + str(missing))
        if args.verify_models: setup.verify_models(".", runtime["models"])
        return dict(nodes_ready=True, models_verified=args.verify_models,
                    system_stats=generation.request(args.url, "/system_stats"), inference_verified=False)
    if c == "prepare": return generation.prepare(args.character, args.direction, args.output, args.url)
    if c in ("run", "resume"):
        if not 0 <= args.observe_seconds <= 60: raise ValueError("Observe 0..60 seconds; resume to keep watching")
        if c == "run": generation.submit(args.directory)
        return generation.follow(args.directory, args.observe_seconds)
    if c == "palette": return dict(palette_rgb=extraction.palette(args.master, args.output, args.colors))
    if c == "extract": return extraction.extract(args.raw, args.output, args.palette, runtime=args.runtime,
                                                  prepared_rgba=args.prepared_rgba, pivot=args.pivot)
    if c == "select": return extraction.select(args.animation, args.output, args.start, args.stop)
    if c == "review": return extraction.review(args.animation, args.output)
    if c == "normals":
        if args.edits and args.painted_layers: raise ValueError("Choose geometry edits or painted layers, not both")
        return normals.build(args.animation, args.geometry, args.output, edits=args.edits, painted_layers=args.painted_layers, material_annotations=args.materials)
    if c == "verify-normals": return normals.verify(args.animation, args.normals)
    if c == "assemble": return delivery.assemble(args.spec, args.output)
    if c == "verify": return delivery.verify(args.bundle)


def main():
    args = parser().parse_args()
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, dict) and result.get("exit_code"):
            sys.exit(result["exit_code"] if result["exit_code"] > 0 else 2)
        if isinstance(result, dict) and result.get("status") in ("failed", "rejected", "submission_unknown"):
            sys.exit(2)
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps(dict(status="error", error=str(error)), ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
