"""Library recovery tests use only synthetic PDFs and isolated temporary folders."""
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from pypdf import PdfReader, PdfWriter

from scripts.library_backup import BackupError, restore_archive
from server import Store
from tests.test_server import DEMO, selection


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="paper-reader-backup-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "source")
        self.record = self.store.import_pdf(DEMO.read_bytes(), "Demo.pdf")
        self.doc_id = self.record["id"]
        self.store.add_highlight(self.doc_id, selection(style="underline", color="blue"))
        self.store.update_highlight(self.doc_id, "a" * 32, {"note": "A saved bilingual note／笔记", "kind": "vocabulary"})
        self.store.upsert_bookmark(self.doc_id, 2, {"title": "Methods"})
        self.store.save_position(self.doc_id, {"page": 2, "zoom": 1.375, "anchor": {"x": 0.2, "y": 0.6}})
        writer = PdfWriter()
        writer.add_page(PdfReader(io.BytesIO(DEMO.read_bytes())).pages[0])
        output = io.BytesIO()
        writer.write(output)
        self.other_id = self.store.import_pdf(output.getvalue(), "Other.pdf")["id"]
        self.backup = self.store.backup()
        self.destination = self.root / "restored"

    def changed_archive(self, change):
        with zipfile.ZipFile(io.BytesIO(self.backup)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        change(files)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in files.items():
                archive.writestr(name, payload)
        return io.BytesIO(output.getvalue())

    def replace_with_checksum(self, files, name, payload):
        files[name] = payload
        manifest = json.loads(files["manifest.json"])
        manifest["files"][name] = {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
        files["manifest.json"] = json.dumps(manifest).encode()

    def assert_rejected_without_partial_directory(self, archive):
        with self.assertRaises(BackupError):
            restore_archive(archive, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob(".paper-reader-restore-*")), [])

    def test_full_roundtrip_preserves_originals_annotations_notes_bookmarks_position(self):
        self.assertEqual(restore_archive(io.BytesIO(self.backup), self.destination), 2)
        restored = Store(self.destination)
        self.assertEqual(restored.active(), self.other_id)
        self.assertEqual(restored.read(self.doc_id), self.store.read(self.doc_id))
        for doc_id in (self.doc_id, self.other_id):
            self.assertEqual((restored.folder(doc_id) / "original.pdf").read_bytes(),
                             (self.store.folder(doc_id) / "original.pdf").read_bytes())
            self.assertEqual((restored.folder(doc_id) / "reading.md").read_bytes(),
                             (self.store.folder(doc_id) / "reading.md").read_bytes())
        self.assertIn("A saved bilingual note", restored.markdown(restored.read(self.doc_id)))

    def test_existing_destination_and_symlink_are_never_overwritten(self):
        self.destination.mkdir()
        sentinel = self.destination / "keep.txt"
        sentinel.write_text("Do not overwrite")
        with self.assertRaises(BackupError):
            restore_archive(io.BytesIO(self.backup), self.destination)
        self.assertEqual(sentinel.read_text(), "Do not overwrite")
        link = self.root / "linked"
        link.symlink_to(self.destination, target_is_directory=True)
        with self.assertRaises(BackupError):
            restore_archive(io.BytesIO(self.backup), link)

    def test_tampered_payload_is_rejected_before_any_file_is_created(self):
        name = f"documents/{self.doc_id}/record.json"
        archive = self.changed_archive(lambda files: files.__setitem__(name, files[name] + b" "))
        self.assert_rejected_without_partial_directory(archive)

    def test_changed_pdf_is_rejected_even_if_manifest_checksum_is_rewritten(self):
        name = f"documents/{self.doc_id}/original.pdf"
        archive = self.changed_archive(lambda files: self.replace_with_checksum(files, name, files[name] + b"\nchanged"))
        self.assert_rejected_without_partial_directory(archive)

    def test_invalid_record_schema_is_rejected_even_with_a_matching_checksum(self):
        name = f"documents/{self.doc_id}/record.json"
        for field, value in [("id", "b" * 64), ("schemaVersion", 2), ("pageCount", "two"),
                             ("position", {"page": 999, "zoom": "fit"}), ("highlights", {})]:
            with self.subTest(field=field):
                def change(files):
                    record = json.loads(files[name])
                    record[field] = value
                    self.replace_with_checksum(files, name, json.dumps(record).encode())
                self.assert_rejected_without_partial_directory(self.changed_archive(change))

    def test_traversal_absolute_and_unexpected_files_are_rejected(self):
        for name in ("../outside.txt", "/absolute.txt", "documents\\outside.txt", "extra.txt", "documents//outside.txt"):
            with self.subTest(name=name):
                archive = self.changed_archive(lambda files: files.__setitem__(name, b"unexpected"))
                self.assert_rejected_without_partial_directory(archive)
        self.assertFalse((self.root.parent / "outside.txt").exists())

    def test_symlink_and_duplicate_zip_entries_are_rejected(self):
        for symlink in (True, False):
            with self.subTest(symlink=symlink):
                output = io.BytesIO(self.backup)
                with zipfile.ZipFile(output, "a") as archive:
                    if symlink:
                        item = zipfile.ZipInfo("link")
                        item.create_system = 3
                        item.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(item, "../outside.txt")
                    else:
                        with self.assertWarns(UserWarning):
                            archive.writestr("manifest.json", "{}")
                output.seek(0)
                self.assert_rejected_without_partial_directory(output)

    def test_missing_file_malicious_active_id_and_duplicate_json_keys_are_rejected(self):
        original = f"documents/{self.doc_id}/original.pdf"
        self.assert_rejected_without_partial_directory(self.changed_archive(lambda files: files.pop(original)))
        def wrong_active(files):
            manifest = json.loads(files["manifest.json"])
            manifest["activeId"] = "../outside"
            files["manifest.json"] = json.dumps(manifest).encode()
        self.assert_rejected_without_partial_directory(self.changed_archive(wrong_active))
        self.assert_rejected_without_partial_directory(self.changed_archive(
            lambda files: files.__setitem__("manifest.json", b'{"format":"paper-reader-library","format":"other"}')))

    def test_backup_refuses_changed_original_instead_of_exporting_incomplete_library(self):
        (self.store.folder(self.doc_id) / "original.pdf").write_bytes(b"%PDF-corrupted")
        with self.assertRaises(ValueError):
            self.store.backup()

    def test_backup_document_limit_is_checked_before_reading_any_original(self):
        with patch.object(self.store, "catalog", return_value=([{"id": self.doc_id}] * 3001, [])):
            with self.assertRaisesRegex(ValueError, "3,000"):
                self.store.backup()

    def test_failed_final_install_removes_only_its_empty_reservation(self):
        with patch("scripts.library_backup.os.replace", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                restore_archive(io.BytesIO(self.backup), self.destination)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob(".paper-reader-restore-*")), [])


if __name__ == "__main__":
    unittest.main()
