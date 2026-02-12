from __future__ import annotations

from io import BytesIO
from datetime import timedelta

import qrcode
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image


def _fmt_dt(dt):
    if not dt:
        return "-"
    # Ajusta a tu TZ
    dt = timezone.localtime(dt)
    return dt.strftime("%d/%m/%Y %H:%M")


def build_movimiento_pdf_bytes(movimiento, *, horas_previstas: int | None = None) -> bytes:
    """
    Genera PDF (bytes) con resumen del movimiento.
    Funciona aunque todavía no tengas campos nuevos en Movimiento:
    - horas_previstas
    - egreso_estimado_at
    - tarifa_hora_aplicada
    - monto_estimado
    (usa getattr + fallback).
    """
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Comprobante de Ingreso",
    )

    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    normal = styles["BodyText"]

    v = movimiento.vehiculo
    c = movimiento.cochera
    cli = v.cliente
    tipo = v.tipo

    horas = getattr(movimiento, "horas_previstas", None) or horas_previstas or 1
    try:
        horas = int(horas)
    except Exception:
        horas = 1
    if horas < 1:
        horas = 1

    ingreso_at = movimiento.ingreso_at
    egreso_at = movimiento.egreso_at

    egreso_estimado = getattr(movimiento, "egreso_estimado_at", None)
    if not egreso_estimado:
        egreso_estimado = ingreso_at + timedelta(hours=horas)

    tarifa_hora = getattr(movimiento, "tarifa_hora_aplicada", None)
    monto_estimado = getattr(movimiento, "monto_estimado", None)

    # QR con el ticket (para búsqueda rápida / egreso)
    qr_img = qrcode.make(v.ticket)
    qr_buf = BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    qr_rl = Image(qr_buf, width=35 * mm, height=35 * mm)

    story = []

    story.append(Paragraph("Comprobante de Ingreso", h1))
    story.append(Spacer(1, 6 * mm))

    # Header con Ticket + QR
    ticket_big = Paragraph(f"<b>TICKET:</b> <font size=16>{v.ticket}</font>", h2)
    header_tbl = Table([[ticket_big, qr_rl]], colWidths=[120 * mm, 40 * mm])
    header_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(header_tbl)
    story.append(Spacer(1, 6 * mm))

    # Datos cochera / vehiculo
    data1 = [
        ["Cochera", c.nombre],
        ["Dirección", c.direccion or "-"],
        ["Tipo de vehículo", tipo.nombre],
        ["Patente (ult. 3)", v.patente_ult3 or "-"],
        ["Espacio", (movimiento.espacio.etiqueta or str(movimiento.espacio_id))],
        ["Estado", movimiento.estado],
    ]
    t1 = Table(data1, colWidths=[45 * mm, 130 * mm])
    t1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t1)
    story.append(Spacer(1, 6 * mm))

    # Horarios + estimación
    salida_label = "Salida real" if egreso_at else "Salida estimada"
    data2 = [
        ["Entrada", _fmt_dt(ingreso_at)],
        [salida_label, _fmt_dt(egreso_at or egreso_estimado)],
        ["Horas", str(horas)],
    ]
    if tarifa_hora is not None:
        data2.append(["Tarifa por hora", f"$ {tarifa_hora}"])
    if monto_estimado is not None:
        data2.append(["Total estimado", f"$ {monto_estimado}"])

    t2 = Table(data2, colWidths=[45 * mm, 130 * mm])
    t2.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t2)
    story.append(Spacer(1, 6 * mm))

    # Cliente
    story.append(Paragraph("Datos del cliente", h2))
    cliente_nombre = (f"{cli.nombre} {cli.apellido}").strip() or "-"
    data3 = [
        ["Nombre", cliente_nombre],
        ["Teléfono", cli.telefono or "-"],
        ["Email", cli.email or "-"],
    ]
    t3 = Table(data3, colWidths=[45 * mm, 130 * mm])
    t3.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t3)

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(f"<i>Emitido: {_fmt_dt(timezone.now())}</i>", normal))

    doc.build(story)
    return buf.getvalue()
