"""Tests für das ImageAnalysisTool (Vision).

Verwendet gemockte API-Aufrufe – keine echten Bilddateien aus der
privaten Sammlung, keine echten NInfer-Calls.
"""
from __future__ import annotations

import base64
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.base import ToolResult
from tools.image_analysis import ImageAnalysisTool


# ---------------------------------------------------------
# Hilfsfunktionen: minimale valide Bilddateien erzeugen
# ---------------------------------------------------------

def _make_jpeg(path: Path, width: int = 10, height: int = 10) -> None:
    """Erzeugt eine minimale JPEG-Datei (JFIF-Header + EOI)."""
    # Minimaler JPEG: SOI + APP0 + EOI
    data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    data += b"\xff\xd9"
    path.write_bytes(data)


def _make_png(path: Path) -> None:
    """Erzeugt eine minimale PNG-Datei."""
    import zlib

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    iend = chunk(b"IEND", b"")
    path.write_bytes(sig + ihdr + idat + iend)


@pytest.fixture
def tool() -> ImageAnalysisTool:
    """Ein ImageAnalysisTool mit fiktiver API-Adresse (kein echter Call)."""
    return ImageAnalysisTool(
        api_base_url="http://127.0.0.1:1/v1",
        model="test-vision-model",
        api_key="test-key",
        timeout=5.0,
    )


@pytest.fixture
def jpeg_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_photo.jpg"
    _make_jpeg(p)
    return p


@pytest.fixture
def png_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_image.png"
    _make_png(p)
    return p


# ---------------------------------------------------------
# Registrierung & Definition
# ---------------------------------------------------------

class TestRegistration:
    def test_tool_name(self):
        assert ImageAnalysisTool.name == "image_analysis"

    def test_definition_openai_compatible(self, tool):
        d = tool.definition
        assert d["type"] == "function"
        assert d["function"]["name"] == "image_analysis"
        assert "image_paths" in d["function"]["parameters"]["properties"]
        assert "question" in d["function"]["parameters"]["properties"]

    def test_registered_in_default_registry(self):
        from tools.registry import get_registry

        reg = get_registry()
        assert "image_analysis" in reg.names()
        t = reg.get("image_analysis")
        assert isinstance(t, ImageAnalysisTool)


# ---------------------------------------------------------
# Erfolgreiche Analyse (gemockt)
# ---------------------------------------------------------

class TestSuccessfulAnalysis:
    @patch("tools.image_analysis.ImageAnalysisTool._get_client")
    def test_single_jpeg(self, mock_get_client, tool, jpeg_file):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Ein Testbild."
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = tool.run(
            image_paths=[str(jpeg_file)],
            question="Was ist auf dem Bild?",
        )
        assert result.success is True
        assert result.data["analysis"] == "Ein Testbild."
        assert result.data["images_analyzed"] == [str(jpeg_file)]

        # API wurde korrekt aufgerufen
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "test-vision-model"
        content = call_kwargs["messages"][0]["content"]
        # Erste Part: Text-Frage, dann Bild
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    @patch("tools.image_analysis.ImageAnalysisTool._get_client")
    def test_multiple_images(self, mock_get_client, tool, jpeg_file, png_file):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Zwei Bilder analysiert."
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = tool.run(
            image_paths=[str(jpeg_file), str(png_file)],
            question="Vergleiche die Bilder.",
        )
        assert result.success is True
        assert len(result.data["images_analyzed"]) == 2

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        content = call_kwargs["messages"][0]["content"]
        # 1 Text + 2 Bilder = 3 Parts
        assert len(content) == 3
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert content[2]["image_url"]["url"].startswith("data:image/png;base64,")

    @patch("tools.image_analysis.ImageAnalysisTool._get_client")
    def test_png_format(self, mock_get_client, tool, png_file):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "PNG-Bild."
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = tool.run(
            image_paths=[str(png_file)],
            question="Beschreibe das Bild.",
        )
        assert result.success is True


# ---------------------------------------------------------
# Fehlerfälle
# ---------------------------------------------------------

class TestErrorHandling:
    def test_nonexistent_file(self, tool, tmp_path):
        result = tool.run(
            image_paths=[str(tmp_path / "nicht_da.jpg")],
            question="Test",
        )
        assert result.success is False
        assert "nicht gefunden" in result.error

    def test_unsupported_format(self, tool, tmp_path):
        bad = tmp_path / "test.bmp"
        bad.write_bytes(b"BM" + b"\x00" * 100)
        result = tool.run(
            image_paths=[str(bad)],
            question="Test",
        )
        assert result.success is False
        assert "Nicht unterstütztes Format" in result.error

    def test_empty_image_paths(self, tool):
        result = tool.run(image_paths=[], question="Test")
        assert result.success is False
        assert "Keine Bilddateipfade" in result.error

    def test_too_many_images(self, tool, jpeg_file):
        result = tool.run(
            image_paths=[str(jpeg_file)] * 5,
            question="Test",
        )
        assert result.success is False
        assert "Zu viele Bilder" in result.error

    def test_empty_question(self, tool, jpeg_file):
        result = tool.run(
            image_paths=[str(jpeg_file)],
            question="   ",
        )
        assert result.success is False
        assert "Keine Fragestellung" in result.error

    def test_relative_path_rejected(self, tool, tmp_path):
        result = tool.run(
            image_paths=["relative/path.jpg"],
            question="Test",
        )
        assert result.success is False
        assert "absolut" in result.error

    def test_directory_rejected(self, tool, tmp_path):
        result = tool.run(
            image_paths=[str(tmp_path)],
            question="Test",
        )
        assert result.success is False
        assert "Keine reguläre Datei" in result.error

    @patch("tools.image_analysis.ImageAnalysisTool._get_client")
    def test_api_error(self, mock_get_client, tool, jpeg_file):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Connection refused")
        mock_get_client.return_value = mock_client

        result = tool.run(
            image_paths=[str(jpeg_file)],
            question="Test",
        )
        assert result.success is False
        assert "Vision-API-Fehler" in result.error

    @patch("tools.image_analysis.ImageAnalysisTool._get_client")
    def test_empty_api_response(self, mock_get_client, tool, jpeg_file):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = tool.run(
            image_paths=[str(jpeg_file)],
            question="Test",
        )
        assert result.success is False
        assert "leere Antwort" in result.error

    def test_zero_byte_file(self, tool, tmp_path):
        empty = tmp_path / "empty.jpg"
        empty.write_bytes(b"")
        result = tool.run(
            image_paths=[str(empty)],
            question="Test",
        )
        assert result.success is False
        assert "Leere Datei" in result.error


# ---------------------------------------------------------
# execute()-Wrapper (Exception-Schutz)
# ---------------------------------------------------------

class TestExecuteWrapper:
    def test_execute_returns_toolresult(self, tool, jpeg_file):
        with patch.object(tool, "run", side_effect=RuntimeError("boom")):
            result = tool.execute({"image_paths": [str(jpeg_file)], "question": "x"})
        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "boom" in result.error
