import pymupdf

from src.common.constants import MIN_CHARS_PER_PAGE_THRESHOLD
from src.common.models import PageContent


class ScannedPdfException(Exception):
    """Excepción lanzada cuando un PDF no contiene suficiente texto digital (posible escaneo)."""


class InvalidPdfException(Exception):
    """Excepción lanzada cuando los bytes provistos no corresponden a un PDF válido o legible."""


def extract_pages_from_pdf_stream(pdf_bytes: bytes) -> list[PageContent]:
    """Extrae secuencialmente el texto estructurado de cada página de un archivo PDF en memoria.

    Args:
        pdf_bytes: Flujo binario del archivo PDF.

    Returns:
        Lista de objetos PageContent conteniendo número de página (base 1),
        texto limpio y conteo de caracteres legibles.

    Raises:
        InvalidPdfException: Si el archivo está vacío, corrupto o no es un PDF.
        ScannedPdfException: Si la densidad de caracteres promedio es inferior
                             al umbral MIN_CHARS_PER_PAGE_THRESHOLD.
    """
    if not pdf_bytes or len(pdf_bytes) < 4:
        raise InvalidPdfException("El flujo de bytes está vacío o es demasiado pequeño para ser un PDF.")

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise InvalidPdfException(f"Error al abrir el documento PDF: {e}") from e

    try:
        total_pages = len(doc)
        if total_pages == 0:
            raise InvalidPdfException("El documento PDF no contiene páginas.")

        pages_content: list[PageContent] = []
        total_chars = 0

        for page_idx in range(total_pages):
            page = doc.load_page(page_idx)
            # Extracción limpia en formato texto plano
            text = page.get_text("text") or ""
            # Limpieza básica de caracteres nulos conservando estructura de párrafos
            cleaned_text = text.replace("\x00", "").strip()
            char_count = len(cleaned_text)
            total_chars += char_count

            pages_content.append(
                PageContent(
                    page_number=page_idx + 1,
                    text=cleaned_text,
                    char_count=char_count,
                )
            )

        avg_chars_per_page = total_chars / total_pages
        if avg_chars_per_page < MIN_CHARS_PER_PAGE_THRESHOLD:
            raise ScannedPdfException(
                f"PDF carece de texto digital extraíble (promedio: {avg_chars_per_page:.1f} caracteres/pág; "
                f"umbral mínimo: {MIN_CHARS_PER_PAGE_THRESHOLD}). Posible PDF escaneado que requiere OCR."
            )

        return pages_content

    finally:
        doc.close()
