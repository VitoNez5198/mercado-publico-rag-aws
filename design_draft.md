# Pipeline Serverless en AWS para Análisis RAG de Licitaciones de Mercado Público

* **Author:** VitoNez5198
* **Status:** Draft
* **Date:** 2026-11-10

--------------------------------------------------------------------------------

## Overview

Este documento especifica el diseño técnico de una solución en la nube (AWS) orientada a eventos para la extracción automatizada y auditoría de factores críticos en bases de licitación de Mercado Público (Chile, Ley N° 19.886). La solución está dirigida a pequeñas y medianas empresas (PYMEs) que participan como proveedoras del Estado y requieren evaluar la viabilidad legal y financiera de pliegos de licitación de 30 a 180 páginas en minutos en lugar de horas.

El sistema recibe documentos en formato PDF mediante Amazon S3, procesa el texto delimitado por página a través de AWS Lambda y almacena representaciones vectoriales en una base serverless sin costos fijos. Mediante técnicas de Retrieval-Augmented Generation (RAG) acotadas por metadatos, extrae garantías, criterios de ponderación, multas y plazos con citas textuales verificables y número de página exacto, operando bajo el régimen de Capa Gratuita (Free Tier) de AWS.

## The Problem

Las PYMEs que licitan con el Estado chileno enfrentan barreras operativas significativas:
1. **Asimetría de Recursos:** Las grandes empresas cuentan con departamentos jurídicos dedicados a desmenuzar las bases de licitación. Una PYME promedio destina de 3 a 5 horas de personal clave para revisar un único pliego licitatorio.
2. **Riesgo de Inadmisibilidad y Pérdida Patrimonial:** Un error común (como no adjuntar la boleta de garantía con la glosa exacta exigida o interpretar erróneamente un plazo de días corridos versus días hábiles) provoca la descalificación inmediata de la oferta o la pérdida de la boleta de seriedad.
3. **Alucinaciones en Herramientas Genéricas de IA:** El uso de herramientas estándar de IA conversacional (chatbots abiertos) sin anclaje determinista genera números de página ficticios o inventa causales de multas inexistentes en el texto original, aumentando el riesgo legal para el oferente.
4. **Barrera de Costos Cloud:** La mayoría de las arquitecturas empresariales de RAG en AWS implementan clústeres como OpenSearch Serverless (~$175 USD/mes mínimo), lo cual resulta inviable para una PYME o un desarrollador en etapa temprana.

## Goals

* **G1 - Automatización de Triage:** Reducir el tiempo de extracción inicial de los 4 factores críticos de una licitación de 4 horas a menos de 90 segundos.
* **G2 - Cero Alucinación de Citas:** Proveer citas textuales exactas acompañadas de su número de página verificado contra el documento original mediante comprobación estricta de subcadenas antes de responder al usuario.
* **G3 - Sostenibilidad Presupuestaria (Free Tier First):** La arquitectura debe operar con costo base de $0 USD mensuales en infraestructura fija, soportando hasta 100 documentos mensuales bajo el nivel gratuito de AWS (S3, Lambda, SQS, DynamoDB, HTTP API) y un costo de inferencia inferior a $0.002 USD por licitación procesada.
* **G4 - Desacoplamiento Asíncrono Resiliente:** Eliminar caídas por timeouts HTTP mediante procesamiento en segundo plano con colas SQS y Dead-Letter Queue (DLQ).
* **G5 - Observabilidad FinOps Operativa:** Medir en Amazon CloudWatch la latencia de ingestión, la duración de inferencia y el costo estimado en dólares por documento analizado.

## Non-Goals

* **NG1 - Scraping Masivo del Portal:** No se descargará de forma automatizada o masiva el catálogo completo de licitaciones de Mercado Público. El sistema opera bajo demanda ante la carga explícita de un documento por parte del usuario.
* **NG2 - Reconocimiento Óptico de Caracteres Pesado (OCR):** No se procesarán en esta versión inicial PDFs que contengan únicamente imágenes escaneadas sin capa de texto incrustada. Si un archivo carece de texto extraíble nativo, se emitirá una alerta temprana de formato no soportado.
* **NG3 - Asesoría Legal Vinculante:** El software es un asistente de extracción y triage documental; no emite juicios de valor legal ni garantiza la adjudicación de una licitación.
* **NG4 - Interacción con la Plataforma Transaccional:** El sistema no enviará ofertas, no firmará documentos ni interactuará con las credenciales de usuario dentro del portal Mercado Público.

