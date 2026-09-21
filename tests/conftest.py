"""ODIN Agent - Test-Konfiguration.

Stellt gemeinsame Fixtures fuer die Tests bereit (Config, Registry).
"""
import os
import sys
from pathlib import Path

import pytest

# Projektwurzel auf den sys.path legen, damit Imports einheitlich sind.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Tests laufen ohne reale .env-Secrets; Standardwerte der Config reichen.
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("LLM_BASE_URL", "http://127.0.0.1:1/v1")


@pytest.fixture
def registry():
    """Eine frisch aufgebaute Tool-Registry."""
    from tools.registry import build_default_registry

    return build_default_registry()


@pytest.fixture
def config():
    from config import Config

    return Config.load()