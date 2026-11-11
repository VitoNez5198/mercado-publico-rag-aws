import json
import logging
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote_plus

import boto3

from src.common.config import settings
from src.common.constants import DEFAULT_TTL_DAYS, SECONDS_IN_DAY
from src.common.models import FactorStatus, TenderStatus
from src.ingestion.candidate_selector import select_candidate_pages
from src.ingestion.extractor import BedrockExtractor
from src.ingestion.parser import (
    InvalidPdfException,
    ScannedPdfException,
    extract_pages_from_pdf_stream,
)
from src.ingestion.verifier import verify_citation

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Instanciación de clientes fuera del handler para reutilización en warm containers
s3_client = boto3.client("s3", region_name=settings.AWS_REGION)
dynamodb_resource = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
table = dynamodb_resource.Table(settings.TABLE_NAME)
bedrock_extractor = BedrockExtractor()


def parse_sqs_s3_event(record_body: str) -> tuple[str, str, str, str]:
    """Extrae bucket, key, licitacion_id y filename desde el cuerpo de un mensaje SQS.

    Soporta formato S3 Event Notifications directo y notificaciones encapsuladas.
    Convención de ruta: uploads/{licitacion_id}/{filename}
    """
    body_data = json.loads(record_body)

    # Si el evento S3 está encapsulado en SNS o viene directo de S3
    if "Records" in body_data and len(body_data["Records"]) > 0:
        s3_info = body_data["Records"][0].get("s3", {})
        bucket_name = s3_info.get("bucket", {}).get("name", "")
        raw_key = s3_info.get("object", {}).get("key", "")
        s3_key = unquote_plus(raw_key)
    else:
        # Carga directa estructurada de prueba
        bucket_name = body_data.get("bucket", settings.UPLOAD_BUCKET_NAME)
        s3_key = body_data.get("key", "")

    # Extracción de licitacion_id y filename
    parts = s3_key.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "uploads":
        licitacion_id = parts[1]
        filename = "/".join(parts[2:])
    elif len(parts) >= 2:
        licitacion_id = parts[0]
        filename = parts[1]
    else:
        licitacion_id = s3_key
        filename = s3_key

    return bucket_name, s3_key, licitacion_id, filename


