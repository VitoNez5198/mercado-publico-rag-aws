# Pipeline Serverless en AWS para Análisis RAG de Licitaciones de Mercado Público

* **Author:** VitoNez5198
* **Status:** Proposed
* **Date:** 2026-11-10

--------------------------------------------------------------------------------

## Overview

Este documento especifica el diseño técnico de una solución en la nube (AWS) orientada a eventos para la extracción automatizada y auditoría de factores críticos en bases de licitación de **Mercado Público** (la plataforma oficial de compras del Estado de Chile, regulada por la **Ley N° 19.886 de Bases sobre Contratos Administrativos de Suministro y Prestación de Servicios**). La solución está dirigida a pequeñas y medianas empresas (PYMEs) que participan como proveedoras del Estado y requieren evaluar la viabilidad legal y financiera de pliegos de licitación de 30 a 180 páginas en minutos en lugar de horas.

El sistema recibe documentos en formato PDF mediante Amazon S3, procesa el texto delimitado por página a través de AWS Lambda utilizando un clasificador heurístico por expresiones regulares (Regex) para aislar ventanas candidatas de páginas relevantes, y extrae mediante Amazon Bedrock cuatro factores críticos:
1. **Garantías Financieras:** Boleta de Seriedad de la Oferta (garantiza el mantenimiento de la propuesta) y Boleta de Fiel Cumplimiento (caución tras la adjudicación), incluyendo sus montos en **UF** (Unidad de Fomento, unidad contable chilena reajustable según inflación), vigencia mínima y **glosa exacta** (texto obligatorio legal exigido por el organismo comprador).
2. **Criterios de Ponderación:** Fórmulas de evaluación técnica vs. económica y puntajes mínimos descalificatorios.
3. **Multas:** Causales, montos en **UTM** (Unidad Tributaria Mensual, unidad tributaria indexada) o UF por día de atraso y tope porcentual de término anticipado.
4. **Plazos Fatales:** Fechas límite de consultas, cierre, apertura y entrega (distinguiendo entre días hábiles administrativos y días corridos).

Cada respuesta incluye una cita textual verificada y el número de página exacto del PDF original, junto con métricas operativas de latencia y costo por documento en Amazon CloudWatch, operando bajo el régimen de Capa Gratuita (Free Tier) de AWS.

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
* **NG2 - Reconocimiento Óptico de Caracteres Pesado (OCR):** No se procesarán en esta versión inicial PDFs que contengan únicamente imágenes escaneadas sin capa de texto incrustada. Si un archivo carece de texto extraíble nativo, se capturará la excepción para actualizar DynamoDB a estado `FAILED` con código `SCANNED_PDF_UNSUPPORTED` sin disparar reintentos en SQS.
* **NG3 - Asesoría Legal Vinculante:** El software es un asistente de extracción y triage documental; no emite juicios de valor legal ni garantiza la adjudicación de una licitación.
* **NG4 - Interacción con la Plataforma Transaccional:** El sistema no enviará ofertas, no firmará documentos ni interactuará con las credenciales de usuario dentro del portal Mercado Público.

## Open Questions

* **Q1 (Resuelta):** *¿Qué mecanismo de almacenamiento vectorial o de extracción en `/tmp` de Lambda ofrece la mejor relación velocidad/tamaño de empaquetado?*
  * **Resolución:** Se descarta el montaje de bases vectoriales pesadas en `/tmp` (LanceDB o FAISS) para el triage inicial, ya que `pyarrow` excede la cuota de 250 MB de Lambda layers. Se adopta la **Ventana de Candidatos Directa vía Regex + PyMuPDF**: las expresiones regulares reducen el documento de 100 páginas a 3-5 páginas (~2.000 tokens) que se inyectan directamente en Bedrock Claude 3.5 Haiku. Esto reduce el layer a < 45 MB, elimina llamadas a Titan Embeddings y baja la latencia a menos de 40 segundos.
* **Q2 (Resuelta):** *¿Cómo manejar licitaciones que dividen sus requisitos en dos archivos separados (Bases Administrativas y Bases Técnicas)?*
  * **Resolución:** La función Lambda utiliza actualizaciones atómicas `UpdateItem` en DynamoDB sobre el mapa `factors`, indexando documentos bajo la misma partición `licitacion_id` y agregando los archivos procesados en el atributo `uploaded_documents` (StringSet) sin sobreescribir factores extraídos previamente.

## Critical User Journeys (CUJs)

