import pymupdf
import pytest

from src.ingestion.parser import (
    InvalidPdfException,
    ScannedPdfException,
    extract_pages_from_pdf_stream,
)


def create_synthetic_pdf(pages_text: list[str]) -> bytes:
    """Genera en memoria un archivo PDF sintético con el texto provisto por página."""
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page(width=595, height=842)  # Formato A4
        page.insert_text((50, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_extract_pages_valid_pdf():
    """Verifica la extracción exitosa de un PDF digital válido de múltiples páginas."""
    pages_data = [
        "Capítulo 1: Bases Administrativas Generales de la Licitación Pública para Servicios Cloud.",
        "Capítulo 2: Garantía de Seriedad de la Oferta por 100 UF pagadera mediante Boleta Bancaria.",
        "Capítulo 3: Criterios de Evaluación Técnica (70%) y Económica (30%) con umbral de 60 puntos.",
    ]
    pdf_bytes = create_synthetic_pdf(pages_data)

    pages = extract_pages_from_pdf_stream(pdf_bytes)

    assert len(pages) == 3
    assert pages[0].page_number == 1
    assert "Bases Administrativas" in pages[0].text
    assert pages[0].char_count > 50

    assert pages[1].page_number == 2
    assert "Garantía de Seriedad" in pages[1].text

    assert pages[2].page_number == 3
    assert "Criterios de Evaluación" in pages[2].text


def test_extract_pages_scanned_pdf_raises_exception():
    """Comprueba que un PDF sin texto suficiente dispare ScannedPdfException."""
    # Páginas en blanco o con menos de 50 caracteres en promedio
    blank_pages = ["", "   ", "Pág 1"]
    pdf_bytes = create_synthetic_pdf(blank_pages)

    with pytest.raises(ScannedPdfException) as exc_info:
        extract_pages_from_pdf_stream(pdf_bytes)

    assert "carece de texto digital" in str(exc_info.value)
    assert "Posible PDF escaneado" in str(exc_info.value)


def test_extract_pages_invalid_bytes_raises_exception():
    """Valida que flujos binarios corruptos o vacíos disparen InvalidPdfException."""
    with pytest.raises(InvalidPdfException):
        extract_pages_from_pdf_stream(b"")

    with pytest.raises(InvalidPdfException):
        extract_pages_from_pdf_stream(b"archivo corrupto no pdf")
