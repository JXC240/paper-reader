"""Offline launch-agent tests. Never contact the real macOS launchctl."""
import contextlib
import io
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.background_service import BackgroundService, LABEL, LAUNCHCTL, ServiceError, main


class FakeLaunchctl:
    def __init__(self):
        self.calls = []
        self.loaded = False
        self.disabled = False
        self.fail = None
        self.print_error = None

    def __call__(self, arguments, **kwargs):
        self.calls.append((arguments, kwargs))
        if arguments[0] != LAUNCHCTL:
            return subprocess.CompletedProcess(arguments, 0, "", "")
        action = arguments[1]
        if action == self.fail:
            return subprocess.CompletedProcess(arguments, 5, "", "Input/output error from test")
        if action == "print":
            if self.print_error:
                return subprocess.CompletedProcess(arguments, 1, "", self.print_error)
            if self.loaded:
                return subprocess.CompletedProcess(arguments, 0,
                    "service = {\n state = running\n pid = 1234\n environment = {\n PRIVATE_TOKEN = secret\n }\n}", "")
            return subprocess.CompletedProcess(arguments, 113, "", "Could not find service")
        if action == "enable":
            self.disabled = False
        elif action == "disable":
            self.disabled = True
        elif action == "bootstrap":
            self.loaded = True
        elif action == "bootout":
            self.loaded = False
        return subprocess.CompletedProcess(arguments, 0, "", "")


class BackgroundServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reader-后台- ")
        self.addCleanup(self.temp.cleanup)
        self.root = (Path(self.temp.name) / "论文项目 with spaces").resolve()
        self.home = (Path(self.temp.name) / "用户 home").resolve()
        self.fake = FakeLaunchctl()
        self.service = BackgroundService(self.root, self.home, 501, self.fake, "Darwin")
        for name in (".venv/bin/python", "server.py", "web/index.html", "web/app.js",
                     "vendor/pdfjs/build/pdf.mjs", "vendor/pdfjs/build/pdf.worker.mjs",
                     "vendor/pdfjs/web/pdf_viewer.css"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("test fixture", encoding="utf-8")
        (self.root / ".venv/bin/python").chmod(0o700)
        self.port = patch.object(BackgroundService, "require_free_port")
        self.port_mock = self.port.start()
        self.addCleanup(self.port.stop)

    def install(self):
        return self.service.install()

    def write_config(self, value):
        self.service.plist_path.parent.mkdir(parents=True, exist_ok=True)
        with self.service.plist_path.open("wb") as stream:
            plistlib.dump(value, stream)

    def actions(self):
        return [args[1] for args, _ in self.fake.calls if args[0] == LAUNCHCTL]

    def test_plist_is_exact_local_project_and_has_privacy_and_restart_options(self):
        self.install()
        with self.service.plist_path.open("rb") as stream:
            value = plistlib.load(stream)
        self.assertEqual(value, self.service.configuration())
        self.assertEqual(value["ProgramArguments"], [str(self.root / ".venv/bin/python"),
                         str(self.root / "server.py"), "--port", "8877", "--data-dir", str(self.root / "data")])
        self.assertEqual(value["WorkingDirectory"], str(self.root.resolve()))
        self.assertIs(value["KeepAlive"], True)
        self.assertIs(value["RunAtLoad"], True)
        self.assertEqual(value["ThrottleInterval"], 10)
        self.assertEqual(value["Umask"], 0o077)
        self.assertEqual(self.service.plist_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.service.log_dir / "stdout.log").stat().st_mode & 0o777, 0o600)
        self.assertNotIn("EnvironmentVariables", value)
        self.assertNotIn("Sockets", value)
        self.assertNotIn("--open", value["ProgramArguments"])

    def test_install_loaded_is_idempotent_and_never_rewrites(self):
        self.install()
        before = self.service.plist_path.read_bytes()
        count = len(self.fake.calls)
        self.assertIn("无需重复", self.install())
        self.assertEqual(len(self.fake.calls), count + 1)
        self.assertEqual(self.service.plist_path.read_bytes(), before)
        self.assertEqual(self.actions().count("bootstrap"), 1)

    def test_install_existing_unloaded_uses_start(self):
        self.write_config(self.service.configuration())
        self.install()
        self.assertTrue(self.fake.loaded)
        self.assertEqual(self.actions(), ["print", "print", "enable", "bootstrap"])

    def test_stop_disables_then_boots_out_and_is_idempotent(self):
        self.install()
        self.fake.calls.clear()
        self.assertIn("登录后也不会自启", self.service.stop())
        self.assertEqual(self.actions(), ["print", "disable", "bootout", "print"])
        self.assertTrue(self.fake.disabled)
        self.assertFalse(self.fake.loaded)
        self.assertTrue(self.service.plist_path.exists())
        self.fake.calls.clear()
        self.service.stop()
        self.assertEqual(self.actions(), ["print", "disable"])

    def test_start_enables_then_bootstraps_and_does_not_duplicate_loaded(self):
        self.install()
        self.service.stop()
        self.fake.calls.clear()
        self.service.start()
        self.assertEqual(self.actions(), ["print", "enable", "bootstrap"])
        self.assertFalse(self.fake.disabled)
        self.fake.calls.clear()
        self.service.start()
        self.assertEqual(self.actions(), ["print", "enable"])

    def test_stop_waits_for_stale_job_to_disappear_before_next_start(self):
        self.install()
        stale = {"state": "running", "pid": 1234}
        with patch.object(self.service, "job_state", side_effect=[stale, stale, stale, None]) as state:
            with patch("scripts.background_service.time.sleep") as sleep:
                self.service.stop()
        self.assertEqual(state.call_count, 4)
        self.assertEqual(sleep.call_count, 2)
        for call in sleep.call_args_list:
            self.assertLessEqual(call.args[0], 0.05)
        self.fake.calls.clear()
        self.service.start()
        self.assertEqual(self.actions(), ["print", "enable", "bootstrap"])
        self.assertTrue(self.fake.loaded)

    def test_stop_polling_timeout_reports_unconfirmed_stop_and_preserves_config(self):
        self.install()
        before = self.service.plist_path.read_bytes()
        stale = {"state": "running", "pid": 1234}
        with patch.object(self.service, "job_state", return_value=stale):
            with patch("scripts.background_service.time.monotonic", side_effect=[100, 100, 100.05, 105.1]):
                with patch("scripts.background_service.time.sleep") as sleep:
                    with self.assertRaisesRegex(ServiceError, "5 秒内仍未确认卸载完成"):
                        self.service.stop()
        self.assertEqual(sleep.call_count, 1)
        self.assertTrue(self.fake.disabled)
        self.assertEqual(self.service.plist_path.read_bytes(), before)

    def test_uninstall_waiting_timeout_does_not_remove_configuration(self):
        self.install()
        with patch.object(self.service, "wait_for_unload", side_effect=ServiceError("未确认卸载完成")):
            with self.assertRaisesRegex(ServiceError, "未确认卸载完成"):
                self.service.uninstall()
        self.assertTrue(self.service.plist_path.exists())
        self.assertEqual(list(self.service.log_dir.glob("*.uninstalled-*.plist")), [])

    def test_stop_and_uninstall_absent_are_non_mutating(self):
        self.service.stop()
        self.service.uninstall()
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.service.plist_path.exists())

    def test_uninstall_preserves_data_logs_and_moves_owned_config(self):
        self.install()
        (self.root / "data").mkdir()
        record = self.root / "data/reading.json"
        record.write_text("private annotation", encoding="utf-8")
        log = self.service.log_dir / "stdout.log"
        log.write_text("old log", encoding="utf-8")
        self.service.uninstall()
        self.assertFalse(self.service.plist_path.exists())
        self.assertEqual(record.read_text(), "private annotation")
        self.assertEqual(log.read_text(), "old log")
        backups = list(self.service.log_dir.glob("*.uninstalled-*.plist"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(plistlib.loads(backups[0].read_bytes()), self.service.configuration())
        self.service.uninstall()
        self.assertEqual(len(list(self.service.log_dir.glob("*.uninstalled-*.plist"))), 1)

    def test_foreign_or_modified_config_is_never_overwritten_stopped_or_deleted(self):
        for foreign in ({"Label": LABEL}, self.service.configuration() | {"WorkingDirectory": "/other/project"},
                        self.service.configuration() | {"ProgramArguments": ["/other/python"]}):
            self.write_config(foreign)
            before = self.service.plist_path.read_bytes()
            self.assertEqual(self.service.is_installed(), 2)
            for action in ("install", "start", "stop", "uninstall", "status"):
                with self.assertRaisesRegex(ServiceError, "拒绝修改"):
                    getattr(self.service, action)()
                self.assertEqual(self.service.plist_path.read_bytes(), before)
            self.assertEqual(self.fake.calls, [])

    def test_broken_or_symlink_config_is_protected(self):
        self.service.plist_path.parent.mkdir(parents=True)
        self.service.plist_path.write_text("not plist")
        self.assertEqual(self.service.is_installed(), 2)
        with self.assertRaises(ServiceError):
            self.install()
        self.service.plist_path.write_text('<?xml version="1.0"?><plist version="1.0"><dict><key>Label</key>')
        self.assertEqual(self.service.is_installed(), 2)
        with self.assertRaises(ServiceError):
            self.service.uninstall()
        self.service.plist_path.unlink()
        target = self.home / "foreign.plist"
        target.write_bytes(plistlib.dumps(self.service.configuration()))
        self.service.plist_path.symlink_to(target)
        self.assertEqual(self.service.is_installed(), 2)
        with self.assertRaises(ServiceError):
            self.service.uninstall()
        self.assertTrue(target.exists())

    def test_matching_label_without_ownership_is_not_adopted(self):
        self.fake.loaded = True
        with self.assertRaisesRegex(ServiceError, "拒绝接管"):
            self.install()
        self.assertEqual(self.actions(), ["print"])
        self.assertFalse(self.service.plist_path.exists())

    def test_busy_port_never_kills_or_writes_configuration(self):
        self.port_mock.side_effect = ServiceError("端口已占用")
        with self.assertRaisesRegex(ServiceError, "占用"):
            self.install()
        self.assertFalse(self.service.plist_path.exists())
        self.assertEqual(self.actions(), ["print"])

    def test_missing_dependency_and_missing_asset_are_clear_and_non_mutating(self):
        (self.root / "vendor/pdfjs/build/pdf.mjs").unlink()
        with self.assertRaisesRegex(ServiceError, "运行环境不完整"):
            self.install()
        self.assertFalse(self.service.plist_path.exists())

    def test_bootstrap_failure_removes_only_new_config_keeps_logs(self):
        self.fake.fail = "bootstrap"
        with self.assertRaisesRegex(ServiceError, "Input/output error from test"):
            self.install()
        self.assertFalse(self.service.plist_path.exists())
        self.assertTrue((self.service.log_dir / "stderr.log").exists())
        self.assertNotIn("bootout", self.actions())

    def test_enable_failure_rolls_back_new_config(self):
        self.fake.fail = "enable"
        with self.assertRaises(ServiceError):
            self.install()
        self.assertFalse(self.service.plist_path.exists())
        self.assertNotIn("bootstrap", self.actions())

    def test_start_failure_preserves_preexisting_owned_config(self):
        self.write_config(self.service.configuration())
        before = self.service.plist_path.read_bytes()
        self.fake.fail = "bootstrap"
        with self.assertRaises(ServiceError):
            self.service.start()
        self.assertEqual(self.service.plist_path.read_bytes(), before)

    def test_install_failure_does_not_delete_concurrently_replaced_config(self):
        def replace_on_enable(arguments, **kwargs):
            if arguments[:2] == [LAUNCHCTL, "enable"]:
                replacement = self.service.plist_path.with_suffix(".replacement")
                replacement.write_bytes(plistlib.dumps({"Label": "someone-else"}))
                os.replace(replacement, self.service.plist_path)
                return subprocess.CompletedProcess(arguments, 1, "", "test failure")
            return self.fake(arguments, **kwargs)
        self.service.runner = replace_on_enable
        with self.assertRaises(ServiceError):
            self.install()
        self.assertEqual(plistlib.loads(self.service.plist_path.read_bytes()), {"Label": "someone-else"})

    def test_job_disappearing_before_bootout_is_safe_and_idempotent(self):
        self.install()
        def absent_on_bootout(arguments, **kwargs):
            if arguments[:2] == [LAUNCHCTL, "bootout"]:
                self.fake.loaded = False
                return subprocess.CompletedProcess(arguments, 3, "", "No such process")
            return self.fake(arguments, **kwargs)
        self.service.runner = absent_on_bootout
        self.service.stop()
        self.assertTrue(self.service.plist_path.exists())
        self.assertTrue(self.fake.disabled)

    def test_symlink_log_is_not_written_or_truncated(self):
        self.service.log_dir.mkdir(parents=True)
        external = self.home / "private-file"
        external.write_text("keep me")
        (self.service.log_dir / "stdout.log").symlink_to(external)
        with self.assertRaisesRegex(ServiceError, "日志目标不是普通文件"):
            self.install()
        self.assertEqual(external.read_text(), "keep me")
        self.assertFalse(self.service.plist_path.exists())

    def test_symlink_log_directory_is_not_used_by_install(self):
        external = self.home / "another-directory"
        external.mkdir(parents=True)
        self.service.log_dir.parent.mkdir(parents=True)
        self.service.log_dir.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ServiceError, "日志目录不是普通目录"):
            self.install()
        self.assertEqual(list(external.iterdir()), [])
        self.assertFalse(self.service.plist_path.exists())

    def test_log_directory_that_is_a_file_is_not_used_by_install(self):
        self.service.log_dir.parent.mkdir(parents=True)
        self.service.log_dir.write_text("keep directory placeholder")
        with self.assertRaisesRegex(ServiceError, "日志目录不是普通目录"):
            self.install()
        self.assertEqual(self.service.log_dir.read_text(), "keep directory placeholder")
        self.assertFalse(self.service.plist_path.exists())

    def test_uninstall_refuses_redirected_log_directory_before_stopping(self):
        self.install()
        before = self.service.plist_path.read_bytes()
        original_logs = self.home / "original-logs"
        self.service.log_dir.rename(original_logs)
        self.service.log_dir.symlink_to(original_logs, target_is_directory=True)
        self.fake.calls.clear()
        with self.assertRaisesRegex(ServiceError, "日志目录不是普通目录"):
            self.service.uninstall()
        self.assertTrue(self.fake.loaded)
        self.assertFalse(self.fake.disabled)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.service.plist_path.read_bytes(), before)
        self.assertEqual(list(original_logs.glob("*.uninstalled-*.plist")), [])

    def test_uninstall_refuses_non_directory_log_path_before_stopping(self):
        self.install()
        self.service.log_dir.rename(self.home / "original-logs")
        self.service.log_dir.write_text("keep placeholder")
        self.fake.calls.clear()
        with self.assertRaisesRegex(ServiceError, "日志目录不是普通目录"):
            self.service.uninstall()
        self.assertTrue(self.fake.loaded)
        self.assertEqual(self.fake.calls, [])
        self.assertTrue(self.service.plist_path.exists())
        self.assertEqual(self.service.log_dir.read_text(), "keep placeholder")

    def test_failed_pypdf_import_is_explained_without_installing_packages(self):
        def missing_pypdf(arguments, **kwargs):
            if arguments[0] != LAUNCHCTL:
                return subprocess.CompletedProcess(arguments, 1, "", "No module named pypdf")
            return self.fake(arguments, **kwargs)
        self.service.runner = missing_pypdf
        with self.assertRaisesRegex(ServiceError, "No module named pypdf"):
            self.install()
        self.assertFalse(self.service.plist_path.exists())

    def test_real_server_binds_only_loopback(self):
        # The launch agent invokes this server with no alternative host option.
        server = Path(__file__).resolve().parents[1] / "server.py"
        self.assertIn('ReaderServer(("127.0.0.1", args.port), store)', server.read_text())

    def test_bootout_failure_preserves_config_and_reports_real_error(self):
        self.install()
        self.fake.fail = "bootout"
        with self.assertRaisesRegex(ServiceError, "Input/output error from test"):
            self.service.uninstall()
        self.assertTrue(self.service.plist_path.exists())
        self.assertEqual(list(self.service.log_dir.glob("*.uninstalled-*.plist")), [])

    def test_print_permission_failure_is_not_treated_as_absent(self):
        self.fake.print_error = "Operation not permitted"
        with self.assertRaisesRegex(ServiceError, "Operation not permitted"):
            self.install()
        self.assertFalse(self.service.plist_path.exists())

    def test_status_is_readonly_and_does_not_expose_launchctl_environment(self):
        self.install()
        before = self.service.plist_path.read_bytes()
        self.fake.calls.clear()
        status = self.service.status()
        self.assertIn("PID：1234", status)
        self.assertIn(str(self.root / "data"), status)
        self.assertNotIn("PRIVATE_TOKEN", status)
        self.assertNotIn("secret", status)
        self.assertEqual(self.actions(), ["print"])
        self.assertEqual(self.service.plist_path.read_bytes(), before)

    def test_macos_only_no_commands_on_other_system(self):
        self.service.system = "Linux"
        self.assertEqual(self.service.is_installed(), 2)
        for action in ("install", "start", "stop", "status", "uninstall"):
            with self.assertRaisesRegex(ServiceError, "仅支持 macOS"):
                getattr(self.service, action)()
        self.assertEqual(self.fake.calls, [])

    def test_is_installed_cli_is_silent_and_returns_three_way_status(self):
        for expected in (1, 0, 2):
            if expected == 0:
                self.write_config(self.service.configuration())
            elif expected == 2:
                self.write_config({"Label": "foreign"})
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("scripts.background_service.BackgroundService", return_value=self.service):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    self.assertEqual(main(["is-installed"]), expected)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "")

    def test_cli_failure_returns_nonzero_and_explains_error(self):
        self.fake.print_error = "Operation not permitted"
        stderr = io.StringIO()
        with patch("scripts.background_service.BackgroundService", return_value=self.service):
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(main(["install"]), 2)
        self.assertIn("Operation not permitted", stderr.getvalue())

    def test_all_commands_use_argument_lists_no_shell_sudo_kill_or_network(self):
        self.install()
        self.service.status()
        self.service.stop()
        self.service.start()
        self.service.uninstall()
        for arguments, kwargs in self.fake.calls:
            self.assertIsInstance(arguments, list)
            self.assertNotIn("shell", kwargs)
            self.assertGreater(kwargs["timeout"], 0)
            self.assertLessEqual(kwargs["timeout"], 10)
            for forbidden in ("sudo", "kill", "killall", "pkill", "caffeinate", "pmset", "curl"):
                self.assertNotIn(forbidden, arguments)
        self.assertEqual(self.service.configuration()["Label"], LABEL)


if __name__ == "__main__":
    unittest.main()
