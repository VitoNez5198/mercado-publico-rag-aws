# Goldfish Annotated Review Report

**Status:** resolved
**Target:** `D:\Proyectos\mercado-publico-rag-aws\docs\designs\pipeline-serverless-rag-mercado-publico.md` (`Lines 1..336`)

## Prioritized Findings & AI Suggestions

### 1. Ausencia Obligatoria de Sección "Risks & Mitigations" [`egm-structural`] - Severity: Blocker
* **Affected Scope:** Lines 268-336 (Document-wide gap)
* **Discrepancy Description:** La especificación carece de una sección formal `## Risks & Mitigations`, violando el estándar mandatorio de calidad (`feature-spec-standard.md`). El documento transiciona directamente desde *Alternatives Considered* hacia *Non-Functional Requirements*.
* **Rationale:** Mandato estricto de especificación técnica formal.
* ***AI Suggestion:*** PROPOSE FIX
* ***Justification:** Se debe insertar la sección `## Risks & Mitigations` detallando los 4 modos de fallo críticos (throttling en Bedrock, límite de capas zip en Lambda, timeouts por pliegos anómalos y PDFs escaneados).
* ***Proposed Edit:***
  * Location: Insertar inmediatamente antes de `## Non-Functional Requirements`.
  * Change: Incorporar la tabla y detalle de mitigaciones técnicas operativas.

---

### 2. Formato de Persistencia de LanceDB en S3 y Tamaño de Layers en Lambda ARM64 [`egm-design`] - Severity: Major
* **Affected Scope:** Lines 111, 149-155, 345
* **Discrepancy Description:** LanceDB requiere Apache Arrow/PyArrow, superando los 200 MB en Linux ARM64 y poniendo en riesgo el límite de 250 MB de Lambda zip.
* **Rationale:** Riesgo de fallo de despliegue en SAM (`Uncompressed image size too large`).
* ***AI Suggestion:*** PROPOSE FIX
* ***Justification:** Adoptar la resolución TRIZ recomendada en la Etapa 5: eliminar LanceDB y PyArrow del worker de ingesta. Dado que el escaneo Regex ya delimita los pliegos a 3-5 páginas por factor (~2.000 tokens), pasar los chunks de esas páginas directamente a Bedrock Claude 3.5 Haiku simplifica la arquitectura, ahorra llamadas a Titan Embeddings y asegura un despliegue ligero (< 50 MB con PyMuPDF).
* ***Proposed Edit:***
  * Location: Líneas 108-115, 149-155 y descripción de componentes.
  * Change: Reemplazar el almacenamiento vectorial local por ventana directa de candidatos con PyMuPDF hacia Bedrock.

---

### 3. Concurrencia Bedrock y Manejo de Throttling en Extracción Paralela [`egm-design`] - Severity: Major
* **Affected Scope:** Lines 112-113, 136, 238-245
* **Discrepancy Description:** 4 llamadas concurrentes a Claude 3.5 Haiku pueden disparar `ThrottlingException` (HTTP 429) en cuentas con cuotas iniciales en Bedrock, enviando mensajes válidos a DLQ si no hay reintentos exponenciales.
* **Rationale:** Estabilidad de ingesta frente a límites de tasa de AWS Bedrock.
* ***AI Suggestion:*** PROPOSE FIX
* ***Justification:** Configurar explícitamente en el cliente `boto3` la política de reintentos con retroceso exponencial adaptativo (`botocore.config.Config(retries={'max_attempts': 5, 'mode': 'adaptive'})`) y prever un fallback secuencial en caso de saturación persistente.
* ***Proposed Edit:***
  * Location: Sección 6 (Motor de Inferencia LLM).
  * Change: Añadir bloque de configuración de resiliencia y manejo de HTTP 429.

---

