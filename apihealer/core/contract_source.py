"""
Fuentes de contrato: de donde se obtiene la "forma" de una API para diffear.

El motor no necesita Swagger especificamente; necesita una DESCRIPCION DE LA
FORMA de la respuesta contra la cual comparar. Swagger es una fuente de esa
forma, pero no la unica:

  - SwaggerSource      -> descarga un spec OpenAPI publicado (implementada).
  - InferredSource     -> llama al endpoint e infiere la forma del JSON real,
                          para APIs viejas que no publican spec (pendiente 10%).
  - (futuro)           -> GraphQL schema, .proto de gRPC, WSDL de SOAP...

Todas producen un artefacto comparable (un archivo con la forma) y todas se
diffean con el mismo motor. Asi, "de donde saco el contrato" queda enchufable
igual que los adapters de lenguaje: el nucleo no cambia al agregar fuentes.
"""

from __future__ import annotations

import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path


class ContractSource(ABC):
    """Contrato que toda fuente debe cumplir para alimentar el diff."""

    #: Nombre corto de la fuente, p. ej. "swagger". Para logs y seleccion.
    name: str = "base"

    @abstractmethod
    def fetch(self, dest: Path) -> None:
        """
        Obtener la forma actual del contrato y escribirla en `dest`.

        Para SwaggerSource: descargar el swagger.json.
        Para InferredSource: llamar al endpoint, inferir la forma del JSON y
        serializarla como un spec normalizado. En ambos casos, el resultado en
        `dest` debe ser comparable por el mismo motor de diff.
        """
        raise NotImplementedError


class SwaggerSource(ContractSource):
    """
    Fuente basada en un spec OpenAPI/Swagger publicado.

    Es la fuente fiable y la unica implementada en el MVP: cubre la mayoria de
    las APIs modernas (y las internas generadas con Swashbuckle).
    """

    name = "swagger"

    def __init__(self, url: str, timeout: int = 30):
        self.url = url
        self.timeout = timeout

    def fetch(self, dest: Path) -> None:
        # Nota de seguridad: la URL la provee el usuario; no incrustamos
        # credenciales. Swaggers protegidos con auth: pendiente (10%).
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(self.url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            dest.write_bytes(resp.read())


class InferredSource(ContractSource):
    """
    PENDIENTE (10% de pulido). Fuente para APIs sin spec: llama al endpoint,
    infiere la forma del JSON real y la normaliza a un spec comparable.

    Limitaciones a resolver cuando se implemente:
      - Una sola respuesta puede no revelar campos opcionales; conviene tomar
        varias muestras para una forma confiable.
      - Solo seguro para lecturas (GET). No invocar operaciones con efectos
        (POST/PUT/DELETE) solo para observar su forma.

    Se deja declarada para fijar la frontera; el nucleo ya sabe trabajar con
    cualquier ContractSource, asi que implementarla no tocara el motor.
    """

    name = "inferred"

    def __init__(self, endpoint_url: str, samples: int = 1):
        self.endpoint_url = endpoint_url
        self.samples = samples

    def fetch(self, dest: Path) -> None:
        raise NotImplementedError(
            "InferredSource aun no esta implementada. "
            "Hoy solo se soportan APIs que publican Swagger/OpenAPI."
        )
