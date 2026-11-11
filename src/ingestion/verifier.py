import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normaliza texto para comparación determinista de citas contra documentos PDF.

    Aplica descomposición Unicode NFKD (separando ligaduras tipográficas como 'fi', 'fl'),
    sustituye comillas curvas y normaliza cualquier secuencia de espacios en blanco
    (incluyendo saltos de línea y tabuladores) a un espacio simple en minúsculas.
    """
    if not text:
        return ""

    # 1. Normalización Unicode NFKD y eliminación de marcas diacríticas/tildes
    # Esto asegura que citas con/sin tildes o con ligaduras descompuestas coincidan perfectamente.
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))

    # 2. Reemplazo de variantes tipográficas de comillas y guiones
    quote_map = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "«": '"',
        "»": '"',
        "–": "-",
        "—": "-",
        "´": "'",
        "`": "'",
        "\u00a0": " ",  # Non-breaking space
    }
    for old, new in quote_map.items():
        stripped = stripped.replace(old, new)

    # 3. Normalizar secuencias de espacios en blanco a un solo espacio
    collapsed_spaces = re.sub(r"\s+", " ", stripped)

    # 4. Homogeneizar a minúsculas y recortar extremos
    return collapsed_spaces.strip().lower()


def verify_citation(
    page_number: int,
    exact_quote: str,
    raw_pages: dict[int, str],
) -> tuple[bool, str | None]:
    """Verifica de forma determinista si la cita textual existe en la página indicada.

    Args:
        page_number: Número de página (base 1) citado por el modelo.
        exact_quote: Fragmento textual extraído por el LLM.
        raw_pages: Diccionario con clave número de página (int) y valor texto crudo (str).

    Returns:
        tuple[bool, str | None]:
            - (True, None) si la cita coincide textualmente en la página indicada.
            - (False, advertencia) si la cita no coincide, informando si se halló en página contigua.
    """
    if not exact_quote or not exact_quote.strip():
        return False, "Cita textual vacía o no provista por el extractor."

    normalized_quote = normalize_text(exact_quote)
    if len(normalized_quote) < 5:
        return False, f"Cita textual demasiado corta para verificación determinista: '{exact_quote}'."

    # Comprobar si la página citada existe en el documento
    if page_number not in raw_pages:
        return (
            False,
            f"La página citada {page_number} no existe en el documento (total páginas: {len(raw_pages)}).",
        )

    # Comprobación en la página citada
    page_text_normalized = normalize_text(raw_pages[page_number])
    if normalized_quote in page_text_normalized:
        return True, None

    # Comprobación heurística en páginas adyacentes (detección de saltos de página o desfases)
    for adjacent_page in (page_number - 1, page_number + 1):
        if adjacent_page in raw_pages:
            adj_text_normalized = normalize_text(raw_pages[adjacent_page])
            if normalized_quote in adj_text_normalized:
                warning_msg = (
                    f"Discrepancia de paginación: La cita fue hallada en la página {adjacent_page}, "
                    f"pero el modelo citó la página {page_number}."
                )
                return False, warning_msg

    return (
        False,
        "Discrepancia detectada en la cita textual; el fragmento no coincide con el contenido de la página.",
    )