## Open Questions

* **Q1:** ¿Qué mecanismo de almacenamiento vectorial local en `/tmp` de Lambda ofrece la mejor relación velocidad/tamaño de empaquetado: LanceDB o FAISS CPU ligero?
* **Q2:** ¿Cómo manejar licitaciones que dividen sus requisitos en dos archivos separados (Bases Administrativas y Bases Técnicas) manteniendo la correlación en la misma sesión de análisis?

## Critical User Journeys (CUJs)

### CUJ 1: Subida de Pliego y Procesamiento Desacoplado
* **Given**: Un usuario de la PYME tiene el archivo PDF oficial de las bases de una licitación de 80 páginas.
* **When**: El usuario solicita una URL prefirmada de subida a Amazon S3 y transfiere el archivo.
* **Then**: S3 emite un evento `ObjectCreated` a una cola SQS. Una función AWS Lambda toma el mensaje, segmenta el documento por páginas usando PyMuPDF, extrae los fragmentos, persiste los embeddings vectoriales en almacenamiento serverless, calcula los 4 factores en paralelo mediante Amazon Bedrock, persiste el resultado en DynamoDB y marca el estado como `READY`.

### CUJ 2: Auditoría y Verificación de Citas por la PYME
* **Given**: La licitación `LIC-2026-001` ha completado su procesamiento asíncrono.
* **When**: El usuario consulta el endpoint `GET /licitaciones/LIC-2026-001/factores`.
* **Then**: La API retorna un JSON estructurado con los 4 factores en menos de 200 ms desde la caché de DynamoDB. Cada factor expone el valor extraído (ej. monto de garantía, días de entrega), el número de página del PDF y el fragmento textual exacto validado mediante subcadena.

--------------------------------------------------------------------------------

## Technical Plan (Architecture)

### 1. Diagrama de Arquitectura Global

```mermaid
flowchart TD
    subgraph Client [Cliente PYME / Frontend Web]
        UI[Portal de Carga y Auditoría]
    end

    subgraph AWS_Cloud [Nube AWS - Arquitectura Serverless]
        subgraph Storage [Capa de Almacenamiento]
            S3_Uploads[S3 Bucket: uploads/]
            S3_Indexes[S3 Bucket: indexes/]
        end

        subgraph Event_Decoupling [Desacoplamiento de Eventos]
            SQS_Queue[Amazon SQS: IngestionQueue]
            SQS_DLQ[Amazon SQS: DeadLetterQueue]
        end

        subgraph Ingestion_Engine [Motor de Ingesta y Vectorización]
            Lambda_Ingest[Lambda: Ingestion & Pre-Extraction Worker]
            Bedrock_Embed[Bedrock: Titan Text Embeddings V2]
        end

        subgraph Database [Estado y Caché]
            DDB[Amazon DynamoDB: TenderAnalysis]
        end

        subgraph API_Layer [Capa de Exposición API]
            APIGW[API Gateway: HTTP API]
            Lambda_API[Lambda: API Handler]
        end

        subgraph LLM_Inference [Extracción de Factores Críticos]
            Bedrock_LLM[Amazon Bedrock: Claude 3.5 Haiku]
        end

        subgraph FinOps [Observabilidad y Control de Gastos]
            CloudWatch[CloudWatch Metrics & Logs]
            Budgets[AWS Budgets: Alerta $1.00 USD]
        end
    end

    UI -->|1. POST /licitaciones/presigned-url| APIGW
    APIGW --> Lambda_API
    Lambda_API -->|Retorna Presigned URL S3| UI
    UI -->|2. PUT directo de PDF| S3_Uploads
    S3_Uploads -->|3. Evento s3:ObjectCreated| SQS_Queue
    SQS_Queue -.->|Fallo tras 3 reintentos| SQS_DLQ
    SQS_Queue -->|4. Trigger batch=1| Lambda_Ingest
    Lambda_Ingest -->|5. Extrae páginas PyMuPDF| Lambda_Ingest
    Lambda_Ingest -->|6. Genera Embeddings 256d| Bedrock_Embed
    Lambda_Ingest -->|7. Persiste índice .lance| S3_Indexes
    Lambda_Ingest -->|8. Invoca 4 llamadas paralelas| Bedrock_LLM
    Bedrock_LLM -->|9. Retorna JSON estructurado + citas| Lambda_Ingest
    Lambda_Ingest -->|10. Verificación Subcadena assert| Lambda_Ingest
    Lambda_Ingest -->|11. Guarda factores y status READY| DDB
    Lambda_Ingest -->|12. Emite métricas latencia/costo| CloudWatch
    CloudWatch -.-> Budgets

    UI -->|13. GET /licitaciones/{id}/factores| APIGW
    APIGW --> Lambda_API
    Lambda_API -->|14. Lectura directa en < 200ms| DDB
    Lambda_API -->|15. Retorna reporte con citas| UI
```

