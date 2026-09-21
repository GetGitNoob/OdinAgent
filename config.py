"""ODIN Agent - Konfiguration.

Laedt Umgebungsvariablen aus der .env-Datei (falls vorhanden)
und stellt typisierte Konfig-Werte bereit.
Secrets (LLM_API_KEY) stehen NIE im Code, sondern nur in .env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_SYSTEM_PROMPT = (
    "Du bist Odin, ein lokaler Assistent auf dem Server Odin. "
    "Antworte kurz und praezise auf Deutsch."
)


@dataclass(frozen=True)
class Config:
    # ---- LLM ----
    llm_base_url: str = "http://127.0.0.1:11436/v1"
    llm_model: str = ""
    llm_api_key: str = "local-"

    # ---- Agent ----
    max_history_messages: int = 20
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    # ---- Filesystem-Tool ----
    filesystem_allowed_roots: tuple[str, ...] = ("/opt/odin-agent", "/tmp")

    # ---- Terminal-Tool ----
    terminal_timeout: int = 10
    terminal_max_output: int = 10_000

    # ---- Server ----
    # 8000 nutzt der SearXNG/Docker-Container; Agent lauscht auf 8081.
    host: str = "0.0.0.0"
    port: int = 8081

    # ---- Communication ----
    whatsapp_enabled: bool = False

    @classmethod
    def load(cls) -> "Config":
        if load_dotenv is not None:
            load_dotenv(PROJECT_ROOT / ".env")

        def _env(name: str, default: str) -> str:
            return os.environ.get(name, default)

        def _int(name: str, default: int) -> int:
            raw = os.environ.get(name)
            if raw is None or raw == "":
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        def _bool(name: str, default: bool) -> bool:
            raw = os.environ.get(name, "").strip().lower()
            if raw in ("1", "true", "yes", "on"):
                return True
            if raw in ("0", "false", "no", "off"):
                return False
            return default

        roots_raw = os.environ.get(
            "FILESYSTEM_ALLOWED_ROOTS", "/opt/odin-agent"
        )
        roots = tuple(
            r.strip()
            for r in roots_raw.split(",")
            if r.strip()
        ) or ("/opt/odin-agent",)

        return cls(
            llm_base_url=_env("LLM_BASE_URL", "http://127.0.0.1:11436/v1"),
            llm_model=_env("LLM_MODEL", ""),
            llm_api_key=_env("LLM_API_KEY", "local-"),
            max_history_messages=_int(
                "MAX_HISTORY_MESSAGES", 20
            ),
            system_prompt=_env("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
            filesystem_allowed_roots=roots,
            terminal_timeout=_int("TERMINAL_TIMEOUT", 10),
            terminal_max_output=_int("TERMINAL_MAX_OUTPUT", 10_000),
            host=_env("HOST", "0.0.0.0"),
            port=_int("PORT", 8081),
            whatsapp_enabled=_bool("WHATSAPP_ENABLED", False),
        )