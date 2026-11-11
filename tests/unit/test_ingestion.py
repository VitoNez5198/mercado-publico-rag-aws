import json
from unittest.mock import MagicMock, patch

import pymupdf

from src.common.models import GarantiaFactor, PageContent, TenderStatus
from src.ingestion.candidate_selector import select_candidate_pages
from src.ingestion.extractor import BedrockExtractor
from src.ingestion.handler import lambda_handler, parse_sqs_s3_event


def create_sample_pdf_bytes() -> bytes:
    """Crea un PDF sintético con 4 páginas con contenido representativo."""
    doc = pymupdf.open()

    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 72), "Licitación ID 1234-LP26: Resumen Ejecutivo del Servicio.", fontsize=12)

    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 72), "Garantía de seriedad de la oferta por 50 UF pagadera en vale vista.", fontsize=12)

    p3 = doc.new_page(width=595, height=842)
    p3.insert_text((50, 72), "Criterios de evaluación técnica 70% y económica 30%.", fontsize=12)

    p4 = doc.new_page(width=595, height=842)
    p4.insert_text((50, 72), "Multas por atraso diario de 1 UF hasta un tope máximo de 10% del total.", fontsize=12)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_select_candidate_pages_matching_and_fallback():
    """Prueba que el selector identifique páginas por regex y aplique fallback cuando no hay coincidencias."""
    pages = [
        PageContent(page_number=1, text="Carátula general sin términos específicos", char_count=60),
        PageContent(page_number=2, text="Detalle de la garantía de fiel cumplimiento", char_count=60),
        PageContent(page_number=3, text="Ponderación de criterios técnicos y económicos", char_count=60),
    ]

    candidates = select_candidate_pages(pages, max_pages=5)

    # Garantías debe hallar la página 2
    assert any(p.page_number == 2 for p in candidates["garantias"])

    # Criterios debe hallar la página 3
    assert any(p.page_number == 3 for p in candidates["criterios"])

    # Plazos no tiene coincidencia, debe aplicar fallback (páginas 1 y 2)
    assert len(candidates["plazos"]) == 2
    assert candidates["plazos"][0].page_number == 1
    assert candidates["plazos"][1].page_number == 2


def test_parse_sqs_s3_event_canonical_key():
    """Valida la extracción de metadatos desde una notificación S3 canónica."""
    event_body = json.dumps({
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-uploads-bucket"},
                    "object": {"key": "uploads/LIC-9988/bases_administrativas.pdf"},
                }
            }
        ]
    })

    bucket, key, licitacion_id, filename = parse_sqs_s3_event(event_body)
    assert bucket == "test-uploads-bucket"
    assert key == "uploads/LIC-9988/bases_administrativas.pdf"
    assert licitacion_id == "LIC-9988"
    assert filename == "bases_administrativas.pdf"


def test_bedrock_extractor_clean_json_parsing():
    """Prueba la deserialización de respuestas JSON envueltas en markdown."""
    raw_response = """```json
{
  "identificado": true,
  "tipo_garantia": "Seriedad de la oferta",
  "monto": "100 UF",
  "vigencia": "60 dias",
  "glosa": "Para garantizar la seriedad",
  "pagina_citada": 2,
  "fragmento_exacto": "garantía de seriedad de la oferta por 100 uf"
}
```"""
    parsed = BedrockExtractor._clean_and_parse_json(raw_response)
    assert parsed["identificado"] is True
    assert parsed["tipo_garantia"] == "Seriedad de la oferta"
    assert parsed["pagina_citada"] == 2


@patch("src.ingestion.handler.s3_client")
@patch("src.ingestion.handler.table")
@patch("src.ingestion.handler.bedrock_extractor")
def test_lambda_handler_full_pipeline_success(mock_bedrock, mock_table, mock_s3):
    """Verifica el flujo completo de la función Lambda de ingesta con mocks de AWS."""
    pdf_bytes = create_sample_pdf_bytes()
    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: pdf_bytes)}

    # Mock de respuesta de Bedrock
    mock_factor = GarantiaFactor(
        identificado=True,
        tipo_garantia="Seriedad de la oferta",
        monto="50 UF",
        pagina_citada=2,
        fragmento_exacto="Garantía de seriedad de la oferta por 50 UF",
    )
    mock_bedrock.extract_factor.return_value = (mock_factor, 1500, 120)

    event = {
        "Records": [
            {
                "body": json.dumps({
                    "Records": [
                        {
                            "s3": {
                                "bucket": {"name": "test-bucket"},
                                "object": {"key": "uploads/LIC-1234/bases.pdf"},
                            }
                        }
                    ]
                })
            }
        ]
    }

    result = lambda_handler(event, None)

    assert result["statusCode"] == 200
    assert result["licitacion_id"] == "LIC-1234"
    assert result["status"] == TenderStatus.READY.value
    assert result["cost_usd_estimate"] > 0

    # Comprobar que se actualizó DynamoDB
    assert mock_table.update_item.call_count >= 2


@patch("src.ingestion.handler.s3_client")
@patch("src.ingestion.handler.table")
def test_lambda_handler_scanned_pdf_failure(mock_table, mock_s3):
    """Comprueba que un PDF sin texto digital marque el estado FAILED en DynamoDB."""
    # PDF vacío / escaneado
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)  # Página en blanco sin texto
    scanned_bytes = doc.tobytes()
    doc.close()

    mock_s3.get_object.return_value = {"Body": MagicMock(read=lambda: scanned_bytes)}

    event = {
        "Records": [
            {
                "body": json.dumps({
                    "Records": [
                        {
                            "s3": {
                                "bucket": {"name": "test-bucket"},
                                "object": {"key": "uploads/LIC-SCANNED/scan.pdf"},
                            }
                        }
                    ]
                })
            }
        ]
    }

    result = lambda_handler(event, None)

    assert result["statusCode"] == 200
    assert result["status"] == TenderStatus.FAILED.value
    # Se debe haber actualizado DynamoDB con el estado FAILED
    assert mock_table.update_item.called

