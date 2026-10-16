"""Wait briefly for our loopback reader before opening a browser window."""
import time
import urllib.error
import urllib.request


def wait_for_reader(timeout=20):
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8877/", timeout=1) as response:
                if response.status == 200 and response.headers.get("Server", "").startswith("PaperReader/"):
                    return True
                # A different service must not be presented as the reader.
                return False
        except (OSError, urllib.error.URLError):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.25)


if __name__ == "__main__":
    if not wait_for_reader():
        print("阅读器尚未就绪，请检查后台服务状态及 Library/Logs/PaperReader 中的日志。")
        raise SystemExit(1)
