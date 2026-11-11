import re

# ==============================================================================
# Domain Regex Patterns for Chilean Public Procurement (Mercado Público)
# ==============================================================================

SECTION_PATTERNS = {
    "garantias": re.compile(
        r"(?i)(garant[ií]a|seriedad\s+de\s+la\s+oferta|fiel\s+cumplimiento|cauci[oó]n|vale\s+vista|p[oó]liza)"
    ),
    "criterios": re.compile(
        r"(?i)(criterios?\s+de\s+evaluaci[oó]n|ponderaci[oó]n|matriz\s+de\s+evaluaci[oó]n|puntaje\s+t[eé]cnico)"
    ),
    "multas": re.compile(
        r"(?i)(multas?|sanciones?|atraso|incumplimiento|tope\s+m[aá]ximo)"
    ),
    "plazos": re.compile(
        r"(?i)(plazos?|fechas?\s+fatales?|calendario|cierre\s+de\s+ofertas|apertura\s+t[eé]cnica)"
    ),
}

# ==============================================================================
# Heuristic & Ingestion Limits
# ==============================================================================

MIN_CHARS_PER_PAGE_THRESHOLD = 50
MAX_CANDIDATE_PAGES_PER_FACTOR = 5
DEFAULT_TTL_DAYS = 30
SECONDS_IN_DAY = 86400

# Canonical S3 key pattern: uploads/{licitacion_id}/{filename}
S3_UPLOAD_PREFIX = "uploads"

# ==============================================================================
# Bedrock Prompts per Risk Factor
# ==============================================================================

EXTRACTION_SYSTEM_PROMPT = """Eres un especialista en auditoría legal y análisis de bases de licitación pública en Chile (Ley N° 19.886 y Mercado Público).
Tu objetivo es extraer con estricta rigurosidad y precisión técnica el factor solicitado desde el texto extraído del pliego.

REGLAS OBLIGATORIAS:
1. No inventes, deduzcas ni extrapoles información que no esté explícitamente en el texto.
2. Si un dato no se encuentra expresamente en el texto provisto, deja el campo como null y marca identificado: false.
3. Para cada factor identificado, DEBES proporcionar la cita textual EXACTA (`fragmento_exacto`) y el número de página correspondiente (`pagina_citada`).
4. Responde ÚNICAMENTE en formato JSON válido que cumpla con el esquema requerido, sin comentarios ni explicaciones adicionales.
"""

