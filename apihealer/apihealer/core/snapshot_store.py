"""
Snapshot store: per-API contract baselines, versioned in the repo.

Each watched API gets its OWN baseline, identified by a human-readable name, so
multiple APIs in one project never overwrite each other's snapshot (the bug of
a single fixed filename). Layout inside the project:

    <project>/.apihealer/
        stripe/
            contract.json        <- committed baseline for "stripe"
        internal-orders/
            contract.json        <- committed baseline for "internal-orders"

Design choice (Option A): the baseline lives in the repo, committed like any
other file. This makes it work identically locally and in ephemeral CI runners:
the runner clones the repo and the baseline is right there. When a change is
detected, the updated baseline is written and travels with the fix in the same
PR -- so git itself is both the persistence and the audit trail of how the
contract evolved.

Names are validated to be safe path segments. If no name is given, a short,
stable hash of the URL is used as a fallback so the tool still works, but a
name is recommended because these files are meant to be read by humans in the
repo tree.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

STORE_DIR = ".apihealer"
BASELINE_FILE = "contract.json"

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def normalize_name(name: str) -> str:
    """Turn a user-provided name into a safe path segment."""
    cleaned = _SAFE_NAME_RE.sub("-", name.strip()).strip("-.")
    return cleaned or "unnamed"


def name_from_url(url: str) -> str:
    """Stable fallback identifier when no name is given: short hash of the URL."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"api-{digest}"


@dataclass
class SnapshotStore:
    """Manages baseline snapshots for a single project, keyed by API name."""

    project_root: Path

    @property
    def root(self) -> Path:
        return self.project_root / STORE_DIR

    def api_dir(self, api_key: str) -> Path:
        return self.root / api_key

    def baseline_path(self, api_key: str) -> Path:
        return self.api_dir(api_key) / BASELINE_FILE

    def has_baseline(self, api_key: str) -> bool:
        return self.baseline_path(api_key).exists()

    def read_baseline(self, api_key: str) -> bytes | None:
        p = self.baseline_path(api_key)
        return p.read_bytes() if p.exists() else None

    def write_baseline(self, api_key: str, content: bytes) -> Path:
        p = self.baseline_path(api_key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def list_apis(self) -> list[str]:
        """Names of all APIs with a stored baseline in this project."""
        if not self.root.is_dir():
            return []
        return sorted(
            d.name for d in self.root.iterdir()
            if d.is_dir() and (d / BASELINE_FILE).exists()
        )

    def resolve_key(self, name: str | None, url: str) -> str:
        """Pick the storage key: the given name if any, else a hash of the URL."""
        return normalize_name(name) if name else name_from_url(url)