### CUJ 1: Subida de Pliego y Procesamiento Desacoplado
* **Given**: Un usuario de la PYME tiene el archivo PDF oficial de las bases de una licitación de 80 páginas.
* **When**: El usuario solicita una URL prefirmada de subida a Amazon S3 y transfiere el archivo.
* **Then**: S3 emite un evento `ObjectCreated` a una cola SQS. Una función AWS Lambda toma el mensaje, segmenta el documento por páginas usando PyMuPDF, aísla las páginas relevantes con filtros regex y extrae los 4 factores en paralelo mediante Amazon Bedrock Claude 3.5 Haiku, persiste el resultado en DynamoDB mediante `UpdateItem` y marca el estado como `READY`.

### CUJ 2: Auditoría y Verificación de Citas por la PYME
* **Given**: La licitación `LIC-2026-001` ha completado su procesamiento asíncrono.
* **When**: El usuario consulta el endpoint `GET /licitaciones/LIC-2026-001/factores`.
* **Then**: La API retorna un JSON estructurado con los 4 factores en menos de 200 ms desde la caché de DynamoDB. Cada factor expone el valor extraído (ej. monto de garantía, días de entrega), el número de página del PDF, el fragmento textual exacto validado mediante subcadena y el estado de verificación (`VERIFIED` o `REQUIRES_MANUAL_REVIEW`).

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
        end

        subgraph Event_Decoupling [Desacoplamiento de Eventos]
            SQS_Queue[Amazon SQS: IngestionQueue]
            SQS_DLQ[Amazon SQS: DeadLetterQueue]
        end

        subgraph Ingestion_Engine [Motor de Ingesta y Extracción]
            Lambda_Ingest[Lambda: PyMuPDF Page-Splitter & Regex Filter]
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

    UI -->|1. POST /licitaciones/upload-url| APIGW
    APIGW --> Lambda_API
    Lambda_API -->|Retorna Presigned URL S3| UI
    UI -->|2. PUT directo de PDF| S3_Uploads
    S3_Uploads -->|3. Evento s3:ObjectCreated| SQS_Queue
    SQS_Queue -.->|Fallo tras 3 reintentos| SQS_DLQ
    SQS_Queue -->|4. Trigger batch=1| Lambda_Ingest
    Lambda_Ingest -->|5. Extrae texto por página PyMuPDF| Lambda_Ingest
    Lambda_Ingest -->|6. Filtra ventanas de páginas por Regex| Lambda_Ingest
    Lambda_Ingest -->|7. Invoca 4 llamadas con Claude 3.5 Haiku| Bedrock_LLM
    Bedrock_LLM -->|8. Retorna JSON estructurado + citas| Lambda_Ingest
    Lambda_Ingest -->|9. Normaliza y verifica subcadena NFKD| Lambda_Ingest
    Lambda_Ingest -->|10. Actualización atómica UpdateItem| DDB
    Lambda_Ingest -->|11. Emite métricas latencia/costo| CloudWatch
    CloudWatch -.-> Budgets

    UI -->|12. GET /licitaciones/{id}/factores| APIGW
    APIGW --> Lambda_API
    Lambda_API -->|13. Lectura directa en < 200ms| DDB
    Lambda_API -->|14. Retorna reporte con citas| UI
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

### 3. Extracción Directa por Ventana de Candidatos (Arquitectura Liviana sin Vector Store)

Para eliminar dependencias binarias pesadas que excedan la cuota de 250 MB de Lambda layers (`pyarrow` + `lancedb` superan los 200 MB en ARM64) y evitar llamadas innecesarias a modelos de embedding:
* **Escaneo y Selección Heurística en Lambda:** Durante la lectura del PDF con PyMuPDF, la función identifica y agrupa las páginas que contienen las secciones clave mediante expresiones regulares. Para cada factor se selecciona una ventana acotada de 3 a 5 páginas relevantes (~1.500 a 2.500 tokens).
* **Inyección Directa en Claude 3.5 Haiku:** Las páginas seleccionadas se envían directamente en paralelo al LLM. Dado que Claude 3.5 Haiku dispone de 200.000 tokens de contexto a bajo costo ($0.80 por millón de tokens de entrada), procesar 2.500 tokens cuesta solo ~$0.002 USD y se ejecuta en sub-segundos, eliminando por completo:
  1. La sobrecarga y el tiempo de computación de generar embeddings vectoriales (~100 llamadas por documento).
  2. La complejidad de gestionar índices locales en `/tmp` y persistirlos en S3.
  3. El riesgo de fallas de despliegue en SAM por tamaño de empaquetado.

### 4. Modelo de Datos en Amazon DynamoDB (`TenderAnalysis`)

Tabla única con facturación On-Demand (Free Tier: 25 RCU/WCU aprovisionadas o modo pago por uso). Soporta ingestión de múltiples documentos por licitación (Bases Administrativas y Técnicas) mediante operaciones atómicas `UpdateItem`.

