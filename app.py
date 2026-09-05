"""Vercel entrypoint for the Python src-layout application."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
os.environ.setdefault("PITWALL_KNOWLEDGE_DB", "/tmp/pitwall/knowledge.db")

from f1_pitwall.api.app import app  # noqa: E402

__all__ = ["app"]
