import asyncio
import hashlib
import io

import pytest
from fastapi import UploadFile

from app.evidence import LocalStorage, capture_upload, safe_filename, verify_digest


def test_streamed_upload_integrity_and_tamper_detection(tmp_path):
    storage = LocalStorage(tmp_path)
    data = b"public source content" * 10000
    key, sha, size = asyncio.run(capture_upload(UploadFile(io.BytesIO(data)), storage, len(data)))
    assert sha == hashlib.sha256(data).hexdigest() and size == len(data)
    assert verify_digest(storage, key, sha)
    storage.path(key).write_bytes(b"tampered")
    assert not verify_digest(storage, key, sha)


def test_oversized_and_empty_uploads_do_not_leave_files(tmp_path):
    storage = LocalStorage(tmp_path)
    for data in (b"", b"abcd"):
        with pytest.raises(ValueError):
            asyncio.run(capture_upload(UploadFile(io.BytesIO(data)), storage, 3))
    assert list(tmp_path.iterdir()) == []


def test_local_storage_forbids_path_traversal_and_symlinks(tmp_path):
    storage = LocalStorage(tmp_path)
    for key in ("../secrets", "/etc/passwd", "a" * 33, ""):
        with pytest.raises(ValueError):
            storage.open(key)
    target = tmp_path / "target"
    target.write_text("secret")
    (tmp_path / ("a" * 32)).symlink_to(target)
    with pytest.raises(ValueError):
        storage.open("a" * 32)


def test_filenames_are_metadata_not_storage_paths():
    assert safe_filename("../../source.txt") == "source.txt"
    assert safe_filename("C:\\Users\\person\\source.txt") == "source.txt"
    assert "\n" not in safe_filename("bad\nfile.txt")


def test_storage_objects_are_never_overwritten(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.put("a" * 32, io.BytesIO(b"first"))
    with pytest.raises(FileExistsError):
        storage.put("a" * 32, io.BytesIO(b"second"))
    with storage.open("a" * 32) as stream:
        assert stream.read() == b"first"
