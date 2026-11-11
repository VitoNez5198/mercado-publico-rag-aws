import argparse
import sys
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


def run_local_audit(pdf_path: str) -> None:
    """Ejecuta una auditoría local de parseo y selección heurística sobre un archivo PDF."""
    path = Path(pdf_path)
    if not path.exists():
        print(f"Error: El archivo '{pdf_path}' no existe.", file=sys.stderr)
        sys.exit(1)

    print("\n=======================================================")
    print(f"  AUDITORÍA LOCAL DE BASES: {path.name}")
    print("=======================================================")

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
    print("    El pliego califica para inferencia directa con Amazon Bedrock Claude 3.5 Haiku.")
    print("=======================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auditoría local de bases de licitación PDF")
    parser.add_argument(
        "--file",
        "-f",
        default="samples/pliego_ejemplo_chilecompra.pdf",
        help="Ruta al archivo PDF a analizar",
    )
    args = parser.parse_args()
    run_local_audit(args.file)
