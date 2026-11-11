from src.common.constants import MAX_CANDIDATE_PAGES_PER_FACTOR, SECTION_PATTERNS
from src.common.models import PageContent


def select_candidate_pages(
    pages: list[PageContent],
    max_pages: int = MAX_CANDIDATE_PAGES_PER_FACTOR,
) -> dict[str, list[PageContent]]:
    """Selecciona mediante escaneo heurístico de expresiones regulares las páginas

    más relevantes para cada uno de los 4 factores de riesgo contractual.

    Args:
        pages: Lista completa de páginas del pliego extraídas del PDF.
        max_pages: Cantidad máxima de páginas candidatas permitidas por factor (default: 5).

    Returns:
        Diccionario con claves ('garantias', 'criterios', 'multas', 'plazos') y
        como valor la lista de objetos PageContent candidatos ordenados por número de página.
    """
    if not pages:
        return {factor: [] for factor in SECTION_PATTERNS}

    candidates: dict[str, list[PageContent]] = {}

    for factor_name, pattern in SECTION_PATTERNS.items():
        matched_pages: list[PageContent] = []

        for page in pages:
            if pattern.search(page.text):
                matched_pages.append(page)
                if len(matched_pages) >= max_pages:
                    break

        # Estrategia de Fallback: Si el pliego no contiene las palabras clave explícitas
        # (ej: encabezados no estándar), se seleccionan las primeras 2 páginas del documento
        # (resumen ejecutivo / carátula) para que el modelo verifique ausencia con certeza.
        if not matched_pages:
            fallback_count = min(2, len(pages))
            matched_pages = pages[:fallback_count]

        candidates[factor_name] = matched_pages

    return candidates

