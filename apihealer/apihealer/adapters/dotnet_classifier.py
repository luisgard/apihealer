"""
API-consumption classifier for .NET projects.

Single responsibility: given a project, decide whether it consumes the API with
a GENERATED, MANUAL or NONE client, AND carry the evidence for that verdict.
Isolated from the adapter because it's the most heuristic and fallible part of
the system -- the one you'll most want to test against real projects and tune.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import ClientClassification, ClientKind
from .dotnet_generators import select_generator

# Signs of HTTP API consumption without a regenerable generator => MANUAL.
_API_CALL_MARKERS = (
    "getasync(",
    "postasync(",
    "putasync(",
    "deleteasync(",
    "getfromjsonasync(",
    "readfromjsonasync(",
    "sendasync(",
)
_API_LIB_MARKERS = ("httpclient", "ihttpclientfactory", "restsharp", "refit")
_CLIENT_CLASS_RE = re.compile(r"class\s+\w*(client|api|service)\b", re.IGNORECASE)


class ClientClassifier:
    """Decides the ClientClassification of a .NET project."""

    def classify(self, project_root: Path) -> ClientClassification:
        # Manifest text (.csproj + generator config files) is authoritative for
        # detecting a generator: package references live there, not in comments.
        # Using code comments would produce false positives (e.g. a comment
        # saying "no nswag here" would look like NSwag).
        manifest_text = self._read_manifest_text(project_root)
        code_text = self._read_code_text(project_root)

        generator = select_generator(project_root, manifest_text)
        if generator is not None:
            return ClientClassification(
                kind=ClientKind.GENERATED,
                confidence=0.9,
                reasons=[f"Detected regenerable generator: {generator.name}."],
                generator_name=generator.name,
            )

        candidates = self.api_consuming_files(project_root)
        if self._looks_like_api_consumer(project_root, code_text):
            return ClientClassification(
                kind=ClientKind.MANUAL,
                confidence=0.6,
                reasons=["API consumption signs found, but no regenerable generator."],
                candidate_files=[str(p.relative_to(project_root)) for p in candidates],
            )

        return ClientClassification(
            kind=ClientKind.NONE,
            confidence=0.7,
            reasons=["No signs of API consumption found."],
        )

    def api_consuming_files(self, project_root: Path) -> list[Path]:
        """.cs files with signs of API consumption (candidates to adapt)."""
        markers = _API_CALL_MARKERS + _API_LIB_MARKERS
        hits: list[Path] = []
        for f in self._iter_cs(project_root):
            try:
                text = f.read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                continue
            if any(m in text for m in markers):
                hits.append(f)
        return hits

    # --- internal heuristics --------------------------------------------------

    def _looks_like_api_consumer(self, project_root: Path, code_text: str) -> bool:
        # Real HTTP calls in code are the strongest signal.
        if any(m in code_text for m in _API_CALL_MARKERS):
            return True
        # HttpClient usage plus a client-named class.
        has_lib = any(m in code_text for m in _API_LIB_MARKERS)
        if has_lib and self._has_client_named_class(project_root):
            return True
        # Refit/RestSharp appear as package references in the manifest, not just
        # in code -- check there too so a bare usage still counts.
        manifest = self._read_manifest_text(project_root)
        return ("restsharp" in manifest or "refit" in manifest
                or "restsharp" in code_text or "refit" in code_text)

    def _has_client_named_class(self, project_root: Path) -> bool:
        for f in self._iter_cs(project_root):
            try:
                if _CLIENT_CLASS_RE.search(f.read_text(encoding="utf-8", errors="ignore")):
                    return True
            except Exception:
                continue
        return False

    # --- file reading (bounded) ----------------------------------------------

    def _iter_cs(self, project_root: Path):
        for f in project_root.rglob("*.cs"):
            if any(seg in f.parts for seg in ("bin", "obj")):
                continue
            yield f

    def _read_manifest_text(self, project_root: Path) -> str:
        """Text of .csproj files plus generator config files, lowercased.

        Authoritative for generator/package detection: this is where
        PackageReference and generator configs live, not code comments.
        """
        parts: list[str] = []
        for csproj in project_root.rglob("*.csproj"):
            if any(seg in csproj.parts for seg in ("bin", "obj")):
                continue
            try:
                parts.append(csproj.read_text(encoding="utf-8", errors="ignore").lower())
            except Exception:
                continue
        # generator config files that also imply a generator
        for cfg in ("nswag.json", "kiota-lock.json", "openapitools.json"):
            for f in project_root.rglob(cfg):
                parts.append(cfg.lower())
        return "\n".join(parts)

    def _read_code_text(self, project_root: Path) -> str:
        """Text of .cs files, lowercased. For API-consumption heuristics."""
        parts: list[str] = []
        for f in self._iter_cs(project_root):
            try:
                parts.append(f.read_text(encoding="utf-8", errors="ignore").lower())
            except Exception:
                continue
        return "\n".join(parts)
