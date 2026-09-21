"""Tests fuer das Filesystem-Tool (Roots + Path-Traversal-Schutz)."""
import pytest

from tools.filesystem import FilesystemTool


@pytest.fixture
def fs():
    return FilesystemTool(allowed_roots=("/tmp",))


def test_write_and_read(fs, tmp_path):
    target = tmp_path / "test.txt"
    r = fs.run("write_file", path=str(target), content="GPU: 42C\n")
    assert r.success is True

    r2 = fs.run("read_file", path=str(target))
    assert r2.success is True
    assert "GPU" in r2.data["content"]


def test_path_traversal_absolute(fs):
    # Direkter Zugriff ausserhalb der Root wird zurueckgewiesen
    r = fs.run("read_file", path="/etc/passwd")
    assert r.success is False
    assert "erlaubten" in (r.error or "").lower() or "ausserhalb" in (r.error or "").lower()


def test_path_traversal_dotdot(fs):
    # '..'-Traversal aus einer erlaubten Root heraus wird geblockt
    r = fs.run("read_file", path="/tmp/../../../etc/passwd")
    assert r.success is False


def test_list_directory_allowed(fs, tmp_path):
    r = fs.run("list_directory", path=str(tmp_path))
    assert r.success is True
    assert "items" in r.data or "entries" in r.data


def test_unknown_action(fs):
    r = fs.run("delete_everything", path="/tmp/foo")
    assert r.success is False


def test_missing_path(fs):
    r = fs.run("read_file")
    assert r.success is False
    assert "Pfad" in (r.error or "")