from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class FactorStatus(str, Enum):
    """Estado de verificación determinista de la cita textual de un factor."""

    VERIFIED = "VERIFIED"
    REQUIRES_MANUAL_REVIEW = "REQUIRES_MANUAL_REVIEW"


class TenderStatus(str, Enum):
    """Estado global del procesamiento del pliego de licitación."""

    PENDING_UPLOAD = "PENDING_UPLOAD"
    PROCESSING = "PROCESSING"
    READY = "READY"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class PageContent(BaseModel):
    """Contenido textual y métricas extraídas de una página individual de un PDF."""

    page_number: int = Field(..., description="Número de página secuencial (iniciando en 1)")
    text: str = Field(..., description="Texto crudo extraído de la página")
    char_count: int = Field(..., description="Cantidad de caracteres legibles en la página")


class BaseFactor(BaseModel):
    """Estructura base para todos los factores de riesgo contractual."""

    identificado: bool = Field(
        default=False,
        description="Indica si el factor fue hallado en el documento",
    )
    pagina_citada: int = Field(
        default=0,
        description="Número de página de donde proviene la cita",
    )
    fragmento_exacto: str = Field(
        default="",
        description="Cita textual exacta que sustenta el hallazgo",
    )
    verificado_en_pagina: bool = Field(
        default=False,
        description="Resultado de la comprobación determinista de subcadena",
    )
    status: FactorStatus = Field(
        default=FactorStatus.REQUIRES_MANUAL_REVIEW,
        description="Estado de auditoría del factor",
    )
    source_file: str = Field(
        default="",
        description="Nombre del archivo PDF origen",
    )
    advertencia: str | None = Field(
        default=None,
        description="Nota explicativa en caso de discrepancia en la cita o ambigüedad",
    )

    @field_validator("pagina_citada", mode="before")
    @classmethod
    def _coerce_pagina_citada(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    @field_validator("fragmento_exacto", mode="before")
    @classmethod
    def _coerce_fragmento(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class GarantiaFactor(BaseFactor):
    """Factor 1: Garantías de seriedad de la oferta y fiel cumplimiento."""

    tipo_garantia: str | None = Field(
        default=None,
        description="Ej: Seriedad de la oferta, Fiel cumplimiento, Correcta ejecución",
    )
    monto: str | None = Field(
        default=None,
        description="Monto explícito (en UF, CLP, USD o porcentaje del contrato)",
    )
    vigencia: str | None = Field(
        default=None,
        description="Plazo de vigencia del instrumento de garantía",
    )
    glosa: str | None = Field(
        default=None,
        description="Glosa o texto obligatorio requerido en la boleta/póliza",
    )


class CriterioFactor(BaseFactor):
    """Factor 2: Criterios y ponderaciones de evaluación."""

    ponderacion_tecnica: str | None = Field(
        default=None,
        description="Porcentaje o puntaje asignado a la propuesta técnica",
    )
    ponderacion_economica: str | None = Field(
        default=None,
        description="Porcentaje o puntaje asignado al precio de la oferta",
    )
    puntaje_minimo_descalificatorio: str | None = Field(
        default=None,
        description="Umbral técnico mínimo que causa descalificación si no se alcanza",
    )


class MultaFactor(BaseFactor):
    """Factor 3: Multas, penalizaciones y sanciones contractuales."""

    causal_principal: str | None = Field(
        default=None,
        description="Motivo de la sanción (ej: atraso en entregables, fallas de SLA)",
    )
    monto_diario: str | None = Field(
        default=None,
        description="Monto o porcentaje de sanción por día hábil/corrido de retraso",
    )
    tope_maximo: str | None = Field(
        default=None,
        description="Tope máximo acumulado de multas antes de término anticipado",
    )


class PlazoFactor(BaseFactor):
    """Factor 4: Plazos fatales y cronograma de hitos."""

    cierre_ofertas: str | None = Field(
        default=None,
        description="Fecha y hora límite de recepción de ofertas en Mercado Público",
    )
    tipo_computo: str | None = Field(
        default=None,
        description="Cómputo en días hábiles administrativos o días corridos",
    )
    plazo_entrega: str | None = Field(
        default=None,
        description="Plazo de entrega o ejecución del servicio licitado",
    )


class FactorsMap(BaseModel):
    """Contenedor de los 4 factores de riesgo auditados."""

    garantias: GarantiaFactor | None = None
    criterios: CriterioFactor | None = None
    multas: MultaFactor | None = None
    plazos: PlazoFactor | None = None


class TenderExtractionResult(BaseModel):
    """Registro completo de auditoría almacenado en DynamoDB."""

    licitacion_id: str = Field(..., description="Identificador único del proceso (ID o UUID)")
    status: TenderStatus = Field(default=TenderStatus.PENDING_UPLOAD)
    created_at: str = Field(..., description="Timestamp ISO 8601 de creación")
    updated_at: str = Field(..., description="Timestamp ISO 8601 de última actualización")
    ttl: int = Field(..., description="Epoch timestamp para expiración automática a 30 días")
    uploaded_documents: list[str] = Field(
        default_factory=list,
        description="Lista de nombres de archivos PDF procesados",
    )
    total_pages: int = Field(default=0, description="Páginas totales analizadas")
    cost_usd_estimate: float = Field(default=0.0, description="Costo estimado en USD de inferencia")
    processing_time_ms: int = Field(default=0, description="Latencia total de procesamiento en ms")
    factors: dict[str, Any] = Field(
        default_factory=dict,
        description="Diccionario de factores extraídos y auditados",
    )
    error_message: str | None = Field(
        default=None,
        description="Mensaje de error en caso de fallo técnico",
    )


# ==============================================================================
# Modelos para HTTP API Gateway
# ==============================================================================

class UploadUrlRequest(BaseModel):
    """Payload para solicitar una URL prefirmada de subida a S3."""

    file_name: str = Field(..., min_length=1, max_length=255, description="Nombre del archivo PDF")
    file_size_bytes: int = Field(
        ...,
        gt=0,
        le=52428800,  # 50 MB
        description="Tamaño del archivo en bytes (máximo 50 MB)",
    )


class UploadUrlResponse(BaseModel):
    """Respuesta con la URL prefirmada para subida directa."""

    licitacion_id: str
    upload_url: str
    s3_key: str
    expires_in_seconds: int