### 2. Flujo de Ingesta Orientado a Eventos y Chunking por Página

El procesamiento de documentos se ejecuta de forma 100% asíncrona para no comprometer tiempos de respuesta HTTP:

1. **Subida Directa a S3:** El cliente solicita a la API una URL prefirmada (`s3:PutObject`) con tiempo de expiración de 15 minutos y restricción de tipo MIME `application/pdf`. La transferencia del archivo viaja directo del navegador al bucket S3 sin pasar por memoria de cómputo intermedia.
2. **Desacoplamiento con SQS:** Amazon S3 emite un evento `s3:ObjectCreated:*` hacia una cola de mensajería `Amazon SQS`. La cola está configurada con:
   * `VisibilityTimeout`: 300 segundos.
   * `MessageRetentionPeriod`: 4 días.
   * `RedrivePolicy`: Máximo 3 intentos antes de enviar el mensaje a `DeadLetterQueue` (DLQ) para análisis de fallos.
3. **Procesamiento en Lambda (`Ingestion Worker`):**
   * **Runtime:** Python 3.12 con arquitectura ARM64 (AWS Graviton2, 20% más económica y rápida).
   * **Memoria:** 1024 MB y timeout de 180 segundos.
   * **Parser Ligero:** Empaquetado de `PyMuPDF` (`fitz`) en Lambda Layer (< 45 MB).
   * **Page-Aware Chunking:** Cada página se divide en fragmentos de máximo 500 palabras respetando los saltos de párrafo, asociando metadatos inmutables:
     ```json
     {
       "doc_id": "LIC-2026-001",
       "page_number": 14,
       "chunk_id": "LIC-2026-001_p14_c1",
       "section_type": "garantias"
     }
     ```
   * **Clasificación Heurística de Encabezados (Regex):** Durante el escaneo de texto plano, expresiones regulares identifican patrones estándar de Mercado Público (ej. `r"(?i)(garant[ií]a|seriedad de la oferta|fiel cumplimiento)"`, `r"(?i)(criterios? de evaluaci[oó]n|ponderaci[oó]n)"`, `r"(?i)(multas?|sanciones?|atraso)"`, `r"(?i)(plazos?|fechas? fatales?|calendario)"`). Esto añade el metadato `section_type` a los fragmentos de esas páginas, permitiendo filtrar búsquedas vectoriales a subespacios de 3 a 5 páginas.

### 3. Almacenamiento Vectorial Serverless sin Costos Fijos

Para evitar clústeres costosos como OpenSearch Serverless, la solución implementa **Vector Store Embebido con Persistencia en S3**:
* Durante la ingesta, Lambda genera embeddings de 256 dimensiones con `amazon.titan-embed-text-v2:0` (reducción de dimensión que ahorra 75% de almacenamiento y memoria RAM manteniendo >97% de precisión semántica).
* El índice vectorial se compila en memoria local mediante `LanceDB` y se exporta como archivo compacto (`s3://licitaciones-indexes/{licitacion_id}.lance`).
* En futuras consultas vectoriales ad-hoc, la Lambda descarga el índice de ~2-4 MB a `/tmp` (ephemeral storage gratuito de 512 MB) en menos de 80 ms y ejecuta búsquedas locales por similitud de coseno en memoria.