### 4. Pregunta Abierta Q1 Sin Resolver y en Contradicción con la Arquitectura [`egm-structural`] - Severity: Major
* **Affected Scope:** Lines 40-41 vs Lines 149-155
* **Discrepancy Description:** La sección *Open Questions* mantiene `Q1` abierta respecto a LanceDB vs FAISS, mientras que la sección 3 adopta LanceDB de manera definitiva.
* **Rationale:** Coherencia interna del documento de diseño.
* ***AI Suggestion:*** PROPOSE FIX
* ***Justification:** Resolver Q1 formalmente estipulando que se descarta tanto LanceDB como FAISS en favor de la extracción directa por ventana de contexto con PyMuPDF y Regex, eliminando dependencias de C++ y capas binarias pesadas.
* ***Proposed Edit:***
  * Location: Sección `## Open Questions`.
  * Change: Marcar Q1 como resuelta y documentar la decisión adoptada.

---

### 5. Inconsistencia en la Denominación del Endpoint de Carga en la API [`egm-structural`] - Severity: Major
* **Affected Scope:** Line 102 vs Line 215 vs Line 349
* **Discrepancy Description:** El diagrama Mermaid declara `POST /licitaciones/presigned-url`, mientras que el Contrato de API y la plantilla SAM definen `POST /licitaciones/upload-url`.
* **Rationale:** Consistencia en los contratos de interfaz pública.
* ***AI Suggestion:*** PROPOSE FIX
* ***Justification:** Unificar la denominación a `POST /licitaciones/upload-url` en el diagrama Mermaid.
* ***Proposed Edit:***
  * Location: Línea 102 (Diagrama Mermaid).
  * Change: Reemplazar `POST /licitaciones/presigned-url` por `POST /licitaciones/upload-url`.

---

### 6. Comportamiento No Especificado ante Fallo en Verificación de Citas [`egm-design`] - Severity: Nit
* **Affected Scope:** Lines 246-254
* **Discrepancy Description:** No se define qué ocurre cuando `verificado_en_pagina == false`.
* **Rationale:** Claridad en la experiencia de usuario y contratos de API.
* ***AI Suggestion:*** PROPOSE FIX
* ***Justification:** Especificar que cuando `verificado_en_pagina: false`, el factor se acompaña de `status: REQUIRES_MANUAL_REVIEW`, conservando el texto pero advirtiendo a la PYME de la discrepancia.
* ***Proposed Edit:***
  * Location: Sección 4 (Modelo DynamoDB) y Sección 6 (Mecanismo Antialucinación).
  * Change: Añadir campo de estado por factor y clarificar comportamiento en la API.

---

### 7. Formato de Razón de Rechazo en "Alternatives Considered" [`egm-style`] - Severity: Nit
* **Affected Scope:** Lines 278, 288, 298, 307
* **Discrepancy Description:** Prefijo redundante `Rejected by author:` en lugar de redactar directamente el trade-off técnico.
* **Rationale:** Cumplimiento con la guía de estilo de documentación técnica objetiva.
* ***AI Suggestion:*** PROPOSE FIX
* ***Justification:** Remover el prefijo literal y redactar directamente el trade-off técnico objetivo.
* ***Proposed Edit:***
  * Location: Líneas 278, 288, 298, 307.
  * Change: Sustituir `Rejected by author: [motivo]` por `Descartado debido a [motivo]`.

---

### 8. Jerarquía de Encabezado en "Future Improvements" [`egm-style`] - Severity: Nit
* **Affected Scope:** Line 329
* **Discrepancy Description:** El encabezado `### Future Improvements` tiene nivel H3 erróneamente subordinado a `## Non-Functional Requirements`.
* **Rationale:** Estructura semántica correcta en Markdown.
* ***AI Suggestion:*** PROPOSE FIX
* ***Justification:** Elevar el encabezado a `## Future Improvements`.
* ***Proposed Edit:***
  * Location: Línea 329.
  * Change: Cambiar `### Future Improvements` por `## Future Improvements`.

