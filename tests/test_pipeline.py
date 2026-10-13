import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import numpy as np
from PIL import Image, ImageDraw
import yaml

from h3_character_studio import core, delivery, extraction, generation, normals, recipe, workflow, reference


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        raw = self.root / "raw"
        raw.mkdir()
        records = []
        for i in range(5):
            image = Image.new("RGBA", (256, 256))
            draw = ImageDraw.Draw(image)
            draw.ellipse((105+i, 40, 151+i, 90), fill=(80, 50, 30, 255))
            draw.polygon([(105+i, 88), (150+i, 88), (173+i, 187), (85+i, 187)], fill=(35, 105, 100, 255))
            draw.rectangle((117+i, 100, 123+i, 108), fill=(195, 130, 65, 255))
            path = raw / f"{i:05d}.png"
            image.save(path)
            records.append(dict(path=path.name, sha256=core.digest(path), index=i))
        core.write_json(raw / "raw.json", dict(fps=24, frames=records))
        self.raw = raw
        self.palette = self.root / "palette.json"
        extraction.palette(raw / "00000.png", self.palette)
        self.geo = self.root / "geometry.yaml"
        shapes = [dict(id="cloth", kind="plane", points=[[1, 1], [254, 1], [254, 254], [1, 254]], normal=[0, 0, 1]),
                  dict(id="hair", kind="ellipsoid", ellipse=[128, 65, 28, 30]),
                  dict(id="copper", kind="ellipsoid", ellipse=[120, 104, 6, 7], metallic=True,
                       palette_colors=[[195, 130, 65]])]
        self.geo.write_text(yaml.safe_dump(dict(schema_version=1, keyframes={0: shapes})))

    def build_normals(self, animation, geo, target, **kwargs):
        # The fixture's copper rectangle is authored in setUp. Bind its exact
        # pixel ownership to each exported frame, rather than infer from a rig.
        ann=self.root/(target.name+"-materials");ann.mkdir(exist_ok=True)
        data=json.loads((animation/"animation.json").read_text())
        for i,row in enumerate(data["frames"]):
            rgb=np.asarray(Image.open(animation/row["path"]).convert("RGBA"))
            yy,xx=np.where((rgb[...,:3]==[195,130,65]).all(-1)&(rgb[...,3]>0))
            core.write_json(ann/f"{i:05d}.json",dict(schema_version=1,frame=i,source_sha256=row["sha256"],
                review_status="agent-reviewed",reviewed_by="authored-test-fixture",regions={"copper":np.stack([xx,yy],-1).tolist()},protected_regions={}))
        return normals.build(animation,geo,target,material_annotations=ann,**kwargs)

    def tearDown(self): self.temp.cleanup()

    def animation(self, name="extracted"):
        output = self.root / name
        extraction.extract(self.raw, output, self.palette, prepared_rgba=True)
        return output / "pixel-256"

    def test_native_extraction_retains_all_frames_and_timing(self):
        animation = self.animation()
        manifest = json.loads((animation / "animation.json").read_text())
        self.assertEqual([row["source"]["raw_frame"] for row in manifest["frames"]], list(range(5)))
        self.assertEqual(sum(row["duration_ms"] for row in manifest["frames"]), round(5000 / 24))
        self.assertEqual(manifest["pivot"], [128, 240])
        self.assertTrue(extraction.check_bundle(animation)["exact_atlas"])

    def test_master_layout_aligns_ground_and_preserves_source(self):
        source = self.raw / "00000.png"
        before = core.digest(source)
        output = self.root / "prepared.png"
        record = reference.normalize(source, output, root_x=128)
        with Image.open(output) as image: self.assertEqual(image.size, (768, 768))
        ys, _ = np.where(np.asarray(Image.open(output).getchannel("A")) >= 128)
        self.assertLessEqual(abs(int(ys.max()) + 1 - 720), 1)
        self.assertEqual(core.digest(source), before)
        self.assertFalse(record["per_animation_frame_recentering"])
        with self.assertRaises(ValueError): reference.normalize(source, output, root_x=128)

    def test_palette_excludes_nearly_transparent_edge_noise(self):
        source = self.root / "master.png"
        image = Image.new("RGBA", (256, 256))
        ImageDraw.Draw(image).rectangle((100, 100, 150, 150), fill=(35, 105, 100, 255))
        image.putpixel((1, 1), (255, 0, 255, 1)); image.save(source)
        colors = extraction.palette(source, self.root / "clean-palette.json", 96)
        self.assertEqual(colors, [(35, 105, 100)])

    def test_native_export_rejects_upscale(self):
        path = self.raw / "00000.png"
        Image.open(path).resize((128, 128), Image.Resampling.NEAREST).save(path)
        data = json.loads((self.raw / "raw.json").read_text())
        data["frames"][0]["sha256"] = core.digest(path)
        core.write_json(self.raw / "raw.json", data)
        with self.assertRaisesRegex(ValueError, "share a square canvas"):
            extraction.extract(self.raw, self.root / "bad", self.palette, prepared_rgba=True)

    def test_raw_tampering_is_rejected_before_export(self):
        (self.raw / "00000.png").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "Raw frame changed"):
            extraction.extract(self.raw, self.root / "bad", self.palette, prepared_rgba=True)
        self.assertFalse((self.root / "bad").exists())

    def test_contiguous_selection_preserves_exact_pixels_and_duration(self):
        animation = self.animation()
        old = json.loads((animation / "animation.json").read_text())
        target = self.root / "selected"
        extraction.select(animation, target, 1, 4)
        selected = json.loads((target / "pixel-256/animation.json").read_text())
        for a, b in zip(old["frames"][1:4], selected["frames"]):
            self.assertEqual(a["sha256"], b["sha256"])
            self.assertEqual(a["duration_ms"], b["duration_ms"])
        self.assertEqual([r["source"]["raw_frame"] for r in selected["frames"]], [1, 2, 3])

    def test_normals_preserve_color_and_pair_exact_alpha_atlas(self):
        animation = self.animation()
        before = {p.name: core.digest(p) for p in animation.glob("frames/*.png")}
        target = self.root / "normals"
        report = self.build_normals(animation, self.geo, target)
        self.assertTrue(report["geometry_coverage_complete"])
        self.assertLess(report["max_unit_vector_error"], .014)
        self.assertEqual(before, {p.name: core.digest(p) for p in animation.glob("frames/*.png")})
        mask = np.asarray(Image.open(target / "masks/00000.png"))
        self.assertGreater((mask[..., 0] == 255).sum(), 0)
        self.assertEqual(mask[140, 128, 0], 0)

    def test_normal_vectors_do_not_come_from_diffuse_brightness(self):
        color = np.asarray(Image.open(self.raw / "00000.png")).copy()
        shapes = yaml.safe_load(self.geo.read_text())["keyframes"][0][:2]
        n1, _, _ = normals.render(color, shapes)
        color[..., :3] = 255 - color[..., :3]
        n2, _, _ = normals.render(color, shapes)
        np.testing.assert_array_equal(n1, n2)

    def test_geometry_rejects_invalid_vectors_and_unsafe_layer_names(self):
        color = np.asarray(Image.open(self.raw / "00000.png"))
        for shape in (dict(id="face", kind="ellipsoid", ellipse=[float("nan"), 65, 28, 30]),
                      dict(id="../face", kind="ellipsoid", ellipse=[128, 65, 28, 30]),
                      dict(id="cloth", kind="plane", points=[[1, 1], [250, 1], [250, 250]], normal=[0, 0, 0])):
            with self.assertRaises(ValueError): normals.render(color, [shape])

    def test_pose_transport_changes_fold_volume_between_anchors(self):
        first = [dict(id="fold", kind="tube", points=[[110,120],[115,170]], radius=4, slope=.2)]
        last = [dict(id="fold", kind="tube", points=[[120,120],[125,170]], radius=10, slope=.8)]
        flow = np.zeros((4,256,256,2), np.float32)
        rigs = normals.transport({0:first, 2:last}, flow, flow)
        self.assertEqual(rigs[1][0]["radius"], 7)
        self.assertAlmostEqual(rigs[1][0]["slope"], .5)
        self.assertAlmostEqual(rigs[3][0]["slope"], .5)
        self.assertEqual(first[0]["radius"], 4)

    def test_surface_region_covers_cloth_outside_volume_ellipse(self):
        color = np.asarray(Image.open(self.raw / "00000.png"))
        shapes = [dict(id="skirt", kind="ellipsoid", ellipse=[128,140,12,18], slope=.5,
                       surface_region=[[80,88],[180,88],[180,190],[80,190]])]
        vectors, labels, _ = normals.render(color, shapes)
        self.assertEqual(labels[170,100], 1)
        self.assertGreater(abs(float(vectors[170,100,0])), .2)
        self.assertEqual(labels[10,10], 0)

    def test_fallback_coverage_is_not_complete_authored_geometry(self):
        animation = self.animation()
        spec = yaml.safe_load(self.geo.read_text())
        spec["keyframes"][0][0]["fallback"] = True
        self.geo.write_text(yaml.safe_dump(spec))
        report = self.build_normals(animation, self.geo, self.root / "fallback")
        self.assertTrue(report["exact_alpha"])
        self.assertFalse(report["geometry_coverage_complete"])
        self.assertGreater(sum(report["fallback_pixels"]), 0)

    def test_per_frame_edits_allow_newly_exposed_fold_topology(self):
        animation = self.animation()
        spec = yaml.safe_load(self.geo.read_text())
        first = dict(id="fold", kind="tube", points=[[110,120],[115,170]], radius=4)
        last = dict(id="fold", kind="tube", points=[[110,120],[113,145],[115,170]], radius=4)
        base = spec["keyframes"][0]
        spec["keyframes"] = {0:base+[first], 2:base+[last]}
        self.geo.write_text(yaml.safe_dump(spec))
        edits = self.root / "edits"
        for index in range(5):
            core.write_json(edits / f"{index:05d}/geometry.json",
                            dict(shapes=base+[first if index<2 else last]))
        target = self.root / "topology"
        report = self.build_normals(animation, self.geo, target, edits=edits)
        self.assertTrue(report["exact_alpha"])
        self.assertEqual(report["frame_count"], 5)
        painted = self.root / "painted-topology"
        rebuilt = self.build_normals(animation, self.geo, painted, painted_layers=target / "editable")
        self.assertTrue(rebuilt["exact_alpha"])
        self.assertEqual(core.digest(target / "mask-atlas.png"), core.digest(painted / "mask-atlas.png"))
        pose = json.loads((painted / "editable/00002/geometry.json").read_text())
        self.assertEqual(len(next(s for s in pose["shapes"] if s["id"] == "fold")["points"]), 3)
        for index in range(5):
            before = np.asarray(Image.open(target / f"frames/{index:05d}.png"))
            after = np.asarray(Image.open(painted / f"frames/{index:05d}.png"))
            visible = before[...,3] > 0
            a = before[visible,:3].astype(float)/127.5-1
            b = after[visible,:3].astype(float)/127.5-1
            cosine = (a*b).sum(-1)/(np.linalg.norm(a,axis=-1)*np.linalg.norm(b,axis=-1))
            # Re-normalizing RGBA8 vectors can change a component by one level.
            self.assertLess(float(np.max(np.degrees(np.arccos(np.clip(cosine,-1,1))))), 1)

    def test_fine_metal_regions_do_not_fill_adjacent_cloth(self):
        color = np.asarray(Image.open(self.raw / "00000.png"))
        shape = dict(id="clasp", kind="ellipsoid", ellipse=[120,104,6,7],
                     metallic=True, pixel_region=[[118,102],[122,106]])
        _, labels, metal = normals.render(color, [shape])
        self.assertTrue(metal[102,118])
        self.assertFalse(metal[104,120])
        self.assertEqual(int(metal.sum()), 2)
        shape["pixel_region"] = [[120.5,104]]
        with self.assertRaises(ValueError): normals.render(color, [shape])

    def test_painted_layers_and_geometry_edits_use_explicit_sources(self):
        animation = self.animation()
        original = self.root / "normals"
        self.build_normals(animation, self.geo, original)
        painted = self.root / "painted"
        self.build_normals(animation, self.geo, painted, painted_layers=original / "editable")
        self.assertTrue(normals.verify(animation, painted)["exact_alpha"])
        edited = self.root / "edited"
        self.build_normals(animation, self.geo, edited, edits=original / "editable")
        self.assertEqual(core.digest(original / "frames/00000.png"), core.digest(edited / "frames/00000.png"))

    def test_normal_atlas_tampering_is_rejected(self):
        animation = self.animation()
        target = self.root / "normals"
        self.build_normals(animation, self.geo, target)
        (target / "atlas.png").write_bytes(b"changed")
        with self.assertRaises((ValueError, OSError)):
            normals.verify(animation, target)

    def test_delivery_is_portable_and_requires_four_matching_directions(self):
        animation = self.animation()
        normal = self.root / "normals"
        self.build_normals(animation, self.geo, normal)
        spec = self.root / "delivery.yaml"
        spec.write_text(yaml.safe_dump(dict(schema_version=1, id="test-character", directions={d: dict(
            animation="extracted/pixel-256", normals="normals", idle_frame=2) for d in recipe.DIRECTIONS})))
        bundle = self.root / "bundle"
        delivery.assemble(spec, bundle)
        self.assertTrue(delivery.verify(bundle)["four_directions"])
        (bundle / "character/down/frames/00000.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "digest"):
            delivery.verify(bundle)

    def test_input_requires_independent_four_direction_references(self):
        spec = self.root / "character.yaml"
        data = dict(schema_version=1, id="test-character", directions={d: dict(master="raw/00000.png", prompt="Walk in place") for d in recipe.DIRECTIONS})
        spec.write_text(yaml.safe_dump(data))
        self.assertEqual(recipe.load(spec)[1]["frames"], 56)
        data["settings"] = dict(frames=55)
        spec.write_text(yaml.safe_dump(data))
        with self.assertRaisesRegex(ValueError, "17k"):
            recipe.load(spec)
        data["settings"] = dict(frames=56)
        data["directions"]["up"]["master"] = "../escape.png"
        spec.write_text(yaml.safe_dump(data))
        with self.assertRaisesRegex(ValueError, "relative"):
            recipe.load(spec)

    def test_submission_unknown_cannot_repeat(self):
        run = self.root / "run"; run.mkdir()
        for name in ("master.png", "workflow.api.json", "prompt.txt"):
            (run / name).write_text("{}")
        state = dict(status="prepared", submission_attempts=0, run_id="one", url="http://127.0.0.1:8197", client_id="test",
                     master_sha256=core.digest(run / "master.png"), graph_sha256=core.digest(run / "workflow.api.json"), prompt_sha256=core.digest(run / "prompt.txt"))
        core.write_json(run / "job.json", state)
        with patch.object(generation, "request", side_effect=TimeoutError("lost response")) as call:
            self.assertEqual(generation.submit(run)["status"], "submission_unknown")
            with self.assertRaisesRegex(ValueError, "already attempted"):
                generation.submit(run)
            self.assertEqual(call.call_count, 1)

    def test_unknown_submission_can_be_found_in_history(self):
        history = {"server-id": dict(prompt=[0, "server-id", {}, {"h3_character_run_id": "one"}])}
        self.assertEqual(generation.find_submission(dict(run_id="one"), {}, history), "server-id")

    def test_graph_uses_current_master_for_endpoints_and_middle_guide(self):
        g = workflow.graph("up.png", "one", recipe.DEFAULTS, "Back view walk", 241)
        self.assertEqual(g["6"]["inputs"]["first_frame"], g["6"]["inputs"]["last_frame"])
        self.assertEqual(g["17"]["inputs"]["frame_idx"], 27)
        self.assertEqual(g["15"]["class_type"], "H3CharacterRawFrames")
        self.assertFalse(any(n["class_type"].startswith("Pixel") for n in g.values()))

    def test_rear_orientation_guides_reach_sampler_without_dangling_links(self):
        settings = dict(recipe.DEFAULTS, extra_guide_frames=[13, 41])
        g = workflow.graph("up.png", "rear-revision", settings, "Rear view only", 442)
        link = g["7"]["inputs"]["conditioning"]
        seen = []
        while g[link[0]]["class_type"] == "MiniMaxH3AddGuide":
            node = g[link[0]]
            seen.append(node["inputs"]["frame_idx"])
            self.assertEqual(node["inputs"]["image"], ["2", 0])
            self.assertEqual(node["inputs"]["latent"], ["6", 1])
            link = node["inputs"]["positive"]
        self.assertEqual(seen, [41, 27, 13])
        self.assertEqual(link, ["6", 0])
        for node in g.values():
            for value in node["inputs"].values():
                if isinstance(value, list): self.assertIn(value[0], g)


if __name__ == "__main__": unittest.main()