### 4. Modelo de Datos en Amazon DynamoDB (`TenderAnalysis`)

Tabla única con facturación On-Demand (Free Tier: 25 RCU/WCU aprovisionadas o modo pago por uso).

* **Partition Key (PK):** `licitacion_id` (String, ej. `"LIC-708-12-LR26"`).
* **Atributos:**
  ```json
  {
    "licitacion_id": "LIC-708-12-LR26",
    "status": "READY",
    "created_at": "2026-11-10T14:30:00Z",
    "updated_at": "2026-11-10T14:31:15Z",
    "file_name": "Bases_Licitacion_708.pdf",
    "total_pages": 78,
    "cost_usd_estimate": 0.0018,
    "processing_time_ms": 74500,
    "factors": {
      "garantias": {
        "identificado": true,
        "tipo_garantia": "Seriedad de la Oferta",
        "monto": "50 UF",
        "vigencia": "60 días corridos contados desde la apertura de ofertas",
        "pagina_citada": 12,
        "fragmento_exacto": "La garantía de seriedad de la oferta deberá ser por un monto de 50 UF con vigencia mínima de 60 días corridos...",
        "verificado_en_pagina": true
      },
      "criterios": {
        "identificado": true,
        "ponderacion_tecnica": "60%",
        "ponderacion_economica": "40%",
        "puntaje_minimo_descalificatorio": "50 puntos técnicos",
        "pagina_citada": 35,
        "fragmento_exacto": "Criterio Técnico (60%): Experiencia 40%, Metodología 20%. Criterio Económico (40%): Menor precio ofertado.",
        "verificado_en_pagina": true
      },
      "multas": {
        "identificado": true,
        "causal_principal": "Atraso en entrega de informes",
        "monto_diario": "2 UTM por día hábil de atraso",
        "tope_maximo": "15% del valor total del contrato",
        "pagina_citada": 54,
        "fragmento_exacto": "Se aplicará una multa de 2 UTM por cada día hábil de atraso, con un tope máximo del 15% del total del contrato...",
        "verificado_en_pagina": true
      },
      "plazos": {
        "identificado": true,
        "cierre_ofertas": "25 de Noviembre de 2026 a las 15:00 hrs",
        "tipo_computo": "Días corridos para entrega; días hábiles administrativos para aclaraciones",
        "plazo_entrega": "45 días corridos",
        "pagina_citada": 8,
        "fragmento_exacto": "El plazo de entrega de los suministros será de 45 días corridos a partir de la notificación de la orden de compra...",
        "verificado_en_pagina": true
      }
    }
  }
  ```

### 5. Contrato de API (Amazon API Gateway HTTP API)

* **`POST /licitaciones/upload-url`**
  * *Request Body:* `{"file_name": "bases.pdf", "file_size_bytes": 14500000}`
  * *Response (200 OK):*
    ```json
    {
      "licitacion_id": "LIC-708-12-LR26",
      "upload_url": "https://licitaciones-inbox.s3.amazonaws.com/LIC-708-12-LR26/bases.pdf?AWSAccessKeyId=...",
      "expires_in_seconds": 900
    }
    ```
* **`GET /licitaciones/{id}/status`**
  * *Response (200 OK):*
    ```json
    {
      "licitacion_id": "LIC-708-12-LR26",
      "status": "PROCESSING",
      "progress_percent": 65
    }
    ```
* **`GET /licitaciones/{id}/factores`**
  * *Response (200 OK - Latencia < 200 ms):* Retorna el objeto `factors` de DynamoDB con las citas y estados de verificación de subcadena.

### 6. Motor de Inferencia LLM y Verificación Determinista de Subcadenas

* **Modelo:** Anthropic Claude 3.5 Haiku en Amazon Bedrock (`anthropic.claude-3-5-haiku-20241022-v1:0`).
* **Prompting con Marcadores Canónicos:**
  ```text
  Eres un auditor técnico de compras públicas chilenas. Analiza los siguientes fragmentos etiquetados por página:
  <<<PAGE_REF:12>>> [Texto del chunk] <<<END_PAGE_REF:12>>>
  Extrae el factor solicitado en formato JSON estricto. Incluye obligatoriamente el número de página de donde extrajiste la información y el fragmento textual EXACTO (copiado y pegado, carácter por carácter).
  ```
