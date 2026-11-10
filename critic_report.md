# Goldfish Review Report: Critic Review

**Target:** `D:\Proyectos\mercado-publico-rag-aws\docs\designs\pipeline-serverless-rag-mercado-publico.md` (`Lines 1..336`)
**Standards Applied:** `feature-spec-standard.md`
**Mode:** REVIEW

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-structural` | completed |
| `egm-design` | completed |
| `egm-style` | completed |

---

## Severity Summary
* 🔴 **Blockers:** 1
* 🟡 **Majors:** 4
* 🟢 **Nits:** 3

---

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Ausencia Obligatoria de Sección "Risks & Mitigations" - Severity: 🔴 Blocker
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** Lines 268-336 (Document-wide gap)
* **Discrepancy Description:** La especificación carece de una sección formal `## Risks & Mitigations`, violando el estándar mandatorio de calidad (`feature-spec-standard.md`). El documento transiciona directamente desde *Alternatives Considered* hacia *Non-Functional Requirements*.
* **Rationale & Recommendation:** Incorporar una sección formal `## Risks & Mitigations` cubriendo throttling de Bedrock, límites de tamaño en Lambda Layers (250 MB), límites de timeout frente a degradación de red y manejo de PDFs escaneados o corruptos.

---

### 2. Formato de Persistencia de LanceDB en S3 y Tamaño de Layers en Lambda ARM64 - Severity: 🟡 Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 111, 149-155, 345
* **Discrepancy Description:** LanceDB es un motor columnar basado en Apache Arrow estructurado como directorio multinivel, no un archivo plano unitario. Adicionalmente, las dependencias `lancedb` + `pyarrow` (~180-220 MB) sumadas a `PyMuPDF` (~45 MB) exceden el límite de 250 MB de Lambda Layers tradicionales.
* **Rationale & Recommendation:** Aclarar la estrategia adoptando la recomendación de la Etapa 5 (eliminar `lancedb` y `pyarrow` usando ventana directa de candidatos hacia Claude 3.5 Haiku, o empaquetar mediante imagen de contenedor ECR `PackageType: Image`).

---

### 3. Concurrencia Bedrock y Manejo de Throttling en Extracción Paralela - Severity: 🟡 Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 112-113, 136, 238-245
* **Discrepancy Description:** 4 llamadas concurrentes a Claude 3.5 Haiku pueden disparar `ThrottlingException` (HTTP 429) en cuentas con cuotas iniciales en Bedrock, enviando mensajes válidos a DLQ si no hay reintentos exponenciales.
* **Rationale & Recommendation:** Documentar en el plan técnico la estrategia de reintentos resilientes con retroceso exponencial y variación aleatoria (exponential backoff con full jitter) mediante configuración de `botocore.config.Config(retries={'max_attempts': 5, 'mode': 'adaptive'})`.

---

### 4. Pregunta Abierta Q1 Sin Resolver y en Contradicción con la Arquitectura - Severity: 🟡 Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** Lines 40-41 vs Lines 149-155
* **Discrepancy Description:** La sección *Open Questions* mantiene `Q1` abierta respecto a LanceDB vs FAISS, mientras que la sección 3 adopta LanceDB de manera definitiva.
* **Rationale & Recommendation:** Resolver y cerrar formalmente Q1 en el documento.

---

### 5. Inconsistencia en la Denominación del Endpoint de Carga en la API - Severity: 🟡 Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** Line 102 vs Line 215 vs Line 349
* **Discrepancy Description:** El diagrama Mermaid declara `POST /licitaciones/presigned-url`, mientras que el Contrato de API y la plantilla SAM definen `POST /licitaciones/upload-url`.
* **Rationale & Recommendation:** Homogeneizar a `POST /licitaciones/upload-url` a lo largo de todo el documento.

---

### 6. Comportamiento No Especificado ante Fallo en Verificación de Citas - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 246-254
* **Discrepancy Description:** No se define qué ocurre cuando `verificado_en_pagina == false`.
* **Rationale & Recommendation:** Estipular que si la verificación falla, el factor se marca con `status: REQUIRES_MANUAL_REVIEW`, conservando el texto extraído pero con una advertencia visible en la respuesta de la API.

---

### 7. Formato de Razón de Rechazo en "Alternatives Considered" - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 278, 288, 298, 307
* **Discrepancy Description:** Prefijo redundante `Rejected by author:` en lugar de redactar directamente el trade-off técnico.
* **Rationale & Recommendation:** Eliminar el prefijo redundante y enunciar directamente el motivo técnico del descarte.

---

### 8. Jerarquía de Encabezado en "Future Improvements" - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Line 329
* **Discrepancy Description:** El encabezado `### Future Improvements` tiene nivel H3 erróneamente subordinado a `## Non-Functional Requirements`.
* **Rationale & Recommendation:** Elevar a nivel H2 (`## Future Improvements`).

