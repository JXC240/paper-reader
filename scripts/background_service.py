"""Manage only this checkout's optional, user-level macOS launch agent.

No sudo, process killing, network exposure, or sleep-policy changes are used.
Paper Reader itself binds 127.0.0.1; launchd runs that same server unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import plistlib
import re
import socket
import subprocess
import sys
import time
from xml.parsers.expat import ExpatError

LABEL = "local.paper-reader"
PORT = 8877
LAUNCHCTL = "/bin/launchctl"
STOP_WAIT_SECONDS = 5.0


class ServiceError(RuntimeError):
    """A safe, user-actionable failure; never silently suppress launchctl errors."""


class BackgroundService:
    def __init__(self, root=None, home=None, uid=None, runner=None, system=None):
        self.root = Path(root or Path(__file__).resolve().parents[1]).resolve()
        self.home = Path(home or Path.home()).resolve()
        self.uid = os.getuid() if uid is None else uid
        self.runner = subprocess.run if runner is None else runner
        self.system = platform.system() if system is None else system
        self.plist_path = self.home / "Library/LaunchAgents" / f"{LABEL}.plist"
        self.log_dir = self.home / "Library/Logs/PaperReader"
        self.domain = f"gui/{self.uid}"
        self.target = f"{self.domain}/{LABEL}"

    def require_macos(self):
        if self.system != "Darwin":
            raise ServiceError("后台托管仅支持 macOS；其他系统仍可使用 start.sh。")

    def configuration(self):
        return {
            "Label": LABEL,
            "ProgramArguments": [str(self.root / ".venv/bin/python"),
                                 str(self.root / "server.py"), "--port", str(PORT),
                                 "--data-dir", str(self.root / "data")],
            "WorkingDirectory": str(self.root),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "Umask": 0o077,
            "StandardOutPath": str(self.log_dir / "stdout.log"),
            "StandardErrorPath": str(self.log_dir / "stderr.log"),
        }

    def is_installed(self):
        """Return 0 for our exact configuration, 1 if absent, 2 if unsafe."""
        try:
            self.require_macos()
            if not self.plist_path.exists() and not self.plist_path.is_symlink():
                return 1
            if self.plist_path.is_symlink() or not self.plist_path.is_file():
                return 2
            with self.plist_path.open("rb") as stream:
                value = plistlib.load(stream)
            return 0 if value == self.configuration() else 2
        except (OSError, ValueError, ExpatError, plistlib.InvalidFileException, ServiceError):
            return 2

    def require_owned_configuration(self):
        ownership = self.is_installed()
        if ownership == 2:
            raise ServiceError(f"拒绝修改外来、损坏或非本项目的配置：{self.plist_path}")
        if ownership == 1:
            raise ServiceError("尚未安装本项目的后台服务，请先运行 install。")

    def run(self, arguments, timeout=10):
        try:
            return self.runner(arguments, capture_output=True, text=True,
                               check=False, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ServiceError(f"无法执行 {Path(arguments[0]).name}：{error}") from error

    @staticmethod
    def diagnostic(result):
        return (result.stderr or result.stdout or "未返回错误详情").strip()[-2000:]

    @staticmethod
    def is_missing_job(detail):
        return bool(re.search(r"could not find service|no such process|service not found",
                              detail, re.IGNORECASE))

    def launchctl(self, *arguments):
        result = self.run([LAUNCHCTL, *arguments])
        if result.returncode:
            raise ServiceError(f"launchctl {arguments[0]} 失败（{result.returncode}）："
                               f"{self.diagnostic(result)}")
        return result

    def job_state(self, timeout=10):
        result = self.run([LAUNCHCTL, "print", self.target], timeout=timeout)
        if result.returncode:
            detail = self.diagnostic(result)
            # launchctl's absent-job error is expected; permission/domain and
            # other failures must not be mistaken for an absent service.
            if self.is_missing_job(detail):
                return None
            raise ServiceError(f"无法查询后台服务（{result.returncode}）：{detail}")
        state = re.search(r"^\s*state = (\S+)", result.stdout, re.MULTILINE)
        pid = re.search(r"^\s*pid = (\d+)\s*$", result.stdout, re.MULTILINE)
        return {"state": state.group(1) if state else "loaded",
                "pid": int(pid.group(1)) if pid else None}

    def validate_dependencies(self):
        required = (".venv/bin/python", "server.py", "web/index.html", "web/app.js",
                    "vendor/pdfjs/build/pdf.mjs", "vendor/pdfjs/build/pdf.worker.mjs",
                    "vendor/pdfjs/web/pdf_viewer.css")
        missing = [name for name in required if not (self.root / name).is_file()]
        if missing or not os.access(self.root / ".venv/bin/python", os.X_OK):
            detail = "、".join(missing) or ".venv/bin/python 不可执行"
            raise ServiceError(f"运行环境不完整：{detail}。请先使用启动阅读器准备依赖。")
        result = self.run([str(self.root / ".venv/bin/python"), "-c", "import pypdf"])
        if result.returncode:
            raise ServiceError(f"Python 依赖不可用：{self.diagnostic(result)}。请先准备依赖。")

    @staticmethod
    def require_free_port():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", PORT))
        except OSError as error:
            raise ServiceError(f"本机端口 {PORT} 已被占用或不可用。请先确认并停止旧服务，"
                               "此工具不会自动结束任何进程。") from error

    def require_log_directory(self):
        if self.log_dir.is_symlink() or (self.log_dir.exists() and not self.log_dir.is_dir()):
            raise ServiceError(f"日志目录不是普通目录，拒绝使用：{self.log_dir}")

    def prepare_logs(self):
        self.require_log_directory()
        self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in ("stdout.log", "stderr.log"):
            path = self.log_dir / name
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise ServiceError(f"日志目标不是普通文件，拒绝使用：{path}")
            descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            os.close(descriptor)

    def install(self):
        self.require_macos()
        ownership = self.is_installed()
        if ownership == 2:
            self.require_owned_configuration()
        if ownership == 0:
            if self.job_state() is not None:
                return "本项目后台服务已安装并加载，无需重复安装。"
            return self.start()
        # Never adopt a job merely because its label matches ours.
        if self.job_state() is not None:
            raise ServiceError("同名后台任务已加载但没有可核验的本项目配置，拒绝接管。")
        self.validate_dependencies()
        self.require_free_port()
        self.prepare_logs()
        self.plist_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = None
        created_identity = None
        try:
            descriptor = os.open(self.plist_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            metadata = os.fstat(descriptor)
            created_identity = (metadata.st_dev, metadata.st_ino)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = None
                plistlib.dump(self.configuration(), stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            self.launchctl("enable", self.target)
            self.launchctl("bootstrap", self.domain, str(self.plist_path))
        except (OSError, ServiceError) as error:
            if descriptor is not None:
                os.close(descriptor)
            # Roll back only the file created by this call, never a concurrent
            # replacement or a pre-existing configuration from another checkout.
            if created_identity is not None and not self.plist_path.is_symlink():
                try:
                    metadata = self.plist_path.stat()
                    if (metadata.st_dev, metadata.st_ino) == created_identity:
                        self.plist_path.unlink()
                except FileNotFoundError:
                    pass
            raise ServiceError(f"安装未完成，本次新建配置已回滚（若存在）：{error}") from error
        return "后台服务已安装并加载；登录后自动启动，异常退出后由 macOS 重启。"

    def start(self):
        self.require_macos()
        self.require_owned_configuration()
        state = self.job_state()
        if state is None:
            self.validate_dependencies()
            self.require_free_port()
            self.prepare_logs()
        self.launchctl("enable", self.target)
        if state is None:
            self.launchctl("bootstrap", self.domain, str(self.plist_path))
        return "后台服务已启用并加载。" if state is None else "后台服务已加载，已确保启用。"

    def stop(self):
        self.require_macos()
        if self.is_installed() == 1:
            return "未安装本项目后台服务，没有修改任何任务。"
        self.require_owned_configuration()
        state = self.job_state()
        self.launchctl("disable", self.target)
        if state is not None:
            result = self.run([LAUNCHCTL, "bootout", self.target])
            if result.returncode and not self.is_missing_job(self.diagnostic(result)):
                raise ServiceError(f"launchctl bootout 失败（{result.returncode}）："
                                   f"{self.diagnostic(result)}")
            self.wait_for_unload()
        return "后台服务已停止并禁用，登录后也不会自启；再次启动须运行 start。配置、日志和论文标注均保留。"

    def wait_for_unload(self):
        """bootout acknowledges a request before the job has fully disappeared."""
        deadline = time.monotonic() + STOP_WAIT_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ServiceError("后台服务已禁用，但在 5 秒内仍未确认卸载完成；"
                                   "不能报告已停止，请稍后检查 status。配置、日志和数据保留。")
            # Bound each query too, so a stuck launchctl cannot turn polling
            # into an unbounded wait. No launchctl bootout --wait is used.
            if self.job_state(timeout=min(remaining, 1.0)) is None:
                return
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.05, remaining))

    def uninstall(self):
        self.require_macos()
        if self.is_installed() == 1:
            return "未安装本项目后台服务，无需卸载；论文、标注和日志未改动。"
        self.require_owned_configuration()
        self.require_log_directory()
        self.stop()
        # Revalidate after launchctl calls, before moving anything.
        self.require_owned_configuration()
        self.require_log_directory()
        self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.log_dir / f"{LABEL}.uninstalled-{stamp}.plist"
        if backup.exists():
            raise ServiceError(f"配置备份已存在，拒绝覆盖：{backup}")
        self.plist_path.rename(backup)
        return f"后台服务已卸载；论文、标注与日志保留。配置备份：{backup}"

    def status(self):
        self.require_macos()
        ownership = self.is_installed()
        if ownership == 2:
            self.require_owned_configuration()
        state = self.job_state()
        installed = "已安装本项目配置" if ownership == 0 else "未安装本项目配置"
        if state is None:
            status = "未加载／未运行"
        else:
            status = f"已加载；状态：{state['state']}"
            if state["pid"] is not None:
                status += f"；PID：{state['pid']}"
            if ownership == 1:
                status += "（没有本项目配置，不接管此任务）"
        return (f"{installed}；{status}\n项目：{self.root}\n配置：{self.plist_path}\n"
                f"日志：{self.log_dir}\n数据：{self.root / 'data'}\n"
                f"地址：http://127.0.0.1:{PORT}/")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Paper Reader 可选的 macOS 本机后台服务")
    parser.add_argument("action", choices=("install", "start", "stop", "status", "uninstall", "is-installed"))
    args = parser.parse_args(argv)
    service = BackgroundService()
    if args.action == "is-installed":
        return service.is_installed()
    try:
        print(getattr(service, args.action)())
    except (ServiceError, OSError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
