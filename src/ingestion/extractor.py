import json
import logging
import re
from typing import Any

import boto3
from botocore.config import Config

from src.common.config import settings
from src.common.constants import EXTRACTION_SYSTEM_PROMPT
from src.common.models import (
    CriterioFactor,
    GarantiaFactor,
    MultaFactor,
    PageContent,
    PlazoFactor,
)

logger = logging.getLogger(__name__)

FACTOR_SCHEMAS = {
    "garantias": (
        GarantiaFactor,
        """{
  "identificado": boolean,
  "tipo_garantia": "string o null (ej: Seriedad de la oferta, Fiel cumplimiento)",
  "monto": "string o null (ej: 100 UF, 5% del valor total)",
  "vigencia": "string o null (ej: 60 dias corridos)",
  "glosa": "string o null (glosa requerida en el documento)",
  "pagina_citada": integer,
  "fragmento_exacto": "string (cita textual exacta del documento que sustenta la respuesta)"
}""",
    ),
    "criterios": (
        CriterioFactor,
        """{
  "identificado": boolean,
  "ponderacion_tecnica": "string o null (ej: 70%, 60 puntos)",
  "ponderacion_economica": "string o null (ej: 30%, 40 puntos)",
  "puntaje_minimo_descalificatorio": "string o null (ej: 50 puntos)",
  "pagina_citada": integer,
  "fragmento_exacto": "string (cita textual exacta del documento que sustenta la respuesta)"
}""",
    ),
    "multas": (
        MultaFactor,
        """{
  "identificado": boolean,
  "causal_principal": "string o null (ej: Atraso en la entrega de informes)",
  "monto_diario": "string o null (ej: 2 UF por dia habil de atraso)",
  "tope_maximo": "string o null (ej: 10% del monto total del contrato)",
  "pagina_citada": integer,
  "fragmento_exacto": "string (cita textual exacta del documento que sustenta la respuesta)"
}""",
    ),
    "plazos": (
        PlazoFactor,
        """{
  "identificado": boolean,
  "cierre_ofertas": "string o null (fecha y hora limite)",
  "tipo_computo": "string o null (ej: Dias habiles administrativos, Dias corridos)",
  "plazo_entrega": "string o null (ej: 30 dias)",
  "pagina_citada": integer,
  "fragmento_exacto": "string (cita textual exacta del documento que sustenta la respuesta)"
}""",
    ),
}


class BedrockExtractor:
    """Motor de inferencia sobre Amazon Bedrock con reintentos adaptativos."""

    def __init__(self, client: Any | None = None) -> None:
        if client:
            self.client = client
        else:
            boto_config = Config(
                retries={
                    "max_attempts": settings.MAX_RETRIES,
                    "mode": settings.ADAPTIVE_RETRY_MODE,
                }
            )
            self.client = boto3.client(
                "bedrock-runtime",
                region_name=settings.AWS_REGION,
                config=boto_config,
            )

    def extract_factor(
        self,
        factor_name: str,
        candidate_pages: list[PageContent],
    ) -> tuple[Any, int, int]:
        """Extrae de manera determinista un factor desde las páginas candidatas provistas.

        Args:
            factor_name: Nombre del factor ('garantias', 'criterios', 'multas', 'plazos').
            candidate_pages: Lista de páginas candidatas.

        Returns:
            tuple[FactorModel, input_tokens, output_tokens]:
                Instancia validada del modelo Pydantic y tokens consumidos.
        """
        if factor_name not in FACTOR_SCHEMAS:
            raise ValueError(f"Factor no soportado: '{factor_name}'")

        model_cls, schema_str = FACTOR_SCHEMAS[factor_name]

        if not candidate_pages:
            return model_cls(identificado=False), 0, 0

        # Construir el contexto documental preservando los números de página
        document_context = []
        for p in candidate_pages:
            document_context.append(f"--- [PÁGINA {p.page_number}] ---\n{p.text}")
        context_str = "\n\n".join(document_context)

        prompt_text = (
            f"Analiza las siguientes páginas de las bases de licitación pública y extrae "
            f"la información correspondiente al factor: '{factor_name.upper()}'.\n\n"
            f"Esquema JSON requerido:\n{schema_str}\n\n"
            f"Documento a analizar:\n{context_str}\n\n"
            f"Responde estrictamente con el JSON solicitado:"
        )

        try:
            response = self.client.converse(
                modelId=settings.BEDROCK_MODEL_ID,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt_text}],
                    }
                ],
                system=[{"text": EXTRACTION_SYSTEM_PROMPT}],
                inferenceConfig={
                    "temperature": 0.0,
                    "maxTokens": 1024,
                },
            )

            usage = response.get("usage", {})
            input_tokens = usage.get("inputTokens", 0)
            output_tokens = usage.get("outputTokens", 0)

            output_message = response.get("output", {}).get("message", {})
            content_blocks = output_message.get("content", [])
            raw_text = "".join(b.get("text", "") for b in content_blocks).strip()

            parsed_json = self._clean_and_parse_json(raw_text)
            factor_instance = model_cls(**parsed_json)
            return factor_instance, input_tokens, output_tokens

        except Exception as e:
            logger.exception("Error invocando Bedrock para factor '%s'", factor_name)
            # Retornar instancia por defecto no identificada en caso de fallo controlado
            default_instance = model_cls(
                identificado=False,
                advertencia=f"Fallo durante la inferencia con Amazon Bedrock: {e!s}",
            )
            return default_instance, 0, 0

    @staticmethod
    def _clean_and_parse_json(text: str) -> dict[str, Any]:
        """Elimina bloques de formato markdown ```json ... ``` y deserializa el JSON."""
        # Limpiar bloques de código markdown si los hay
        cleaned = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()

        # Buscar el inicio del primer objeto JSON y decodificar solo hasta el cierre válido
        start_idx = cleaned.find("{")
        if start_idx != -1:
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(cleaned[start_idx:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                logger.debug("raw_decode no pudo parsear JSON continuo, intentando regex fallback.")

        # Fallback a regex no voraz
        match = re.search(r"(\{.*?\})", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1)

        return json.loads(cleaned)

