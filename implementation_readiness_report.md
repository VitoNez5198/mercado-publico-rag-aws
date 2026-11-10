# Reporte de Revisión EGM: Implementation Readiness

**Status:** resolved
**Target:** `D:\Proyectos\mercado-publico-rag-aws\docs\designs\pipeline-serverless-rag-mercado-publico.md` (`385..534`)  
**Estándar Aplicado:** `implementation-readiness-standard.md`

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

## Resumen Ejecutivo de Severidad

* 🔴 **Bloqueadores (Blocker):** 3
* 🟡 **Mayores (Major):** 3
* 🟢 **Menores (Nit):** 2

---

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Ausencia total de Fases Incrementales y Puntos de Control (Phasing & Checkpoints) - Severity: 🔴 Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Líneas 385-483 (Sección `Detailed Implementation Plan`)
* **Discrepancy Description:** El estándar *Implementation Readiness Standard* estipula como requisito mandatorio: *"The plan must partition the work into logical, incremental phases. Each phase must leave the codebase in a stable, buildable, and testable state"*. La sección actual presenta una lista plana y desordenada de 16 archivos a crear (del 1 al 16), sin dependencias secuenciales, sin agrupación por fases de entrega y sin criterios de verificación intermedios (*exit criteria*) entre etapas.
* **Rationale & Recommendation:** Un implementador o sesión de IA que tome este plan no sabrá en qué orden construir y verificar el sistema, lo que induce a implementaciones monolíticas con alto riesgo de regresión. Se debe estructurar la implementación en 5 fases secuenciales estrictas:
  1. **Fase 1 (Fundaciones, IaC y Modelos):** `template.yaml`, `samconfig.toml`, `requirements.txt`, `src/common/config.py`, `src/common/constants.py`, `src/common/models.py`. *Checkpoint:* `sam validate` y validación de tipos con `mypy/ruff`.
  2. **Fase 2 (Núcleo de Parseo y Verificación Determinista):** `src/ingestion/parser.py`, `src/ingestion/verifier.py`, `tests/unit/test_parser.py`, `tests/unit/test_verifier.py`. *Checkpoint:* `pytest` pasa al 100% en lógica offline sin dependencias cloud.
  3. **Fase 3 (Motor de Ingesta Asíncrona y Bedrock):** `src/ingestion/candidate_selector.py`, `src/ingestion/extractor.py`, `src/ingestion/handler.py`. *Checkpoint:* Invocación local `sam local invoke IngestionFunction` con evento simulado de SQS.
  4. **Fase 4 (Capa de API Gateway y Endpoints):** `src/api/handler.py`, `tests/unit/test_api.py`. *Checkpoint:* `sam local start-api` y verificación de respuestas HTTP.
  5. **Fase 5 (Integración E2E, FinOps y Documentación):** `tests/integration/test_pipeline_e2e.py`, `README.md`. *Checkpoint:* Ejecución completa de suite de integración y verificación de alarmas de CloudWatch.

---

### 2. Violación de la Regla de Cero Decisiones en Modelos y Esquemas de Datos - Severity: 🔴 Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Líneas 408-428 (`src/common/config.py`, `src/common/models.py`, `src/ingestion/parser.py`)
* **Discrepancy Description:** El plan describe los contratos en lenguaje conceptual vago (ejemplo: *"GarantiaFactor: campos para tipo, monto, vigencia, glosa, número de página, texto citado y status"*), omitiendo los esquemas de código Pydantic v2, tipos exactos (`str`, `int`, `Optional[float]`, `Literal`), validaciones de campo y modelos auxiliares. Asimismo, la firma de `src/ingestion/parser.py` introduce el tipo `PageContent` (`extract_pages_from_pdf_stream(pdf_bytes: bytes) -> List[PageContent]`), el cual no está definido en `models.py`.
* **Rationale & Recommendation:** Fuerza al implementador a inventar la arquitectura de datos y los nombres exactos de atributos. El plan debe documentar explícitamente los modelos de Pydantic v2 listos para implementar con sus tipos exactos.

---

### 3. Incompatibilidad de Dependencias en Pydantic v2 (`pydantic-settings` omitido) - Severity: 🔴 Blocker
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Líneas 404-411 (`requirements.txt` y `src/common/config.py`)
* **Discrepancy Description:** El plan fija `pydantic>=2.6.0` y especifica: *"Carga centralizada de variables de entorno mediante Pydantic BaseSettings"*. En Pydantic v2, la clase `BaseSettings` fue retirada del paquete principal y trasladada a la librería separada `pydantic-settings`. Si un desarrollador o agente instala el `requirements.txt` especificado y ejecuta `from pydantic import BaseSettings`, se producirá un error fatal en tiempo de importación: `ImportError: cannot import name 'BaseSettings' from 'pydantic'`.
* **Rationale & Recommendation:** Rompe el principio de reproducibilidad inmediata ("first attempt execution"). Se debe agregar `pydantic-settings>=2.2.0` al listado de `requirements.txt`, indicar la importación `from pydantic_settings import BaseSettings, SettingsConfigDict` y detallar la clase `Settings`.

