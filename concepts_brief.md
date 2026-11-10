# Pipeline Serverless en AWS para Análisis RAG de Licitaciones de Mercado Público

* **Author:** VitoNez5198
* **Date:** 2026-11-10

## Overview

Este sistema es un pipeline en la nube de AWS diseñado con una arquitectura serverless orientada a eventos para pequeñas y medianas empresas (PYMEs) proveedoras del Estado chileno (Mercado Público / Ley N° 19.886). 

El sistema permite que un usuario suba las bases de licitación en formato PDF a un bucket de Amazon S3. De forma automática y desacoplada, una función AWS Lambda procesa el documento respetando los límites de página, extrae los fragmentos textuales y genera embeddings vectoriales. Posteriormente, un orquestador RAG extrae cuatro factores críticos descalificatorios o de alto riesgo financiero:
1. **Garantías:** Montos, plazos de vigencia y glosa de seriedad de la oferta y fiel cumplimiento.
2. **Criterios de Ponderación:** Fórmulas de evaluación técnica vs. económica y puntajes mínimos.
3. **Multas:** Causales, montos en UTM/UF por día de atraso y tope porcentual de término anticipado.
4. **Plazos Fatales:** Fechas límite de consultas, cierre, apertura y entrega (días hábiles vs. corridos).

Cada respuesta incluye una cita textual verificada y el número de página exacto del PDF original, junto con métricas operativas de latencia y costo por documento en Amazon CloudWatch, operando dentro de los márgenes de la capa gratuita (Free Tier).

## Analysis

### 1. Resolución de Contradicciones Inventivas (TRIZ)
* **Contradicción 1: Precisión y Exhaustividad vs. Latencia y Presupuesto.**
  * *Problema:* Enviar 150 páginas de bases legales a un modelo fundacional excede los límites de memoria de AWS Lambda, satura la ventana de contexto y eleva los costos. Un RAG semántico simple a menudo recupera fragmentos irrelevantes y omite cláusulas de multas críticas.
  * *Resolución:* Separación en espacio y filtrado determinista previo. Durante el escaneo en Lambda, expresiones regulares de alta especificidad detectan encabezados regulatorios estándar de ChileCompra (ej. "TÍTULO V: DE LAS MULTAS", "CAPÍTULO III: GARANTÍAS"). Los chunks reciben metadatos tipados (`section_type`), permitiendo que el RAG filtre primero por sección antes de realizar la búsqueda vectorial, reduciendo el espacio de búsqueda a 3-5 páginas con 99% de exhaustividad.
* **Contradicción 2: Trazabilidad Verificable vs. Alucinación de Números de Página.**
  * *Problema:* Los modelos de lenguaje tienden a inventar números de página cuando se consolidan múltiples fragmentos en un prompt.
  * *Resolución:* Inyección de marcadores unívocos (`<<<PAGE_REF:X>>>`) y verificación estricta de subcadenas en Python (`assert fragmento_exacto in texto_pagina`). Si el fragmento extraído no coincide exactamente con el texto de la página indicada, el sistema marca el factor como "Requiere auditoría manual" antes de exponerlo al cliente.

### 2. Ergonomía y Operación para PYMEs
* Las PYMEs no requieren un chatbot conversacional abierto, sino un panel de control con tarjetas resumen de los 4 factores, semáforos de riesgo (verde/amarillo/rojo) y enlace directo a la página del PDF con el texto resaltado.
* El tiempo de evaluación humana de una licitación se reduce de 4 horas a menos de 90 segundos.

### 3. Límites Operativos de la Infraestructura Cloud (AWS Free Tier)
* **AWS Lambda:** Cómputo dentro del millón de invocaciones gratuitas mensuales. Límite de 15 minutos y 250 MB por defecto en layer.
* **Amazon OpenSearch Serverless Descartado:** No cuenta con capa gratuita (costo base ~$175 USD/mes). Se reemplaza por almacenamiento vectorial serverless embebido (S3 + LanceDB en `/tmp`) o Pinecone Serverless Free Tier.
* **Amazon API Gateway HTTP API:** Timeout de 29 segundos mitigado mediante pre-cálculo asíncrono y almacenamiento en caché de DynamoDB (`GET /licitaciones/{id}/factores` responde en < 200 ms).
* **Costos de Inferencia LLM:** Empleando Claude 3.5 Haiku o Amazon Titan Text V2 con esquemas estructurados Pydantic, el costo por licitación promedia ~$0.0015 USD, permitiendo procesar cientos de documentos con menos de $1 USD.

## Goals vs. Non-Goals

* **In-Scope Goals:**
  * Pipeline de ingesta asíncrono activado por eventos S3 (`s3:ObjectCreated`).
  * Desacoplamiento mediante cola SQS con Dead-Letter Queue (DLQ).
  * Extracción de texto estructurado por página utilizando PyMuPDF (`fitz`).
  * Indexación vectorial serverless con metadata de página.
  * Extracción de los 4 factores críticos mediante prompts estructurados con salida JSON estricta.
  * Verificación determinista de subcadena para garantizar citas infalsificables.
  * Métricas de observabilidad en CloudWatch (costo por licitación, tiempo de ingesta, tasa de alucinación prevenida).
  * Presupuesto protegido con AWS Budgets y alarma a $1.00 USD.

* **Out-of-Scope Non-Goals:**
  * Procesamiento masivo por scraping automático de todo el portal de Mercado Público (ingesta bajo demanda únicamente).
  * Soporte para PDFs escaneados como imagen sin capa de texto (OCR pesado con AWS Textract se difiere a una fase posterior).
  * Asesoría legal vinculante o redacción automática de ofertas comerciales.
  * Modificación o anulación de ofertas dentro de la plataforma del Estado.

## Alternatives Weighed

* **Base Vectorial con Amazon OpenSearch Serverless:**
  * *Rechazado por el autor y revisores:* Costo prohibitivo para un proyecto personal o PYME (~$175 USD/mes sin capa gratuita). Se optó por arquitectura serverless basada en S3 + LanceDB / Pinecone Free Tier.
* **Procesamiento Síncrono a través de API Gateway:**
  * *Rechazado:* Inviable para bases extensas (80-150 páginas) debido al timeout inmodificable de 29 segundos de API Gateway. Se adoptó el patrón asíncrono con SQS + Lambda y consulta por lectura de caché en DynamoDB.
* **RAG de Pregunta Abierta (Chatbot Genérico):**
  * *Rechazado:* Baja utilidad para una PYME y alto riesgo de alucinación en datos contractuales. Se reemplazó por extracción estructurada dirigida a los 4 factores críticos.

## Key Decisions & Staging for Next Steps

1. **Stack Tecnológico Central:**
   * Almacenamiento: Amazon S3 (PDFs y artefactos de índice).
   * Orquestación de Ingesta: S3 Event -> SQS Queue -> AWS Lambda (Python 3.12 + PyMuPDF).
   * Base de Datos de Estado y Caché: Amazon DynamoDB (`TenderAnalysis`).
   * Motor LLM / RAG: Amazon Bedrock (Claude 3.5 Haiku) con llamadas paralelas por factor.
   * Monitoreo: Amazon CloudWatch (métricas personalizadas de latencia y costo).
2. **Siguiente Hito:**
   * Pasar a la fase de diseño formal de arquitectura (`/egm-draft`) para generar la especificación técnica detallada, esquemas de tablas DynamoDB, políticas IAM de mínimo privilegio y plantillas IaC (AWS SAM / CloudFormation).

