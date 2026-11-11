import os

import pymupdf


def generate_sample_tender(output_path: str = "samples/pliego_ejemplo_chilecompra.pdf") -> str:
    """Genera un archivo PDF sintético representativo de un pliego de licitación pública

    chileno (Mercado Público) de 6 páginas con cláusulas reales de la Ley N° 19.886.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = pymupdf.open()

    # Página 1: Carátula Oficial
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(
        (50, 72),
        "GOBIERNO DE CHILE\n"
        "MINISTERIO DE SALUD - SERVICIO DE SALUD METROPOLITANO\n\n"
        "BASES ADMINISTRATIVAS Y TÉCNICAS PARA LA ADQUISICIÓN DE:\n"
        "\"SERVICIO DE GESTIÓN DOCUMENTAL CLOUD Y PLATAFORMA DIGITAL\"\n\n"
        "ID DE LICITACIÓN EN MERCADO PÚBLICO: 1057432-88-LR26\n"
        "TIPO DE LICITACIÓN: Licitación Pública Mayor a 1.000 UTM (LR)\n"
        "FECHA DE PUBLICACIÓN: Noviembre de 2026\n\n"
        "1. DISPOSICIONES GENERALES\n"
        "La presente contratación se rige estrictamente por la Ley N° 19.886 de Bases sobre\n"
        "Contratos Administrativos de Suministro y Prestación de Servicios y su Reglamento (D.S. N° 250).",
        fontsize=11,
    )

    # Página 2: Garantías Contractuales
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text(
        (50, 72),
        "2. GARANTÍAS CONTRACTUALES EXIGIDAS\n\n"
        "2.1 GARANTÍA DE SERIEDAD DE LA OFERTA:\n"
        "Para participar en la licitación, los oferentes deberán caucionar la seriedad de su propuesta\n"
        "mediante Vale Vista bancario o Boleta de Garantía pagadera a la vista por un monto único de\n"
        "150 UF (Ciento cincuenta Unidades de Fomento).\n"
        "Vigencia: Deberá mantener vigencia no inferior a 90 días corridos contados desde la apertura.\n"
        "Glosa Obligatoria: \"Garantiza la seriedad de la oferta en licitación pública ID 1057432-88-LR26\".\n\n"
        "2.2 GARANTÍA DE FIEL Y OPORTUNO CUMPLIMIENTO:\n"
        "El adjudicatario deberá entregar, previo a la suscripción del contrato, una garantía de fiel\n"
        "cumplimiento por un monto equivalente al 5% del valor total neto adjudicado, con vigencia\n"
        "que cubra el plazo total del contrato más 60 días corridos adicionales.",
        fontsize=11,
    )

    # Página 3: Criterios de Evaluación y Ponderaciones
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text(
        (50, 72),
        "3. CRITERIOS DE EVALUACIÓN Y METODOLOGÍA DE ADJUDICACIÓN\n\n"
        "La Comisión Evaluadora evaluará las ofertas admisibles conforme a la siguiente matriz ponderada:\n\n"
        "• Oferta Técnica y Calidad del Servicio: 60% de la ponderación total.\n"
        "  - Cumplimiento de requerimientos de arquitectura cloud (30%)\n"
        "  - Experiencia acreditada del equipo consultor (20%)\n"
        "  - Plan de contingencia y SLA garantizado (10%)\n\n"
        "• Oferta Económica (Precio): 35% de la ponderación total.\n"
        "  - Evaluada mediante la fórmula: (Precio Mínimo / Precio Ofertado) * 35 puntos.\n\n"
        "• Cumplimiento de Requisitos Formales: 5% de la ponderación total.\n\n"
        "UMBRAL TÉCNICO MÍNIMO DESCALIFICATORIO:\n"
        "Aquellas ofertas que obtengan un puntaje técnico ponderado inferior a 50 puntos serán declaradas\n"
        "inadmisibles y descalificadas de forma automática del proceso.",
        fontsize=11,
    )

    # Página 4: Régimen de Multas y Sanciones
    p4 = doc.new_page(width=595, height=842)
    p4.insert_text(
        (50, 72),
        "4. RÉGIMEN DE SANCIONES Y MULTAS\n\n"
        "El Servicio podrá aplicar al proveedor las siguientes multas pecuniarias:\n\n"
        "4.1 Multa por Atraso Injustificado en Entregables:\n"
        "Por cada día hábil de retraso en la entrega de los informes de avance o puestas en producción,\n"
        "se aplicará una multa diaria ascendente a 3 UF por día de atraso.\n\n"
        "4.2 Multa por Incumplimiento de Niveles de Servicio (SLA):\n"
        "Fallas de disponibilidad del sistema inferiores al 99.5% mensual devengarán una multa equivalente\n"
        "al 2% del pago mensual respectivo por cada 0.5% de indisponibilidad adicional.\n\n"
        "TOPE MÁXIMO ACUMULADO:\n"
        "El monto acumulado total de las multas aplicadas no podrá superar bajo ninguna circunstancia el\n"
        "15% del valor total del contrato. Si las multas alcanzan dicho tope, el Servicio queda facultado\n"
        "para rescindir administrativamente el contrato de forma unilateral y cobrar la boleta de fiel cumplimiento.",
        fontsize=11,
    )

    # Página 5: Plazos Fatales y Cronograma
    p5 = doc.new_page(width=595, height=842)
    p5.insert_text(
        (50, 72),
        "5. CALENDARIO DE HITOS Y PLAZOS FATALES\n\n"
        "Todas las fechas y plazos estipulados en las presentes bases se consideran fatales:\n\n"
        "• Fecha y hora de inicio de preguntas en el portal: 12-11-2026 a las 09:00 horas.\n"
        "• Fecha límite de aclaraciones y respuestas: 18-11-2026 a las 18:00 horas.\n"
        "• FECHA Y HORA DE CIERRE DE RECEPCIÓN DE OFERTAS: 28-11-2026 a las 15:00 horas.\n"
        "• Acto de apertura técnica y económica electrónica: 28-11-2026 a las 15:30 horas.\n\n"
        "RÉGIMEN DE CÓMPUTO DE PLAZOS:\n"
        "Salvo estipulación expresa en contrario, todos los plazos del proceso de postulación se\n"
        "computarán en días hábiles administrativos, entendiéndose inhábiles los días sábados, domingos\n"
        "y festivos, conforme al artículo 25 de la Ley N° 19.880.\n\n"
        "PLAZO DE EJECUCIÓN CONTRACTUAL:\n"
        "El plazo máximo de entrega e implementación de la solución será de 60 días corridos contados\n"
        "desde la total tramitación de la resolución administrativa que apruebe el contrato.",
        fontsize=11,
    )

    # Página 6: Anexos y Firma
    p6 = doc.new_page(width=595, height=842)
    p6.insert_text(
        (50, 72),
        "6. ANEXOS Y FORMATOS COMPLEMENTARIOS\n\n"
        "Anexo N° 1: Formato de Declaración Jurada Simple de no estar inhabilitado para contratar con el Estado.\n"
        "Anexo N° 2: Formato de Oferta Económica Desglosada.\n"
        "Anexo N° 3: Identificación del Equipo Consultor y Certificaciones requeridas.\n\n"
        "-------------------------------------------------------------------------\n"
        "DIRECCIÓN DE COMPRAS PÚBLICAS Y CONTRATACIÓN DEL SERVICIO DE SALUD\n"
        "Santiago de Chile, 2026.",
        fontsize=11,
    )

    doc.save(output_path)
    doc.close()
    return os.path.abspath(output_path)


if __name__ == "__main__":
    generated_file = generate_sample_tender()
    print(f"Pliego de prueba generado exitosamente en: {generated_file}")
