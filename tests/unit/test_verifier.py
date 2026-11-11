from src.ingestion.verifier import normalize_text, verify_citation


def test_normalize_text_unicode_ligatures_and_quotes():
    """Valida la descomposición de ligaduras, sustitución de comillas tipográficas y espacios."""
    # Texto con comillas tipográficas, ligadura 'fi' y espacios irregulares
    sample = "  “Cláusula   de   Fiel Cumplimiento   con  garantía   de  100  UF” \n\t "
    normalized = normalize_text(sample)

    assert normalized == '"clausula de fiel cumplimiento con garantia de 100 uf"'


def test_verify_citation_exact_match():
    """Comprueba verificación exitosa cuando la cita textual se encuentra en la página indicada."""
    raw_pages = {
        1: "Bases Administrativas de la licitación pública.",
        2: "El oferente deberá constituir una garantía de fiel cumplimiento por el 5% del valor total del contrato.",
        3: "Los plazos de entrega serán de 30 días hábiles administrativos contados desde la notificación.",
    }

    quote = "garantía de fiel cumplimiento por el 5% del valor total"
    verified, warning = verify_citation(page_number=2, exact_quote=quote, raw_pages=raw_pages)

    assert verified is True
    assert warning is None


def test_verify_citation_adjacent_page_detection():
    """Detecta cuando una cita pertenece a una página contigua (error de desfase)."""
    raw_pages = {
        1: "Página 1 con información general del organismo licitante.",
        2: "Página 2 con los criterios de evaluación: 60% técnico y 40% económico.",
    }

    quote = "criterios de evaluación: 60% técnico y 40% económico"
    # Citamos la página 1 cuando realmente está en la 2
    verified, warning = verify_citation(page_number=1, exact_quote=quote, raw_pages=raw_pages)

    assert verified is False
    assert warning is not None
    assert "Discrepancia de paginación" in warning
    assert "página 2" in warning


def test_verify_citation_hallucinated_text():
    """Comprueba que una cita inventada o alterada por el LLM sea rechazada."""
    raw_pages = {
        1: "La multa por atraso será de 1 UF diaria hasta un tope del 10% del contrato.",
    }

    quote = "La multa por atraso será de 50 UF diarias y expulsión inmediata del registro"
    verified, warning = verify_citation(page_number=1, exact_quote=quote, raw_pages=raw_pages)

    assert verified is False
    assert "Discrepancia detectada en la cita textual" in warning


def test_verify_citation_page_out_of_bounds():
    """Valida el manejo de páginas citadas que exceden el documento."""
    raw_pages = {1: "Página única del documento."}
    quote = "Página única"

    verified, warning = verify_citation(page_number=99, exact_quote=quote, raw_pages=raw_pages)

    assert verified is False
    assert "no existe en el documento" in warning
