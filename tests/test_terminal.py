"""Tests fuer das Terminal-Tool (Deny-Liste, Timeout, Output-Cap)."""
import pytest

from tools.terminal import TerminalTool


@pytest.fixture
def term():
    return TerminalTool(timeout=5, max_output=2048)


def test_status_denylist(term):
    """Gefaelschte Admin-Standard-Kommandos werden blockiert."""
    blocked = [
        "rm -rf /",
        "rm -f /",
        "rm -rf /*",
        "shutdown now",
        "reboot",
        "systemctl stop llama.service",
        "dd if=/dev/zero of=/dev/sda",
        "mkfs.ext4 /dev/sdb1",
    ]
    for cmd in blocked:
        r = term.run(cmd)
        assert r.success is False, f"sollte blockiert sein: {cmd}"
        assert r.approval_required is True
        assert "blockiert" in (r.error or "").lower() or "sicherheit" in (r.error or "").lower()


def test_allowed_command(term):
    r = term.run("echo odin-ok")
    assert r.success is True
    assert "odin-ok" in r.data["stdout"]


def test_working_dir_nonexistent(term):
    # Nicht-existierendes WorkingDir -> zurueckgewiesen
    r = term.run("pwd", working_dir="/etc/nichtda")
    assert r.success is False
    assert "existiert" in (r.error or "")


def test_timeout(term):
    r = term.run("sleep 10", timeout=1)
    assert r.success is False
    assert "Timeout" in (r.error or "")


def test_output_cap(term):
    r = term.run("seq 1 10000")
    assert r.success is True
    assert r.data["truncated"] is True or len(r.data["stdout"]) <= 2048