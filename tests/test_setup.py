"""Offline regressions for incomplete or unverifiable browser-asset installs."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import setup


class AssetSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / "vendor/pdfjs"
        self.target.mkdir(parents=True)
        self.payload = self.archive()
        self.spec = {"version": "test-version", "url": "https://example.invalid/assets.tgz",
                     "integrity": "sha512-" + base64.b64encode(hashlib.sha512(self.payload).digest()).decode()}
        (self.root / "assets-lock.json").write_text(json.dumps({"pdfjs-dist": self.spec}))
        self.root_patch = patch.object(setup, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    @staticmethod
    def archive(exclude=None):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name in setup.REQUIRED_ASSETS:
                if name == exclude:
                    continue
                content = b"synthetic test asset"
                member = tarfile.TarInfo("package/" + name)
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        return buffer.getvalue()

    def install_files(self):
        for name in setup.REQUIRED_ASSETS:
            item = self.target / name
            item.parent.mkdir(parents=True, exist_ok=True)
            item.write_bytes(b"existing fixture")
        (self.target / ".version").write_text(self.spec["version"])

    @patch("scripts.setup.urllib.request.urlopen")
    def test_complete_installation_does_not_download(self, download):
        self.install_files()
        setup.main()
        download.assert_not_called()

    @patch("scripts.setup.urllib.request.urlopen")
    def test_matching_marker_with_missing_worker_is_repaired(self, download):
        self.install_files()
        (self.target / "build/pdf.worker.mjs").unlink()
        download.return_value.__enter__.return_value.read.return_value = self.payload
        setup.main()
        download.assert_called_once()
        self.assertTrue(setup.assets_ready(self.target))
        self.assertEqual((self.target / ".version").read_text().strip(), self.spec["version"])

    @patch("scripts.setup.urllib.request.urlopen")
    def test_zero_byte_stylesheet_is_repaired(self, download):
        self.install_files()
        (self.target / "web/pdf_viewer.css").write_bytes(b"")
        download.return_value.__enter__.return_value.read.return_value = self.payload
        setup.main()
        self.assertGreater((self.target / "web/pdf_viewer.css").stat().st_size, 0)
        download.assert_called_once()

    @patch("scripts.setup.urllib.request.urlopen")
    def test_integrity_mismatch_is_rejected_before_marker(self, download):
        download.return_value.__enter__.return_value.read.return_value = b"unverified bytes"
        with self.assertRaisesRegex(RuntimeError, "integrity"):
            setup.main()
        self.assertFalse((self.target / ".version").exists())

    @patch("scripts.setup.urllib.request.urlopen")
    def test_incomplete_verified_archive_does_not_get_marker(self, download):
        payload = self.archive(exclude="build/pdf.worker.mjs")
        self.spec["integrity"] = "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode()
        (self.root / "assets-lock.json").write_text(json.dumps({"pdfjs-dist": self.spec}))
        download.return_value.__enter__.return_value.read.return_value = payload
        with self.assertRaisesRegex(RuntimeError, "missing required assets"):
            setup.main()
        self.assertFalse((self.target / ".version").exists())


if __name__ == "__main__":
    unittest.main()