* **Partition Key (PK):** `licitacion_id` (String, ej. `"LIC-708-12-LR26"`).
* **Configuración TTL:** Atributo `ttl` habilitado (`TimeToLiveSpecification: { AttributeName: "ttl", Enabled: true }`), fijado a 30 días posteriores a la fecha de creación para garantizar permanencia bajo la cuota gratuita de almacenamiento.
* **Atributos:**
  ```json
  {
    "licitacion_id": "LIC-708-12-LR26",
    "status": "READY",
    "created_at": "2026-11-10T14:30:00Z",
    "updated_at": "2026-11-10T14:31:15Z",
    "ttl": 1799514600,
    "uploaded_documents": ["Bases_Administrativas_708.pdf", "Bases_Tecnicas_708.pdf"],
    "total_pages": 78,
    "cost_usd_estimate": 0.0016,
    "processing_time_ms": 32400,
    "factors": {
      "garantias": {
        "status": "VERIFIED",
        "identificado": true,
        "tipo_garantia": "Seriedad de la Oferta",
        "monto": "50 UF",
        "vigencia": "60 días corridos contados desde la apertura de ofertas",
        "pagina_citada": 12,
        "fragmento_exacto": "La garantía de seriedad de la oferta deberá ser por un monto de 50 UF con vigencia mínima de 60 días corridos...",
        "verificado_en_pagina": true
      },
      "criterios": {
        "status": "VERIFIED",
        "identificado": true,
        "ponderacion_tecnica": "60%",
        "ponderacion_economica": "40%",
        "puntaje_minimo_descalificatorio": "50 puntos técnicos",
        "pagina_citada": 35,
        "fragmento_exacto": "Criterio Técnico (60%): Experiencia 40%, Metodología 20%. Criterio Económico (40%): Menor precio ofertado.",
        "verificado_en_pagina": true
      },
      "multas": {
        "status": "VERIFIED",
        "identificado": true,
        "causal_principal": "Atraso en entrega de informes",
        "monto_diario": "2 UTM por día hábil de atraso",
        "tope_maximo": "15% del valor total del contrato",
        "pagina_citada": 54,
        "fragmento_exacto": "Se aplicará una multa de 2 UTM por cada día hábil de atraso, con un tope máximo del 15% del total del contrato...",
        "verificado_en_pagina": true
      },
      "plazos": {
        "status": "REQUIRES_MANUAL_REVIEW",
        "identificado": true,
        "cierre_ofertas": "25 de Noviembre de 2026 a las 15:00 hrs",
        "tipo_computo": "Días corridos para entrega; días hábiles administrativos para aclaraciones",
        "plazo_entrega": "45 días corridos",
        "pagina_citada": 8,
        "fragmento_exacto": "El plazo de entrega de los suministros será de 45 días corridos...",
        "verificado_en_pagina": false,
        "advertencia": "Discrepancia detectada en la cita textual; requiere confirmación manual en página 8."
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

### 6. Motor de Inferencia LLM, Verificación y Resiliencia

* **Modelo:** Anthropic Claude 3.5 Haiku en Amazon Bedrock (`anthropic.claude-3-5-haiku-20241022-v1:0`).
* **Configuración del Cliente con Retroceso Adaptativo (Anti-Throttling HTTP 429):**
  ```python
  import boto3
  from botocore.config import Config

  bedrock_config = Config(
      retries={
          'max_attempts': 5,
          'mode': 'adaptive'
      },
      connect_timeout=5,
      read_timeout=30
  )
  bedrock_client = boto3.client("bedrock-runtime", config=bedrock_config)
  ```
* **Prompting con Marcadores Canónicos:**
  ```text
  Eres un auditor técnico de compras públicas chilenas. Analiza los siguientes fragmentos etiquetados por página:
  <<<PAGE_REF:12>>> [Texto del chunk] <<<END_PAGE_REF:12>>>
  Extrae el factor solicitado en formato JSON estricto. Incluye obligatoriamente el número de página de donde extrajiste la información y el fragmento textual EXACTO (copiado y pegado, carácter por carácter).
  ```
* **Mecanismo Antialucinación con Normalización Unicode:**
  ```python
  import unicodedata

  def normalize_text(text: str) -> str:
      # Normaliza caracteres Unicode (NFKD) para resolver ligaduras (fi, fl) y comillas tipográficas
      text = unicodedata.normalize('NFKD', text)
      return " ".join(text.strip().split())

  def verify_citation(page_number: int, exact_quote: str, page_texts: dict) -> bool:
      target_page = page_texts.get(page_number, "")
      clean_quote = normalize_text(exact_quote)
      clean_page = normalize_text(target_page)
      return clean_quote in clean_page
  ```
  Si la subcadena no existe en esa página, `verificado_en_pagina` se establece en `false` y el estado del factor pasa a `REQUIRES_MANUAL_REVIEW`, impidiendo entregar datos falsificados a la PYME.

### 7. Observabilidad FinOps y Alarmas de Costo

* **CloudWatch Custom Metrics:**
  * `TenderIngestionDurationMs`: Alarma si `p90 > 60000 ms`.
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
* **Reason for Rejection:** Descartado debido al costo base fijo prohibitivo (~$175 USD/mes) sin capa gratuita en AWS, lo que viola el objetivo G3 de operar con costo base de $0 USD mensuales.

### Alternative B: Procesamiento Síncrono Directo a través de API Gateway

* **Pros:**
  * Flujo conceptual más simple sin necesidad de cola SQS ni persistencia intermedia de estados en DynamoDB.
  * Menor cantidad de recursos de infraestructura que declarar en plantillas IaC.
* **Cons:**
  * Límite duro de timeout no modificable de 29 segundos en Amazon API Gateway (tanto HTTP como REST APIs).
  * Procesar un PDF de 80 a 150 páginas (extracción de texto y llamadas a Bedrock) toma típicamente entre 30 y 60 segundos, lo que genera errores HTTP 504 Gateway Timeout constantes.
* **Reason for Rejection:** Inviable ante el límite duro de timeout de 29 segundos en API Gateway al procesar pliegos extensos de compras públicas.

### Alternative C: RAG Conversacional de Pregunta Abierta (Chatbot Genérico)

* **Pros:**
  * Máxima libertad para que el usuario escriba cualquier consulta en lenguaje natural.
* **Cons:**
  * Alta tasa de alucinaciones en datos numéricos contractuales sensibles (confusión de multas en UTM vs UF, invención de plazos o números de página).
  * Exige que el usuario sepa exactamente qué preguntar en lugar de obtener un resumen estructurado estandarizado de los 4 factores de riesgo.
  * Mayor consumo de tokens y latencia acumulada por múltiples turnos conversacionales.
* **Reason for Rejection:** Riesgo inaceptable de alucinación legal y fatiga operativa para la PYME; se reemplazó por extracción estructurada dirigida a los 4 factores críticos con citas verificadas.

### Alternative D: Base de Datos Relacional Gestionada con Extensión pgvector (Amazon Aurora / RDS)

* **Pros:**
  * Consultas SQL combinadas con filtros vectoriales nativos en una sola base de datos.
* **Cons:**
  * Amazon Aurora Serverless v2 no dispone de nivel gratuito permanente (costo base de ~0.5 ACU = ~$43 USD/mes mínimo).
  * RDS PostgreSQL bajo Free Tier (db.t3.micro/db.t4g.micro) expira a los 12 meses y sufre degradación severa de memoria al indexar embeddings multidimensionales.
* **Reason for Rejection:** Genera costos fijos mensuales en AWS sin capa gratuita permanente y sobrecarga el presupuesto operativo del proyecto.

--------------------------------------------------------------------------------

## Risks & Mitigations

| Riesgo Técnico / Operacional | Severidad | Impacto | Mitigación Implementada |
| :--- | :---: | :--- | :--- |
| **Throttling en Amazon Bedrock (HTTP 429)** | 🔴 Alta | Fallo en extracción concurrente de los 4 factores si la cuenta supera el límite inicial de RPM. | Configuración de cliente `boto3` con retroceso adaptativo (`adaptive retry`) y hasta 5 reintentos con variación aleatoria (*full jitter*). Si persiste la saturación, el worker conmuta automáticamente a despacho secuencial. |
| **Exceso de Cuota en Lambda Layers (250 MB)** | 🔴 Alta | Fallo de despliegue en SAM (`Uncompressed image size too large`) al empaquetar librerías pesadas. | Eliminación de `lancedb` y `pyarrow` del stack. Se utiliza exclusivamente `PyMuPDF` (~45 MB) empaquetado en ARM64, manteniendo el layer en < 50 MB (20% del límite permitido). |
| **PDFs Escaneados o sin Capa de Texto** | 🟡 Media | PyMuPDF extrae 0 caracteres, imposibilitando el análisis de pliegos basados en imágenes. | Detección temprana en la función de parseo: si el promedio de caracteres por página es menor a 50, se captura `ScannedPdfException`, se marca DynamoDB inmediatamente como `FAILED` (`SCANNED_PDF_UNSUPPORTED`) y se finaliza el mensaje SQS exitosamente para evitar reintentos inútiles. |
| **Pliegos Anómalos con Timeout (> 180s)** | 🟡 Media | Documentos excepcionalmente densos (180+ páginas con tablas complejas) podrían acercarse al timeout de Lambda. | Temporizador interno en Lambda: al alcanzar el segundo 165 ($T - 15$), la función detiene la extracción adicional, persiste los factores recolectados hasta ese punto y marca el documento como `PARTIAL_SUCCESS` para no redescargar el archivo en SQS. |
| **Acumulación de Almacenamiento en Free Tier** | 🟡 Media | Archivos PDF y registros en DynamoDB acumulados a lo largo de meses exceden la cuota gratuita de AWS. | Regla de ciclo de vida en S3 para expirar PDFs a los 30 días y especificación Time-To-Live (TTL) en DynamoDB para purgar registros antiguos automáticamente a costo cero. |

--------------------------------------------------------------------------------

## Non-Functional Requirements

### Security & Privacy
* **Principio de Mínimo Privilegio (IAM):** Las funciones Lambda poseen roles dedicados de ejecución con permisos restringidos exclusivamente a sus buckets S3 específicos (`arn:aws:s3:::licitaciones-*/*`), su cola SQS, su tabla DynamoDB y a la acción `bedrock:InvokeModel` restringida exclusivamente al modelo Claude 3.5 Haiku (`arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0`).
* **Aislamiento de Carga:** Los archivos PDF subidos a S3 cuentan con cifrado en reposo del lado del servidor (`SSE-S3 / AES-256`) y políticas de acceso bloqueando cualquier acceso público (`BlockPublicAccess: true`).
* **Presigned URLs con Expiración Breve:** Las URLs de carga se emiten con tiempo de expiración estricto de 15 minutos (900 segundos).

### Performance & Latency
* **Tasa de Respuesta en Consulta (Read Path):** El endpoint de consulta de factores `GET /licitaciones/{id}/factores` responde en menos de 200 milisegundos en el percentil 95 (p95), sirviendo datos precalculados desde DynamoDB.
* **Tiempo de Ingesta Asíncrona (Write Path):** Parseo por página, selección de candidatos por Regex y extracción concurrente de los 4 factores para documentos de 100 páginas en menos de 45 segundos.
* **Optimización de Memoria en Lambda:** Layer optimizado de PyMuPDF en arquitectura ARM64 Graviton2 (< 45 MB), operando con margen holgado sobre la cuota de 250 MB.

### Rollout & Rollback
* **Infraestructura como Código (IaC):** Despliegue automatizado y reproducible mediante AWS SAM (`template.yaml`).
* **Estrategia de Rollback:** En caso de fallas durante el despliegue del stack SAM (`sam deploy`), CloudFormation ejecuta rollback automático al último estado estable sin interrumpir el bucket de almacenamiento de datos.

--------------------------------------------------------------------------------

## Future Improvements

* **Soporte OCR Nativo con AWS Textract:** Incorporar una rama de procesamiento condicional en la ingesta que detecte PDFs escaneados (densidad de caracteres < 50) y despache las páginas críticas a AWS Textract de forma asíncrona.
* **Extracción de Tablas Complejas con Estructura HTML/Markdown:** Integrar parsers especializados para bases que utilicen matrices de ponderación de múltiples niveles anidadas en tablas.
* **Exportación Automatizada a Hoja de Resumen (Excel/PDF):** Endpoint que genere una ficha ejecutiva de evaluación de 1 página para el comité de compras de la PYME.

--------------------------------------------------------------------------------

## Detailed Implementation Plan (Phased Execution)

### Fase 1: Fundaciones, Infraestructura (SAM) y Modelos Fuertemente Tipados

#### 1. `template.yaml` (Create)
* **Tipo / Alcance:** Infraestructura como Código (AWS SAM).
* **Cambios Específicos:**
  * `S3BucketUploads`: Bucket S3 para ingesta con ciclo de vida de 30 días (`ExpirationInDays: 30`) y bloqueo total de acceso público.
  * `IngestionQueue` & `IngestionDLQ`: Cola SQS con Dead-Letter Queue tras 3 reintentos (`maxReceiveCount: 3`) y `VisibilityTimeout: 300` segundos.
  * `IngestionFunction`: AWS Lambda (Python 3.12, ARM64 Graviton2, 1024 MB RAM, timeout 180s) conectada al trigger de SQS con layer de PyMuPDF (< 45 MB).
  * `ApiFunction`: AWS Lambda (Python 3.12, ARM64, 512 MB RAM, timeout 15s) conectada a HTTP API Gateway.
  * `HttpApi`: Amazon API Gateway v2 con rutas `POST /licitaciones/upload-url`, `GET /licitaciones/{id}/status` y `GET /licitaciones/{id}/factores`.
  * `TenderAnalysisTable`: Tabla DynamoDB con Partition Key `licitacion_id` (String), modo On-Demand y atributo TTL habilitado (`ttl`).
  * `BudgetsAlarm`: Alarma de presupuesto de $1.00 USD con tópico SNS.

#### 2. `samconfig.toml` (Create)
* **Tipo / Alcance:** Configuración de despliegue SAM CLI.
* **Cambios Específicos:** Parámetros para `sam build` y `sam deploy` en región `us-east-1`, habilitando empaquetado reproducible y nombres de stack `mercado-publico-rag-aws`.

#### 3. `requirements.txt` (Create)
* **Tipo / Alcance:** Manifiesto de dependencias Python.
* **Cambios Específicos:** Dependencias fijadas y compatibles:
  ```text
  boto3>=1.34.0
  PyMuPDF>=1.23.0
  pydantic>=2.6.0
  pydantic-settings>=2.2.0
  pytest>=8.0.0
  pytest-mock>=3.12.0
  ruff>=0.3.0
  ```

#### 4. `src/common/config.py` (Create)
* **Tipo / Alcance:** Configuración tipada mediante `pydantic-settings`.
* **Cambios Específicos:**
  ```python
  from pydantic_settings import BaseSettings, SettingsConfigDict

  class Settings(BaseSettings):
      TABLE_NAME: str = "TenderAnalysis"
      UPLOAD_BUCKET_NAME: str = "licitaciones-uploads"
      BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-haiku-20241022-v1:0"
      AWS_REGION: str = "us-east-1"
      PRESIGNED_URL_EXPIRATION_SECONDS: int = 900
      MAX_TIMEOUT_MARGIN_SECONDS: int = 165
      
      model_config = SettingsConfigDict(env_file=".env", extra="ignore")

  settings = Settings()
  ```

#### 5. `src/common/constants.py` (Create)
* **Tipo / Alcance:** Módulo centralizado de patrones Regex y constantes de dominio.
* **Cambios Específicos:**
  ```python
  import re

  SECTION_PATTERNS = {
      "garantias": re.compile(r"(?i)(garant[ií]a|seriedad de la oferta|fiel cumplimiento|cauci[oó]n|vale vista|p[oó]liza)"),
      "criterios": re.compile(r"(?i)(criterios? de evaluaci[oó]n|ponderaci[oó]n|matriz de evaluaci[oó]n|puntaje t[eé]cnico)"),
      "multas": re.compile(r"(?i)(multas?|sanciones?|atraso|incumplimiento|tope m[aá]ximo)"),
      "plazos": re.compile(r"(?i)(plazos?|fechas? fatales?|calendario|cierre de ofertas|apertura t[eé]cnica)")
  }
  ```

#### 6. `src/common/models.py` (Create)
* **Tipo / Alcance:** Modelos de datos Pydantic v2 (Regla de Cero Decisiones).
* **Cambios Específicos:**
  ```python
  from enum import Enum
  from typing import Optional, List, Dict, Any
  from pydantic import BaseModel, Field

  class FactorStatus(str, Enum):
      VERIFIED = "VERIFIED"
      REQUIRES_MANUAL_REVIEW = "REQUIRES_MANUAL_REVIEW"

  class TenderStatus(str, Enum):
      PENDING_UPLOAD = "PENDING_UPLOAD"
      PROCESSING = "PROCESSING"
      READY = "READY"
      PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
      FAILED = "FAILED"

  class PageContent(BaseModel):
      page_number: int
      text: str
      char_count: int

  class BaseFactor(BaseModel):
      identificado: bool = False
      pagina_citada: int = 0
      fragmento_exacto: str = ""
      verificado_en_pagina: bool = False
      status: FactorStatus = FactorStatus.REQUIRES_MANUAL_REVIEW
      source_file: str = ""
      advertencia: Optional[str] = None

  class GarantiaFactor(BaseFactor):
      tipo_garantia: Optional[str] = None
      monto: Optional[str] = None
      vigencia: Optional[str] = None
      glosa: Optional[str] = None

  class CriterioFactor(BaseFactor):
      ponderacion_tecnica: Optional[str] = None
      ponderacion_economica: Optional[str] = None
      puntaje_minimo_descalificatorio: Optional[str] = None

  class MultaFactor(BaseFactor):
      causal_principal: Optional[str] = None
      monto_diario: Optional[str] = None
      tope_maximo: Optional[str] = None

  class PlazoFactor(BaseFactor):
      cierre_ofertas: Optional[str] = None
      tipo_computo: Optional[str] = None
      plazo_entrega: Optional[str] = None

  class TenderExtractionResult(BaseModel):
      licitacion_id: str
      status: TenderStatus
      created_at: str
      updated_at: str
      ttl: int
      uploaded_documents: List[str] = Field(default_factory=list)
      total_pages: int = 0
      cost_usd_estimate: float = 0.0
      processing_time_ms: int = 0
      factors: Dict[str, Any] = Field(default_factory=dict)

  class UploadUrlRequest(BaseModel):
      file_name: str
      file_size_bytes: int

  class UploadUrlResponse(BaseModel):
      licitacion_id: str
      upload_url: str
      expires_in_seconds: int
  ```

* **Checkpoint Fase 1:** `sam validate --lint` exitoso y validación estricta de tipos `ruff check src/common/`.

--------------------------------------------------------------------------------

### Fase 2: Núcleo de Parseo y Verificación Determinista

#### 7. `src/ingestion/parser.py` (Create)
* **Tipo / Alcance:** Parser de documentos PDF con PyMuPDF.
* **Cambios Específicos:**
  * Implementa `extract_pages_from_pdf_stream(pdf_bytes: bytes) -> List[PageContent]`.
  * Validación de densidad: si el promedio de caracteres por página es menor a 50, lanza `ScannedPdfException("PDF carece de texto extraíble digital; posible imagen escaneada")`.
  * Normalización básica de saltos de línea sin fragmentar arbitrariamente el texto de cada página.

#### 8. `src/ingestion/verifier.py` (Create)
* **Tipo / Alcance:** Motor determinista de citas con normalización Unicode.
* **Cambios Específicos:**
  * `normalize_text(text: str) -> str`: Normaliza caracteres Unicode usando `unicodedata.normalize('NFKD', text)` para resolver ligaduras (`fi`, `fl`) y comillas tipográficas.
  * `verify_citation(page_number: int, exact_quote: str, raw_pages: Dict[int, str]) -> Tuple[bool, Optional[str]]`: Comprueba si la cita normalizada es subcadena exacta de la página normalizada. Retorna `(True, None)` si coincide; si falla, retorna `(False, "Discrepancia detectada en la cita textual; requiere confirmación manual")`.

#### 9. `tests/unit/test_parser.py` (Create)
* **Tipo / Alcance:** Pruebas unitarias de extracción PDF.
* **Escenarios Obligatorios:**
  * PDF válido de 10 páginas generado sintéticamente en memoria con PyMuPDF.
  * PDF escaneado con texto nulo (verifica que se lance `ScannedPdfException`).
  * Preservación estricta de límites de página y conteo de caracteres.

#### 10. `tests/unit/test_verifier.py` (Create)
* **Tipo / Alcance:** Pruebas unitarias de verificación de citas.
* **Escenarios Obligatorios:**
  * Coincidencia exacta de párrafo.
  * Citas con ligaduras Unicode (`fi`, `fl`, `æ`) y comillas curvadas (`“`, `”`).
  * Cita alterada por alucinación de LLM (verifica retorno `(False, warning)`).
  * Número de página inexistente en el diccionario del pliego.

* **Checkpoint Fase 2:** `pytest tests/unit/test_parser.py tests/unit/test_verifier.py -v` pasa al 100% en entorno aislado sin credenciales de AWS.

--------------------------------------------------------------------------------

### Fase 3: Motor de Ingesta Asíncrona SQS y Extracción Paralela con Bedrock

#### 11. `src/ingestion/candidate_selector.py` (Create)
* **Tipo / Alcance:** Ensamblador de ventanas de páginas candidatas por factor.
* **Cambios Específicos:**
  * Toma `List[PageContent]` y aplica los patrones de `src/common/constants.py`.
  * Agrupa hasta 3-5 páginas relevantes por cada factor crítico (`garantias`, `criterios`, `multas`, `plazos`).
  * Formatea el contexto inyectando delimitadores canónicos:
    `<<<PAGE_REF:X>>> [Texto de la página X] <<<END_PAGE_REF:X>>>`.

#### 12. `src/ingestion/extractor.py` (Create)
* **Tipo / Alcance:** Orquestador de inferencia LLM en Bedrock Claude 3.5 Haiku.
* **Cambios Específicos:**
  * Cliente `boto3` configurado con `botocore.config.Config(retries={'max_attempts': 5, 'mode': 'adaptive'})` para mitigar HTTP 429.
  * Invocación concurrente (`ThreadPoolExecutor`) de 4 llamadas dirigidas a Bedrock.
  * Valida la respuesta estructurada contra los modelos Pydantic de `src/common/models.py`.

#### 13. `src/ingestion/handler.py` (Create)
* **Tipo / Alcance:** Entrypoint de AWS Lambda para eventos SQS.
* **Cambios Específicos:**
  * Convención canónica de key en S3: `uploads/{licitacion_id}/{filename}`.
  * Extracción determinista de metadatos:
    ```python
    s3_record = json.loads(sqs_record["body"])["Records"][0]["s3"]
    bucket = s3_record["bucket"]["name"]
    key = urllib.parse.unquote_plus(s3_record["object"]["key"])
    licitacion_id = key.split("/")[1]
    filename = key.split("/")[-1]
    ```
  * Manejo de `ScannedPdfException`: actualiza DynamoDB a `FAILED` (`SCANNED_PDF_UNSUPPORTED`) y finaliza el mensaje SQS exitosamente (evitando reintentos inútiles).
  * Control de tiempo a 165 segundos: si el tiempo transcurrido supera 165s, persiste los factores ya calculados y marca `status: PARTIAL_SUCCESS`.
  * Actualización en DynamoDB mediante `UpdateItem` atómico registrando `source_file: filename` y emitiendo métricas a CloudWatch.

* **Checkpoint Fase 3:** Ejecución local exitosa con `sam local invoke IngestionFunction -e events/sample_sqs_event.json` simulando la ingesta de un PDF base.

--------------------------------------------------------------------------------

### Fase 4: Capa de Exposición API Gateway HTTP y Gestión de Estados

#### 14. `src/api/handler.py` (Create)
* **Tipo / Alcance:** Entrypoint de AWS Lambda para API Gateway HTTP API.
* **Cambios Específicos:**
  * `POST /licitaciones/upload-url`:
    1. Genera `licitacion_id` único y key `uploads/{licitacion_id}/{filename}`.
    2. Inicializa el registro en DynamoDB con `status: PENDING_UPLOAD`, `created_at` y `ttl = now + 30 días`.
    3. Retorna URL prefirmada `s3:PutObject` con expiración de 900 segundos.
  * `GET /licitaciones/{id}/status`: Consulta DynamoDB y retorna `PENDING_UPLOAD`, `PROCESSING`, `READY`, `PARTIAL_SUCCESS` o `FAILED`.
  * `GET /licitaciones/{id}/factores`: Retorna el mapa `factors` en < 200 ms directamente desde DynamoDB.

#### 15. `tests/unit/test_api.py` (Create)
* **Tipo / Alcance:** Pruebas unitarias de la API Gateway.
* **Escenarios Obligatorios:**
  * Generación de presigned URL con inicialización de estado `PENDING_UPLOAD`.
  * Consulta de estado para licitación inexistente (retorna 404).
  * Consulta de factores con caché lista (retorna 200 con payload verificado).

* **Checkpoint Fase 4:** `sam local start-api` y verificación con llamadas locales `curl`.

--------------------------------------------------------------------------------

### Fase 5: Suite de Integración E2E, Observabilidad FinOps y Documentación

#### 16. `tests/integration/test_pipeline_e2e.py` (Create)
* **Tipo / Alcance:** Prueba de integración de extremo a extremo.
* **Escenarios Obligatorios:**
  * Simula subida de pliego de prueba real de Mercado Público.
  * Verifica el paso por SQS, extracción en Lambda, actualización atómica en DynamoDB y lectura final vía API.

#### 17. `README.md` (Create)
* **Tipo / Alcance:** Documentación exhaustiva y guía de portafolio para entrevistas técnicas.
* **Contenido Obligatorio:**
  * Diagrama de arquitectura serverless y dolor de negocio para PYMEs en Chile.
  * Desglose de costos demostrando cumplimiento de AWS Free Tier ($0 base).
  * Guía paso a paso para desplegar con AWS CLI y SAM (`sam deploy --guided`).
  * Demostración en vivo guiada para reclutadores técnicos.

### Verification Plan Global

* **Compilación y Sintaxis IaC:** `sam validate --lint` y `sam build`.
* **Pruebas Unitarias y Cobertura:** `pytest tests/unit/ -v --cov=src --cov-report=term-missing` (cobertura mínima requerida: 85%+).
* **Análisis Estático y Calidad:** `ruff check src/ tests/` sin advertencias.
* **Simulación Local:**
  * Ingesta: `sam local invoke IngestionFunction -e events/sample_sqs_event.json`.
  * API: `sam local start-api` y pruebas con `curl http://127.0.0.1:3000/licitaciones/upload-url`.
* **Validación FinOps:** Verificación de logs y métricas de consumo en CloudWatch asegurando costo estimado de inferencia < $0.002 USD por licitación.

--------------------------------------------------------------------------------

*Drafted with EGM*