---

### 4. Contradicción Arquitectural Residual: Referencias a Modelos Titan y Embeddings - Severity: 🟡 Major
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Líneas 362 y 369 (`Security & Privacy` y `Performance & Latency`) frente a Líneas 47, 154-162 y 404-441
* **Discrepancy Description:** En las decisiones de diseño se descartó taxativamente el uso de embeddings y bases vectoriales para optimizar el empaquetado de Lambda Layers (< 45 MB). Sin embargo, en la sección de requerimientos no funcionales persisten menciones obsoletas a Titan y embeddings de 256 dimensiones.
* **Rationale & Recommendation:** Eliminar por completo las menciones a Titan y a los embeddings en las secciones no funcionales, ratificando la política de ventana heurística directa a Claude 3.5 Haiku.

---

### 5. Inconsistencia en la Firma de `verify_citation` y Retornos del Verificador - Severity: 🟡 Major
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Línea 446 (`src/ingestion/verifier.py`) frente a Línea 284 (`Mecanismo Antialucinación`)
* **Discrepancy Description:** En la sección técnica previa, el diseño implementa `def verify_citation(...) -> bool:`. Sin embargo, en el plan de implementación se declara `verify_citation(...) -> Tuple[bool, str]` sin especificar qué contiene el segundo elemento de la tupla.
* **Rationale & Recommendation:** Armonizar el contrato en el plan: `Tuple[bool, Optional[str]]` donde el segundo valor es el mensaje de advertencia si no fue verificado.

---

### 6. Ambigüedad en la Estructura del Evento SQS y Enrutamiento del Objeto S3 - Severity: 🟡 Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Líneas 449-455 (Archivo 10 `src/ingestion/handler.py`)
* **Discrepancy Description:** El plan indica que `handler.py` procesa eventos SQS con `batch_size = 1`, pero no especifica la convención exacta de almacenamiento en S3 ni cómo la función Lambda extrae `licitacion_id`.
* **Rationale & Recommendation:** Documentar la key canónica `uploads/{licitacion_id}/{filename}` y el fragmento de extracción en `handler.py`.

---

### 7. Ausencia de Matriz de Casos de Prueba Negativos y Edge Cases - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Líneas 464-479 y 484-500 (`tests/` y `Verification Plan`)
* **Discrepancy Description:** El plan de pruebas enumera archivos pero no detalla los escenarios de error críticos definidos en la arquitectura (PDF escaneado < 50 chars, ligaduras Unicode, timeout de Bedrock).
* **Rationale & Recommendation:** Detallar los escenarios de prueba unitaria en la sección de verificación.

---

### 8. Ausencia de Módulo Centralizado de Constantes Regex - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-codebase-details` / `egm-style`
* **Affected Scope:** Líneas 427 y 432 (`parser.py` y `candidate_selector.py`)
* **Discrepancy Description:** Los patrones de expresiones regulares para identificar secciones de Mercado Público se duplican conceptualmente entre el parser y el selector de candidatos.
* **Rationale & Recommendation:** Declarar `src/common/constants.py` como único punto de verdad para los patrones regex compilados.

---

## Resolution Summary

Todas las 8 discrepancias fueron corregidas y armonizadas en el documento de diseño técnico `D:\Proyectos\mercado-publico-rag-aws\docs\designs\pipeline-serverless-rag-mercado-publico.md`:
1. **Fases Incrementales y Puntos de Control:** Se reestructuró la sección de implementación en 5 fases secuenciales estrictas (Fundaciones, Parseo/Verificación Offline, Ingesta/Bedrock, API Gateway, Integración E2E/FinOps) con criterios de salida explícitos por fase.
2. **Cero Decisiones en Modelos:** Se plasmaron los esquemas Pydantic v2 completos (`PageContent`, `BaseFactor`, `GarantiaFactor`, `CriterioEvaluacionFactor`, `MultaFactor`, `PlazoFactor`, `LicitacionAuditRecord`, `ExtractionResult`) con tipos estrictos, enums y validaciones.
3. **Pydantic-Settings v2:** Se añadió `pydantic-settings>=2.2.0` al plan de dependencias y se codificó la clase `Settings` con `SettingsConfigDict(env_prefix="APP_")`.
4. **Limpieza Residual de Titan/Embeddings:** Se eliminaron todas las referencias contradictorias a Titan y embeddings vectoriales de las secciones no funcionales.
5. **Armonización de Firma en `verify_citation`:** Se fijó uniformemente `Tuple[bool, Optional[str]]`.
6. **Contrato S3 y SQS en Ingestión:** Se documentó la convención `uploads/{licitacion_id}/{filename}` y el bloque de extracción de metadatos en `handler.py`.
7. **Matriz de Casos de Prueba Negativos:** Se incorporaron explícitamente escenarios de PDFs escaneados (< 50 caracteres), ligaduras Unicode (`fi`, `fl`, comillas curvas), y errores de timeout/throttling en Bedrock.
8. **Módulo de Constantes Regex:** Se centralizaron todas las expresiones regulares compiladas en `src/common/constants.py`.
