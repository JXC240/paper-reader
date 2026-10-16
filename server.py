"""Local-only PDF library, atomic annotation storage, and portable exports."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import threading
import urllib.parse
import uuid
import webbrowser

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Highlight
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                           FloatObject, NameObject, RectangleObject, TextStringObject)

ROOT = Path(__file__).resolve().parent
ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_UPLOAD = 100 * 1024 * 1024
COLORS = {"yellow": "FFE066", "green": "A8DFBE", "pink": "FFB4CC", "blue": "91C9FF",
          "purple": "C7B4F5", "orange": "FFBE75", "red": "FF9696"}
LINE_COLORS = {"yellow": "B78A00", "green": "308566", "pink": "BE4F83", "blue": "276DB6",
               "purple": "7750B7", "orange": "BD6B17", "red": "C33F45"}
COLOR_LABELS = dict(zip(COLORS, ("黄色", "绿色", "粉色", "蓝色", "紫色", "橙色", "红色")))
STYLES = {"highlight": ("高亮", "/Highlight"), "underline": ("下划线", "/Underline"),
          "strikeout": ("删除线", "/StrikeOut")}


def line_appearance(writer, annotation, quads, style, color):
    """Provide a standard PDF appearance so line placement does not depend on viewer heuristics."""
    x0, y0, x1, y1 = (float(v) for v in annotation["/Rect"])
    annotation[NameObject("/Rect")] = RectangleObject((x0 - 1, y0 - 1, x1 + 1, y1 + 1))
    x0, y0 = x0 - 1, y0 - 1
    rgb = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    commands = ["q", " ".join(f"{v:.6f}" for v in rgb) + " RG", "0.85 w"]
    for quad in quads:
        if style == "underline":
            start, end = quad[4:6], quad[6:8]
        else:
            start = [(quad[0] + quad[4]) / 2, (quad[1] + quad[5]) / 2]
            end = [(quad[2] + quad[6]) / 2, (quad[3] + quad[7]) / 2]
        commands.append(f"{start[0] - x0:.6f} {start[1] - y0:.6f} m {end[0] - x0:.6f} {end[1] - y0:.6f} l S")
    commands.append("Q")
    appearance = DecodedStreamObject()
    appearance.set_data(("\n".join(commands) + "\n").encode("ascii"))
    appearance.update({NameObject("/Type"): NameObject("/XObject"),
                       NameObject("/Subtype"): NameObject("/Form"),
                       NameObject("/BBox"): RectangleObject((0, 0, x1 + 1 - x0, y1 + 1 - y0)),
                       NameObject("/Resources"): DictionaryObject()})
    annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): writer._add_object(appearance)})


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, content: bytes):
    """Replace only a complete, flushed file; never truncate the live record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


