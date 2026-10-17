"""Behavioral tests against real PDF bytes and the HTTP service."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Highlight
from pypdf.generic import ArrayObject, FloatObject

from server import COLORS, LINE_COLORS, STYLES, InvalidRequest, ReaderServer, Store

DEMO = Path(__file__).resolve().parents[1] / "examples" / "reader-demo.pdf"


def selection(**overrides):
    body = {"clientId": "a" * 32, "page": 1, "pageLabel": "1", "rawText": "A highlight is a question",
            "quads": [[48, 635, 190, 635, 48, 620, 190, 620]],
            "contextBefore": "", "contextAfter": " waiting to be understood.", "color": "yellow", "textOrder": 3}
    return body | overrides


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paper-reader-unit-")
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.payload = DEMO.read_bytes()
        self.record = self.store.import_pdf(self.payload, "Demo.pdf")
        self.doc_id = self.record["id"]

    def test_import_original_is_unchanged_and_duplicate_retains_highlights(self):
        self.store.add_highlight(self.doc_id, selection())
        duplicate = self.store.import_pdf(self.payload, "Renamed.pdf")
        self.assertEqual(len(duplicate["highlights"]), 1)
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual((self.store.folder(self.doc_id) / "original.pdf").read_bytes(), self.payload)

    def test_same_filename_different_document_is_separate(self):
        writer = PdfWriter()
        writer.add_page(PdfReader(io.BytesIO(self.payload)).pages[0])
        output = io.BytesIO()
        writer.write(output)
        other = self.store.import_pdf(output.getvalue(), "Demo.pdf")
        self.assertNotEqual(self.doc_id, other["id"])
        self.assertEqual(len(self.store.list()), 2)

    def test_record_survives_new_store_and_has_original_context(self):
        h = self.store.add_highlight(self.doc_id, selection())
        reopened = Store(self.temp.name).read(self.doc_id)
        self.assertEqual(reopened["highlights"][0], h)
        snapshot = json.loads((Path(self.temp.name) / "current-reading.json").read_text())
        self.assertEqual(snapshot["id"], self.doc_id)
        self.assertIn("waiting to be understood", snapshot["highlights"][0]["contextAfter"])

    def test_retry_is_idempotent(self):
        first = self.store.add_highlight(self.doc_id, selection())
        second = self.store.add_highlight(self.doc_id, selection())
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.store.read(self.doc_id)["highlights"]), 1)

    def test_note_vocabulary_markdown_and_delete(self):
        h = self.store.add_highlight(self.doc_id, selection())
        self.store.update_highlight(self.doc_id, h["id"], {"kind": "vocabulary", "note": "question：这里表示理解卡点。"})
        markdown = self.store.markdown(self.store.read(self.doc_id))
        self.assertIn("读者确认的生词", markdown)
        self.assertIn("PDF 第 1 页", markdown)
        self.assertIn("question：这里表示理解卡点", markdown)
        self.store.delete_highlight(self.doc_id, h["id"])
        self.assertEqual(self.store.read(self.doc_id)["highlights"], [])

    def test_export_is_standard_highlight_and_keeps_original_text(self):
        h = self.store.add_highlight(self.doc_id, selection())
        _, output = self.store.annotated_pdf(self.doc_id)
        result = PdfReader(io.BytesIO(output))
        annotation = result.pages[0]["/Annots"][-1].get_object()
        self.assertEqual(annotation["/Subtype"], "/Highlight")
        self.assertEqual(annotation["/NM"], h["id"])
        self.assertEqual([float(n) for n in annotation["/QuadPoints"]], selection()["quads"][0])
        self.assertEqual(result.pages[0].extract_text(), PdfReader(io.BytesIO(self.payload)).pages[0].extract_text())
        self.assertEqual(hashlib.sha256((self.store.folder(self.doc_id) / "original.pdf").read_bytes()).hexdigest(), self.doc_id)

    def test_two_clients_additions_do_not_overwrite_each_other(self):
        threads = [threading.Thread(target=self.store.add_highlight, args=(self.doc_id, selection(clientId=f"{i:032x}"))) for i in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(self.store.read(self.doc_id)["highlights"]), 12)

    def test_activation_keeps_an_edit_scheduled_at_the_first_unlocked_boundary(self):
        """Force the old read/save gap without relying on request timing or sleeps."""
        released, edited = threading.Event(), threading.Event()
        activation = None
        errors = []

        class AfterUnlock:
            def __init__(self):
                self.lock, self.depth, self.fired = threading.RLock(), threading.local(), False

            def __enter__(self):
                self.lock.acquire()
                self.depth.value = getattr(self.depth, "value", 0) + 1

            def __exit__(self, *unused):
                self.depth.value -= 1
                self.lock.release()
                if threading.current_thread() is activation and self.depth.value == 0 and not self.fired:
                    self.fired = True
                    released.set()
                    if not edited.wait(3):
                        raise AssertionError("Concurrent edit did not reach its scheduled boundary")

        self.store.lock = AfterUnlock()

        def activate():
            try:
                self.store.activate(self.doc_id)
            except Exception as error:
                errors.append(error)

        def edit():
            try:
                if not released.wait(3):
                    raise AssertionError("Activation did not release the store lock")
                self.store.add_highlight(self.doc_id, selection())
            except Exception as error:
                errors.append(error)
            finally:
                edited.set()

        activation = threading.Thread(target=activate)
        editor = threading.Thread(target=edit)
        activation.start()
        editor.start()
        activation.join(5)
        editor.join(5)
        self.assertFalse(activation.is_alive() or editor.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(self.store.read(self.doc_id)["highlights"]), 1)

    def test_document_snapshots_stay_bound_when_another_paper_becomes_active(self):
        self.store.add_highlight(self.doc_id, selection())
        writer = PdfWriter()
        writer.add_page(PdfReader(io.BytesIO(self.payload)).pages[0])
        output = io.BytesIO()
        writer.write(output)
        other = self.store.import_pdf(output.getvalue(), "Other.pdf")
        paths = self.store.assistant_files(self.doc_id)
        self.assertIn("A highlight is a question", Path(paths["markdown"]).read_text())
        self.assertEqual(json.loads(Path(paths["record"]).read_text())["id"], self.doc_id)
        self.assertEqual(json.loads((self.store.directory / "current-reading.json").read_text())["id"], other["id"])
        self.store.update_highlight(self.doc_id, "a" * 32, {"note": "Saved while Other.pdf is active"})
        self.assertIn("Saved while Other.pdf is active", Path(paths["markdown"]).read_text())
        self.assertNotIn("Saved while Other.pdf is active", (self.store.directory / "current-reading.md").read_text())

    def test_corrupt_record_is_isolated_without_rewriting_it(self):
        broken_id = "b" * 64
        folder = self.store.folder(broken_id)
        folder.mkdir(parents=True)
        path = folder / "record.json"
        for content in [b"{broken", json.dumps({"id": broken_id, "name": "Incomplete"}).encode()]:
            with self.subTest(content=content):
                path.write_bytes(content)
                documents, warnings = self.store.catalog()
                self.assertEqual([item["id"] for item in documents], [self.doc_id])
                self.assertEqual(warnings[0]["documentId"], broken_id)
                self.assertNotIn(str(folder), json.dumps(warnings))
                self.assertEqual(path.read_bytes(), content)
                with self.assertRaises(InvalidRequest):
                    self.store.backup()

    def test_existing_annotations_are_preserved_on_export(self):
        writer = PdfWriter()
        writer.clone_document_from_reader(PdfReader(io.BytesIO(self.payload)))
        writer.add_annotation(0, Highlight(rect=(48, 600, 180, 615),
            quad_points=ArrayObject([FloatObject(n) for n in [48,615,180,615,48,600,180,600]])))
        output = io.BytesIO()
        writer.write(output)
        imported = self.store.import_pdf(output.getvalue(), "Existing annotations.pdf")
        self.store.add_highlight(imported["id"], selection())
        _, exported = self.store.annotated_pdf(imported["id"])
        self.assertEqual(len(PdfReader(io.BytesIO(exported)).pages[0]["/Annots"]), 2)

    def test_rotated_cropped_page_export_preserves_geometry(self):
        writer = PdfWriter()
        page = writer.add_page(PdfReader(io.BytesIO(self.payload)).pages[0])
        page.rotate(90)
        page.cropbox.lower_left = (20, 20)
        output = io.BytesIO()
        writer.write(output)
        imported = self.store.import_pdf(output.getvalue(), "Rotated.pdf")
        self.store.add_highlight(imported["id"], selection())
        _, exported = self.store.annotated_pdf(imported["id"])
        result = PdfReader(io.BytesIO(exported)).pages[0]
        self.assertEqual(result.rotation, 90)
        self.assertEqual(tuple(result.cropbox.lower_left), (20, 20))
        self.assertEqual(list(result["/Annots"][-1].get_object()["/QuadPoints"]), selection()["quads"][0])

    def test_invalid_pdf_coordinates_and_fields_are_rejected(self):
        for changes in [{"page": 999}, {"rawText": " "}, {"quads": []}, {"quads": [[float("nan")] * 8]},
                        {"quads": [[-500, 600, 20, 600, -500, 590, 20, 590]]}, {"clientId": "../../secret"},
                        {"color": "cyan"}, {"color": []}, {"style": "wavy"}, {"style": False}]:
            with self.subTest(changes=changes), self.assertRaises(InvalidRequest):
                self.store.add_highlight(self.doc_id, selection(**changes))
        with self.assertRaises(InvalidRequest):
            self.store.import_pdf(b"This is not a PDF", "fake.pdf")
        with self.assertRaises(InvalidRequest):
            self.store.folder("../secret")

    def test_all_styles_and_colors_persist_and_export_standard_annotations(self):
        originals = []
        for style in STYLES:
            for color in COLORS:
                item = self.store.add_highlight(self.doc_id, selection(clientId=f"{len(originals):032x}", style=style, color=color))
                originals.append(item)
        reopened = Store(self.temp.name).read(self.doc_id)
        self.assertEqual(reopened["highlights"], originals)
        _, exported = self.store.annotated_pdf(self.doc_id)
        result = PdfReader(io.BytesIO(exported))
        for reference, item in zip(result.pages[0]["/Annots"], originals):
            annotation = reference.get_object()
            self.assertEqual(annotation["/Subtype"], STYLES[item["style"]][1])
            self.assertEqual(list(annotation["/QuadPoints"]), item["quads"][0])
            rgb = (COLORS if item["style"] == "highlight" else LINE_COLORS)[item["color"]]
            for actual, index in zip(annotation["/C"], (0, 2, 4)):
                self.assertAlmostEqual(float(actual), int(rgb[index:index + 2], 16) / 255, places=6)
            if item["style"] != "highlight":
                appearance = annotation["/AP"]["/N"].get_object()
                self.assertEqual(appearance["/Subtype"], "/Form")
                self.assertIn(b" l S", appearance.get_data())
                self.assertEqual(float(annotation["/CA"]), 1)
                self.assertEqual(int(annotation["/F"]) & 4, 4)
        original = PdfReader(io.BytesIO(self.payload))
        self.assertEqual(result.pages[0].get_contents().get_data(), original.pages[0].get_contents().get_data())

    def test_old_records_without_style_are_highlights_and_not_migrated(self):
        self.store.add_highlight(self.doc_id, selection())
        record = self.store.read(self.doc_id)
        record["highlights"][0].pop("style")
        self.store.save(record)
        before = (self.store.folder(self.doc_id) / "record.json").read_bytes()
        self.assertIn("标注：高亮 · 黄色", self.store.markdown(record))
        _, exported = self.store.annotated_pdf(self.doc_id)
        self.assertEqual(PdfReader(io.BytesIO(exported)).pages[0]["/Annots"][0].get_object()["/Subtype"], "/Highlight")
        self.assertEqual((self.store.folder(self.doc_id) / "record.json").read_bytes(), before)

    def test_restyling_preserves_geometry_and_invalid_updates_do_not_write(self):
        item = self.store.add_highlight(self.doc_id, selection(style="underline", color="blue"))
        edited = self.store.update_highlight(self.doc_id, item["id"], {"style": "strikeout", "color": "purple"})
        self.assertEqual((edited["style"], edited["color"]), ("strikeout", "purple"))
        self.assertEqual(edited["quads"], item["quads"])
        self.assertEqual(edited["rawText"], item["rawText"])
        before = self.store.read(self.doc_id)
        for body in [{"style": "wave"}, {"color": "cyan"}, {"style": []}, {"color": None}, {"style": "highlight", "color": "cyan"}]:
            with self.subTest(body=body), self.assertRaises(InvalidRequest):
                self.store.update_highlight(self.doc_id, item["id"], body)
            self.assertEqual(self.store.read(self.doc_id), before)

    def test_old_reading_records_get_bookmarks_without_disk_migration(self):
        legacy = self.store.read(self.doc_id)
        legacy.pop("bookmarks")
        self.store.save(legacy)
        path = self.store.folder(self.doc_id) / "record.json"
        before = path.read_bytes()
        reopened = Store(self.temp.name).read(self.doc_id)
        self.assertEqual(reopened["bookmarks"], [])
        self.assertEqual(reopened["position"], {"page": 1, "zoom": "fit"})
        self.assertEqual(path.read_bytes(), before)

    def test_anchor_and_bookmarks_persist_without_changing_annotations_or_source(self):
        highlight = self.store.add_highlight(self.doc_id, selection())
        position = {"page": 1, "zoom": 1.375, "anchor": {"x": 0.35, "y": 0.6}}
        self.store.save_position(self.doc_id, position)
        bookmark = self.store.upsert_bookmark(self.doc_id, 1, {"title": "  Abstract  "})
        self.assertEqual(bookmark["title"], "Abstract")
        reopened = Store(self.temp.name).read(self.doc_id)
        self.assertEqual(reopened["position"], position)
        self.assertEqual(reopened["bookmarks"], [bookmark])
        self.assertEqual(reopened["highlights"], [highlight])
        snapshot = json.loads((Path(self.temp.name) / "current-reading.json").read_text())
        self.assertEqual(snapshot["position"], position)
        self.assertEqual(snapshot["bookmarks"], [bookmark])
        self.assertEqual((self.store.folder(self.doc_id) / "original.pdf").read_bytes(), self.payload)
        removed = self.store.delete_bookmark(self.doc_id, 1)
        self.assertEqual(removed, bookmark)
        self.assertEqual(self.store.read(self.doc_id)["position"], position)
        self.assertEqual(self.store.read(self.doc_id)["highlights"], [highlight])

    def test_bookmarks_upsert_once_per_page_and_delete_is_idempotent(self):
        first = self.store.upsert_bookmark(self.doc_id, 1, {"title": "Abstract"})
        path = self.store.folder(self.doc_id) / "record.json"
        before_retry = path.read_bytes()
        self.assertEqual(self.store.upsert_bookmark(self.doc_id, "1", {"title": " Abstract "}), first)
        self.assertEqual(path.read_bytes(), before_retry)
        changed = self.store.upsert_bookmark(self.doc_id, 1, {"title": "Introduction"})
        self.assertEqual(changed["createdAt"], first["createdAt"])
        self.assertEqual(changed["title"], "Introduction")
        self.assertEqual(self.store.read(self.doc_id)["bookmarks"], [changed])
        self.assertEqual(self.store.delete_bookmark(self.doc_id, "1"), changed)
        before_retry = path.read_bytes()
        self.assertIsNone(self.store.delete_bookmark(self.doc_id, 1))
        self.assertEqual(path.read_bytes(), before_retry)

    def test_invalid_bookmarks_never_write(self):
        self.store.upsert_bookmark(self.doc_id, 1, {"title": "Existing"})
        record_path = self.store.folder(self.doc_id) / "record.json"
        snapshot_path = Path(self.temp.name) / "current-reading.json"
        before, snapshot_before = record_path.read_bytes(), snapshot_path.read_bytes()
        for page in [0, -1, 3, True, 1.0, None, "0", "-1", "01", "1.0", "not-a-page"]:
            with self.subTest(page=page):
                with self.assertRaises(InvalidRequest):
                    self.store.upsert_bookmark(self.doc_id, page, {"title": "Rejected"})
                with self.assertRaises(InvalidRequest):
                    self.store.delete_bookmark(self.doc_id, page)
                self.assertEqual(record_path.read_bytes(), before)
        for title in ["", " \n\t ", "x" * 201, True, 123, None, []]:
            with self.subTest(title=title), self.assertRaises(InvalidRequest):
                self.store.upsert_bookmark(self.doc_id, 1, {"title": title})
            self.assertEqual(record_path.read_bytes(), before)
        self.assertEqual(snapshot_path.read_bytes(), snapshot_before)

    def test_concurrent_bookmarks_and_annotations_keep_all_record_fields(self):
        position = {"page": 1, "zoom": "fit", "anchor": {"x": 0.4, "y": 0.8}}
        self.store.save_position(self.doc_id, position)
        threads = [threading.Thread(target=self.store.upsert_bookmark,
                    args=(self.doc_id, page, {"title": f"Page {page}"})) for page in (1, 2)]
        threads += [threading.Thread(target=self.store.add_highlight,
                    args=(self.doc_id, selection(clientId=f"{i:032x}"))) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        reopened = Store(self.temp.name).read(self.doc_id)
        self.assertEqual([bookmark["page"] for bookmark in reopened["bookmarks"]], [1, 2])
        self.assertEqual(len(reopened["highlights"]), 4)
        self.assertEqual(reopened["position"], position)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paper-reader-http-")
        self.store = Store(self.temp.name)
        self.server = ReaderServer(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.token = self.server.csrf

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        request = urllib.request.Request(self.base + path, data=body, method=method,
                                        headers=headers or {})
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            response = error
        # Buffer small fixture responses so status-only assertions do not leak sockets.
        with response:
            result = io.BytesIO(response.read())
            result.status = response.status
            result.headers = response.headers
            return result

    def test_origin_csrf_and_private_paths(self):
        self.assertEqual(self.request("/api/session").status, 200)
        self.assertEqual(self.request("/api/session", headers={"Origin": "https://unrelated.example"}).status, 403)
        self.assertEqual(self.request("/api/import", "POST", DEMO.read_bytes()).status, 403)
        for path in ["/.git/config", "/data/current-reading.json", "/web/../../server.py", "/server.py"]:
            self.assertEqual(self.request(path).status, 404)

    def test_session_reports_isolated_documents_and_stable_assistant_paths(self):
        record = self.store.import_pdf(DEMO.read_bytes(), "Valid.pdf")
        broken_id = "b" * 64
        folder = self.store.folder(broken_id)
        folder.mkdir(parents=True)
        (folder / "record.json").write_text("{broken")
        (self.store.directory / "active.json").write_text(json.dumps({"id": broken_id}))
        response = self.request("/api/session")
        self.assertEqual(response.status, 200)
        session = json.load(response)
        self.assertEqual(session["version"], "0.4.0")
        self.assertIsNone(session["activeId"])
        self.assertEqual(len(session["documents"]), 1)
        self.assertEqual(session["warnings"][0]["documentId"], broken_id)
        self.assertTrue(Path(session["assistantFiles"][record["id"]]["markdown"]).is_file())
        self.assertEqual(self.request("/api/library/backup").status, 400)

    def test_http_activation_uses_the_atomic_store_operation(self):
        record = self.store.import_pdf(DEMO.read_bytes(), "Demo.pdf")
        with patch.object(self.store, "activate", wraps=self.store.activate) as activate:
            response = self.request(f'/api/documents/{record["id"]}/activate', "POST", b"{}",
                                    {"X-Reader-Token": self.token})
        self.assertEqual(response.status, 200)
        activate.assert_called_once_with(record["id"])

    def test_http_backup_download_contains_original_and_saved_metadata(self):
        record = self.store.import_pdf(DEMO.read_bytes(), "Demo.pdf")
        self.store.add_highlight(record["id"], selection())
        response = self.request("/api/library/backup")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(response) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["documents"], [record["id"]])
            self.assertEqual(archive.read(f'documents/{record["id"]}/original.pdf'), DEMO.read_bytes())
            saved = json.loads(archive.read(f'documents/{record["id"]}/record.json'))
            self.assertEqual(saved["highlights"][0]["rawText"], selection()["rawText"])
        self.assertEqual(self.request("/api/library/backup", headers={"Origin": "https://unrelated.example"}).status, 403)

    def test_http_import_persist_export_and_position(self):
        headers = {"X-Reader-Token": self.token, "X-Filename": "Demo.pdf"}
        response = self.request("/api/import", "POST", DEMO.read_bytes(), headers)
        self.assertEqual(response.status, 201)
        doc_id = json.load(response)["id"]
        prefix = "/api/documents/" + doc_id
        response = self.request(prefix + "/highlights", "POST", json.dumps(selection()).encode(), headers)
        self.assertEqual(response.status, 201)
        response = self.request(prefix + "/position", "PUT", b'{"page":2,"zoom":1.25}', headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(self.store.read(doc_id)["position"], {"page": 2, "zoom": 1.25})
        self.assertIn("A highlight is a question", self.request(prefix + "/markdown").read().decode())
        exported = self.request(prefix + "/annotated.pdf")
        self.assertEqual(exported.headers["Content-Type"], "application/pdf")
        self.assertEqual(PdfReader(io.BytesIO(exported.read())).pages[0]["/Annots"][0].get_object()["/Subtype"], "/Highlight")

    def test_custom_zoom_range_and_invalid_position_preserve_record(self):
        record = self.store.import_pdf(DEMO.read_bytes(), "Demo.pdf")
        route = f'/api/documents/{record["id"]}/position'
        headers = {"X-Reader-Token": self.token}
        for zoom in [0.25, 1.375, 4, "fit"]:
            with self.subTest(zoom=zoom):
                response = self.request(route, "PUT", json.dumps({"page": 1, "zoom": zoom}).encode(), headers)
                self.assertEqual(response.status, 200)
                self.assertEqual(self.store.read(record["id"])["position"], {"page": 1, "zoom": zoom})
        for zoom in [0.249, 4.001, -1, 0, True, "137%", None, float("nan"), float("inf"), 10 ** 400]:
            with self.subTest(zoom=zoom):
                response = self.request(route, "PUT", json.dumps({"page": 1, "zoom": zoom}).encode(), headers)
                self.assertEqual(response.status, 400)
                self.assertEqual(self.store.read(record["id"])["position"], {"page": 1, "zoom": "fit"})

    def test_http_annotation_style_edit_and_export(self):
        record = self.store.import_pdf(DEMO.read_bytes(), "Demo.pdf")
        headers = {"X-Reader-Token": self.token}
        route = f'/api/documents/{record["id"]}'
        response = self.request(route + "/highlights", "POST", json.dumps(selection(style="underline", color="blue")).encode(), headers)
        self.assertEqual(response.status, 201)
        item = json.load(response)
        response = self.request(route + "/highlights/" + item["id"], "PATCH", b'{"style":"strikeout","color":"red"}', headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.load(response)["style"], "strikeout")
        exported = PdfReader(io.BytesIO(self.request(route + "/annotated.pdf").read()))
        self.assertEqual(exported.pages[0]["/Annots"][0].get_object()["/Subtype"], "/StrikeOut")

    def test_http_anchor_persistence_legacy_updates_and_page_changes(self):
        record = self.store.import_pdf(DEMO.read_bytes(), "Demo.pdf")
        route = f'/api/documents/{record["id"]}/position'
        headers = {"X-Reader-Token": self.token}
        legacy = {"page": 1, "zoom": 1.25}
        response = self.request(route, "PUT", json.dumps(legacy).encode(), headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.load(response), legacy)
        for anchor in [{"x": 0, "y": 1}, {"x": 1, "y": 0}, {"x": 0.37, "y": 0.81}]:
            position = {**legacy, "anchor": anchor}
            response = self.request(route, "PUT", json.dumps(position).encode(), headers)
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response), position)
        response = self.request(route, "PUT", b'{"page":1,"zoom":2}', headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.load(response), {"page": 1, "zoom": 2, "anchor": anchor})
        self.assertEqual(Store(self.temp.name).read(record["id"])["position"]["anchor"], anchor)
        response = self.request(route, "PUT", b'{"page":2,"zoom":"fit"}', headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.load(response), {"page": 2, "zoom": "fit"})

    def test_http_invalid_anchors_and_missing_position_fields_do_not_write(self):
        record = self.store.import_pdf(DEMO.read_bytes(), "Demo.pdf")
        route = f'/api/documents/{record["id"]}/position'
        headers = {"X-Reader-Token": self.token}
        position = {"page": 1, "zoom": 1.375, "anchor": {"x": 0.3, "y": 0.6}}
        self.store.save_position(record["id"], position)
        record_path = self.store.folder(record["id"]) / "record.json"
        snapshot_path = Path(self.temp.name) / "current-reading.json"
        before, snapshot_before = record_path.read_bytes(), snapshot_path.read_bytes()
        anchors = [None, [], 0, {}, {"x": 0.5}, {"y": 0.5}, {"x": True, "y": 0.5},
                   {"x": 0.5, "y": False}, {"x": -0.001, "y": 0.5}, {"x": 0.5, "y": 1.001},
                   {"x": "0.5", "y": 0.5}, {"x": float("nan"), "y": 0.5},
                   {"x": 0.5, "y": float("inf")}, {"x": 10 ** 400, "y": 0.5}]
        bodies = [{**position, "anchor": anchor} for anchor in anchors]
        bodies += [{"zoom": 1.25}, {"page": 1}, {"page": True, "zoom": 1.25},
                   {"page": 0, "zoom": 1.25}, {"page": 3, "zoom": 1.25}]
        for body in bodies:
            with self.subTest(body=body):
                response = self.request(route, "PUT", json.dumps(body).encode(), headers)
                self.assertEqual(response.status, 400)
                self.assertEqual(record_path.read_bytes(), before)
                self.assertEqual(snapshot_path.read_bytes(), snapshot_before)

    def test_http_bookmark_upsert_delete_and_document_isolation(self):
        record = self.store.import_pdf(DEMO.read_bytes(), "Demo.pdf")
        prefix = f'/api/documents/{record["id"]}'
        headers = {"X-Reader-Token": self.token}
        route = prefix + "/bookmarks/2"
        response = self.request(route, "PUT", b'{"title":"  Methods  "}', headers)
        self.assertEqual(response.status, 200)
        item = json.load(response)
        self.assertEqual(item["title"], "Methods")
        self.assertEqual(item["page"], 2)
        response = self.request(route, "PUT", b'{"title":"Methods"}', headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.load(response), item)
        response = self.request(route, "PUT", b'{"title":"Results"}', headers)
        self.assertEqual(response.status, 200)
        edited = json.load(response)
        self.assertEqual(edited["createdAt"], item["createdAt"])
        fetched = json.load(self.request(prefix + "/record"))
        self.assertEqual(fetched["bookmarks"], [edited])
        writer = PdfWriter()
        writer.add_page(PdfReader(io.BytesIO(DEMO.read_bytes())).pages[0])
        output = io.BytesIO()
        writer.write(output)
        other = self.store.import_pdf(output.getvalue(), "Other.pdf")
        self.assertEqual(self.store.read(other["id"])["bookmarks"], [])
        response = self.request(route, "DELETE", headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.load(response), edited)
        response = self.request(route, "DELETE", headers=headers)
        self.assertEqual(response.status, 200)
        self.assertIsNone(json.load(response))
        self.assertEqual(self.store.read(record["id"])["bookmarks"], [])

    def test_http_bookmark_permissions_and_invalid_input_preserve_record(self):
        record = self.store.import_pdf(DEMO.read_bytes(), "Demo.pdf")
        prefix = f'/api/documents/{record["id"]}/bookmarks/'
        valid_headers = {"X-Reader-Token": self.token}
        self.store.upsert_bookmark(record["id"], 1, {"title": "Existing"})
        path = self.store.folder(record["id"]) / "record.json"
        before = path.read_bytes()
        for method, body in [("PUT", b'{"title":"Forbidden"}'), ("DELETE", None)]:
            for headers in [{}, {"X-Reader-Token": "wrong"},
                            {**valid_headers, "Origin": "https://unrelated.example"}]:
                with self.subTest(method=method, headers=headers):
                    self.assertEqual(self.request(prefix + "1", method, body, headers).status, 403)
                    self.assertEqual(path.read_bytes(), before)
        for page in ["0", "-1", "3", "01", "1.0", "unknown"]:
            for method, body in [("PUT", b'{"title":"Invalid"}'), ("DELETE", None)]:
                with self.subTest(page=page, method=method):
                    self.assertEqual(self.request(prefix + page, method, body, valid_headers).status, 400)
                    self.assertEqual(path.read_bytes(), before)
        for body in [{}, {"title": " "}, {"title": "x" * 201}, {"title": None},
                     {"title": False}, {"title": []}, [], "title"]:
            with self.subTest(body=body):
                self.assertEqual(self.request(prefix + "1", "PUT", json.dumps(body).encode(), valid_headers).status, 400)
                self.assertEqual(path.read_bytes(), before)
        response = self.request(prefix + "1", "PUT", json.dumps({"title": "x" * 200}).encode(), valid_headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(len(json.load(response)["title"]), 200)


if __name__ == "__main__":
    unittest.main()
