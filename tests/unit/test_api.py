import json
from unittest.mock import patch

from src.api.handler import lambda_handler
from src.common.models import TenderStatus


@patch("src.api.handler.s3_client")
@patch("src.api.handler.table")
def test_post_upload_url_success(mock_table, mock_s3):
    """Verifica la generación exitosa de presigned URL para un archivo PDF válido."""
    mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/upload-presigned"

    event = {
        "rawPath": "/licitaciones/upload-url",
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps({
            "file_name": "bases_administrativas.pdf",
            "file_size_bytes": 1048576,
        }),
    }

    response = lambda_handler(event, None)
    assert response["statusCode"] == 201

    body = json.loads(response["body"])
    assert "upload_url" in body
    assert body["upload_url"] == "https://s3.amazonaws.com/test-bucket/upload-presigned"
    assert "licitacion_id" in body
    assert body["licitacion_id"].startswith("LIC-")
    assert body["s3_key"].startswith("uploads/LIC-")

    # Verifica inserción en DynamoDB
    assert mock_table.put_item.called
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["status"] == TenderStatus.PENDING_UPLOAD.value


def test_post_upload_url_invalid_extension():
    """Valida el rechazo de archivos que no sean PDF."""
    event = {
        "rawPath": "/licitaciones/upload-url",
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps({
            "file_name": "propuesta.docx",
            "file_size_bytes": 1024,
        }),
    }

    response = lambda_handler(event, None)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Solo se admiten archivos en formato PDF" in body["error"]


def test_post_upload_url_invalid_size():
    """Valida el rechazo de archivos que superen el límite de 50 MB."""
    event = {
        "rawPath": "/licitaciones/upload-url",
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps({
            "file_name": "pliego_gigante.pdf",
            "file_size_bytes": 60 * 1024 * 1024,  # 60 MB
        }),
    }

    response = lambda_handler(event, None)
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Validación fallida" in body["error"]


@patch("src.api.handler.table")
def test_get_status_found(mock_table):
    """Consulta exitosa del estado de una licitación en DynamoDB."""
    mock_table.get_item.return_value = {
        "Item": {
            "licitacion_id": "LIC-TEST1",
            "status": TenderStatus.READY.value,
            "total_pages": 45,
            "cost_usd_estimate": "0.0042",
            "processing_time_ms": 15200,
            "uploaded_documents": ["bases.pdf"],
            "created_at": "2026-11-11T12:00:00Z",
            "updated_at": "2026-11-11T12:00:15Z",
        }
    }

    event = {
        "rawPath": "/licitaciones/LIC-TEST1/status",
        "pathParameters": {"id": "LIC-TEST1"},
        "requestContext": {"http": {"method": "GET"}},
    }

    response = lambda_handler(event, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["licitacion_id"] == "LIC-TEST1"
    assert body["status"] == TenderStatus.READY.value
    assert body["total_pages"] == 45


@patch("src.api.handler.table")
def test_get_status_not_found(mock_table):
    """Respuesta 404 cuando la licitación no existe en la base de datos."""
    mock_table.get_item.return_value = {}

    event = {
        "rawPath": "/licitaciones/LIC-INEXISTENTE/status",
        "pathParameters": {"id": "LIC-INEXISTENTE"},
        "requestContext": {"http": {"method": "GET"}},
    }

    response = lambda_handler(event, None)
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert "no encontrada" in body["error"]


@patch("src.api.handler.table")
def test_get_factores_ready(mock_table):
    """Consulta exitosa de factores auditados cuando el procesamiento finalizó."""
    mock_table.get_item.return_value = {
        "Item": {
            "licitacion_id": "LIC-TEST1",
            "status": TenderStatus.READY.value,
            "factors": {
                "garantias": {
                    "identificado": True,
                    "tipo_garantia": "Seriedad",
                    "monto": "100 UF",
                    "status": "VERIFIED",
                }
            },
        }
    }

    event = {
        "rawPath": "/licitaciones/LIC-TEST1/factores",
        "pathParameters": {"id": "LIC-TEST1"},
        "requestContext": {"http": {"method": "GET"}},
    }

    response = lambda_handler(event, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == TenderStatus.READY.value
    assert "garantias" in body["factors"]


def test_cors_preflight():
    """Valida el manejo de solicitudes OPTIONS preflight para navegadores web."""
    event = {
        "rawPath": "/licitaciones/upload-url",
        "requestContext": {"http": {"method": "OPTIONS"}},
    }

    response = lambda_handler(event, None)
    assert response["statusCode"] == 200
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"

