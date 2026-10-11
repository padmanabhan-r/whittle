"""Code uploaded as a zip: unpacked once, safely, into data/uploads/<id>/code.

A zip from a stranger is untrusted. Nothing in it is run here; it is only unpacked, and
only regular files that stay inside the target folder, within a size and count limit.
"""

from __future__ import annotations

import io
import shutil
import stat
import uuid
import zipfile
from pathlib import Path

from costcutter.proxy import store

MAX_ZIP_BYTES = 60 * 1024 * 1024
MAX_UNPACKED_BYTES = 300 * 1024 * 1024
MAX_FILES = 20_000
SKIP_TOP = {"__MACOSX"}
SKIP_PARTS = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".next", "dist", "build"}


class UploadError(ValueError):
    pass


def root() -> Path:
    return store.DATA_ROOT / "uploads"


def extracted(upload_id: str) -> Path:
    if not upload_id.isalnum():
        raise UploadError("That upload id is not valid.")
    path = root() / upload_id / "code"
    if not path.is_dir():
        raise UploadError("That upload is gone. Upload the zip again.")
    return path


def save(data: bytes, name: str) -> tuple[str, int, int]:
    """Unpack a zip. Returns (upload_id, files, bytes)."""
    if len(data) > MAX_ZIP_BYTES:
        raise UploadError(f"The zip is larger than {MAX_ZIP_BYTES // (1024 * 1024)} MB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UploadError("That file is not a zip archive.") from None
    upload_id = uuid.uuid4().hex[:16]
    target = root() / upload_id / "code"
    target.mkdir(parents=True)
    base = target.resolve()
    files = total = 0
    try:
        for info in archive.infolist():
            parts = Path(info.filename).parts
            if info.is_dir() or not parts or parts[0] in SKIP_TOP or any(p in SKIP_PARTS for p in parts):
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                continue  # a link could point outside the folder
            dest = (target / info.filename).resolve()
            if base not in dest.parents:
                raise UploadError("The zip holds a path that leaves its own folder.")
            total += info.file_size
            files += 1
            if total > MAX_UNPACKED_BYTES or files > MAX_FILES:
                raise UploadError("The zip unpacks to more than Whittle accepts (300 MB or 20,000 files).")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
        if files == 0:
            raise UploadError("The zip holds no files.")
    except UploadError:
        shutil.rmtree(target.parent, ignore_errors=True)
        raise
    # A zip of one folder: use that folder as the project.
    entries = [p for p in target.iterdir()]
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        staging = target.parent / "unwrapped"
        inner.rename(staging)
        target.rmdir()
        staging.rename(target)
    return upload_id, files, total
