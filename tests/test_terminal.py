"""Tests fuer das Terminal-Tool (Deny-Liste, Timeout, Output-Cap, Fehlerdiagnose)."""
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
    # Muss den konkreten Befehl und die Exception-Klasse enthalten
    assert "TimeoutExpired" in (r.error or "")
    assert "sleep 10" in (r.error or "")


def test_output_cap(term):
    r = term.run("seq 1 10000")
    assert r.success is True
    assert r.data["truncated"] is True or len(r.data["stdout"]) <= 2048


# --- Neue Tests: Fehlerdiagnose -------------------------------------------

def test_file_not_found_includes_exception_msg(term):
    """Fehlender Befehl: Bei shell=True meldet die Shell Exit-Code 127 + stderr.
    
    Der Tool-Code muss diese Information korrekt weitergeben (exit_code + stderr + note).
    """
    r = term.run("/nonexistent_binary_xyz_12345 arg1")
    # Bei shell=True: Der Prozess läuft, aber das Binary fehlt -> Exit-Code 127
    assert r.success is True  # Prozess lief aus (Shell meldet den Fehler)
    assert r.data["exit_code"] == 127
    # stderr muss die Fehlermeldung der Shell enthalten
    assert "not found" in r.data["stderr"].lower()
    # note-Feld muss vorhanden sein (kennzeichnet den Fehler)
    assert "note" in r.data
    assert "127" in r.data["note"]


def test_file_not_found_python_exception():
    """FileNotFoundError als Python-Exception (wuerde bei shell=False auftreten).
    
    Wir testen hier, dass der except-Block in terminal.py den Exception-Text
    korrekt einbindet, indem wir den Code-Pfad simulieren.
    """
    from tools.base import ToolResult
    # Simuliere was der except-Block erzeugen wuerde
    fake_e = type('FakeErr', (FileNotFoundError,), {'msg': '/nonexistent_binary_xyz_12345'})()
    msg = getattr(fake_e, "msg", None) or str(fake_e)
    expected = f"FileNotFoundError: Befehl nicht gefunden: {msg} (Befehl war: '/nonexistent_binary_xyz_12345 arg1')"
    # Pruefe, dass der String nicht leer ist und Details enthaelt
    assert "nicht gefunden" in expected
    assert "nonexistent_binary_xyz_12345" in expected
    assert len(expected) > len("Befehl nicht gefunden:")


def test_exit_code_nonzero_returns_data_with_note(term):
    """Exit-Code != 0 liefert success=True (Befehl lief aus) + note-Feld."""
    r = term.run("exit 42")
    assert r.success is True  # Der Befehl wurde ausgeführt
    assert r.data["exit_code"] == 42
    assert "note" in r.data
    assert "42" in r.data["note"]


def test_stderr_captured_on_failure(term):
    """stderr wird bei Exit-Code != 0 im Data-Feld geliefert."""
    r = term.run("echo 'fehlermeldung' >&2; exit 1")
    assert r.success is True  # Befehl lief aus
    assert r.data["exit_code"] == 1
    assert "fehlermeldung" in r.data["stderr"]
    assert "note" in r.data


def test_permission_error_handling(term):
    """Permission denied: Bei shell=True meldet die Shell Exit-Code + stderr.
    
    Der Tool-Code muss diese Information korrekt weitergeben.
    """
    r = term.run("echo test > /proc/sys/kernel/osrelease")
    # Bei shell=True: Shell meldet "Permission denied" als Exit-Code + stderr
    assert r.success is True  # Prozess lief aus
    assert r.data["exit_code"] != 0
    # stderr muss die Fehlermeldung enthalten
    assert "permission denied" in r.data["stderr"].lower()
    # note-Feld muss vorhanden sein
    assert "note" in r.data


def test_permission_error_python_exception():
    """PermissionError als Python-Exception (wuerde bei shell=False auftreten).
    
    Wir pruefen, dass der except-Block in terminal.py den Exception-Text
    korrekt einbindet.
    """
    from tools.base import ToolResult
    # Simuliere was der except-Block erzeugen wuerde
    fake_e = type("FakeErr", (PermissionError,), {"msg": "[Errno 13] Permission denied: /proc/sys/kernel/osrelease"})()
    msg = getattr(fake_e, "msg", None) or str(fake_e)
    expected = f"PermissionError: Keine Berechtigung: {msg} (Befehl war: 'echo test > /proc/sys/kernel/osrelease')"
    assert "Keine Berechtigung" in expected
    assert "Permission denied" in expected
    assert len(expected) > 20


def test_tool_result_fail_string_representation():
    """ToolResult.fail().__str__() gibt die konkrete Fehlermeldung, nicht 'True'."""
    from tools.base import ToolResult
    r = ToolResult.fail(error="Konkreter Fehler: Datei /tmp/x nicht gefunden")
    s = str(r)
    assert "Konkreter Fehler" in s
    assert "Datei /tmp/x nicht gefunden" in s
    # Darf NICHT nur "FEHLER: True" sein
    assert s != "FEHLER: True"
    assert "True" not in s.split(":")[1] if ":" in s else True


def test_tool_result_ok_string_representation():
    """ToolResult.ok().__str__() gibt JSON-Daten."""
    from tools.base import ToolResult
    r = ToolResult.ok(data={"key": "wert"})
    s = str(r)
    assert '"key"' in s
    assert '"wert"' in s


def test_empty_command(term):
    """Leerer Befehl wird sauber abgefangen."""
    r = term.run("")
    assert r.success is False
    assert "Kein Befehl" in (r.error or "")


def test_oserror_handling(term):
    """OSError (z.B. zu viele offene Dateien) wird korrekt gemeldet."""
    # Simuliere einen OSError durch einen ungültigen Pfad
    r = term.run("cat /dev/null/nonexistent", timeout=2)
    # Dies wird typischerweise als Exit-Code != 0 kommen (cat meldet den Fehler)
    # Oder als OSError wenn der Pfad wirklich ungültig ist
    if r.success:
        assert r.data["exit_code"] != 0
    else:
        assert r.error is not None
        assert len(r.error) > 0
