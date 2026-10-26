"""ODIN Agent - Image Analysis Tool (Vision).

Analysiert lokale Bilddateien über die NInfer-Vision-API (OpenAI-kompatibel).
Unterstützte Formate: JPEG, PNG, WebP.

Sicherheit:
  - Nur reguläre Dateien aus erlaubten lokalen Pfaden.
  - Max. 4 Bilder pro Anfrage, max. 20 MB pro Bild.
  - Keine Cloud-Dienste, keine externen Uploads.
  - Bildinhalte werden als Daten behandelt, nicht als Anweisungen.
  - Keine Base64-Daten in Logs.
"""
from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

from tools.base import BaseTool, ToolResult

logger = logging.getLogger("odin-agent")

# Unterstützte Dateierweiterungen -> MIME-Typ
_SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

MAX_IMAGES_PER_REQUEST = 4
MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


class ImageAnalysisTool(BaseTool):
    name = "image_analysis"
    description = (
        "Analysiert ein oder mehrere lokale Bilder visuell mit dem Qwen-Vision-Modell. "
        "Übergib eine Liste von Bilddateipfaden (JPEG, PNG, WebP) und eine Fragestellung. "
        "Das Modell beschreibt den Bildinhalt, erkennt Objekte, Text, Szenen usw. "
        "Maximal 4 Bilder pro Anfrage, max. 20 MB pro Bild. "
        "Verwende dieses Tool, wenn du den visuellen Inhalt eines Bildes beurteilen musst. "
        "Für reine EXIF- oder Dateisystemfragen nutze stattdessen terminal/filesystem."
    )
    parameters = {
        "type": "object",
        "properties": {
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Liste lokaler Bilddateipfade (absolut). "
                    "Unterstützt: .jpg, .jpeg, .png, .webp. Max. 4 Einträge."
                ),
            },
            "question": {
                "type": "string",
                "description": (
                    "Die Fragestellung zur Bildanalyse, z. B. 'Beschreibe das Bild', "
                    "'Ist das ein echtes Foto oder ein Internet-Bild?', "
                    "'Was steht im Text auf dem Bild?'"
                ),
            },
        },
        "required": ["image_paths", "question"],
        "additionalProperties": False,
    }

    def __init__(
        self,
        api_base_url: str = "http://127.0.0.1:8082/v1",
        model: str = "qwen3.8-27b",
        api_key: str = "local-dummy",
        timeout: float = 120.0,
    ) -> None:
        super().__init__()
        self._api_base_url = api_base_url
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client = None

    def _get_client(self):
        """Erzeugt den OpenAI-Client lazy."""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self._api_base_url,
                api_key=self._api_key or "local-dummy",
                timeout=self._timeout,
                max_retries=1,
            )
        return self._client

    @staticmethod
    def _detect_mime(path: Path) -> str | None:
        """Liefert den MIME-Typ basierend auf der Dateiendung, oder None."""
        ext = path.suffix.lower()
        return _SUPPORTED_EXTENSIONS.get(ext)

    @staticmethod
    def _validate_path(path_str: str) -> Path:
        """Validiert einen Bilddateipfad. Wirft ValueError bei Problemen."""
        p = Path(path_str)
        if not p.is_absolute():
            raise ValueError(f"Pfad muss absolut sein: {path_str}")
        if not p.exists():
            raise ValueError(f"Datei nicht gefunden: {path_str}")
        if not p.is_file():
            raise ValueError(f"Keine reguläre Datei: {path_str}")
        mime = ImageAnalysisTool._detect_mime(p)
        if mime is None:
            raise ValueError(
                f"Nicht unterstütztes Format ({p.suffix}): {path_str}. "
                "Erlaubt: .jpg, .jpeg, .png, .webp"
            )
        size = p.stat().st_size
        if size > MAX_IMAGE_SIZE_BYTES:
            raise ValueError(
                f"Bild zu groß ({size / 1024 / 1024:.1f} MB > 20 MB): {path_str}"
            )
        if size == 0:
            raise ValueError(f"Leere Datei: {path_str}")
        return p

    def run(
        self,
        image_paths: list[str],
        question: str,
    ) -> ToolResult:
        start = time.perf_counter()

        # --- Eingabevalidierung ---
        if not image_paths:
            return ToolResult.fail(
                error="Keine Bilddateipfade angegeben.",
                duration=time.perf_counter() - start,
            )
        if len(image_paths) > MAX_IMAGES_PER_REQUEST:
            return ToolResult.fail(
                error=(
                    f"Zu viele Bilder ({len(image_paths)}). "
                    f"Maximal {MAX_IMAGES_PER_REQUEST} pro Anfrage."
                ),
                duration=time.perf_counter() - start,
            )
        question = question.strip()
        if not question:
            return ToolResult.fail(
                error="Keine Fragestellung angegeben.",
                duration=time.perf_counter() - start,
            )

        # --- Bilder laden und validieren ---
        content_parts: list[dict] = []
        loaded_files: list[str] = []

        for path_str in image_paths:
            try:
                p = self._validate_path(path_str)
            except ValueError as e:
                return ToolResult.fail(
                    error=str(e),
                    duration=time.perf_counter() - start,
                )

            try:
                raw = p.read_bytes()
            except OSError as e:
                return ToolResult.fail(
                    error=f"Lesefehler bei {path_str}: {e}",
                    duration=time.perf_counter() - start,
                )

            b64 = base64.b64encode(raw).decode("ascii")
            mime = self._detect_mime(p)
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
            loaded_files.append(str(p))

        # --- API-Aufruf ---
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                *content_parts,
            ],
        }]

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=1024,
                temperature=0.2,
                stream=False,
            )
        except Exception as e:
            logger.warning(
                "ImageAnalysis API-Fehler: %s (files=%d)", type(e).__name__, len(loaded_files)
            )
            return ToolResult.fail(
                error=f"Vision-API-Fehler: {type(e).__name__}: {e}",
                duration=time.perf_counter() - start,
            )

        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            return ToolResult.fail(
                error="Vision-API hat eine leere Antwort geliefert.",
                duration=time.perf_counter() - start,
            )

        return ToolResult.ok(
            data={
                "question": question,
                "images_analyzed": loaded_files,
                "analysis": answer,
            },
            duration=time.perf_counter() - start,
        )
