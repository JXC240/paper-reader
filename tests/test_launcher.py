import unittest
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

from scripts.wait_for_reader import wait_for_reader


class LauncherReadinessTests(unittest.TestCase):
    def response(self, server="PaperReader/0.1", status=200):
        result = MagicMock()
        result.__enter__.return_value.status = status
        result.__enter__.return_value.headers = {"Server": server}
        return result

    @patch("scripts.wait_for_reader.urllib.request.urlopen")
    def test_our_reader_is_ready(self, request):
        request.return_value = self.response()
        self.assertTrue(wait_for_reader())
        self.assertEqual(request.call_args.args[0], "http://127.0.0.1:8877/")

    @patch("scripts.wait_for_reader.urllib.request.urlopen")
    def test_foreign_service_is_not_success(self, request):
        request.return_value = self.response(server="OtherServer/1")
        self.assertFalse(wait_for_reader())
        self.assertEqual(request.call_count, 1)

    @patch("scripts.wait_for_reader.time.sleep")
    @patch("scripts.wait_for_reader.urllib.request.urlopen")
    def test_brief_startup_delay_is_retried(self, request, sleep):
        request.side_effect = [ConnectionRefusedError(), self.response()]
        self.assertTrue(wait_for_reader())
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(.25)

    @patch("scripts.wait_for_reader.time.monotonic", side_effect=[0, 21])
    @patch("scripts.wait_for_reader.urllib.request.urlopen", side_effect=ConnectionRefusedError())
    def test_deadline_is_bounded(self, request, monotonic):
        self.assertFalse(wait_for_reader())
        self.assertEqual(request.call_count, 1)


class LauncherEnvironmentTests(unittest.TestCase):
    """Run the real entry point with isolated, intentionally broken interpreters."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copyfile(Path(__file__).resolve().parents[1] / "start.sh", self.root / "start.sh")
        self.bin = self.root / "test-bin"
        self.bin.mkdir()
        (self.bin / "dirname").symlink_to(shutil.which("dirname"))
        self.environment = dict(os.environ, PATH=str(self.bin))

    def interpreter(self, body, target=None):
        filename = target or self.bin / "python3"
        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_text("#!/bin/sh\n" + body)
        filename.chmod(0o755)

    def launch(self):
        return subprocess.run(["/bin/sh", "start.sh", "--prepare-only"], cwd=self.root,
                              env=self.environment, capture_output=True, text=True, timeout=5)

    def test_missing_python_gives_installation_guidance(self):
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python 3.10 or later", result.stderr)
        self.assertFalse((self.root / ".venv").exists())

    def test_unsupported_python_stops_before_environment_creation(self):
        self.interpreter('exit 1\n')
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python 3.10 or later", result.stderr)
        self.assertFalse((self.root / ".venv").exists())

    def test_missing_venv_support_explains_recovery(self):
        self.interpreter('if [ "$1" = "-c" ]; then exit 0; fi\nexit 1\n')
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("venv/ensurepip", result.stderr)
        self.assertIn("python3-venv", result.stderr)

    def test_existing_unsupported_environment_does_not_use_another_python(self):
        self.interpreter('exit 0\n')
        self.interpreter('exit 1\n', self.root / ".venv/bin/python")
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rename .venv", result.stderr)
        self.assertIn("keep data/ unchanged", result.stderr)

if __name__ == "__main__":
    unittest.main()
