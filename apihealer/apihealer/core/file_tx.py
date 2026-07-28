"""
File transaction: apply multiple file writes atomically-ish, with rollback.

When a fix touches several files, a half-applied change that then fails leaves
the user's repo in a broken partial state. This wraps a set of writes so that
if any step fails, everything already written is restored to its original
content (or deleted, if the file was newly created).

It is not a true database transaction -- there's no cross-process locking --
but for a single CLI run remediating a working copy it gives the guarantee that
matters: all-or-nothing within the run.

Usage:
    with FileTransaction() as tx:
        tx.write(path_a, new_a)
        tx.write(path_b, new_b)
    # on leaving the block without error -> changes stay
    # if an exception is raised inside -> all writes are rolled back
"""

from __future__ import annotations

from pathlib import Path


class FileTransaction:
    def __init__(self):
        # path -> original bytes (None means the file did not exist before)
        self._backups: dict[Path, bytes | None] = {}
        self._committed = False

    def write(self, path: Path, content: str) -> None:
        """Write `content` to `path`, backing up its previous state first."""
        path = Path(path)
        if path not in self._backups:
            self._backups[path] = path.read_bytes() if path.exists() else None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def written_paths(self) -> list[Path]:
        return list(self._backups.keys())

    def rollback(self) -> None:
        """Restore every touched file to its original state."""
        for path, original in self._backups.items():
            try:
                if original is None:
                    # file was created during the transaction -> remove it
                    if path.exists():
                        path.unlink()
                else:
                    path.write_bytes(original)
            except Exception:
                # best-effort restore; keep going with the rest
                continue

    def commit(self) -> None:
        self._committed = True

    def __enter__(self) -> "FileTransaction":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None and not self._committed:
            self.rollback()
        # do not suppress the exception
        return False