class InvalidRequest(ValueError):
    pass


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def folder(self, doc_id):
        if not ID_PATTERN.fullmatch(doc_id):
            raise InvalidRequest("无效的论文编号")
        return self.directory / "documents" / doc_id

    def read(self, doc_id):
        with self.lock:
            record = json.loads((self.folder(doc_id) / "record.json").read_text("utf-8"))
            # Old records remain unchanged on disk until the reader saves an edit.
            record.setdefault("bookmarks", [])
            return record

    def list(self):
        with self.lock:
            result = []
            for path in (self.directory / "documents").glob("*/record.json"):
                item = json.loads(path.read_text("utf-8"))
                result.append({k: item[k] for k in ("id", "name", "pageCount", "updatedAt")})
            return sorted(result, key=lambda item: item["updatedAt"], reverse=True)

    def active(self):
        path = self.directory / "active.json"
        return json.loads(path.read_text())["id"] if path.exists() else None

    def save(self, record, *, activate=False):
        with self.lock:
            record["updatedAt"] = now()
            atomic_json(self.folder(record["id"]) / "record.json", record)
            if activate:
                atomic_json(self.directory / "active.json", {"id": record["id"]})
            if self.active() == record["id"]:
                # This portable snapshot is the file the current chat can read.
                atomic_json(self.directory / "current-reading.json", record)
                atomic_write(self.directory / "current-reading.md", self.markdown(record).encode())
            return record

    def import_pdf(self, payload, filename):
        if not payload.startswith(b"%PDF-"):
            raise InvalidRequest("请选择 PDF 文件")
        try:
            reader = PdfReader(io.BytesIO(payload))
            if reader.is_encrypted and not reader.decrypt(""):
                raise InvalidRequest("首版暂不支持需要密码的 PDF，请先保存解密副本")
            count = len(reader.pages)
            if count == 0:
                raise InvalidRequest("PDF 中没有页面")
        except InvalidRequest:
            raise
        except Exception as error:
            raise InvalidRequest("PDF 无法读取，文件可能损坏") from error
        doc_id = hashlib.sha256(payload).hexdigest()
        clean_name = Path(filename.replace("\\", "/")).name[:240] or "未命名论文.pdf"
        with self.lock:
            if (self.folder(doc_id) / "record.json").exists():
                return self.save(self.read(doc_id), activate=True)
            record = {"schemaVersion": 1, "id": doc_id, "name": clean_name,
                      "pageCount": count, "createdAt": now(), "updatedAt": now(),
                      "position": {"page": 1, "zoom": "fit"}, "highlights": [], "bookmarks": []}
            atomic_write(self.folder(doc_id) / "original.pdf", payload)
            return self.save(record, activate=True)

    def add_highlight(self, doc_id, body):
        with self.lock:
            record = self.read(doc_id)
            highlight_id = body.get("clientId", uuid.uuid4().hex)
            if not isinstance(highlight_id, str) or not re.fullmatch(r"[0-9a-f]{32}", highlight_id):
                raise InvalidRequest("高亮记录编号无效")
            existing = next((h for h in record["highlights"] if h["id"] == highlight_id), None)
            if existing:
                return existing  # A retried response must not duplicate a saved selection.
            page = body.get("page")
            if type(page) is not int or not 1 <= page <= record["pageCount"]:
                raise InvalidRequest("高亮页码无效")
            raw_text = body.get("rawText", "")
            if not isinstance(raw_text, str) or not raw_text.strip() or len(raw_text) > 30000:
                raise InvalidRequest("选中文字为空或过长；请分段标记")
            quads = body.get("quads")
            if not isinstance(quads, list) or not 1 <= len(quads) <= 500:
                raise InvalidRequest("高亮位置无效")
            pdf_page = PdfReader(self.folder(doc_id) / "original.pdf").pages[page - 1]
            box = pdf_page.cropbox
            for quad in quads:
                if not isinstance(quad, list) or len(quad) != 8:
                    raise InvalidRequest("高亮坐标无效")
                if any(type(v) not in (float, int) or not math.isfinite(v) for v in quad):
                    raise InvalidRequest("高亮坐标必须是有限数字")
                if any(not float(box.left) - 2 <= x <= float(box.right) + 2 for x in quad[0::2]):
                    raise InvalidRequest("高亮超出页面")
                if any(not float(box.bottom) - 2 <= y <= float(box.top) + 2 for y in quad[1::2]):
                    raise InvalidRequest("高亮超出页面")
            color = body.get("color", "yellow")
            if not isinstance(color, str) or color not in COLORS:
                raise InvalidRequest("不支持的标注颜色")
            style = body.get("style", "highlight")
            if not isinstance(style, str) or style not in STYLES:
                raise InvalidRequest("不支持的标注方式")
            text_order = body.get("textOrder", 0)
            if type(text_order) is not int or not 0 <= text_order <= 1000000:
                raise InvalidRequest("选文顺序无效")
            highlight = {"id": highlight_id, "page": page, "textOrder": text_order,
                         "pageLabel": str(body.get("pageLabel", page))[:60],
                         "rawText": raw_text, "text": re.sub(r"\s+", " ", raw_text).strip(),
                         "contextBefore": str(body.get("contextBefore", ""))[-5000:],
                         "contextAfter": str(body.get("contextAfter", ""))[:5000],
                         "contextReview": "待核对PDF原文；双栏与公式可能影响文本顺序",
                         "quads": quads, "color": color, "style": style, "kind": "passage", "note": "",
                         "createdAt": now(), "updatedAt": now()}
            record["highlights"].append(highlight)
            self.save(record)
            return highlight

    def update_highlight(self, doc_id, highlight_id, body):
        with self.lock:
            record = self.read(doc_id)
            item = next((h for h in record["highlights"] if h["id"] == highlight_id), None)
            if item is None:
                raise FileNotFoundError()
            if "kind" in body:
                if body["kind"] not in ("passage", "vocabulary"):
                    raise InvalidRequest("类型无效")
                item["kind"] = body["kind"]
            if "note" in body:
                if not isinstance(body["note"], str) or len(body["note"]) > 30000:
                    raise InvalidRequest("笔记过长")
                item["note"] = body["note"]
            for field, allowed in (("color", COLORS), ("style", STYLES)):
                if field in body:
                    if not isinstance(body[field], str) or body[field] not in allowed:
                        raise InvalidRequest("标注颜色或方式无效")
                    item[field] = body[field]
            item["updatedAt"] = now()
            self.save(record)
            return item

    def delete_highlight(self, doc_id, highlight_id):
        with self.lock:
            record = self.read(doc_id)
            matches = [h for h in record["highlights"] if h["id"] == highlight_id]
            if not matches:
                raise FileNotFoundError()
            record["highlights"] = [h for h in record["highlights"] if h["id"] != highlight_id]
            self.save(record)
            return matches[0]

    def save_position(self, doc_id, body):
        with self.lock:
            record = self.read(doc_id)
            page, zoom = body.get("page"), body.get("zoom")
            if type(page) is not int or not 1 <= page <= record["pageCount"]:
                raise InvalidRequest("页码无效")
            if zoom != "fit" and (type(zoom) not in (int, float) or not 0.25 <= zoom <= 4 or not math.isfinite(zoom)):
                raise InvalidRequest("缩放值无效")
            position = {"page": page, "zoom": zoom}
            if "anchor" in body:
                anchor = body["anchor"]
                if not isinstance(anchor, dict) or any(
                    type(anchor.get(axis)) not in (int, float)
                    or not 0 <= anchor[axis] <= 1 or not math.isfinite(anchor[axis])
                    for axis in ("x", "y")
                ):
                    raise InvalidRequest("页内阅读位置无效")
                position["anchor"] = {axis: anchor[axis] for axis in ("x", "y")}
            elif record["position"]["page"] == page and "anchor" in record["position"]:
                # Older clients can change zoom without discarding this page's anchor.
                position["anchor"] = record["position"]["anchor"]
            record["position"] = position
            self.save(record)
            return position

    @staticmethod
    def bookmark_page(record, page):
        if isinstance(page, str):
            if not re.fullmatch(r"[1-9][0-9]*", page):
                raise InvalidRequest("书签页码无效")
            try:
                page = int(page)
            except ValueError as error:
                raise InvalidRequest("书签页码无效") from error
        if type(page) is not int or not 1 <= page <= record["pageCount"]:
            raise InvalidRequest("书签页码无效")
        return page

    def upsert_bookmark(self, doc_id, page, body):
        with self.lock:
            record = self.read(doc_id)
            page = self.bookmark_page(record, page)
            title = body.get("title") if isinstance(body, dict) else None
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
                raise InvalidRequest("书签标题须为1—200个字符")
            title = title.strip()
            item = next((b for b in record["bookmarks"] if b["page"] == page), None)
            if item and item["title"] == title:
                return item  # Retrying an unchanged title must not duplicate a bookmark.
            stamp = now()
            if item:
                item.update(title=title, updatedAt=stamp)
            else:
                item = {"page": page, "title": title, "createdAt": stamp, "updatedAt": stamp}
                record["bookmarks"].append(item)
                record["bookmarks"].sort(key=lambda bookmark: bookmark["page"])
            self.save(record)
            return item

    def delete_bookmark(self, doc_id, page):
        with self.lock:
            record = self.read(doc_id)
            page = self.bookmark_page(record, page)
            item = next((b for b in record["bookmarks"] if b["page"] == page), None)
            if item:
                record["bookmarks"] = [b for b in record["bookmarks"] if b["page"] != page]
                self.save(record)
            return item

    @staticmethod
    def markdown(record):
        lines = ["# " + record["name"], "", "文档 SHA-256：`" + record["id"] + "`", "",
                 "标注表示阅读卡点，不代表已经理解。生词由读者主动确认。删除线仅是读者标记，不代表原文错误或被删除。", "",
                 "请先核对原PDF中的完整句子与上下文，再逐句翻译、解释结构和科研含义。", ""]
        for i, h in enumerate(sorted(record["highlights"], key=lambda h: (h["page"], h.get("textOrder", 0), -max(h["quads"][0][1::2]))), 1):
            lines += [f"## {i}. PDF 第 {h['page']} 页 · 页标签 {h['pageLabel']}", "",
                      "类型：" + ("读者确认的生词" if h["kind"] == "vocabulary" else "整句阅读卡点"), "",
                      "标注：" + STYLES[h.get("style", "highlight")][0] + " · " + COLOR_LABELS[h["color"]], "",
                      "### 标注原文", "", "> " + h["rawText"].replace("\n", "\n> "), "",
                      "### 附近原文（自动提取，需回看PDF核对）", "",
                      h["contextBefore"] + "【标注】" + h["rawText"] + "【标注结束】" + h["contextAfter"], "",
                      "### 讲解／笔记", "", h["note"] or "尚未记录。", "",
                      "记录ID：`" + h["id"] + "`", ""]
        if not record["highlights"]:
            lines += ["尚无标注。", ""]
        return "\n".join(lines)

    def annotated_pdf(self, doc_id):
        with self.lock:
            record = self.read(doc_id)
            reader = PdfReader(self.folder(doc_id) / "original.pdf")
            if reader.is_encrypted:
                reader.decrypt("")
            writer = PdfWriter()
            writer.clone_document_from_reader(reader)
            for h in record["highlights"]:
                style = h.get("style", "highlight")  # Old records remain highlights without a migration.
                color = (COLORS if style == "highlight" else LINE_COLORS)[h["color"]]
                points = [v for q in h["quads"] for v in q]
                xs, ys = points[0::2], points[1::2]
                annotation = Highlight(rect=(min(xs), min(ys), max(xs), max(ys)),
                                       quad_points=ArrayObject([FloatObject(v) for v in points]),
                                       highlight_color=color, printing=True)
                annotation[NameObject("/Subtype")] = NameObject(STYLES[style][1])
                annotation[NameObject("/Contents")] = TextStringObject(h["text"] + ("\n" + h["note"] if h["note"] else ""))
                annotation[NameObject("/T")] = TextStringObject("Paper Reader")
                annotation[NameObject("/NM")] = TextStringObject(h["id"])
                annotation[NameObject("/CA")] = FloatObject(0.4 if style == "highlight" else 1)
                if style != "highlight":
                    line_appearance(writer, annotation, h["quads"], style, color)
                writer.add_annotation(page_number=h["page"] - 1, annotation=annotation)
            output = io.BytesIO()
            writer.write(output)
            return record, output.getvalue()


class ReaderServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store):
        self.store = store
        self.csrf = secrets.token_urlsafe(32)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "PaperReader/0.1"

    def log_message(self, fmt, *args):
        # Keep PDF names, selections, and notes out of access logs.
        if args and str(args[1:2]) != "('200',)":
            super().log_message(fmt, *args)

    def send(self, body=b"", status=200, content_type="application/json; charset=utf-8", filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if filename:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(filename))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, value, status=200):
        self.send(json.dumps(value, ensure_ascii=False).encode(), status)

    def checked(self, mutate=False):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            self.json({"error": "仅允许本机访问"}, 403)
            return False
        origin = self.headers.get("Origin")
        if (origin and origin not in {"http://" + host for host in hosts}) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.json({"error": "不允许跨站访问"}, 403)
            return False
        if mutate and not secrets.compare_digest(self.headers.get("X-Reader-Token", ""), self.server.csrf):
            self.json({"error": "页面已过期，请刷新后重试"}, 403)
            return False
        return True

    def body(self, maximum=1024 * 1024):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise InvalidRequest("请求长度无效") from error
        if not 0 < length <= maximum:
            raise InvalidRequest("文件或记录为空，或超过大小限制")
        return self.rfile.read(length)

    def route(self):
        return urllib.parse.unquote(urllib.parse.urlsplit(self.path).path).strip("/").split("/")

    def do_GET(self):
        if not self.checked():
            return
        try:
            route = self.route()
            store = self.server.store
            if route == ["api", "session"]:
                return self.json({"token": self.server.csrf, "documents": store.list(), "activeId": store.active()})
            if route[:2] == ["api", "documents"] and len(route) == 4:
                doc_id, operation = route[2:]
                if operation == "record":
                    return self.json(store.read(doc_id))
                if operation == "pdf":
                    return self.send((store.folder(doc_id) / "original.pdf").read_bytes(), content_type="application/pdf")
                if operation in ("markdown", "annotated.pdf"):
                    if operation == "markdown":
                        record = store.read(doc_id)
                        payload = store.markdown(record).encode()
                        extension, content_type = ".md", "text/markdown; charset=utf-8"
                    else:
                        record, payload = store.annotated_pdf(doc_id)
                        extension, content_type = "-annotated.pdf", "application/pdf"
                    filename = Path(record["name"]).stem + extension
                    atomic_write(store.directory / "exports" / (doc_id[:12] + extension), payload)
                    return self.send(payload, content_type=content_type, filename=filename)
            path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            if path == "/":
                file = ROOT / "web" / "index.html"
            elif any(path.startswith("/" + prefix + "/") for prefix in ("web", "vendor", "examples")):
                file = (ROOT / path.lstrip("/")).resolve()
                allowed = any(file.is_relative_to((ROOT / prefix).resolve()) for prefix in ("web", "vendor", "examples"))
                if not allowed:
                    raise FileNotFoundError()
            else:
                raise FileNotFoundError()
            mime = "text/javascript" if file.suffix == ".mjs" else mimetypes.guess_type(file)[0] or "application/octet-stream"
            return self.send(file.read_bytes(), content_type=mime)
        except (FileNotFoundError, IsADirectoryError):
            self.json({"error": "找不到文件或记录"}, 404)
        except InvalidRequest as error:
            self.json({"error": str(error)}, 400)
        except Exception:
            self.json({"error": "读取失败，请检查本机服务后重试"}, 500)

    def mutate(self):
        if not self.checked(mutate=True):
            return
        try:
            route, store = self.route(), self.server.store
            if self.command == "POST" and route == ["api", "import"]:
                filename = urllib.parse.unquote(self.headers.get("X-Filename", "document.pdf"))
                return self.json(store.import_pdf(self.body(MAX_UPLOAD), filename), 201)
            if route[:2] != ["api", "documents"] or len(route) < 4:
                raise FileNotFoundError()
            doc_id, operation = route[2:4]
            if self.command == "DELETE" and operation == "highlights" and len(route) == 5:
                return self.json(store.delete_highlight(doc_id, route[4]))
            if self.command == "DELETE" and operation == "bookmarks" and len(route) == 5:
                return self.json(store.delete_bookmark(doc_id, route[4]))
            body = json.loads(self.body())
            if not isinstance(body, dict):
                raise InvalidRequest("记录格式无效")
            if self.command == "POST" and operation == "activate":
                return self.json(store.save(store.read(doc_id), activate=True))
            if self.command == "POST" and operation == "highlights" and len(route) == 4:
                return self.json(store.add_highlight(doc_id, body), 201)
            if self.command == "PATCH" and operation == "highlights" and len(route) == 5:
                return self.json(store.update_highlight(doc_id, route[4], body))
            if self.command == "PUT" and operation == "bookmarks" and len(route) == 5:
                return self.json(store.upsert_bookmark(doc_id, route[4], body))
            if self.command == "PUT" and operation == "position" and len(route) == 4:
                return self.json(store.save_position(doc_id, body))
            raise FileNotFoundError()
        except FileNotFoundError:
            self.json({"error": "找不到记录"}, 404)
        except (InvalidRequest, json.JSONDecodeError, UnicodeDecodeError) as error:
            self.json({"error": str(error)}, 400)
        except Exception:
            self.json({"error": "保存失败，高亮仍在页面中；请重试或复制备份"}, 500)

    do_POST = mutate
    do_PUT = mutate
    do_PATCH = mutate
    do_DELETE = mutate


def main():
    parser = argparse.ArgumentParser(description="Paper Reader local server")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--import-pdf", type=Path)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    if not (ROOT / "vendor/pdfjs/build/pdf.mjs").exists():
        parser.error("PDF.js assets missing. Run: python3 scripts/setup.py")
    store = Store(args.data_dir)
    if args.import_pdf:
        store.import_pdf(args.import_pdf.read_bytes(), args.import_pdf.name)
    try:
        server = ReaderServer(("127.0.0.1", args.port), store)
    except OSError:
        parser.error(f"端口 {args.port} 已被使用。若阅读器已运行，请直接打开页面；否则使用 --port 指定其他端口。")
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"Paper Reader: {address} · started {now()} · pid {os.getpid()}", flush=True)
    if args.open_browser:
        threading.Thread(target=webbrowser.open, args=(address,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
