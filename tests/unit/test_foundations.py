from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.common.config import settings
from src.common.constants import (
    SECTION_PATTERNS,
)
from src.common.models import (
    CriterioFactor,
    FactorStatus,
    GarantiaFactor,
    MultaFactor,
    PageContent,
    PlazoFactor,
    TenderExtractionResult,
    TenderStatus,
    UploadUrlRequest,
)


def test_settings_defaults():
    """Verifica que las configuraciones por defecto carguen valores esperados."""
    assert settings.AWS_REGION == "us-east-1"
    assert "haiku" in settings.BEDROCK_MODEL_ID.lower()
    assert settings.PRESIGNED_URL_EXPIRATION_SECONDS == 900
    assert settings.TABLE_NAME == "TenderAnalysis"
    assert settings.UPLOAD_BUCKET_NAME == "licitaciones-uploads"


def test_section_patterns_matching():
    """Comprueba que los patrones regex identifiquen la terminología de Mercado Público."""
    # Garantias
    assert SECTION_PATTERNS["garantias"].search("El oferente deberá presentar boleta de garantía bancaria")
    assert SECTION_PATTERNS["garantias"].search("Garantía de seriedad de la oferta por 500 UF")
    assert SECTION_PATTERNS["garantias"].search("Póliza de seguro o vale vista")

    # Criterios
    assert SECTION_PATTERNS["criterios"].search("Criterios de Evaluación y ponderación técnica")
    assert SECTION_PATTERNS["criterios"].search("Matriz de evaluación con puntaje técnico mínimo")

    # Multas
    assert SECTION_PATTERNS["multas"].search("Se aplicarán multas por atraso injustificado")
    assert SECTION_PATTERNS["multas"].search("Sanciones con tope máximo del 15% del valor total")

    # Plazos
    assert SECTION_PATTERNS["plazos"].search("Fecha y hora de cierre de ofertas en el portal")
    assert SECTION_PATTERNS["plazos"].search("Plazos fatales en días hábiles administrativos")


def test_page_content_validation():
    """Verifica la validación del modelo PageContent."""
    page = PageContent(page_number=1, text="Texto de prueba en página 1", char_count=28)
    assert page.page_number == 1
    assert page.char_count == 28


def test_factor_models_and_inheritance():
    """Valida la creación y herencia de los 4 factores de riesgo."""
    garantia = GarantiaFactor(
        identificado=True,
        pagina_citada=14,
        fragmento_exacto="Garantía de seriedad por 100 UF",
        verificado_en_pagina=True,
        status=FactorStatus.VERIFIED,
        source_file="bases_administrativas.pdf",
        tipo_garantia="Seriedad de la oferta",
        monto="100 UF",
        vigencia="60 días",
    )
    assert garantia.status == FactorStatus.VERIFIED
    assert garantia.identificado is True
    assert garantia.tipo_garantia == "Seriedad de la oferta"

    criterio = CriterioFactor(
        identificado=True,
        ponderacion_tecnica="70%",
        ponderacion_economica="30%",
        puntaje_minimo_descalificatorio="60 puntos",
    )
    assert criterio.status == FactorStatus.REQUIRES_MANUAL_REVIEW
    assert criterio.ponderacion_tecnica == "70%"

    multa = MultaFactor(
        identificado=True,
        causal_principal="Atraso en entrega de informe de avance",
        monto_diario="5 UF por día hábil",
        tope_maximo="10% del contrato",
    )
    assert multa.causal_principal == "Atraso en entrega de informe de avance"

    plazo = PlazoFactor(
        identificado=True,
        cierre_ofertas="15-12-2026 15:00 hrs",
        tipo_computo="Días hábiles administrativos",
        plazo_entrega="45 días",
    )
    assert plazo.tipo_computo == "Días hábiles administrativos"


def test_tender_extraction_result():
    """Valida la serialización y atributos de un registro completo de auditoría."""
    now_iso = datetime.now(UTC).isoformat()
    record = TenderExtractionResult(
        licitacion_id="1234-56-LP26",
        status=TenderStatus.READY,
        created_at=now_iso,
        updated_at=now_iso,
        ttl=1735689600,
        uploaded_documents=["bases_tecnicas.pdf"],
        total_pages=42,
        cost_usd_estimate=0.0035,
        processing_time_ms=18400,
        factors={
            "garantias": {"identificado": True, "tipo_garantia": "Seriedad"},
        },
    )
    assert record.licitacion_id == "1234-56-LP26"
    assert record.status == TenderStatus.READY
    assert record.total_pages == 42
    assert record.cost_usd_estimate == 0.0035


def test_upload_url_request_validation():
    """Comprueba las validaciones de tamaño y nombre de archivo para presigned URLs."""
    valid_req = UploadUrlRequest(file_name="pliego_licitacion.pdf", file_size_bytes=1024 * 1024)
    assert valid_req.file_name == "pliego_licitacion.pdf"

    # Exceso de tamaño (> 50 MB)
    with pytest.raises(ValidationError):
        UploadUrlRequest(file_name="archivo_enorme.pdf", file_size_bytes=60 * 1024 * 1024)

    # Tamaño negativo o cero
    with pytest.raises(ValidationError):
        UploadUrlRequest(file_name="vacio.pdf", file_size_bytes=0)
