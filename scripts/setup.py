"""Install pinned browser assets locally; no CDN is used while reading."""
import base64
import hashlib
import io
import json
from pathlib import Path
import ssl
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ASSETS = (
    "build/pdf.mjs", "build/pdf.worker.mjs", "web/pdf_viewer.css",
    "cmaps/78-EUC-H.bcmap", "standard_fonts/FoxitDingbats.pfb",
    "wasm/jbig2.wasm", "wasm/openjpeg.wasm", "wasm/qcms_bg.wasm", "LICENSE",
)


def assets_ready(target):
    """A version marker alone cannot prove a copied/partial installation works."""
    return all((target / name).is_file() and (target / name).stat().st_size > 0
               for name in REQUIRED_ASSETS)


def main():
    spec = json.loads((ROOT / "assets-lock.json").read_text())["pdfjs-dist"]
    target = ROOT / "vendor" / "pdfjs"
    marker = target / ".version"
    if marker.exists() and marker.read_text().strip() == spec["version"] and assets_ready(target):
        print("PDF.js assets already installed:", spec["version"])
        return
    print("Downloading pinned PDF.js assets:", spec["version"])
    context = ssl.create_default_context()
    # Some python.org macOS installs have no configured CA file. Use the
    # operating system's CA bundle without disabling certificate verification.
    if not ssl.get_default_verify_paths().cafile and Path("/etc/ssl/cert.pem").is_file():
        context.load_verify_locations("/etc/ssl/cert.pem")
    with urllib.request.urlopen(spec["url"], timeout=120, context=context) as response:
        payload = response.read()
    actual = "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode()
    if actual != spec["integrity"]:
        raise RuntimeError("PDF.js integrity check failed")
    target.mkdir(parents=True, exist_ok=True)
    prefixes = ("build/", "cmaps/", "standard_fonts/", "wasm/", "web/pdf_viewer.css")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            relative = member.name.removeprefix("package/")
            if not member.isfile() or not (relative.startswith(prefixes) or relative == "LICENSE"):
                continue
            destination = (target / relative).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise RuntimeError("Unexpected asset path")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source:
                destination.write_bytes(source.read())
    if not assets_ready(target):
        raise RuntimeError("PDF.js archive is missing required assets; installation was not accepted")
    marker.write_text(spec["version"] + "\n")
    print("PDF.js assets verified and ready.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, tarfile.TarError) as error:
        print(f"PDF.js 安装失败 / installation failed: {error}", file=sys.stderr)
        print("请检查网络后重试；保留 data/。Check the connection and retry; keep data/ unchanged.", file=sys.stderr)
        sys.exit(1)
