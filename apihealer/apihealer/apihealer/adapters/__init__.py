"""
Language adapter registry.

To add support for a new language:
  1. Create a module (e.g. node_adapter.py) with a class inheriting from
     LanguageAdapter.
  2. Import it here and add it to ALL_ADAPTERS.
The core doesn't change.
"""

from __future__ import annotations

from pathlib import Path

from .base import LanguageAdapter
from .dotnet_adapter import DotNetAdapter

# Order = detection priority. The first to recognize the project wins.
ALL_ADAPTERS: list[LanguageAdapter] = [
    DotNetAdapter(),
]


def select_adapter(project_root: Path) -> LanguageAdapter | None:
    """Return the first adapter that recognizes the project, or None."""
    for adapter in ALL_ADAPTERS:
        try:
            if adapter.detect(project_root):
                return adapter
        except Exception:
            # a broken adapter must not prevent trying the others
            continue
    return None