* **Mecanismo Antialucinación (Python Assertion en Lambda):**
  ```python
  def verify_citation(page_number: int, exact_quote: str, page_texts: dict) -> bool:
      target_page = page_texts.get(page_number, "")
      clean_quote = " ".join(exact_quote.strip().split())
      clean_page = " ".join(target_page.strip().split())
      return clean_quote in clean_page
  ```
  Si la subcadena no existe en esa página, `verificado_en_pagina` se establece en `false`, impidiendo que el sistema reporte citas espurias a la PYME.

### 7. Observabilidad FinOps y Alarmas de Costo

* **CloudWatch Custom Metrics:**
  * `TenderIngestionDurationMs`: Alarma si `p90 > 120000 ms`.
  * `TokensBedrockInput` y `TokensBedrockOutput`: Para cálculo en tiempo real de consumo en USD.
  * `CitationVerificationFailures`: Conteo de alucinaciones interceptadas.
* **Alarma de Facturación (AWS Budgets):**
  * Límite estricto: **$1.00 USD** de gasto mensual acumulado.
  * Acción: Notificación inmediata vía Amazon SNS al correo del desarrollador.

--------------------------------------------------------------------------------

## Alternatives Considered

### Alternative A: Almacenamiento Vectorial con Amazon OpenSearch Serverless

* **Pros:**
  * Integración nativa directa con Amazon Bedrock Knowledge Bases.
  * No requiere gestión de archivos de índice en S3 ni montaje en memoria local.
* **Cons:**
  * No tiene capa gratuita (Free Tier).
  * La unidad mínima de cómputo (1 OCU de indexación + 1 OCU de búsqueda) genera un costo base fijo de aproximadamente $175 USD al mes, incluso con tráfico cero.
* **Reason for Rejection:** `Rejected by author: Costo mensual prohibitivo (~$175 USD/mes) sin capa gratuita en AWS, lo que viola el objetivo G3 de operar con costo base de $0 USD mensuales.`

### Alternative B: Procesamiento Síncrono Directo a través de API Gateway

* **Pros:**
  * Flujo conceptual más simple sin necesidad de cola SQS ni persistencia intermedia de estados en DynamoDB.
  * Menor cantidad de recursos de infraestructura que declarar en plantillas IaC.
* **Cons:**
  * Límite duro de timeout no modificable de 29 segundos en Amazon API Gateway (tanto HTTP como REST APIs).
  * Procesar un PDF de 80 a 150 páginas (extracción de texto, generación de embeddings y llamadas a Bedrock) toma típicamente entre 45 y 90 segundos, lo que genera errores HTTP 504 Gateway Timeout constantes.
* **Reason for Rejection:** `Rejected by author: Inviable ante el límite duro de timeout de 29 segundos en API Gateway al procesar pliegos extensos de compras públicas.`

### Alternative C: RAG Conversacional de Pregunta Abierta (Chatbot Genérico)

* **Pros:**
  * Máxima libertad para que el usuario escriba cualquier consulta en lenguaje natural.
* **Cons:**
  * Alta tasa de alucinaciones en datos numéricos contractuales sensibles (confusión de multas en UTM vs UF, invención de plazos o números de página).
  * Exige que el usuario sepa exactamente qué preguntar en lugar de obtener un resumen estructurado estandarizado de los 4 factores de riesgo.
  * Mayor consumo de tokens y latencia acumulada por múltiples turnos conversacionales.
* **Reason for Rejection:** `Rejected by author: Riesgo inaceptable de alucinación legal y fatiga operativa para la PYME; se reemplazó por extracción estructurada dirigida a los 4 factores críticos con citas verificadas.`

### Alternative D: Base de Datos Relacional Gestionada con Extensión pgvector (Amazon Aurora / RDS)

* **Pros:**
  * Consultas SQL combinadas con filtros vectoriales nativos en una sola base de datos.
