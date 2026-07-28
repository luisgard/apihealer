"""
.NET toolchain: the single place that invokes native tools.

Embodies the project's philosophy ("Python orchestrates, native tools do the
work") in a concrete object. Strategies and the adapter receive a
DotNetToolchain by injection, instead of calling subprocess themselves.

Testing benefit: a FakeToolchain inheriting from this class lets you test the
strategies without dotnet/nswag installed.
"""

from __future__ import annotations

from pathlib import Path

from ..core.tools import ToolResult, run_tool, tool_available
from .dotnet_generators import Generator, select_generator


class DotNetToolchain:
    """Wraps build, error parsing and client regeneration."""

    def dotnet_available(self) -> bool:
        return tool_available("dotnet")

    def build(self, project_root: Path) -> ToolResult | None:
        """Compile. Returns a ToolResult, or None if dotnet is missing."""
        if not self.dotnet_available():
            return None
        return run_tool(["dotnet", "build", "--nologo"], cwd=str(project_root))

    def select_generator(self, project_root: Path, project_text: str) -> Generator | None:
        return select_generator(project_root, project_text)

    def regenerate(self, generator: Generator, project_root: Path, contract_new: Path) -> ToolResult:
        return generator.regenerate(project_root, contract_new)

    def parse_compiler_errors(self, build_output: str) -> list[dict]:
        """Extract errors from the MSBuild format: File.cs(42,13): error CS...: msg"""
        errors: list[dict] = []
        for line in build_output.splitlines():
            if ": error " not in line:
                continue
            try:
                location, rest = line.split(": error ", 1)
                file_part = location.strip()
                lineno = ""
                if "(" in file_part and ")" in file_part:
                    path, coords = file_part.rsplit("(", 1)
                    lineno = coords.split(",")[0].strip(") ")
                    file_part = path.strip()
                errors.append({"file": file_part, "line": lineno, "message": rest.strip()})
            except Exception:
                continue
        return errors
