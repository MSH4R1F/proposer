"""
PDF generation utilities for settlement documents.

Generates settlement summary PDFs using reportlab.
All outputs are informational only — not legally binding.
"""

import io
from datetime import datetime
from typing import Any, Dict


def generate_settlement_pdf(settlement_data: Dict[str, Any]) -> bytes:
    """
    Generate a settlement summary PDF from settlement data.

    Args:
        settlement_data: Dictionary containing settlement details:
            - dispute_id: str
            - settlement_amount: float
            - property_address: str (optional)
            - deposit_amount: float (optional)
            - started_at: str (ISO timestamp, optional)
            - settled_at: str (ISO timestamp, optional)

    Returns:
        PDF content as bytes.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors

    buf = io.BytesIO()
    page_width, page_height = A4
    c = canvas.Canvas(buf, pagesize=A4)

    margin = 20 * mm
    content_width = page_width - 2 * margin
    y = page_height - margin

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(colors.HexColor("#1a1a2e"))
    c.drawString(margin, y, "Proposer - Settlement Summary")
    y -= 8 * mm

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#555555"))
    now_str = datetime.utcnow().strftime("%d %B %Y, %H:%M UTC")
    c.drawString(margin, y, f"Date: {now_str}")
    y -= 4 * mm

    # Horizontal rule
    c.setStrokeColor(colors.HexColor("#cccccc"))
    c.setLineWidth(0.5)
    c.line(margin, y, page_width - margin, y)
    y -= 8 * mm

    # -----------------------------------------------------------------------
    # Section: Dispute Details
    # -----------------------------------------------------------------------
    def section_header(title: str) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.HexColor("#1a1a2e"))
        c.drawString(margin, y, title)
        y -= 6 * mm

    def field_row(label: str, value: str) -> None:
        nonlocal y
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.HexColor("#333333"))
        c.drawString(margin, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#000000"))
        c.drawString(margin + 55 * mm, y, value)
        y -= 6 * mm

    section_header("Dispute Details")

    dispute_id = settlement_data.get("dispute_id", "N/A")
    field_row("Dispute ID", str(dispute_id))

    property_address = settlement_data.get("property_address")
    if property_address:
        field_row("Property", str(property_address))

    deposit_amount = settlement_data.get("deposit_amount")
    if deposit_amount is not None:
        field_row("Deposit Amount", f"£{float(deposit_amount):,.2f}")

    y -= 4 * mm

    # -----------------------------------------------------------------------
    # Section: Agreed Terms
    # -----------------------------------------------------------------------
    section_header("Agreed Terms")

    settlement_amount = settlement_data.get("settlement_amount")
    if settlement_amount is not None:
        # Large bold settlement amount
        c.setFont("Helvetica-Bold", 22)
        c.setFillColor(colors.HexColor("#2e7d32"))
        amount_str = f"£{float(settlement_amount):,.2f}"
        c.drawString(margin, y, f"Settlement Amount: {amount_str}")
        y -= 10 * mm
    else:
        field_row("Settlement Amount", "Not specified")

    y -= 4 * mm

    # -----------------------------------------------------------------------
    # Section: Timeline
    # -----------------------------------------------------------------------
    section_header("Timeline")

    started_at = settlement_data.get("started_at")
    if started_at:
        try:
            dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            started_str = dt.strftime("%d %B %Y, %H:%M UTC")
        except (ValueError, TypeError):
            started_str = str(started_at)
        field_row("Mediation Started", started_str)

    settled_at = settlement_data.get("settled_at")
    if settled_at:
        try:
            dt = datetime.fromisoformat(str(settled_at).replace("Z", "+00:00"))
            settled_str = dt.strftime("%d %B %Y, %H:%M UTC")
        except (ValueError, TypeError):
            settled_str = str(settled_at)
        field_row("Mediation Settled", settled_str)

    y -= 4 * mm

    # -----------------------------------------------------------------------
    # Section: Disclaimer (prominent, bordered box)
    # -----------------------------------------------------------------------
    disclaimer_text = (
        "This document is for informational purposes only and is NOT a legally binding "
        "contract. It does not create any legal obligation between the parties. The AI "
        "analysis and mediation process are confidential and cannot be referred to in "
        "later legal proceedings."
    )

    # Estimate box height: wrap text at ~85 chars per line
    line_height = 5 * mm
    chars_per_line = 85
    words = disclaimer_text.split()
    lines: list[str] = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip()
        if len(test) <= chars_per_line:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    box_padding = 4 * mm
    box_height = (
        (len(lines) * line_height) + (2 * box_padding) + 6 * mm
    )  # title + lines + padding

    # Draw box
    c.setStrokeColor(colors.HexColor("#c62828"))
    c.setFillColor(colors.HexColor("#fff8f8"))
    c.setLineWidth(1.5)
    c.rect(margin, y - box_height, content_width, box_height, fill=1, stroke=1)

    # Disclaimer title
    text_y = y - box_padding - 5 * mm
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#c62828"))
    c.drawString(margin + box_padding, text_y, "IMPORTANT DISCLAIMER")
    text_y -= line_height + 1 * mm

    # Disclaimer body
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#333333"))
    for line in lines:
        c.drawString(margin + box_padding, text_y, line)
        text_y -= line_height

    y -= box_height + 8 * mm

    # -----------------------------------------------------------------------
    # Footer
    # -----------------------------------------------------------------------
    footer_y = margin
    c.setStrokeColor(colors.HexColor("#cccccc"))
    c.setLineWidth(0.5)
    c.line(margin, footer_y + 6 * mm, page_width - margin, footer_y + 6 * mm)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#888888"))
    footer_text = f"Generated by Proposer AI Mediation Platform - {now_str}"
    c.drawCentredString(page_width / 2, footer_y, footer_text)

    c.save()
    return buf.getvalue()
