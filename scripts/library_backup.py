"""Restore a validated reader backup to a new directory, never over a live library."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import ID_PATTERN, MAX_UPLOAD, Store, validate_document, validate_record  # noqa: E402

MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_METADATA_BYTES = 64 * 1024 * 1024


class BackupError(ValueError):
    pass


def strict_json(payload):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise BackupError("JSON contains duplicate keys")
            value[key] = item
        return value

    try:
        return json.loads(payload, object_pairs_hook=pairs)
    except (ValueError, UnicodeDecodeError) as error:
        raise BackupError("Backup metadata is not valid JSON") from error


def checked_files(source):
    """Validate every entry before creating a destination or writing any file."""
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if len(infos) > 10000 or sum(item.file_size for item in infos) > MAX_ARCHIVE_BYTES:
                raise BackupError("Backup exceeds the supported 1 GiB / 10,000 files limit")
            names = set()
            for info in infos:
                path = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (info.filename in names or "\\" in info.filename or path.is_absolute()
                        or any(part in (".", "..") for part in info.filename.split("/"))
                        or str(path) != info.filename or info.is_dir() or info.flag_bits & 1
                        or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not stat.S_ISREG(mode))):
                    raise BackupError("Backup contains an unsafe, duplicate, or unsupported entry")
                names.add(info.filename)
            if "manifest.json" not in names or archive.getinfo("manifest.json").file_size > 1024 * 1024:
                raise BackupError("Backup manifest is missing or too large")
            manifest = strict_json(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("format") != "paper-reader-library" or type(manifest.get("version")) is not int or manifest["version"] != 1:
                raise BackupError("Unsupported backup format or version")
            documents, entries, active = manifest.get("documents"), manifest.get("files"), manifest.get("activeId")
            if (not isinstance(documents, list) or len(documents) > 3000
                    or any(not isinstance(doc_id, str) or not ID_PATTERN.fullmatch(doc_id) for doc_id in documents)
                    or len(set(documents)) != len(documents) or not isinstance(entries, dict)
                    or (active is not None and (not isinstance(active, str) or active not in documents))):
                raise BackupError("Backup document list is invalid")
            expected = {f"documents/{doc_id}/{name}" for doc_id in documents
                        for name in ("original.pdf", "record.json", "reading.md")}
            if active:
                expected.update(("active.json", "current-reading.json", "current-reading.md"))
            if set(entries) != expected or names != expected | {"manifest.json"}:
                raise BackupError("Backup file list is incomplete or contains unexpected files")
            files = {}
            for name, metadata in entries.items():
                maximum = MAX_UPLOAD if name.endswith("original.pdf") else MAX_METADATA_BYTES
                size = archive.getinfo(name).file_size
                if (not isinstance(metadata, dict) or type(metadata.get("size")) is not int
                        or metadata["size"] != size or not 0 <= size <= maximum
                        or not isinstance(metadata.get("sha256"), str)
                        or not ID_PATTERN.fullmatch(metadata["sha256"])):
                    raise BackupError("Backup file size or checksum metadata is invalid")
                payload = archive.read(name)
                if hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
                    raise BackupError("Backup checksum mismatch")
                files[name] = payload
            records = {}
            for doc_id in documents:
                prefix = f"documents/{doc_id}/"
                payload = files[prefix + "original.pdf"]
                if not payload.startswith(b"%PDF-") or hashlib.sha256(payload).hexdigest() != doc_id:
                    raise BackupError("Original PDF does not match its document ID")
                record = validate_record(strict_json(files[prefix + "record.json"]), doc_id)
                validate_document(record, payload)
                record.setdefault("bookmarks", [])
                if files[prefix + "reading.md"] != Store.markdown(record).encode():
                    raise BackupError("Reading snapshot does not match its annotations")
                records[doc_id] = record
            if active:
                if (strict_json(files["active.json"]) != {"id": active}
                        or strict_json(files["current-reading.json"]) != records[active]
                        or files["current-reading.md"] != Store.markdown(records[active]).encode()):
                    raise BackupError("Active reading snapshot is inconsistent")
            return files, len(documents)
    except BackupError:
        raise
    except Exception as error:
        raise BackupError("Backup is damaged or contains invalid document data") from error


def restore_archive(source, destination):
    destination = Path(destination).expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise BackupError("Destination already exists. Choose a new directory; existing libraries are never overwritten.")
    if not destination.parent.is_dir():
        raise BackupError("Destination parent directory must already exist")
    files, count = checked_files(source)
    staging = Path(tempfile.mkdtemp(prefix=".paper-reader-restore-", dir=destination.parent))
    reserved = None
    try:
        for name, payload in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        # Reserve the final name exclusively. The completed staging directory can
        # then replace only this empty reservation, never a pre-existing library.
        destination.mkdir()
        reserved = destination.stat()
        os.replace(staging, destination)
        reserved = None
        return count
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if reserved is not None and destination.exists() and not destination.is_symlink():
            current = destination.stat()
            if (current.st_dev, current.st_ino) == (reserved.st_dev, reserved.st_ino):
                try:
                    destination.rmdir()
                except OSError:
                    pass  # Never remove files another process put in the reservation.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    restore = subparsers.add_parser("restore", help="Validate and restore into a new directory")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--to", required=True, type=Path, dest="destination")
    args = parser.parse_args()
    try:
        count = restore_archive(args.archive, args.destination)
    except (BackupError, OSError) as error:
        parser.exit(1, f"Restore failed: {error}\n")
    print(f"Restored {count} document(s) to {args.destination.resolve()}.")
    print("Verify this library using server.py --data-dir PATH on an unused port before switching your regular reader.")


if __name__ == "__main__":
    main()
