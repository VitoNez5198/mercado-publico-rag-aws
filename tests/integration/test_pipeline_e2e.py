import json
from unittest.mock import MagicMock, patch

import pymupdf

import src.api.handler as api_handler
import src.ingestion.handler as ingestion_handler
from src.common.models import (
    CriterioFactor,
    GarantiaFactor,
    MultaFactor,
    PlazoFactor,
    TenderStatus,
)


def create_realistic_tender_pdf() -> bytes:
    """Genera en memoria un pliego de licitación sintético de 5 páginas representativo

    del portal de compras públicas de Chile (Mercado Público).
    """
    doc = pymupdf.open()

    # Página 1: Carátula y Resumen
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(
        (50, 72),
        "REPÚBLICA DE CHILE - DIRECCIÓN DE COMPRAS PÚBLICAS\n"
        "BASES ADMINISTRATIVAS Y TÉCNICAS DE LICITACIÓN PÚBLICA\n"
        "ID LICITACIÓN: 2239-14-LR26\n"
        "SERVICIO: Implementación y Soporte de Infraestructura Cloud Serverless.",
        fontsize=11,
    )

    # Página 2: Garantías Contractuales
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text(
        (50, 72),
        "CLÁUSULA 8: GARANTÍA DE FIEL Y OPORTUNO CUMPLIMIENTO DEL CONTRATO.\n"
        "El adjudicatario deberá entregar una garantía de fiel cumplimiento por un monto\n"
        "equivalente al 5% del valor total del contrato, con una vigencia mínima de 90 días\n"
        "corridos contados desde la firma del contrato. Glosa: Para garantizar el fiel cumplimiento.",
        fontsize=11,
    )

    # Página 3: Criterios de Evaluación
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text(
        (50, 72),
        "CLÁUSULA 12: CRITERIOS DE EVALUACIÓN Y PONDERACIÓN DE OFERTAS.\n"
        "La evaluación se estructurará con una ponderación técnica del 70% y una ponderación\n"
        "económica del 30%. El oferente que obtenga un puntaje técnico inferior a 60 puntos\n"
        "quedará automáticamente descalificado del proceso licitatorio.",
        fontsize=11,
    )

    # Página 4: Régimen de Multas y Sanciones
    p4 = doc.new_page(width=595, height=842)
    p4.insert_text(
        (50, 72),
        "CLÁUSULA 19: MULTAS POR ATRASO E INCUMPLIMIENTO CONTRACTUAL.\n"
        "Se aplicará una multa diaria de 2 UF por cada día hábil de atraso en la entrega\n"
        "de los hitos del proyecto, con un tope máximo del 10% del valor total adjudicado.\n"
        "Superado dicho tope, el organismo podrá poner término anticipado al contrato.",
        fontsize=11,
    )

    # Página 5: Calendario y Plazos Fatales
    p5 = doc.new_page(width=595, height=842)
    p5.insert_text(
        (50, 72),
        "CLÁUSULA 25: CALENDARIO DE LA LICITACIÓN Y PLAZOS FATALES.\n"
        "El cierre de recepción de ofertas será el 30 de noviembre de 2026 a las 15:00 horas.\n"
        "Todos los plazos se computarán en días hábiles administrativos.\n"
        "El plazo de entrega y puesta en marcha del servicio será de 45 días corridos.",
        fontsize=11,
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_pipeline_e2e_full_lifecycle():
    """Simulación End-to-End completa del ciclo de vida del pipeline serverless:

    1. Cliente solicita URL prefirmada de subida (POST /licitaciones/upload-url).
    2. Subida del pliego a S3 y emisión del evento a SQS.
    3. Worker Lambda procesa el PDF, consulta Bedrock y verifica citas deterministas.
    4. Cliente sondea el estado de la licitación (GET /licitaciones/{id}/status).
    5. Cliente obtiene el reporte auditado con los 4 factores (GET /licitaciones/{id}/factores).
    """
    # Base de datos en memoria para simular DynamoDB
    in_memory_db: dict[str, dict] = {}

    def mock_put_item(Item):
        in_memory_db[Item["licitacion_id"]] = Item.copy()

    def mock_get_item(Key):
        item = in_memory_db.get(Key["licitacion_id"])
        return {"Item": item.copy()} if item else {}

    def mock_update_item(Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues):
        lic_id = Key["licitacion_id"]
        item = in_memory_db.setdefault(lic_id, {"licitacion_id": lic_id})
        status_key = ExpressionAttributeNames.get("#st", "status")
        item[status_key] = ExpressionAttributeValues[":status"]
        item["updated_at"] = ExpressionAttributeValues[":updated_at"]
        if ":total_pages" in ExpressionAttributeValues:
            item["total_pages"] = ExpressionAttributeValues[":total_pages"]
            item["cost_usd_estimate"] = ExpressionAttributeValues[":cost_usd"]
            item["processing_time_ms"] = ExpressionAttributeValues[":proc_time"]
            item["factors"] = ExpressionAttributeValues[":factors"]
            docs = item.setdefault("uploaded_documents", [])
            docs.extend(ExpressionAttributeValues.get(":new_doc", []))

    pdf_bytes = create_realistic_tender_pdf()
    s3_storage: dict[str, bytes] = {}

    def mock_generate_presigned_url(ClientMethod, Params, ExpiresIn):
        key = Params["Key"]
        return f"https://mock-s3.amazonaws.com/{key}?token=mock-token"

    def mock_get_object(Bucket, Key):
        if Key not in s3_storage:
            raise KeyError(f"Key {Key} not found in mock S3")
        return {"Body": MagicMock(read=lambda: s3_storage[Key])}

    # Parchear clientes en ambos handlers (API y Ingestion)
    with (
        patch.object(api_handler.table, "put_item", side_effect=mock_put_item),
        patch.object(api_handler.table, "get_item", side_effect=mock_get_item),
        patch.object(api_handler.s3_client, "generate_presigned_url", side_effect=mock_generate_presigned_url),
        patch.object(ingestion_handler.table, "update_item", side_effect=mock_update_item),
        patch.object(ingestion_handler.s3_client, "get_object", side_effect=mock_get_object),
        patch.object(ingestion_handler.bedrock_extractor, "extract_factor") as mock_extract,
    ):
        # Configurar respuestas simuladas de Bedrock para los 4 factores
        def fake_extract_factor(factor_name, candidate_pages):
            if factor_name == "garantias":
                return (
                    GarantiaFactor(
                        identificado=True,
                        tipo_garantia="Fiel cumplimiento",
                        monto="5% del valor total",
                        vigencia="90 días corridos",
                        glosa="Para garantizar el fiel cumplimiento",
                        pagina_citada=2,
                        fragmento_exacto="garantía de fiel cumplimiento por un monto equivalente al 5%",
                    ),
                    1200,
                    150,
                )
            elif factor_name == "criterios":
                return (
                    CriterioFactor(
                        identificado=True,
                        ponderacion_tecnica="70%",
                        ponderacion_economica="30%",
                        puntaje_minimo_descalificatorio="60 puntos",
                        pagina_citada=3,
                        fragmento_exacto="ponderación técnica del 70% y una ponderación económica del 30%",
                    ),
                    1100,
                    120,
                )
            elif factor_name == "multas":
                return (
                    MultaFactor(
                        identificado=True,
                        causal_principal="Atraso en la entrega de los hitos",
                        monto_diario="2 UF por cada día hábil",
                        tope_maximo="10% del valor total",
                        pagina_citada=4,
                        fragmento_exacto="multa diaria de 2 UF por cada día hábil de atraso",
                    ),
                    1150,
                    140,
                )
            elif factor_name == "plazos":
                return (
                    PlazoFactor(
                        identificado=True,
                        cierre_ofertas="30 de noviembre de 2026 a las 15:00 horas",
                        tipo_computo="días hábiles administrativos",
                        plazo_entrega="45 días corridos",
                        pagina_citada=5,
                        fragmento_exacto="cierre de recepción de ofertas será el 30 de noviembre de 2026",
                    ),
                    1050,
                    130,
                )
            raise ValueError(f"Unknown factor: {factor_name}")

        mock_extract.side_effect = fake_extract_factor

        # ----------------------------------------------------------------------
        # PASO 1: Cliente solicita Presigned URL
        # ----------------------------------------------------------------------
        upload_event = {
            "rawPath": "/licitaciones/upload-url",
            "requestContext": {"http": {"method": "POST"}},
            "body": json.dumps({
                "file_name": "bases_2239-14-LR26.pdf",
                "file_size_bytes": len(pdf_bytes),
            }),
        }
        res_upload = api_handler.lambda_handler(upload_event, None)
        assert res_upload["statusCode"] == 201
        upload_data = json.loads(res_upload["body"])
        licitacion_id = upload_data["licitacion_id"]
        s3_key = upload_data["s3_key"]

        # ----------------------------------------------------------------------
        # PASO 2: Cliente sube el PDF a S3 simulado
        # ----------------------------------------------------------------------
        s3_storage[s3_key] = pdf_bytes

        # ----------------------------------------------------------------------
        # PASO 3: SQS dispara el Ingestion Lambda Worker
        # ----------------------------------------------------------------------
        sqs_event = {
            "Records": [
                {
                    "body": json.dumps({
                        "Records": [
                            {
                                "s3": {
                                    "bucket": {"name": "test-uploads-bucket"},
                                    "object": {"key": s3_key},
                                }
                            }
                        ]
                    })
                }
            ]
        }
        res_worker = ingestion_handler.lambda_handler(sqs_event, None)
        assert res_worker["statusCode"] == 200
        assert res_worker["status"] == TenderStatus.READY.value

        # ----------------------------------------------------------------------
        # PASO 4: Cliente consulta estado de la licitación
        # ----------------------------------------------------------------------
        status_event = {
            "rawPath": f"/licitaciones/{licitacion_id}/status",
            "pathParameters": {"id": licitacion_id},
            "requestContext": {"http": {"method": "GET"}},
        }
        res_status = api_handler.lambda_handler(status_event, None)
        assert res_status["statusCode"] == 200
        status_data = json.loads(res_status["body"])
        assert status_data["status"] == TenderStatus.READY.value
        assert status_data["total_pages"] == 5
        assert status_data["cost_usd_estimate"] > 0.0

        # ----------------------------------------------------------------------
        # PASO 5: Cliente consulta factores auditados
        # ----------------------------------------------------------------------
        factores_event = {
            "rawPath": f"/licitaciones/{licitacion_id}/factores",
            "pathParameters": {"id": licitacion_id},
            "requestContext": {"http": {"method": "GET"}},
        }
        res_factores = api_handler.lambda_handler(factores_event, None)
        assert res_factores["statusCode"] == 200
        factores_data = json.loads(res_factores["body"])

        factors = factores_data["factors"]
        assert len(factors) == 4

        # Verificación determinista de Garantías
        assert factors["garantias"]["tipo_garantia"] == "Fiel cumplimiento"
        assert factors["garantias"]["verificado_en_pagina"] is True
        assert factors["garantias"]["status"] == "VERIFIED"
        assert factors["garantias"]["pagina_citada"] == 2

        # Verificación determinista de Criterios
        assert factors["criterios"]["ponderacion_tecnica"] == "70%"
        assert factors["criterios"]["verificado_en_pagina"] is True
        assert factors["criterios"]["status"] == "VERIFIED"

        # Verificación determinista de Multas
        assert factors["multas"]["causal_principal"] == "Atraso en la entrega de los hitos"
        assert factors["multas"]["verificado_en_pagina"] is True

        # Verificación determinista de Plazos
        assert factors["plazos"]["cierre_ofertas"] == "30 de noviembre de 2026 a las 15:00 horas"
        assert factors["plazos"]["verificado_en_pagina"] is True

        print(f"\nE2E Lifecycle Test Exitoso: Licitación {licitacion_id} procesada.")
        print(f"Costo Total Estimado: ${status_data['cost_usd_estimate']} USD.")
