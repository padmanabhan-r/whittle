"""A zip from a stranger is unpacked safely or not at all."""

from __future__ import annotations

import io
import zipfile

import pytest

from costcutter import uploads
from costcutter.proxy import store as store_module


def make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_a_zip_of_one_folder_becomes_the_project(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path)
    upload_id, files, size = uploads.save(make_zip({"proj/agent.py": b"x = 1\n", "proj/pkg/util.py": b"y = 2\n", "proj/node_modules/big.js": b"z", "__MACOSX/proj/._agent.py": b"junk"}), "proj.zip")
    code = uploads.extracted(upload_id)
    assert files == 2 and size == 12
    assert (code / "agent.py").read_text() == "x = 1\n" and (code / "pkg" / "util.py").is_file()
    assert not (code / "node_modules").exists()


def test_paths_that_leave_the_folder_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path)
    with pytest.raises(uploads.UploadError):
        uploads.save(make_zip({"../../escape.py": b"x"}), "bad.zip")
    assert not (tmp_path.parent / "escape.py").exists()
    assert not any((tmp_path / "uploads").iterdir())  # nothing is left behind


def test_not_a_zip_and_an_empty_zip_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module, "DATA_ROOT", tmp_path)
    with pytest.raises(uploads.UploadError):
        uploads.save(b"not a zip", "x.zip")
    with pytest.raises(uploads.UploadError):
        uploads.save(make_zip({}), "empty.zip")
    with pytest.raises(uploads.UploadError):
        uploads.extracted("../etc")
