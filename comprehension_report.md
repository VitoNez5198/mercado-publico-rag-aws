# Comprehension Review Report

**Target:** `D:\Proyectos\mercado-publico-rag-aws\docs\designs\pipeline-serverless-rag-mercado-publico.md`
**Mode:** REVIEW

---

### What this proposes

This document proposes an event-driven, zero-fixed-cost serverless architecture on AWS to automate the extraction and verification of four critical tender factors—guarantees, evaluation criteria, fines, and deadlines—from Chilean public procurement PDFs (30–180 pages) uploaded by SMEs. Ingestion is decoupled via Amazon S3, SQS, and an AWS Lambda worker running PyMuPDF that performs page-bounded chunking and embeds chunks with Amazon Bedrock Titan Text V2 into an ephemeral LanceDB index saved to S3. Parallel Bedrock Claude 3.5 Haiku invocations extract factor values along with exact source quotes, which are deterministically validated via page substring matching before being written to DynamoDB and served via an HTTP API Gateway in under 200 ms.

### How the existing system works, per this document

Per the document, SMEs currently review 30- to 180-page Chilean public procurement tender documents manually, expending 3 to 5 hours of key staff time per pliego to identify critical legal, financial, and administrative requirements. Generic commercial conversational AI tools hallucinate page numbers, invent fine clauses, or confuse contract terms, creating severe legal and financial risks for bidders such as immediate inadmissibility or forfeiture of bid guarantee bonds. Furthermore, conventional AWS RAG architectures require persistent vector search services such as Amazon OpenSearch Serverless, which incur a prohibitive minimum baseline cost of approximately $175 USD/month that exceeds SME and early-stage budgets.

---

### Findings

#### 1. Undefined Chilean Public Procurement Terms and Monetary Acronyms - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** Lines 11-21, Lines 176-194, and Line 295
* **Discrepancy Description & Rationale**:
  The document assumes institutional knowledge of Chilean procurement law and economic indices without inline definitions or links:
  - **`Mercado Público` & `Ley N° 19.886`**: Mentioned without clarifying that Ley 19.886 is the statutory basis governing administrative supply and service contracts with the State of Chile.
  - **`glosa exacta` & `boleta de seriedad` / `fiel cumplimiento`**: "Glosa" is specific procurement jargon referring to mandatory verbatim text required on bank guarantees; "boleta de seriedad" (bid bond) and "fiel cumplimiento" (performance bond) are mentioned without clarifying their legal function or why omission causes inadmissibility.
  - **`UF` (Unidad de Fomento) & `UTM` (Unidad Tributaria Mensual)**: Standard Chilean indexed accounting units used for contractual guarantees and daily fines, respectively. A reader outside Chile cannot determine whether these are currencies, fixed fees, or indexation units without definition.

#### 2. Undefined Vector Retrieval Query Mechanism for Factor Extraction - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** Lines 110-113, Lines 147-154, and Lines 387-394
* **Discrepancy Description & Rationale**:
  Section 2 states that regex tags chunks with `section_type`, Section 3 states that an index is built in LanceDB, and Section 1/Detailed Plan indicates 4 parallel Bedrock calls. However, the retrieval step connecting LanceDB to Bedrock Haiku is undefined:
  - If chunks are already tagged by regex (`section_type="garantias"`), does the Lambda pass all regex-tagged chunks directly to the LLM, or does it issue an embedded vector query against LanceDB?
  - If it queries LanceDB, what are the canonical query strings/embeddings used to search for each of the 4 factors?
  - The document leaves the RAG context selection step ambiguous between pure metadata filtering and semantic vector search (directly echoing Zoom Out Finding #2).

#### 3. Unhandled Failure State in DynamoDB on Scanned PDFs - Severity: Major
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** Line 34, Line 379, and Lines 406-408
* **Discrepancy Description & Rationale**:
  NG2 states that scanned PDFs with non-extractable text trigger an early alert, and line 379 specifies throwing `ScannedPdfException` when character density is < 50 chars/page. However, in the SQS event handler flow, raising an uncaught exception triggers SQS retries (up to 3 times) before transferring the message to the DLQ. The document does not specify whether the worker catches `ScannedPdfException` to update DynamoDB status to `FAILED` with an actionable error code (e.g., `SCANNED_PDF_UNSUPPORTED`), leaving the client querying `GET /licitaciones/{id}/status` stuck in `PROCESSING` until SQS retries exhaust.

#### 4. Route Contract Inconsistency between Architecture Diagram and API Spec - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** Line 102 vs. Line 215, Line 349, and Line 413
* **Discrepancy Description & Rationale**:
  The Mermaid diagram in Section 1 labels Step 1 as `POST /licitaciones/presigned-url`, whereas Section 5 (API Contract), Section Target File 1 (`template.yaml`), and Section Target File 11 define the endpoint as `POST /licitaciones/upload-url`. The route naming should be unified across the document.

#### 5. Data Contract Semantics When Citation Verification Fails - Severity: Nit
* **Reviewer Lens:** `egm-comprehension`
* **Affected Scope:** Lines 247-255 and Lines 173-209
* **Discrepancy Description & Rationale**:
  Line 254 notes that if substring verification fails, `verificado_en_pagina` is set to `false`, "preventing the system from reporting spurious citations to the SME." However, the schema in Section 4 displays all extracted fields (`monto`, `vigencia`, etc.) populated alongside `verificado_en_pagina: true`. The document does not state whether a verification failure suppresses the extracted factor values, clears `fragmento_exacto`, or retains the extracted values while presenting an unverified warning flag.

