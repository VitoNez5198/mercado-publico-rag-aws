import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.candidate_selector import select_candidate_pages
from src.ingestion.parser import (
    InvalidPdfException,
    ScannedPdfException,
    extract_pages_from_pdf_stream,
)

DEFAULT_API_URL = "https://01lzy8hu0c.execute-api.us-east-1.amazonaws.com"


def print_banner(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def run_local_audit(pdf_path: str) -> None:
    """Ejecuta una auditoría local de parseo y selección heurística sobre un archivo PDF."""
    path = Path(pdf_path)
    if not path.exists():
        print(f"Error: El archivo '{pdf_path}' no existe.", file=sys.stderr)
        sys.exit(1)

    print_banner(f"AUDITORÍA LOCAL DE BASES: {path.name}")
    with open(path, "rb") as f:
        pdf_bytes = f.read()

    print(f"[*] Tamaño del archivo: {len(pdf_bytes):,} bytes")

    # 1. Parseo con PyMuPDF
    try:
        pages = extract_pages_from_pdf_stream(pdf_bytes)
        print(f"[+] Total de páginas analizadas: {len(pages)}")
    except (InvalidPdfException, ScannedPdfException) as e:
        print(f"[!] Error durante el parseo de PDF: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Selección heurística de páginas candidatas
    candidates = select_candidate_pages(pages, max_pages=5)

    print("\n--- RESUMEN DE VENTANAS CANDIDATAS POR FACTOR ---")
    for factor, matched_pages in candidates.items():
        page_numbers = [p.page_number for p in matched_pages]
        total_chars = sum(p.char_count for p in matched_pages)
        est_tokens = int(total_chars / 4)
        print(
            f"• Factor: {factor.upper():<12} | "
            f"Páginas: {page_numbers!s:<12} | "
            f"Caracteres: {total_chars:<6} | "
            f"Tokens aprox: ~{est_tokens}"
        )

    print("\n[+] Auditoría heurística local completada con éxito.")
    print("    Para analizar en la nube de AWS con Bedrock, añade la opción '--cloud'.")
    print("=======================================================\n")


def run_cloud_audit(pdf_path: str, api_url: str = DEFAULT_API_URL) -> None:
    """Sube un pliego PDF a AWS S3 y consulta la extracción de factores en tiempo real."""
    path = Path(pdf_path)
    if not path.exists():
        print(f"Error: El archivo '{pdf_path}' no existe.", file=sys.stderr)
        sys.exit(1)

    file_size = path.stat().st_size
    print_banner(f"AUDITORÍA EN LA NUBE AWS: {path.name}")
    print(f"[*] Archivo: {path.name} ({file_size:,} bytes)")
    print(f"[*] API Endpoint: {api_url}")

    # 1. Solicitar URL prefirmada
    print("\n[1/4] Solicitando URL prefirmada a API Gateway...")
    payload = {"file_name": path.name, "file_size_bytes": file_size}
    req = urllib.request.Request(
        f"{api_url}/licitaciones/upload-url",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"[!] Error al contactar la API: {e}", file=sys.stderr)
        sys.exit(1)

    lic_id = data["licitacion_id"]
    upload_url = data["upload_url"]
    print(f"      ID Asignado: {lic_id}")

    # 2. Cargar archivo a Amazon S3
    print("\n[2/4] Subiendo archivo directamente a Amazon S3...")
    with open(path, "rb") as f:
        pdf_bytes = f.read()

    put_req = urllib.request.Request(
        upload_url,
        data=pdf_bytes,
        headers={"Content-Type": "application/pdf"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(put_req) as resp:
            print(f"      Subida completada (HTTP {resp.status}).")
    except urllib.error.URLError as e:
        print(f"[!] Error subiendo a S3: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Monitorear progreso en Lambda Ingestion + Bedrock
    print("\n[3/4] Esperando procesamiento serverless (SQS -> Lambda -> Bedrock)...")
    finished = False
    for i in range(25):
        time.sleep(3)
        try:
            status_req = urllib.request.Request(f"{api_url}/licitaciones/{lic_id}/status")
            with urllib.request.urlopen(status_req) as s_resp:
                st_data = json.loads(s_resp.read().decode("utf-8"))
                status = st_data.get("status")
                print(f"      [+{(i+1)*3}s] Estado en DynamoDB: {status}")
                if status in ["READY", "PARTIAL_SUCCESS", "FAILED"]:
                    finished = True
                    break
        except urllib.error.URLError as e:
            print(f"      Error consultando estado: {e}")

    if not finished:
        print("\n[!] El procesamiento tardó más de lo esperado. Revisa los logs de CloudWatch.")
        return

    # 4. Obtener y mostrar factores auditados
    print("\n[4/4] Obteniendo Factores de Riesgo Auditados...")
    factors_req = urllib.request.Request(f"{api_url}/licitaciones/{lic_id}/factores")
    with urllib.request.urlopen(factors_req) as f_resp:
        result = json.loads(f_resp.read().decode("utf-8"))

    print_banner(f"REPORTE DE AUDITORÍA: {lic_id}")
    print(f"Estado General:     {result.get('status')}")
    print(f"Páginas analizadas: {result.get('total_pages')}")
    print(f"Latencia Lambda:    {result.get('processing_time_ms', 0):,} ms")
    print(f"Costo Bedrock:      ${result.get('cost_usd_estimate', 0):.6f} USD")

    factors = result.get("factors", {})
    for nombre, data in factors.items():
        st = data.get("status", "UNKNOWN")
        icon = "✔" if st == "VERIFIED" else "⚠"
        pag = data.get("pagina_citada", 0)
        print(f"\n{icon} [{nombre.upper()}] - Estado: {st} (Pág. {pag})")

        # Imprimir campos específicos del factor
        for k, v in data.items():
            if k not in ["identificado", "pagina_citada", "fragmento_exacto", "status", "verificado_en_pagina", "advertencia", "source_file"]:
                print(f"   • {k.replace('_', ' ').title()}: {v}")

        if data.get("advertencia"):
            print(f"   [!] Advertencia: {data['advertencia']}")

        quote = data.get("fragmento_exacto", "").strip()
        if quote:
            clean_quote = quote if len(quote) < 140 else quote[:137] + "..."
            print(f"   • Cita Textual: \"{clean_quote}\"")

    print("\n" + "=" * 65 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auditoría de bases de licitación PDF (Local o en AWS Cloud)")
    parser.add_argument(
        "--file",
        "-f",
        default="samples/pliego_ejemplo_chilecompra.pdf",
        help="Ruta al archivo PDF a analizar (por defecto: pliego de prueba)",
    )
    parser.add_argument(
        "--cloud",
        "-c",
        action="store_true",
        help="Ejecutar análisis en la nube de AWS (API Gateway + Bedrock)",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help="URL base del API Gateway de AWS",
    )
    args = parser.parse_args()

    if args.cloud:
        run_cloud_audit(args.file, args.api_url)
    else:
        run_local_audit(args.file)