* **Cons:**
  * Amazon Aurora Serverless v2 no dispone de nivel gratuito permanente (costo base de ~0.5 ACU = ~$43 USD/mes mínimo).
  * RDS PostgreSQL bajo Free Tier (db.t3.micro/db.t4g.micro) expira a los 12 meses y sufre degradación severa de memoria al indexar embeddings multidimensionales.
* **Reason for Rejection:** `Rejected by author: Genera costos fijos mensuales en AWS sin capa gratuita permanente y sobrecarga el presupuesto operativo del proyecto.`

--------------------------------------------------------------------------------

## Non-Functional Requirements

### Security & Privacy
* **Principio de Mínimo Privilegio (IAM):** Las funciones Lambda poseen roles dedicados de ejecución con permisos restringidos exclusivamente a sus buckets S3 específicos (`arn:aws:s3:::licitaciones-*/*`), su cola SQS, su tabla DynamoDB y a la acción `bedrock:InvokeModel` sobre los modelos Titan y Claude 3.5 Haiku.
* **Aislamiento de Carga:** Los archivos PDF subidos a S3 cuentan con cifrado en reposo del lado del servidor (`SSE-S3 / AES-256`) y políticas de acceso bloqueando cualquier acceso público (`BlockPublicAccess: true`).
* **Presigned URLs con Expiración Breve:** Las URLs de carga se emiten con tiempo de expiración estricto de 15 minutos (900 segundos).

### Performance & Latency
* **Tasa de Respuesta en Consulta (Read Path):** El endpoint de consulta de factores `GET /licitaciones/{id}/factores` responde en menos de 200 milisegundos en el percentil 95 (p95), sirviendo datos precalculados desde DynamoDB.
* **Tiempo de Ingesta Asíncrona (Write Path):** Ingesta, chunking, embeddings y extracción paralela de los 4 factores para documentos de 100 páginas en menos de 90 segundos.
* **Optimización de Memoria en Lambda:** Empleo de embeddings de 256 dimensiones y layers optimizados en arquitectura ARM64 Graviton2 para evitar desbordamiento de memoria en la cuota gratuita de cómputo.

### Rollout & Rollback
* **Infraestructura como Código (IaC):** Despliegue automatizado y reproducible mediante AWS SAM (`template.yaml`).
* **Estrategia de Rollback:** En caso de fallas durante el despliegue del stack SAM (`sam deploy`), CloudFormation ejecuta rollback automático al último estado estable sin interrumpir el bucket de almacenamiento de datos.

--------------------------------------------------------------------------------

### Future Improvements

* **Soporte OCR Nativo con AWS Textract:** Incorporar una rama de procesamiento condicional en la ingesta que detecte PDFs escaneados (densidad de caracteres < 50) y despache las páginas críticas a AWS Textract de forma asíncrona.
* **Extracción de Tablas Complejas con Estructura HTML/Markdown:** Integrar parsers especializados para bases que utilicen matrices de ponderación de múltiples niveles anidadas en tablas.
* **Exportación Automatizada a Hoja de Resumen (Excel/PDF):** Endpoint que genere una ficha ejecutiva de evaluación de 1 página para el comité de compras de la PYME.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

#### 1. `template.yaml` (Create)
* **Type / Scope**: AWS Serverless Application Model (SAM) Infrastructure as Code.
* **Proposed Changes**: Declaración completa de recursos serverless:
  * `S3BucketUploads`: Bucket S3 para ingesta con ciclo de vida de 30 días (`ExpirationInDays: 30`) y bloqueo de acceso público.
  * `S3BucketIndexes`: Bucket S3 para artefactos `.lance`.
  * `IngestionQueue` & `IngestionDLQ`: Cola SQS con Dead-Letter Queue tras 3 reintentos y tiempo de visibilidad de 300 segundos.
  * `IngestionFunction`: AWS Lambda (Python 3.12, ARM64 Graviton2, 1024 MB RAM, timeout 180s) conectada al trigger de SQS.
  * `ApiFunction`: AWS Lambda (Python 3.12, ARM64, 512 MB RAM, timeout 15s) conectada a HTTP API Gateway.
  * `HttpApi`: Amazon API Gateway v2 con rutas `POST /licitaciones/upload-url`, `GET /licitaciones/{id}/status` y `GET /licitaciones/{id}/factores`.
  * `TenderAnalysisTable`: Tabla DynamoDB con Partition Key `licitacion_id` (String) y modo On-Demand.
  * `BudgetsAlarm`: Alarma de presupuesto de $1.00 USD con tópico SNS.

