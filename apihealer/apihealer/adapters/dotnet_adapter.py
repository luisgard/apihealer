"""
.NET project adapter: COORDINATOR.

After extracting classification (ClientClassifier), fix algorithms
(GeneratedFixStrategy / ManualFixStrategy) and native tools (DotNetToolchain),
the adapter is reduced to what it should be: detect the language, ask the
classifier, pick a strategy from the registry and delegate.

Strategies are registered as plugins keyed by ClientKind (see STRATEGY_REGISTRY),
so adding a new remediation path is registering a class, not editing the
coordinator. Collaborators are injectable (with defaults) for testing.
"""

from __future__ import annotations

from pathlib import Path

from .base import (
    ClientClassification,
    ClientKind,
    FixContext,
    LanguageAdapter,
    RemediationResult,
    VerificationKind,
    verification_report,
)
from .dotnet_classifier import ClientClassifier
from .dotnet_strategies import GeneratedFixStrategy, ManualFixStrategy
from .dotnet_toolchain import DotNetToolchain

# Plugin registry: ClientKind -> strategy class. Register a new path here.
STRATEGY_REGISTRY = {
    ClientKind.GENERATED: GeneratedFixStrategy,
    ClientKind.MANUAL: ManualFixStrategy,
}


class DotNetAdapter(LanguageAdapter):
    name = "dotnet"

    def __init__(self, toolchain=None, classifier=None, registry=None):
        self.tc = toolchain or DotNetToolchain()
        self.classifier = classifier or ClientClassifier()
        registry = registry or STRATEGY_REGISTRY
        # instantiate each registered strategy with the shared collaborators
        self._strategies = {
            kind: cls(self.tc, self.classifier) for kind, cls in registry.items()
        }

    def detect(self, project_root: Path) -> bool:
        return any(project_root.rglob("*.csproj"))

    def classify_client(self, project_root: Path) -> ClientClassification:
        return self.classifier.classify(project_root)

    def propose_fix(self, ctx: FixContext) -> RemediationResult:
        classification = self.classify_client(ctx.project_root)
        kind = classification.kind

        if kind is ClientKind.NONE:
            return RemediationResult(
                summary=(
                    "No API consumption detected in the project. Nothing to "
                    "remediate.\n\nContract changes:\n" + ctx.breaking_changes
                ),
                verification=verification_report(VerificationKind.NONE),
                notes=["No API client (ClientKind.NONE)."] + classification.reasons,
            )

        strategy = self._strategies.get(kind)
        if strategy is None:
            return RemediationResult(
                summary=f"No strategy for ClientKind={kind.value}.",
                verification=verification_report(VerificationKind.NONE),
                notes=["Client kind has no assigned strategy."],
            )
        return strategy.fix(ctx)
