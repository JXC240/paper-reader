import unittest
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


if __name__ == "__main__":
    unittest.main()
