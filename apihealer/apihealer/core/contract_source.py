"""
Contract sources: where the "shape" of an API comes from, to diff against.

The engine doesn't need Swagger specifically; it needs a DESCRIPTION OF THE
SHAPE of the response to compare against. Swagger is one source of that shape,
but not the only one:

  - SwaggerSource      -> download a published OpenAPI spec (implemented).
  - InferredSource     -> call the endpoint and infer the shape of the real
                          JSON, for old APIs that don't publish a spec (pending).
  - (future)           -> GraphQL schema, gRPC .proto, SOAP WSDL...

All produce a comparable artifact (a file with the shape) and all are diffed by
the same engine. This makes "where the contract comes from" pluggable just like
the language adapters: the core doesn't change when adding sources.
"""

from __future__ import annotations

import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path


class ContractSource(ABC):
    """Contract every source must fulfill to feed the diff."""

    #: Short source name, e.g. "swagger". For logs and selection.
    name: str = "base"

    @abstractmethod
    def fetch(self, dest: Path) -> None:
        """
        Obtain the current shape of the contract and write it to `dest`.

        For SwaggerSource: download the swagger.json.
        For InferredSource: call the endpoint, infer the shape of the JSON and
        serialize it as a normalized spec. In both cases, the result in `dest`
        must be comparable by the same diff engine.
        """
        raise NotImplementedError


class SwaggerSource(ContractSource):
    """
    Source based on a published OpenAPI/Swagger spec.

    The reliable source and the only one implemented in the MVP: it covers most
    modern APIs (and internal ones generated with Swashbuckle).
    """

    name = "swagger"

    def __init__(self, url: str, timeout: int = 30):
        self.url = url
        self.timeout = timeout

    def fetch(self, dest: Path) -> None:
        # Security note: the URL is user-provided; we don't embed credentials.
        # Auth-protected Swaggers: pending (polish).
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(self.url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            dest.write_bytes(resp.read())


class InferredSource(ContractSource):
    """
    PENDING (polish). Source for APIs without a spec: call the endpoint, infer
    the shape of the real JSON and normalize it into a comparable spec.

    Limitations to solve when implemented:
      - A single response may not reveal optional fields; it's better to take
        several samples for a reliable shape.
      - Only safe for reads (GET). Do not invoke operations with side effects
        (POST/PUT/DELETE) just to observe their shape.

    Declared to pin the boundary; the core already works with any
    ContractSource, so implementing this won't touch the engine.
    """

    name = "inferred"

    def __init__(self, endpoint_url: str, samples: int = 1):
        self.endpoint_url = endpoint_url
        self.samples = samples

    def fetch(self, dest: Path) -> None:
        raise NotImplementedError(
            "InferredSource is not implemented yet. "
            "Only APIs that publish Swagger/OpenAPI are supported for now."
        )
