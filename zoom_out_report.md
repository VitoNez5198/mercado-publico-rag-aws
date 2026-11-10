# Goldfish Review Report: Zoom Out Audit

**Target:** `D:\Proyectos\mercado-publico-rag-aws\docs\designs\pipeline-serverless-rag-mercado-publico.md` (`Lines 1..457`)
**Standard Applied:** `zoom-out-standard.md`
**Mode:** REVIEW
**Report Target:** `zoom_out_report.md`

---

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

---

## Severity Summary

* 🔴 **Blocker**: 1
* 🟡 **Major**: 3
* 🟢 **Nit**: 2

---

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Hard Lambda Layer Size Ceiling with LanceDB & PyArrow - Severity: 🔴 Blocker
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 134-138`, `Lines 347-348`, `Lines 357-360` (Section 2 & Detailed Implementation Plan Targets 1, 3)
* **Discrepancy Description**: The plan defines `IngestionFunction` as a standard AWS Lambda zip package with layers containing `PyMuPDF`, `lancedb`, and `pyarrow` on Python 3.12 (ARM64). AWS Lambda has an uncompressed limit of 250 MB for code plus layers. Precompiled `pyarrow` wheels for Linux ARM64 alone require ~180–220 MB uncompressed, which when combined with `PyMuPDF` (~45 MB) and `lancedb` exceeds or critically approaches the 250 MB ceiling, causing `sam deploy` failures (`Uncompressed image size too large`).
* **Rationale & Recommendation**: Either:
  1. *(Recommended - see Finding #2)* Eliminate `lancedb` and `pyarrow` entirely from the ingestion worker; OR
  2. If an embedded vector store is strictly required, switch `IngestionFunction` in `template.yaml` from Zip deployment to Container Image (`PackageType: Image` built from an Amazon ECR base image), which supports up to 10 GB.

---

### 2. Architectural Over-Engineering: Redundant In-Memory Vector Store vs. Direct Candidate Extraction - Severity: 🟡 Major
* **Reviewer Lens:** `egm-zoom-out` / `egm-inventive-catalyst`
* **Affected Scope:** `Lines 108-115`, `Lines 149-155`, `Lines 382-388` (Architecture Diagram, Section 3, and Target 7 `src/ingestion/indexer.py`)
* **Discrepancy Description**: Section 2 (lines 147–148) already introduces heuristic regex scanning that filters documents down to 3–5 candidate pages per critical factor. Despite this, the pipeline generates 256-dimension Bedrock Titan embeddings for every single chunk, creates a local `.lance` index in `/tmp`, uploads it to S3, and queries it back. Building a full vector index for a single document triage is premature optimization (violating Zoom Out Standard Section 2: Simplicity & Extensibility / YAGNI).
* **Rationale & Recommendation**:
  * *Inventive Contradiction Resolution*: Claude 3.5 Haiku features a 200,000-token context window at $0.80/M input tokens. A 3–5 page filtered window is only ~1,500–3,000 tokens ($0.0024 USD).
  * Passing candidate pages directly to Claude 3.5 Haiku eliminates:
    1. Bedrock Titan Embeddings roundtrips (~100 calls per document).
    2. LanceDB and PyArrow dependencies.
    3. `S3BucketIndexes` infrastructure.
    4. ~30 seconds of cold start and processing latency.
  * Simplify the data flow: S3 PDF $\rightarrow$ PyMuPDF page parsing $\rightarrow$ Regex candidate page selector $\rightarrow$ 4 parallel Bedrock Claude 3.5 Haiku calls $\rightarrow$ Substring verification $\rightarrow$ DynamoDB.

---

### 3. State Overwrite on Multi-Document Tenders (Open Question Q2 Unresolved) - Severity: 🟡 Major
* **Reviewer Lens:** `egm-zoom-out` / `egm-inventive-catalyst`
* **Affected Scope:** `Lines 40-42`, `Lines 156-211` (Open Question Q2 & Section 4 Data Model)
* **Discrepancy Description**: In Mercado Público, the vast majority of tenders publish two distinct PDF files: *Bases Administrativas* (garantías, multas, plazos) and *Bases Técnicas* (criterios de evaluación). In the proposed DynamoDB schema, the Partition Key is `licitacion_id`. If a user uploads both PDFs, the second S3 event triggers an independent worker run that completely overwrites the DynamoDB item, erasing the previously extracted factors.
* **Rationale & Recommendation**: Resolve Q2 structurally before implementation:
  * Model DynamoDB with either:
    * A Composite Key (`PK: licitacion_id`, `SK: document_id`); OR
    * Use atomic partial updates (`UpdateItem` with `SET factors.#k = :val`) and an `uploaded_documents` set, aggregating factors across multiple files without race overwrites.

---

### 4. Storage Lifecycle Gaps in Indexes Bucket and DynamoDB Table - Severity: 🟡 Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 149-155`, `Lines 343-352` (Section 3 and Target 1 `template.yaml`)
* **Discrepancy Description**: While `S3BucketUploads` specifies an expiration rule (`ExpirationInDays: 30`), `S3BucketIndexes` has no lifecycle configuration, and DynamoDB `TenderAnalysisTable` lacks Time-To-Live (TTL). Over weeks and months, orphaned index files and DynamoDB records will continuously accumulate, eventually exceeding the AWS Free Tier storage allocation and violating Goal G3 ($0 USD base cost).
* **Rationale & Recommendation**:
  * If `S3BucketIndexes` is retained, add an explicit 30-day lifecycle rule.
  * Add `TimeToLiveSpecification: { AttributeName: "ttl", Enabled: true }` to `TenderAnalysisTable`, setting `ttl = created_at + 30 days` upon item creation.

---

### 5. Brittle Substring Verification on PDF Ligatures & Character Encodings - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `Lines 246-254`, `Lines 396-402` (Section 6 & Target 9 `src/ingestion/verifier.py`)
* **Discrepancy Description**: `verify_citation` relies on strict Python membership (`clean_quote in clean_page`). Standard PDF extraction via PyMuPDF frequently produces ligatures (e.g., `fi`, `fl`), non-breaking spaces (`\xa0`), and typographic curly quotes (`“`, `”`). An LLM copying verbatim text will often output ASCII quotes or expanded ligatures, causing false-negative verification failures (`verificado_en_pagina: false`) despite the excerpt being accurate.
* **Rationale & Recommendation**: Normalize both strings using `unicodedata.normalize('NFKD', text)` and replace typographic punctuation before testing substring containment, with a fallback fuzzy similarity threshold (`difflib.SequenceMatcher > 0.95`).

---

### 6. SQS Visibility Timeout Safety Margin for Edge-Case Pliegos - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 130-136` (Section 2 Flujo de Ingesta)
* **Discrepancy Description**: Lambda timeout is set to 180s and SQS visibility timeout to 300s. If an exceptionally long or complex pliego (180 pages with heavy tables) hits the 180s Lambda timeout, SQS will immediately redrive up to 3 times, tripling token consumption and Bedrock costs before landing in DLQ.
* **Rationale & Recommendation**: With Finding #2 implemented (eliminating vector embedding overhead), execution time will be well under 45s. If vectorization is kept, implement an explicit early timeout handler in Lambda at $T - 15$ seconds that checkpoints progress to avoid wasteful SQS re-executions.

---

## Conclusion & Recommended Next Step
The architecture is fundamentally sound, event-driven, and well-aligned with AWS Free Tier economics. Resolving the packaging constraint (Finding #1) and adopting direct candidate windowing instead of premature in-Lambda LanceDB indexing (Finding #2) will cut complexity, remove the largest failure mode, and ensure immediate deployment success.

