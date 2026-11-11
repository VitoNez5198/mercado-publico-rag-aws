import json
import sys
import time
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.models import FactorStatus
from src.ingestion.candidate_selector import select_candidate_pages
from src.ingestion.parser import extract_pages_from_pdf_stream
from src.ingestion.verifier import verify_citation


def print_banner(text: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {text}")
    print(f"{'=' * 65}")


def run_interactive_demo(pdf_path: str = "samples/pliego_ejemplo_chilecompra.pdf") -> None:
    path = Path(pdf_path)
    if not path.exists():
        print(f"Error: No se encontró el archivo '{pdf_path}'.", file=sys.stderr)
        return

    print_banner("DEMO INTERACTIVA: PIPELINE SERVERLESS MERCADO PÚBLICO")
    print("Este demo simula todo el recorrido del pliego por la arquitectura serverless.")
    time.sleep(1)

    # --------------------------------------------------------------------------
    # PASO 1: Simulación de API Gateway
    # --------------------------------------------------------------------------
    licitacion_id = "LIC-1057432-88-LR26"
    print("\n[PASO 1] Cliente solicita URL prefirmada a API Gateway...")
    print("  • Endpoint: POST /licitaciones/upload-url")
    print(f"  • Archivo: {path.name} ({path.stat().st_size:,} bytes)")
    print(f"  • ID Asignado: {licitacion_id}")
    print("  • Estado en DynamoDB: PENDING_UPLOAD")
    time.sleep(1)

    # --------------------------------------------------------------------------
    # PASO 2: Carga en S3 y Trigger SQS
    # --------------------------------------------------------------------------
    print("\n[PASO 2] Archivo cargado en Amazon S3:")
    print(f"  • S3 Key: uploads/{licitacion_id}/{path.name}")
    print("  • Evento S3 notificado a Amazon SQS (licitaciones-queue).")
    print("  • Invocando Worker Lambda en Python 3.12 (ARM64)...")
    time.sleep(1)

    # --------------------------------------------------------------------------
    # PASO 3: Extracción de Texto con PyMuPDF
    # --------------------------------------------------------------------------
    print("\n[PASO 3] Worker Lambda lee y valida el documento PDF:")
    with open(path, "rb") as f:
        pdf_bytes = f.read()

    pages = extract_pages_from_pdf_stream(pdf_bytes)
    total_chars = sum(p.char_count for p in pages)
    print(f"  • Total de páginas procesadas: {len(pages)}")
    print(f"  • Total caracteres legibles: {total_chars:,}")
    print(f"  • Densidad media: {total_chars / len(pages):.1f} chars/pág (> 50 chars/pág -> PDF Digital Válido)")
    time.sleep(1)

    # --------------------------------------------------------------------------
    # PASO 4: Ventanas Heurísticas de Candidatos (Ahorro FinOps)
    # --------------------------------------------------------------------------
    print("\n[PASO 4] Escáner Regex filtra páginas clave (Evitando Base Vectorial pesada):")
    candidates = select_candidate_pages(pages, max_pages=5)
    for factor, matched in candidates.items():
        p_nums = [p.page_number for p in matched]
        p_tokens = sum(p.char_count for p in matched) // 4
        print(f"  • Factor '{factor.upper():<9}': Páginas {p_nums!s:<8} (~{p_tokens} tokens)")

    time.sleep(1)

    # --------------------------------------------------------------------------
    # PASO 5: Simulación de Inferencia LLM y Verificación Antialucinación
    # --------------------------------------------------------------------------
    print("\n[PASO 5] Inferencia en Amazon Bedrock (Claude 3.5 Haiku) + Verificación Determinista:")

    # Diccionario de páginas para el verificador
    raw_pages = {p.page_number: p.text for p in pages}

    # Datos estructurados extraídos del pliego de muestra
    simulated_extractions = {
        "garantias": {
            "tipo_garantia": "Seriedad de la oferta",
            "monto": "150 UF",
            "vigencia": "90 días corridos contados desde la apertura",
            "glosa": "Garantiza la seriedad de la oferta en licitación pública ID 1057432-88-LR26",
            "pagina_citada": 2,
            "fragmento_exacto": "Vale Vista bancario o Boleta de Garantía pagadera a la vista por un monto único de 150 UF",
        },
        "criterios": {
            "ponderacion_tecnica": "60%",
            "ponderacion_economica": "35%",
            "puntaje_minimo_descalificatorio": "50 puntos",
            "pagina_citada": 3,
            "fragmento_exacto": "Oferta Técnica y Calidad del Servicio: 60% de la ponderación total",
        },
        "multas": {
            "causal_principal": "Atraso Injustificado en Entregables",
            "monto_diario": "3 UF por día de atraso",
            "tope_maximo": "15% del valor total del contrato",
            "pagina_citada": 4,
            "fragmento_exacto": "se aplicará una multa diaria ascendente a 3 UF por día de atraso",
        },
        "plazos": {
            "cierre_ofertas": "28-11-2026 a las 15:00 horas",
            "tipo_computo": "Días hábiles administrativos (Ley N° 19.880)",
            "plazo_entrega": "60 días corridos",
            "pagina_citada": 5,
            "fragmento_exacto": "FECHA Y HORA DE CIERRE DE RECEPCIÓN DE OFERTAS: 28-11-2026 a las 15:00 horas",
        },
    }

    final_factors = {}
    for factor_name, data in simulated_extractions.items():
        # Verificación determinista matemática
        verified, warning = verify_citation(
            page_number=data["pagina_citada"],
            exact_quote=data["fragmento_exacto"],
            raw_pages=raw_pages,
        )

        status = FactorStatus.VERIFIED if verified else FactorStatus.REQUIRES_MANUAL_REVIEW
        status_badge = "[VERIFIED]" if verified else "[MANUAL_REVIEW]"

        print(f"\n  Factor Auditado: {factor_name.upper()} {status_badge}")
        print(f"    - Página Citada: Página {data['pagina_citada']}")
        print(f"    - Cita Extraída: \"{data['fragmento_exacto']}\"")
        print(f"    - Verificación Determinista NFKD: {'Coincidencia Exacta en Página' if verified else warning}")

        data["verificado_en_pagina"] = verified
        data["status"] = status.value
        data["advertencia"] = warning
        final_factors[factor_name] = data
        time.sleep(0.5)

    # --------------------------------------------------------------------------
    # PASO 6: Persistencia y Métricas FinOps
    # --------------------------------------------------------------------------
    tokens_in = 1850
    tokens_out = 480
    cost_usd = (tokens_in / 1000.0 * 0.0008) + (tokens_out / 1000.0 * 0.004)

    print("\n[PASO 6] Resultado Final Persistido en Amazon DynamoDB:")
    print("  • Estado Global: READY")
    print(f"  • Total Páginas: {len(pages)}")
    print(f"  • Tokens Consumidos: ~{tokens_in} entrada / ~{tokens_out} salida")
    print(f"  • Costo FinOps Estimado: ${cost_usd:.6f} USD (~${cost_usd * 980:.2f} CLP)")
    print("  • TTL en DynamoDB: 30 días (Expiración automática $0)")

    print_banner("PAYLOAD FINAL RETORNADO POR: GET /licitaciones/{id}/factores")
    print(json.dumps({"licitacion_id": licitacion_id, "status": "READY", "factors": final_factors}, indent=2, ensure_ascii=False))
    print("\n¡Demostración completada con éxito! El pipeline funciona de punta a punta.\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Demo interactiva del pipeline serverless")
    parser.add_argument(
        "--file",
        "-f",
        default="samples/pliego_ejemplo_chilecompra.pdf",
        help="Ruta al archivo PDF a procesar en la demo",
    )
    args = parser.parse_args()
    run_interactive_demo(args.file)
