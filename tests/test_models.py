import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from h3_character_studio import cli, setup


class SharedModelsTests(unittest.TestCase):
    def test_shared_layout_reuses_toonout_without_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = b"existing verified model"
            target = root / "toonout/toonout.pth"
            target.parent.mkdir()
            target.write_bytes(content)
            row = dict(id="toonout", subdir="toonout", filename="toonout.pth",
                       file="toonout.pth", size=len(content),
                       sha256=hashlib.sha256(content).hexdigest())
            with patch.object(setup, "models", return_value=[row]), \
                    patch.object(setup.urllib.request, "urlopen") as download:
                self.assertEqual(setup.download_models(root), {"toonout": str(target)})
                download.assert_not_called()
                target.write_bytes(b"different model bytes!")
                with self.assertRaisesRegex(ValueError, "Existing model changed"):
                    setup.download_models(root)
                download.assert_not_called()

    def test_model_commands_default_to_shared_home(self):
        for arguments in (["download-models"], ["prepare-runtime", "--runtime", ".runtime"]):
            args = cli.parser().parse_args(arguments)
            self.assertEqual(args.models_dir, Path.home() / "Models/shared")


if __name__ == "__main__":
    unittest.main()