def update_tender_status(
    licitacion_id: str,
    status: TenderStatus,
    error_message: str | None = None,
) -> None:
    """Actualiza el estado de una licitación en DynamoDB de forma rápida."""
    now_iso = datetime.now(UTC).isoformat()
    ttl_epoch = int(time.time()) + (DEFAULT_TTL_DAYS * SECONDS_IN_DAY)

    update_expr = "SET #st = :status, updated_at = :updated_at, #ttl = :ttl"
    expr_names = {"#st": "status", "#ttl": "ttl"}
    expr_values = {
        ":status": status.value,
        ":updated_at": now_iso,
        ":ttl": ttl_epoch,
    }

    if error_message:
        update_expr += ", error_message = :err"
        expr_values[":err"] = error_message

    table.update_item(
        Key={"licitacion_id": licitacion_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Punto de entrada de la función Lambda de Ingestión activada por SQS."""
    start_time = time.time()
    records = event.get("Records", [])
    if not records:
        logger.warning("No se recibieron registros SQS para procesar.")
        return {"statusCode": 200, "message": "No records"}

    # Concurrencia unitaria configurada (BatchSize: 1)
    record = records[0]
    bucket_name, s3_key, licitacion_id, filename = parse_sqs_s3_event(record.get("body", "{}"))

    logger.info(f"Iniciando procesamiento de pliego. Licitación: {licitacion_id}, Archivo: {filename}")

    # 1. Marcar estado como PROCESSING en DynamoDB
    update_tender_status(licitacion_id, TenderStatus.PROCESSING)

    # 2. Descargar PDF desde S3
    try:
        s3_response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        pdf_bytes = s3_response["Body"].read()
    except Exception as e:
        logger.error(f"Error descargando {s3_key} desde {bucket_name}: {e}")
        update_tender_status(
            licitacion_id,
            TenderStatus.FAILED,
            f"No se pudo descargar el archivo de S3: {e!s}",
        )
        raise

    # 3. Parsear texto del PDF con PyMuPDF
    try:
        pages = extract_pages_from_pdf_stream(pdf_bytes)
    except ScannedPdfException as e:
        logger.warning(f"Licitación {licitacion_id} contiene PDF escaneado sin texto digital: {e}")
        update_tender_status(licitacion_id, TenderStatus.FAILED, str(e))
        return {"statusCode": 200, "licitacion_id": licitacion_id, "status": TenderStatus.FAILED.value}
    except InvalidPdfException as e:
        logger.error(f"Archivo PDF inválido o corrupto para licitación {licitacion_id}: {e}")
        update_tender_status(licitacion_id, TenderStatus.FAILED, str(e))
        return {"statusCode": 200, "licitacion_id": licitacion_id, "status": TenderStatus.FAILED.value}

    total_pages = len(pages)
    raw_pages = {p.page_number: p.text for p in pages}

    # 4. Seleccionar ventanas de páginas candidatas por factor
    candidates_by_factor = select_candidate_pages(pages)

    # 5. Extracción y Verificación de los 4 factores
    factors_results: dict[str, Any] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    has_manual_review = False

    for factor_name in ("garantias", "criterios", "multas", "plazos"):
        candidate_pages = candidates_by_factor.get(factor_name, [])
        factor_obj, in_tokens, out_tokens = bedrock_extractor.extract_factor(
            factor_name=factor_name,
            candidate_pages=candidate_pages,
        )
        total_input_tokens += in_tokens
        total_output_tokens += out_tokens

        # Verificación determinista de la cita
        if factor_obj.identificado and factor_obj.fragmento_exacto:
            verified, warning = verify_citation(
                page_number=factor_obj.pagina_citada,
                exact_quote=factor_obj.fragmento_exacto,
                raw_pages=raw_pages,
            )
            factor_obj.verificado_en_pagina = verified
            factor_obj.status = FactorStatus.VERIFIED if verified else FactorStatus.REQUIRES_MANUAL_REVIEW
            factor_obj.advertencia = warning
            if not verified:
                has_manual_review = True
        else:
            factor_obj.status = FactorStatus.VERIFIED
            factor_obj.verificado_en_pagina = True

        factor_obj.source_file = filename
        factors_results[factor_name] = factor_obj.model_dump()

    # 6. Cálculo FinOps de Costos (Precios Claude 3.5 Haiku)
    # Entrada: $0.0008 / 1.000 tokens | Salida: $0.004 / 1.000 tokens
    cost_estimate = (total_input_tokens / 1000.0 * 0.0008) + (total_output_tokens / 1000.0 * 0.004)
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Estado final: READY si todas las citas verificaron, PARTIAL_SUCCESS si alguna requiere revisión manual
    final_status = TenderStatus.PARTIAL_SUCCESS if has_manual_review else TenderStatus.READY
    now_iso = datetime.now(UTC).isoformat()
    ttl_epoch = int(time.time()) + (DEFAULT_TTL_DAYS * SECONDS_IN_DAY)

    # 7. Actualización atómica en DynamoDB
    table.update_item(
        Key={"licitacion_id": licitacion_id},
        UpdateExpression=(
            "SET #st = :status, "
            "updated_at = :updated_at, "
            "#ttl = :ttl, "
            "total_pages = :total_pages, "
            "cost_usd_estimate = :cost_usd, "
            "processing_time_ms = :proc_time, "
            "factors = :factors, "
            "uploaded_documents = list_append(if_not_exists(uploaded_documents, :empty_list), :new_doc)"
        ),
        ExpressionAttributeNames={
            "#st": "status",
            "#ttl": "ttl",
        },
        ExpressionAttributeValues={
            ":status": final_status.value,
            ":updated_at": now_iso,
            ":ttl": ttl_epoch,
            ":total_pages": total_pages,
            ":cost_usd": str(round(cost_estimate, 6)),  # DynamoDB maneja números flotantes como string/decimal
            ":proc_time": elapsed_ms,
            ":factors": factors_results,
            ":empty_list": [],
            ":new_doc": [filename],
        },
    )

    logger.info(
        f"Licitación {licitacion_id} procesada exitosamente en {elapsed_ms}ms con estado {final_status.value}. "
        f"Costo estimado: ${cost_estimate:.6f} USD"
    )

    return {
        "statusCode": 200,
        "licitacion_id": licitacion_id,
        "status": final_status.value,
        "processing_time_ms": elapsed_ms,
        "cost_usd_estimate": cost_estimate,
    }

