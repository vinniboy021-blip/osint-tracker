"""Private evidence storage with opaque keys, bounded uploads and integrity checks."""

import hashlib
import io
import os
from pathlib import Path
from typing import BinaryIO, Protocol, cast
from uuid import uuid4

from fastapi import UploadFile


class Storage(Protocol):
    def put(self, key: str, stream: BinaryIO) -> None: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, key: str) -> Path:
        if not key or not key.isalnum() or len(key) != 32:
            raise ValueError("Chave de armazenamento inválida")
        path = self.root / key
        if path.is_symlink():
            raise ValueError("Links simbólicos não são permitidos")
        return path

    def put(self, key: str, stream: BinaryIO) -> None:
        path = self.path(key)
        # O_EXCL prevents replacing an existing evidence object.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as target:
                while chunk := stream.read(64 * 1024):
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def open(self, key: str) -> BinaryIO:
        fd = os.open(self.path(key), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        return os.fdopen(fd, "rb")

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


class S3Storage:
    """Optional admin-configured S3/MinIO adapter; objects stay private."""

    def __init__(self, client: object, bucket: str):
        self.client = client
        self.bucket = bucket

    def put(self, key: str, stream: BinaryIO) -> None:
        self.client.upload_fileobj(stream, self.bucket, key)  # type: ignore[attr-defined]

    def open(self, key: str) -> BinaryIO:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]  # type: ignore[attr-defined,no-any-return]

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)  # type: ignore[attr-defined]


async def capture_upload(upload: UploadFile, storage: Storage, max_bytes: int) -> tuple[str, str, int]:
    import tempfile

    key = uuid4().hex
    sha = hashlib.sha256()
    size = 0
    # A spool bounds RAM while streaming the HTTP upload.
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as stream:
        # Starlette's UploadFile delegates to a threadpool. Reading the backing
        # spooled file directly also keeps standalone worker/unit-test usage
        # deterministic while preserving bounded chunks for HTTP uploads.
        while True:
            if isinstance(upload.file, io.IOBase):
                chunk = upload.file.read(64 * 1024)
            else:
                chunk = await upload.read(64 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("Arquivo excede o limite configurado")
            sha.update(chunk)
            stream.write(chunk)
        if not size:
            raise ValueError("Arquivo vazio")
        stream.seek(0)
        storage.put(key, cast(BinaryIO, stream))
    return key, sha.hexdigest(), size


def verify_digest(storage: Storage, key: str, expected: str) -> bool:
    sha = hashlib.sha256()
    with storage.open(key) as stream:
        while chunk := stream.read(64 * 1024):
            sha.update(chunk)
    return sha.hexdigest() == expected


def download_chunks(storage: Storage, key: str):
    with storage.open(key) as stream:
        while chunk := stream.read(64 * 1024):
            yield chunk


def safe_filename(name: str | None) -> str:
    import re

    cleaned = re.sub(r"[^\w. -]", "_", (name or "evidence.bin").replace("\\", "/").split("/")[-1])
    return cleaned[:180].strip(". ") or "evidence.bin"