#### 2. `samconfig.toml` (Create)
* **Type / Scope**: Configuración de despliegue SAM CLI.
* **Proposed Changes**: Parámetros preconfigurados para `sam build` y `sam deploy --guided` en la región `us-east-1`, habilitando resolución de dependencias por contenedor y nombres de stack reproducibles.

#### 3. `requirements.txt` (Create)
* **Type / Scope**: Manifiesto de dependencias de Python para desarrollo y empaquetado.
* **Proposed Changes**: Dependencias fijadas: `boto3>=1.34.0`, `PyMuPDF>=1.23.0`, `pydantic>=2.6.0`, `lancedb>=0.5.0`, `pyarrow>=14.0.0`, `pytest>=8.0.0`, `pytest-mock>=3.12.0`, `ruff>=0.3.0`.

#### 4. `src/common/config.py` (Create)
* **Type / Scope**: Módulo de configuración compartida.
* **Proposed Changes**: Carga centralizada de variables de entorno mediante Pydantic BaseSettings: nombres de buckets, tabla DynamoDB, modelo Bedrock (`anthropic.claude-3-5-haiku-20241022-v1:0` y `amazon.titan-embed-text-v2:0`), límites de tokens y umbrales de latencia.

#### 5. `src/common/models.py` (Create)
* **Type / Scope**: Esquemas de datos Pydantic v2.
* **Proposed Changes**: Definición de contratos fuertemente tipados:
  * `GarantiaFactor`: campos para tipo, monto, vigencia, número de página y texto citado.
  * `CriterioFactor`: campos para ponderaciones técnicas/económicas y puntajes mínimos.
  * `MultaFactor`: causal, monto diario y tope porcentual.
  * `PlazoFactor`: fechas fatales, plazo de entrega y distinción hábil vs. corrido.
  * `TenderExtractionResult`: consolidación de los 4 factores con flags de verificación booleana.
  * `UploadUrlRequest` / `UploadUrlResponse`: contratos de entrada/salida de la API.

#### 6. `src/ingestion/parser.py` (Create)
* **Type / Scope**: Componente de extracción de texto y chunking respetando fronteras de página.
* **Proposed Changes**:
  * Función `extract_pages_from_pdf_stream(pdf_bytes: bytes) -> List[PageContent]`.
  * Validación de densidad de caracteres: si el promedio de caracteres por página es menor a 50, lanza `ScannedPdfException`.
  * Clasificador heurístico por Regex para etiquetar chunks con metadato `section_type` (`garantias`, `criterios`, `multas`, `plazos`).

#### 7. `src/ingestion/indexer.py` (Create)
* **Type / Scope**: Motor de indexación vectorial embebido serverless.
* **Proposed Changes**:
  * Invocación a Bedrock Titan Embeddings V2 con vector normalizado a 256 dimensiones.
  * Creación del índice local en `/tmp/{licitacion_id}.lance` y empaquetado/subida a `s3://licitaciones-indexes/{licitacion_id}.lance`.
  * Función de búsqueda top-k con filtrado estricto por metadato `section_type`.

#### 8. `src/ingestion/extractor.py` (Create)
* **Type / Scope**: Motor de extracción paralela con LLM.
* **Proposed Changes**:
  * Orquestación de 4 llamadas concurrentes a Bedrock Claude 3.5 Haiku mediante `concurrent.futures`.
  * Formateo de chunks inyectando marcadores canónicos `<<<PAGE_REF:X>>> ... <<<END_PAGE_REF:X>>>`.
  * Forzado de respuesta estructurada JSON validada contra los modelos de `src/common/models.py`.

