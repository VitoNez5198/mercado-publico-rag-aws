import base64
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import boto3
from pydantic import ValidationError

from src.common.config import settings
from src.common.constants import DEFAULT_TTL_DAYS, SECONDS_IN_DAY
from src.common.models import (
    TenderStatus,
    UploadUrlRequest,
    UploadUrlResponse,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Instanciación de clientes fuera del handler para reutilización en warm containers
s3_client = boto3.client("s3", region_name=settings.AWS_REGION)
dynamodb_resource = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
table = dynamodb_resource.Table(settings.TABLE_NAME)

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def _response(status_code: int, body: Any) -> dict[str, Any]:
    """Genera una respuesta normalizada compatible con API Gateway HTTP/REST API."""
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body) if not isinstance(body, str) else body,
    }


def _extract_request_context(event: dict[str, Any]) -> tuple[str, str, dict[str, str], str]:
    """Extrae de manera uniforme el método HTTP, la ruta, los pathParameters y el cuerpo.

    Soporta formatos HTTP API v2 y REST API v1.
    """
    # Método HTTP
    http_method = (
        event.get("requestContext", {}).get("http", {}).get("method")
        or event.get("httpMethod")
        or "GET"
    ).upper()

    # Ruta
    raw_path = event.get("rawPath") or event.get("path") or ""

    # Path Parameters
    path_parameters = event.get("pathParameters") or {}

    # Body (con soporte de base64)
    body_str = event.get("body") or ""
    if event.get("isBase64Encoded", False) and body_str:
        body_str = base64.b64decode(body_str).decode("utf-8")

    return http_method, raw_path, path_parameters, body_str


def handle_upload_url(body_str: str) -> dict[str, Any]:
    """POST /licitaciones/upload-url: Genera una URL prefirmada S3 para subida de pliegos."""
    try:
        data = json.loads(body_str) if body_str else {}
        request_model = UploadUrlRequest(**data)
    except ValidationError as e:
        return _response(400, {"error": "Validación fallida", "details": e.errors()})
    except json.JSONDecodeError:
        return _response(400, {"error": "Cuerpo de la petición debe ser un JSON válido."})

    # Validar extensión obligatoria .pdf
    if not request_model.file_name.lower().endswith(".pdf"):
        return _response(
            400,
            {"error": "Formato no permitido. Solo se admiten archivos en formato PDF (.pdf)."},
        )

    licitacion_id = f"LIC-{uuid.uuid4().hex[:10].upper()}"
    s3_key = f"uploads/{licitacion_id}/{request_model.file_name}"
    expires_in = settings.PRESIGNED_URL_EXPIRATION_SECONDS

    # Generar Presigned URL para subida directa (PUT)
    try:
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": settings.UPLOAD_BUCKET_NAME,
                "Key": s3_key,
                "ContentType": "application/pdf",
            },
            ExpiresIn=expires_in,
        )
    except Exception as e:
        logger.exception("Error generando presigned URL en S3")
        return _response(500, {"error": f"Error al generar presigned URL: {e!s}"})

    now_iso = datetime.now(UTC).isoformat()
    ttl_epoch = int(time.time()) + (DEFAULT_TTL_DAYS * SECONDS_IN_DAY)

    # Crear registro inicial en DynamoDB
    table.put_item(
        Item={
            "licitacion_id": licitacion_id,
            "status": TenderStatus.PENDING_UPLOAD.value,
            "created_at": now_iso,
            "updated_at": now_iso,
            "ttl": ttl_epoch,
            "uploaded_documents": [],
            "factors": {},
        }
    )

    response_model = UploadUrlResponse(
        licitacion_id=licitacion_id,
        upload_url=presigned_url,
        s3_key=s3_key,
        expires_in_seconds=expires_in,
    )
    return _response(201, response_model.model_dump())


def handle_get_status(licitacion_id: str) -> dict[str, Any]:
    """GET /licitaciones/{id}/status: Consulta el estado de procesamiento del pliego."""
    if not licitacion_id:
        return _response(400, {"error": "Parámetro licitacion_id no provisto."})

    response = table.get_item(Key={"licitacion_id": licitacion_id})
    item = response.get("Item")
    if not item:
        return _response(404, {"error": f"Licitación '{licitacion_id}' no encontrada."})

    status_data = {
        "licitacion_id": item.get("licitacion_id"),
        "status": item.get("status"),
        "total_pages": item.get("total_pages", 0),
        "cost_usd_estimate": float(item.get("cost_usd_estimate", 0.0)),
        "processing_time_ms": item.get("processing_time_ms", 0),
        "uploaded_documents": item.get("uploaded_documents", []),
        "error_message": item.get("error_message"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }
    return _response(200, status_data)


def handle_get_factores(licitacion_id: str) -> dict[str, Any]:
    """GET /licitaciones/{id}/factores: Consulta los factores de riesgo contractual auditados."""
    if not licitacion_id:
        return _response(400, {"error": "Parámetro licitacion_id no provisto."})

    response = table.get_item(Key={"licitacion_id": licitacion_id})
    item = response.get("Item")
    if not item:
        return _response(404, {"error": f"Licitación '{licitacion_id}' no encontrada."})

    current_status = item.get("status")
    if current_status in (TenderStatus.PENDING_UPLOAD.value, TenderStatus.PROCESSING.value):
        return _response(
            200,
            {
                "licitacion_id": licitacion_id,
                "status": current_status,
                "message": "El documento aún se encuentra en procesamiento o en espera de carga.",
                "factors": {},
            },
        )

    factores_data = {
        "licitacion_id": item.get("licitacion_id"),
        "status": current_status,
        "total_pages": item.get("total_pages", 0),
        "cost_usd_estimate": float(item.get("cost_usd_estimate", 0.0)),
        "processing_time_ms": item.get("processing_time_ms", 0),
        "uploaded_documents": item.get("uploaded_documents", []),
        "factors": item.get("factors", {}),
        "error_message": item.get("error_message"),
    }
    return _response(200, factores_data)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Punto de entrada para API Gateway HTTP API."""
    http_method, raw_path, path_parameters, body_str = _extract_request_context(event)

    # Manejo de solicitudes de preflight OPTIONS (CORS)
    if http_method == "OPTIONS":
        return _response(200, {"message": "CORS preflight OK"})

    licitacion_id = path_parameters.get("id", "")

    # Enrutamiento de peticiones
    if http_method == "POST" and raw_path.endswith("/licitaciones/upload-url"):
        return handle_upload_url(body_str)

    if http_method == "GET" and raw_path.endswith("/status"):
        return handle_get_status(licitacion_id)

    if http_method == "GET" and raw_path.endswith("/factores"):
        return handle_get_factores(licitacion_id)

    return _response(404, {"error": f"Ruta '{http_method} {raw_path}' no encontrada."})
