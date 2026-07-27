"""
Deteccion de breaking changes entre dos artefactos de contrato.

NUCLEO PURO y agnostico al lenguaje Y a la fuente: recibe dos archivos (el
snapshot previo y el actual, producidos por cualquier ContractSource) y los
compara. El diff lo hace oasdiff, que ya codifica correctamente las reglas de
compatibilidad OpenAPI; no las reimplementamos.

La obtencion del contrato ya NO vive aqui: la hace la ContractSource
(ver core/contract_source.py). Esto deja el motor de diff independiente de si
el contrato vino de un Swagger publicado o de una forma inferida.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .tools import run_tool, tool_available


@dataclass
class DiffResult:
    first_run: bool          # no habia snapshot previo: nada que comparar aun
    changed: bool            # el contrato cambio respecto al snapshot
    has_breaking: bool       # hay cambios incompatibles
    breaking_report: str     # salida legible de oasdiff (para el PR)


def diff_contracts(old_path: Path, new_path: Path) -> DiffResult:
    """
    Compara dos artefactos de contrato. Si no hay snapshot previo
    (`old_path` no existe), es la primera corrida: nada que comparar todavia.
    """
    if not old_path.exists():
        return DiffResult(first_run=True, changed=False, has_breaking=False, breaking_report="")

    if old_path.read_bytes() == new_path.read_bytes():
        return DiffResult(first_run=False, changed=False, has_breaking=False, breaking_report="")

    result = run_tool(["oasdiff", "breaking", str(old_path), str(new_path)])

    # oasdiff sale con codigo != 0 cuando ENCUENTRA breaking changes.
    # Distinguimos "encontro breaking" de "fallo real" por stderr.
    has_breaking = bool(result.stdout.strip()) and "error" not in result.stderr.lower()
    report = result.stdout.strip() or result.stderr.strip()

    return DiffResult(first_run=False, changed=True, has_breaking=has_breaking, breaking_report=report)


def oasdiff_installed() -> bool:
    return tool_available("oasdiff")
