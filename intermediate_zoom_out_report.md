# Goldfish Review Report: Zoom Out Audit (Intermediate Synthesis)

**Target:** `D:\Proyectos\mercado-publico-rag-aws\docs\designs\pipeline-serverless-rag-mercado-publico.md` (`Lines 1..504`)  
**Standard Applied:** `zoom-out-standard.md`  
**Mode:** REVIEW  
**Report Target:** `intermediate_zoom_out_report.md`

---

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

---

## Severity Summary

* 🔴 **Blocker**: 0
* 🟡 **Major**: 3
* 🟢 **Nit**: 2

---

## Executive Summary & Stage Assessment

The document has undergone substantial positive refactoring following the Comprehension and Critic review stages:
1. **Critical Blocker Resolved**: The uncompressed Lambda layer ceiling (>250 MB from `lancedb` + `pyarrow`) was completely eliminated by adopting direct candidate page selection via PyMuPDF and regex heuristic filtering, feeding directly into Amazon Bedrock Claude 3.5 Haiku.
2. **Simplified Data Flow (YAGNI & Anti-Weeds)**: Removal of Titan embeddings and the intermediate S3 indexes bucket significantly reduced moving parts, cold start latency, and operational cost while maintaining alignment with the AWS Free Tier ($0 base cost).
3. **Resilience Improvements**: Introduction of the scanned PDF circuit-breaker (`ScannedPdfException`), Boto3 adaptive retries for HTTP 429 throttling, Unicode NFKD citation normalization, and DynamoDB TTL/S3 lifecycle policies represent sound architectural mitigations.

The remaining findings focus on eliminating lingering residual references from the retired vector architecture, tightening the lifecycle state machine between the API and SQS worker, and preventing state collisions in multi-document tender ingestion.

---

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Residual Stale References to Vector Embeddings and Titan Models - Severity: 🟡 Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 152-153`, `Lines 362-363`, `Lines 368-370` (Section 2, Section 8 Security & Performance)
* **Discrepancy Description**: Section 3 and Open Question Q1 explicitly established the elimination of vector embeddings and the Titan model in favor of regex-filtered candidate windows to Claude 3.5 Haiku. However, multiple sections retain obsolete vector terminology:
  * Line 152: "...permitiendo filtrar búsquedas vectoriales a subespacios de 3 a 5 páginas."
  * Line 362: "...y a la acción `bedrock:InvokeModel` sobre los modelos Titan y Claude 3.5 Haiku."
  * Line 368: "Tiempo de Ingesta Asíncrona (Write Path): Ingesta, chunking, embeddings y extracción paralela..."
  * Line 369: "Empleo de embeddings de 256 dimensiones y layers optimizados en arquitectura ARM64..."
* **Rationale & Recommendation**: These residual mentions cause specification drift and confusion during implementation. Purge all references to Titan embeddings, 256-dimension vectors, and vector searches across Sections 2, 8, and IAM permission policies.

---

### 2. State Machine Contract Drift & Upload Lifecycle Race Gap - Severity: 🟡 Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 227-250`, `Lines 353-355`, `Lines 456-463` (Section 5 API Contract, Section 7 Risks, Target 11 API Handler)
* **Discrepancy Description**:
  1. **Contract Drift**: Section 7 introduces `PARTIAL_SUCCESS` when the worker reaches the 165s timeout margin. However, Section 5 (`GET /licitaciones/{id}/status`) and Target 11 only specify `PROCESSING`, `READY`, and `FAILED`. A client polling the API will receive an unhandled status code upon a partial timeout.
  2. **Lifecycle Race Gap**: `POST /licitaciones/upload-url` generates an S3 presigned URL but does not initialize a record in DynamoDB. If the client immediately polls `GET /licitaciones/{id}/status` before S3 uploads complete or SQS triggers the worker, DynamoDB returns null/404, forcing client-side ambiguity between "non-existent tender" and "pending upload".
* **Rationale & Recommendation**:
  * Formalize the lifecycle states across the API contract and models: `PENDING_UPLOAD` $\rightarrow$ `PROCESSING` $\rightarrow$ `READY` | `PARTIAL_SUCCESS` | `FAILED`.
  * Have `POST /licitaciones/upload-url` create an initial DynamoDB item with `status: PENDING_UPLOAD` and TTL.
  * Ensure `GET /licitaciones/{id}/status` returns `PARTIAL_SUCCESS` with a list of extracted factors when timeout mitigation is triggered.

---

### 3. Multi-Document Factor Attribution and Overwrite Collisions - Severity: 🟡 Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 48-50`, `Lines 163-181`, `Lines 413-421` (Resolution Q2, Section 4 DynamoDB Model, Target 5 Pydantic Models)
* **Discrepancy Description**: Resolution Q2 specifies using DynamoDB `UpdateItem` on the `factors` map to allow both *Bases Administrativas* and *Bases Técnicas* to write under the same `licitacion_id`. However:
  * If both files contain sections matching common keywords (e.g. both files have criteria or penalty clauses), the worker processing the second file will overwrite the entire sub-map (e.g., `factors.criterios`) of the first file without provenance tracking.
  * The schema does not record which file contributed which factor or citation.
* **Rationale & Recommendation**:
  * In `src/common/models.py`, add a `source_file: str` attribute to each factor schema (`GarantiaFactor`, `CriterioFactor`, `MultaFactor`, `PlazoFactor`).
  * In the worker `UpdateItem` logic, use conditional expressions or granular updates (`SET factors.#f = :val`) only if the factor was newly identified, or append to a history/list if both documents define distinct aspects (e.g., administrative penalty vs technical SLA penalty).

---

### 4. Premature Concurrency Throttling Fallback Logic (YAGNI) - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 349-351`, `Lines 437-440` (Section 7 Bedrock Throttling, Target 8 Extractor)
* **Discrepancy Description**: Line 351 states: "Si persiste la saturación, el worker conmuta automáticamente a despacho secuencial." Implementing dynamic runtime concurrency downgrading within Lambda adds speculative control-flow complexity. The Boto3 SDK client configuration already specifies `mode: 'adaptive'` with 5 retries and exponential jitter, which natively throttles request rates to the Bedrock service quotas.
* **Rationale & Recommendation**: Rely on standard SDK adaptive retries and SQS backoff. Remove the requirement for dynamic switching to sequential execution in `extractor.py` to keep the Lambda worker lean and standard.

---

### 5. Redundant 500-Word Chunking Abstraction - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 143-151`, `Lines 424-428` (Section 2 Page-Aware Chunking, Target 6 Parser)
* **Discrepancy Description**: Section 2 describes slicing pages into chunks of 500 words. However, Candidate Selection (Section 3 and Target 7) operates directly at the page level, selecting 3–5 candidate pages (~1,500–2,500 tokens) marked with `<<<PAGE_REF:X>>>` to feed Claude 3.5 Haiku. Micro-chunking pages into 500-word blocks is an obsolete vestige of the vector pipeline that introduces unnecessary string manipulation in `parser.py`.
* **Rationale & Recommendation**: Simplify `PageContent` to contain raw page text indexed by `page_number`. Candidate selection can extract full or half pages directly without maintaining internal sub-chunk boundaries.

---

## Conclusion

The architecture is in an excellent, highly viable state. The transition from vector databases to direct candidate windowing solved the project's primary packaging and cost bottlenecks. Resolving the 3 Major points (stale vector cleanup, status state machine completeness, and multi-document attribution) will make the design completely production-ready for implementation.

