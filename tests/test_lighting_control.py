import importlib.util
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lighting_control", ROOT / "examples/video/lighting-control/serve.py")
CONTROL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTROL)
sys.path.insert(0, str(ROOT / "examples/video"))
import pixel_overlay


class LightingControlTests(unittest.TestCase):
    def test_unusable_values_are_rejected(self):
        for key, value in [("energy", float("nan")), ("ambient", -.1), ("direction", .5),
                           ("frame", 27), ("normals_enabled", 1), ("color", "red")]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                CONTROL.validate(dict(CONTROL.DEFAULTS, **{key: value}))

    def test_save_requires_the_actual_displayed_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            studio = CONTROL.Studio(state, 18793)
            studio.frames = {}
            params = dict(CONTROL.DEFAULTS, energy=.65)
            revision = studio.preview(params)["revision"]
            with self.assertRaises(ValueError):
                studio.save(params, revision, 7)
            receipt = dict(revision=revision, sequence=7, params=params, image="frame-1.png")
            png = b"actual-image-fixture"
            CONTROL.atomic_json(state / "rendered.json", receipt)
            studio.frames[7] = receipt, png
            saved = studio.save(params, revision, 7)
            self.assertEqual((state / saved["snapshot"]).read_bytes(), png)
            self.assertEqual(CONTROL.read_json(state / "selected.json")["params"], params)
            studio.preview(dict(params, ambient=.1))
            with self.assertRaises(ValueError):
                studio.save(params, revision, 7)
            self.assertEqual(CONTROL.read_json(state / "selected.json")["params"], params)

    def test_editing_does_not_replace_a_saved_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            chosen = dict(CONTROL.DEFAULTS, energy=1.25)
            CONTROL.atomic_json(state / "selected.json", dict(params=chosen))
            studio = CONTROL.Studio(state, 18793)
            self.assertEqual(studio.current["params"], chosen)
            studio.preview(CONTROL.DEFAULTS)
            self.assertEqual(CONTROL.read_json(state / "selected.json")["params"], chosen)

    def test_direction_highlights_follow_selected_duration(self):
        parts = [dict(id="roam", title="漫游", frames=300),
                 dict(id="cardinal", title="四向光照", frames=240)]
        for direction in range(4):
            expected = tuple(bytes.fromhex(pixel_overlay.DIRECTION_COLORS[direction][1:])) + (255,)
            header = pixel_overlay.header("cardinal", direction * 60, direction_frames=60, playback_scale=1)
            footer = pixel_overlay.progress_overlay(parts, 300 + direction * 60)
            self.assertIn(expected, set(header.getdata()))
            self.assertIn(expected, set(footer.getdata()))
        self.assertIn("1×", pixel_overlay.cardinal_caption(1))


if __name__ == "__main__":
    unittest.main()
