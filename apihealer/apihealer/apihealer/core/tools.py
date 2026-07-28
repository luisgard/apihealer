"""
Running external tools (oasdiff, nswag, dotnet, git...).

This module centralizes external process execution so the rest of the code
doesn't repeat subprocess handling, timeouts and error management. It is the
foundation of the "Python orchestrates, native tools do the work" pattern.

Cross-platform: uses shutil.which to locate binaries and assumes no paths from
any specific operating system.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class ToolResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def tool_available(name: str) -> bool:
    """True if the binary `name` is on the system PATH."""
    return shutil.which(name) is not None


def run_tool(
    args: list[str],
    cwd: str | None = None,
    timeout: int = 120,
) -> ToolResult:
    """
    Run an external command and capture its output.

    - args: list, e.g. ["oasdiff", "breaking", "old.json", "new.json"].
      Passed as a list (not a string) to avoid shell and injection issues.
    - cwd: working directory (for example the .NET project root).
    - timeout: seconds before aborting; prevents a hung build from blocking
      the tool.
    """
    if not args:
        return ToolResult(ok=False, exit_code=-1, stdout="", stderr="empty command")

    if not tool_available(args[0]):
        return ToolResult(
            ok=False,
            exit_code=-1,
            stdout="",
            stderr=f"tool not found on PATH: {args[0]}",
        )

    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return ToolResult(
            ok=(proc.returncode == 0),
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            ok=False,
            exit_code=-1,
            stdout="",
            stderr=f"timeout after {timeout}s running: {' '.join(args)}",
        )
    except Exception as exc:  # defensive: never crash the CLI over a tool
        return ToolResult(ok=False, exit_code=-1, stdout="", stderr=str(exc))
