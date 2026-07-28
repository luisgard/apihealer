"""
Pluggable .NET client generators.

Each Generator knows how to: (a) recognize whether a project uses it, and
(b) regenerate the client from a new contract, invoking its native tool as an
external process. Adding Kiota or openapi-generator is writing a class here and
registering it in ALL_GENERATORS; the adapter doesn't change.

Note: Refit is NOT a generator (it produces no regenerable files), so it
doesn't live here: it's handled as a MANUAL client in the adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..core.tools import ToolResult, run_tool, tool_available


class Generator(ABC):
    """Contract of a regenerable client generator."""

    name: str = "base"
    #: binary this generator invokes (to check availability).
    tool: str = ""

    @abstractmethod
    def matches(self, project_root: Path, project_text: str) -> bool:
        """Does this project use this generator? (project_text = csproj+cs, lowercased)"""
        raise NotImplementedError

    def available(self) -> bool:
        """Is the generator's binary installed?"""
        return tool_available(self.tool) if self.tool else False

    @abstractmethod
    def regenerate(self, project_root: Path, contract_new: Path) -> ToolResult:
        """Regenerate the client from `contract_new`. Returns the ToolResult."""
        raise NotImplementedError


class NSwagGenerator(Generator):
    name = "nswag"
    tool = "nswag"

    def matches(self, project_root: Path, project_text: str) -> bool:
        if any(project_root.rglob("nswag.json")):
            return True
        return "nswag" in project_text

    def regenerate(self, project_root: Path, contract_new: Path) -> ToolResult:
        # If nswag.json exists, `nswag run` uses it. (Pointing the input to the
        # new contract per the project's real config is polish.)
        return run_tool(["nswag", "run"], cwd=str(project_root))


class KiotaGenerator(Generator):
    name = "kiota"
    tool = "kiota"

    def matches(self, project_root: Path, project_text: str) -> bool:
        return "microsoft.kiota" in project_text or "kiota" in project_text

    def regenerate(self, project_root: Path, contract_new: Path) -> ToolResult:
        # kiota generate -d <contract> -l csharp ; exact flags (namespace,
        # output folder) come from the project config in the polish phase.
        return run_tool(
            ["kiota", "generate", "-d", str(contract_new), "-l", "csharp"],
            cwd=str(project_root),
        )


class OpenApiGenerator(Generator):
    name = "openapi-generator"
    tool = "openapi-generator-cli"

    def matches(self, project_root: Path, project_text: str) -> bool:
        return "openapi-generator" in project_text or "openapitools" in project_text

    def regenerate(self, project_root: Path, contract_new: Path) -> ToolResult:
        return run_tool(
            ["openapi-generator-cli", "generate", "-i", str(contract_new), "-g", "csharp"],
            cwd=str(project_root),
        )


# Order = detection priority.
ALL_GENERATORS: list[Generator] = [
    NSwagGenerator(),
    KiotaGenerator(),
    OpenApiGenerator(),
]


def select_generator(project_root: Path, project_text: str) -> Generator | None:
    """Return the first generator that recognizes the project, or None."""
    for gen in ALL_GENERATORS:
        try:
            if gen.matches(project_root, project_text):
                return gen
        except Exception:
            continue
    return None
