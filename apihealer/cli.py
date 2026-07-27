"""
CLI de APIHealer.

Flujo (con el diff barato ANTES del adapter):
    1. Pedir la ruta del proyecto.
    2. Detectar lenguaje -> seleccionar adapter.
    3. Pedir la URL del contrato (hoy: Swagger).
    4. Obtener el contrato (ContractSource) y diffear contra el snapshot.
    5. Si hay breaking changes que afectan, el adapter propone el fix.

Multiplataforma: solo libreria estandar + herramientas externas por PATH.
Corre igual en Windows, Linux y Mac.

Dos ejes de extensibilidad, ambos enchufables sin tocar el nucleo:
  - Adapters de lenguaje  (adapters/): como remediar el codigo.
  - Fuentes de contrato   (core/contract_source.py): de donde sale la forma.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapters import select_adapter
from .core import diff as diff_mod
from .core.contract_source import SwaggerSource

SNAPSHOT_DIR = ".apihealer"


def _prompt(text: str, provided: str | None) -> str:
    if provided:
        return provided
    return input(text).strip()


def _info(msg: str) -> None:
    print(f"  {msg}")


def _step(msg: str) -> None:
    print(f"\n> {msg}")


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _promote_snapshot(new_snapshot: Path, old_snapshot: Path) -> None:
    """El contrato nuevo pasa a ser la linea base para la proxima corrida."""
    old_snapshot.write_bytes(new_snapshot.read_bytes())


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apihealer",
        description="Detecta cambios en el contrato de una API y remedia el codigo que la consume.",
    )
    parser.add_argument("--path", help="Ruta de la carpeta principal del proyecto.")
    parser.add_argument("--swagger-url", help="URL del swagger.json a vigilar.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Permitir que el adapter aplique cambios en disco (por defecto solo propone).",
    )
    args = parser.parse_args(argv)

    print("=" * 60)
    print("  APIHealer  -  auto-remediacion de contratos de API")
    print("=" * 60)

    if not diff_mod.oasdiff_installed():
        print("\n[!] oasdiff no esta instalado o no esta en el PATH.")
        print("    Es la herramienta que detecta breaking changes.")
        print("    Instalacion: https://github.com/oasdiff/oasdiff  (binario unico, multiplataforma)")
        return 2

    # Paso 1: ruta del proyecto.
    _step("Paso 1/5 - Proyecto")
    raw_path = _prompt("  Ruta de la carpeta principal del proyecto: ", args.path)
    project_root = Path(raw_path).expanduser().resolve()
    if not project_root.is_dir():
        print(f"[!] La ruta no existe o no es una carpeta: {project_root}")
        return 1
    _info(f"Proyecto: {project_root}")

    # Paso 2: detectar lenguaje / adapter.
    _step("Paso 2/5 - Deteccion de lenguaje")
    adapter = select_adapter(project_root)
    if adapter is None:
        print("[!] Ningun adapter reconocio este proyecto.")
        print("    Hoy soportamos: .NET. (Otros lenguajes: proximamente.)")
        return 1
    _info(f"Adapter seleccionado: {adapter.name}")
    generated = adapter.uses_generated_client(project_root)
    _info(
        "Consumo de API: cliente GENERADO (camino facil)."
        if generated
        else "Consumo de API: parece MANUAL (camino dificil, soporte limitado)."
    )

    # Paso 3: fuente del contrato (hoy, Swagger).
    _step("Paso 3/5 - Contrato de la API")
    swagger_url = _prompt("  URL del swagger.json: ", args.swagger_url)
    if not swagger_url:
        print("[!] Se requiere la URL del contrato.")
        return 1
    source = SwaggerSource(swagger_url)
    _info(f"Fuente de contrato: {source.name}")

    snap_dir = project_root / SNAPSHOT_DIR
    old_snapshot = snap_dir / "contract_prev.json"
    new_snapshot = snap_dir / "contract_new.json"

    # Paso 4: obtener y diffear.
    _step("Paso 4/5 - Deteccion de cambios")
    try:
        source.fetch(new_snapshot)
    except Exception as exc:
        print(f"[!] No se pudo obtener el contrato: {exc}")
        return 1
    _info("Contrato obtenido.")

    diff = diff_mod.diff_contracts(old_snapshot, new_snapshot)

    if diff.first_run:
        _info("Primera corrida: guardado como linea base. Nada que comparar aun.")
        _promote_snapshot(new_snapshot, old_snapshot)
        print("\nLinea base establecida. Vuelve a correr tras el proximo cambio del proveedor.")
        return 0

    if not diff.changed:
        _info("El contrato no cambio desde la ultima vez. Nada que hacer.")
        return 0

    if not diff.has_breaking:
        _info("El contrato cambio, pero sin breaking changes. Actualizo la linea base.")
        _promote_snapshot(new_snapshot, old_snapshot)
        return 0

    print("\n[!] Se detectaron breaking changes:")
    print(_indent(diff.breaking_report))

    # Paso 5: remediacion via adapter.
    _step("Paso 5/5 - Remediacion")
    proposal = adapter.propose_fix(project_root, new_snapshot, diff.breaking_report)

    print(_indent(proposal.summary))
    if proposal.notes:
        print("\n  Notas:")
        for n in proposal.notes:
            print(f"   - {n}")
    print(f"\n  Confianza: {proposal.confidence:.0%}")

    if proposal.applied:
        _info("Cambios aplicados en tu working copy. Revisa el diff antes de commitear.")
        _promote_snapshot(new_snapshot, old_snapshot)
    else:
        _info("No se aplicaron cambios automaticamente (solo propuesta).")
        _info("La linea base NO se actualizo: el cambio sigue pendiente de resolver.")

    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