#### 9. `src/ingestion/verifier.py` (Create)
* **Type / Scope**: Motor determinista antialucinación.
* **Proposed Changes**:
  * Función `verify_citation(page_number: int, exact_quote: str, raw_pages: Dict[int, str]) -> bool`.
  * Normalización de espacios en blanco y comparación estricta de subcadenas (`clean_quote in clean_page`).
  * Emisión de conteo a CloudWatch si se detecta discrepancia o alucinación de cita.

#### 10. `src/ingestion/handler.py` (Create)
* **Type / Scope**: Entrypoint de AWS Lambda para eventos SQS.
* **Proposed Changes**:
  * Lectura de mensajes SQS con batch size = 1.
  * Pipeline completo: descarga PDF desde S3 -> parseo por página -> indexación vectorial -> extracción LLM paralela -> verificación de citas -> guardado en DynamoDB en estado `READY` -> métricas CloudWatch (`TenderIngestionDurationMs`, `CostEstimatedUsd`).

#### 11. `src/api/handler.py` (Create)
* **Type / Scope**: Entrypoint de AWS Lambda para API Gateway HTTP API.
* **Proposed Changes**:
  * Enrutador ligero para peticiones HTTP:
    * `POST /licitaciones/upload-url`: genera URL prefirmada con `boto3.client('s3').generate_presigned_url`.
    * `GET /licitaciones/{id}/status`: consulta estado en DynamoDB (`PROCESSING`, `READY`, `FAILED`).
    * `GET /licitaciones/{id}/factores`: lee directamente los 4 factores validados desde DynamoDB y retorna respuesta en < 200 ms.

#### 12. `tests/unit/test_parser.py` (Create)
* **Type / Scope**: Pruebas unitarias de parseo y segmentación.
* **Proposed Changes**: Pruebas con archivos PDF sintéticos (generados en memoria con PyMuPDF): validación de extracción por página, detección de PDFs escaneados y etiquetado regex de secciones.

#### 13. `tests/unit/test_verifier.py` (Create)
* **Type / Scope**: Pruebas unitarias del validador antialucinación.
* **Proposed Changes**: Casos de prueba para coincidencias exactas, variaciones de saltos de línea, textos citados que no existen en la página declarada y fragmentos alterados por el LLM.

#### 14. `tests/unit/test_api.py` (Create)
* **Type / Scope**: Pruebas unitarias de endpoints API.
* **Proposed Changes**: Mocks de llamadas a DynamoDB y S3 verificando generación de URLs prefirmadas, validación de schemas de entrada y retornos HTTP 200/400/404.

#### 15. `tests/integration/test_pipeline_e2e.py` (Create)
* **Type / Scope**: Prueba de integración de extremo a extremo.
* **Proposed Changes**: Flujo simulado completo: carga de documento base de prueba de Mercado Público, ejecución del worker con mocks de llamadas Bedrock para validar estructura de persistencia en DynamoDB.

#### 16. `README.md` (Create)
* **Type / Scope**: Documentación exhaustiva del repositorio y guía de portafolio técnico.
* **Proposed Changes**: Diagrama de arquitectura, explicación del dolor de negocio para PYMEs, desglose de costos en AWS Free Tier, instrucciones paso a paso para desplegar con AWS CLI y SAM, y guía de demostración para entrevistas técnicas.

### Verification Plan

* **Compilation/Build**:
  * Ejecución de `sam build --use-container` para empaquetar layers y validar sintaxis de `template.yaml`.
* **Unit Tests**:
  * `pytest tests/unit/ -v --cov=src --cov-report=term-missing`
  * Cobertura mínima requerida: 85%+ en lógica de parseo, verificación y extracción.
* **Static Analysis & Linting**:
  * `ruff check src/ tests/` (Linter y formateador ultrarrápido).
* **E2E / Local Execution**:
  * Ejecución local del worker con evento SQS de prueba:
    `sam local invoke IngestionFunction -e events/sample_sqs_event.json`
  * Ejecución local de la API:
    `sam local start-api` y verificación con `curl http://127.0.0.1:3000/licitaciones/upload-url`.
* **FinOps Validation**:
  * Verificación de métricas en CloudWatch Logs asegurando que el consumo de tokens y duración por ejecución se registren en cada corrida.

--------------------------------------------------------------------------------

*Drafted with EGM*
