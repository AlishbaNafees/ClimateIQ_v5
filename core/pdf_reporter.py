"""
core/pdf_reporter.py  —  ClimateIQ Dynamic PDF Report Generator
════════════════════════════════════════════════════════════════

Generates a fully dynamic PDF that:
  • Automatically includes EVERY chart produced by chart_engine.py
  • Pairs each chart with its AI-generated explanation
  • Does NOT hardcode chart names — everything is driven by the
    dict keys returned by generate_all_charts()

Dependencies
────────────
    pip install reportlab pillow

Usage (called from _PdfWorker in main_window.py)
─────
    from core.pdf_reporter import generate_pdf

    ok, msg = generate_pdf(
        output_path,   # str  — destination .pdf file
        stats,         # dict — from data_manager.compute_stats()
        city,          # str
        date_start,    # date
        date_end,      # date
        chart_bytes,   # dict  — { chart_key: PNG bytes }
        explanations,  # dict  — { chart_key: explanation_text }  (optional)
    )
"""

from __future__ import annotations

import io
import traceback
from datetime import date, datetime
from typing import Dict, Optional

# ── ReportLab imports ─────────────────────────────────────────────────────────
from reportlab.lib          import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles   import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units    import cm, mm
from reportlab.platypus     import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    Table, TableStyle, HRFlowable, PageBreak, KeepTogether,
)
from reportlab.lib.enums    import TA_CENTER, TA_LEFT, TA_JUSTIFY


# ── Design constants ──────────────────────────────────────────────────────────
_DARK_NAVY   = colors.HexColor("#0A1C50")
_MID_BLUE    = colors.HexColor("#2563EB")
_LIGHT_BLUE  = colors.HexColor("#3B82F6")
_VERY_LIGHT  = colors.HexColor("#EFF6FF")
_GREEN       = colors.HexColor("#059669")
_RED         = colors.HexColor("#DC2626")
_AMBER       = colors.HexColor("#D97706")
_PURPLE      = colors.HexColor("#7C3AED")
_TEAL        = colors.HexColor("#0891B2")
_BORDER      = colors.HexColor("#BFDBFE")
_BLACK       = colors.black
_WHITE       = colors.white
_LIGHT_GREY  = colors.HexColor("#F8FAFF")
_TEXT_DARK   = colors.HexColor("#1E3A5F")
_TEXT_MID    = colors.HexColor("#374151")


# ── Human-readable chart titles (fallback: auto-generated from key) ───────────
_CHART_LABELS: Dict[str, str] = {
    "sentiment_donut":    "Sentiment Distribution",
    "emotion_bar":        "Emotion Category Analysis",
    "topic_frequency":    "Climate Keyword Frequency",
    "city_comparison":    "City-Based Sentiment Comparison",
    "score_distribution": "VADER Score Distribution",
    "daily_activity":     "Daily Tweet Activity & Trends",
    "weather_breakdown":  "Weather Condition Breakdown",
}

_CHART_ICONS: Dict[str, str] = {
    "sentiment_donut":    "📊",
    "emotion_bar":        "🎭",
    "topic_frequency":    "🔑",
    "city_comparison":    "🗺️",
    "score_distribution": "📈",
    "daily_activity":     "📅",
    "weather_breakdown":  "🌤️",
}


def _chart_label(key: str) -> str:
    return _CHART_LABELS.get(key, key.replace("_", " ").title())


def _chart_icon(key: str) -> str:
    return _CHART_ICONS.get(key, "📊")


# ── Style sheet ───────────────────────────────────────────────────────────────
def _build_styles():
    base = getSampleStyleSheet()

    styles = {}

    styles["cover_title"] = ParagraphStyle(
        "cover_title",
        fontName="Helvetica-Bold",
        fontSize=26,
        textColor=_WHITE,
        alignment=TA_CENTER,
        spaceAfter=6,
        leading=32,
    )
    styles["cover_sub"] = ParagraphStyle(
        "cover_sub",
        fontName="Helvetica",
        fontSize=12,
        textColor=colors.HexColor("#BFDBFE"),
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    styles["cover_meta"] = ParagraphStyle(
        "cover_meta",
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#93C5FD"),
        alignment=TA_CENTER,
    )
    styles["section_num"] = ParagraphStyle(
        "section_num",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=_MID_BLUE,
        spaceBefore=4,
        spaceAfter=2,
    )
    styles["section_title"] = ParagraphStyle(
        "section_title",
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=_DARK_NAVY,
        spaceBefore=6,
        spaceAfter=4,
        leading=20,
    )
    styles["explanation"] = ParagraphStyle(
        "explanation",
        fontName="Helvetica",
        fontSize=10,
        textColor=_TEXT_DARK,
        alignment=TA_JUSTIFY,
        leading=15,
        spaceBefore=6,
        spaceAfter=10,
    )
    styles["kpi_label"] = ParagraphStyle(
        "kpi_label",
        fontName="Helvetica",
        fontSize=8,
        textColor=_TEXT_MID,
        alignment=TA_CENTER,
    )
    styles["kpi_value"] = ParagraphStyle(
        "kpi_value",
        fontName="Helvetica-Bold",
        fontSize=15,
        textColor=_DARK_NAVY,
        alignment=TA_CENTER,
    )
    styles["footer_text"] = ParagraphStyle(
        "footer_text",
        fontName="Helvetica",
        fontSize=7.5,
        textColor=colors.HexColor("#9CA3AF"),
        alignment=TA_CENTER,
    )
    styles["toc_entry"] = ParagraphStyle(
        "toc_entry",
        fontName="Helvetica",
        fontSize=10,
        textColor=_TEXT_DARK,
        leading=16,
    )
    styles["ai_label"] = ParagraphStyle(
        "ai_label",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=_PURPLE,
        spaceBefore=8,
        spaceAfter=3,
    )

    return styles


# ── Page template callbacks ───────────────────────────────────────────────────
def _on_first_page(canvas, doc):
    """Cover page — no header/footer."""
    pass


def _on_later_pages(canvas, doc):
    """Header + footer on every page after cover."""
    W, H = A4
    canvas.saveState()

    # Header bar
    canvas.setFillColor(_DARK_NAVY)
    canvas.rect(0, H - 28 * mm, W, 28 * mm, fill=1, stroke=0)
    canvas.setFillColor(_LIGHT_BLUE)
    canvas.rect(0, H - 29 * mm, W, 1 * mm, fill=1, stroke=0)

    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(_WHITE)
    canvas.drawString(2 * cm, H - 16 * mm, "🌍  ClimateIQ — Climate Sentiment Analysis Report")

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#93C5FD"))
    ts = datetime.now().strftime("%d %B %Y  %H:%M")
    canvas.drawRightString(W - 2 * cm, H - 16 * mm, ts)

    # Footer
    canvas.setFillColor(colors.HexColor("#F0F6FF"))
    canvas.rect(0, 0, W, 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(_BORDER)
    canvas.rect(0, 14 * mm, W, 0.4 * mm, fill=1, stroke=0)

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.drawCentredString(W / 2, 5 * mm, f"Page {doc.page}")
    canvas.drawString(2 * cm, 5 * mm, "Generated by ClimateIQ v3.0  ·  Powered by FLAN-T5 AI")
    canvas.drawRightString(W - 2 * cm, 5 * mm, "Confidential — Academic Research Use Only")

    canvas.restoreState()


# ── Cover page builder ────────────────────────────────────────────────────────
def _cover_page(styles, city: str, ds, de, stats: dict) -> list:
    W, H = A4
    story = []

    # Gradient cover rectangle is drawn via canvas callback (handled in template).
    # We use a full-width coloured Table as a stand-in inside platypus.

    def _fmt(d):
        return d.strftime("%d %B %Y") if isinstance(d, date) else str(d)

    # Use actual data date range if available (prevents start>end display bug)
    act_start = stats.get("actual_start")
    act_end   = stats.get("actual_end")
    if act_start: date_start = act_start
    if act_end:   date_end   = act_end

    cover_data = [[
        Paragraph("🌍", ParagraphStyle("ico", fontName="Helvetica", fontSize=48,
                                        alignment=TA_CENTER, textColor=_WHITE)),
    ]]
    cover_tbl = Table(cover_data, colWidths=[A4[0] - 4 * cm])
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _DARK_NAVY),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 36),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [12]),
    ]))
    story.append(cover_tbl)
    story.append(Spacer(1, 0.4 * cm))

    title_block_data = [[
        Paragraph("Climate Sentiment Analysis Report", styles["cover_title"]),
    ],[
        Paragraph("Powered by VADER NLP · Hybrid Lexical Analysis · FLAN-T5 AI Explanations",
                  styles["cover_sub"]),
    ],[
        Paragraph(
            f"<b>City / Region:</b> {city}  &nbsp;·&nbsp;  "
            f"<b>Period:</b> {_fmt(ds)} — {_fmt(de)}",
            styles["cover_meta"],
        ),
    ],[
        Paragraph(
            f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M')}",
            styles["cover_meta"],
        ),
    ]]
    title_tbl = Table(title_block_data, colWidths=[A4[0] - 4 * cm])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _DARK_NAVY),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
    ]))
    story.append(title_tbl)
    story.append(Spacer(1, 0.8 * cm))

    # KPI summary row
    pos = stats.get("positive", 0)
    neg = stats.get("negative", 0)
    neu = stats.get("neutral", 0)
    tot = stats.get("total", 0)
    pp  = stats.get("pos_pct", 0)
    np_ = stats.get("neg_pct", 0)
    nup = stats.get("neu_pct", 0)
    avg = stats.get("avg_score", 0)

    kpi_vals = [
        (str(tot),        "Total Tweets",      _MID_BLUE),
        (f"{pos} ({pp}%)", "Positive",          _GREEN),
        (f"{neg} ({np_}%)", "Negative",         _RED),
        (f"{neu} ({nup}%)", "Neutral",          _AMBER),
        (str(avg),        "Avg VADER Score",    _TEAL),
        (str(stats.get("cities_n", 0)), "Cities Covered", _PURPLE),
    ]

    kpi_cells   = [[Paragraph(v, ParagraphStyle(
        "kpiv", fontName="Helvetica-Bold", fontSize=14,
        textColor=c, alignment=TA_CENTER)) for v, _, c in kpi_vals]]
    label_cells = [[Paragraph(l, ParagraphStyle(
        "kpil", fontName="Helvetica", fontSize=7.5,
        textColor=colors.HexColor("#6B7280"), alignment=TA_CENTER))
                    for _, l, _ in kpi_vals]]

    kpi_tbl = Table(
        kpi_cells + label_cells,
        colWidths=[(A4[0] - 4 * cm) / 6] * 6,
    )
    kpi_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _VERY_LIGHT),
        ("BOX",           (0, 0), (-1, -1), 1, _BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, _BORDER),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROUNDEDCORNERS", [10]),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 0.6 * cm))

    # Insight chips row
    top_city    = stats.get("top_city",    "—")
    top_topic   = stats.get("top_topic",   "—")
    top_emotion = stats.get("top_emotion", "—")

    chip_data = [[
        Paragraph(f"🏙️ Top City<br/><b>{top_city}</b>",
                  ParagraphStyle("c", fontName="Helvetica", fontSize=9,
                                  textColor=_TEXT_DARK, alignment=TA_CENTER, leading=14)),
        Paragraph(f"🔑 Top Topic<br/><b>{top_topic}</b>",
                  ParagraphStyle("c", fontName="Helvetica", fontSize=9,
                                  textColor=_TEXT_DARK, alignment=TA_CENTER, leading=14)),
        Paragraph(f"🎭 Dominant Emotion<br/><b>{top_emotion}</b>",
                  ParagraphStyle("c", fontName="Helvetica", fontSize=9,
                                  textColor=_TEXT_DARK, alignment=TA_CENTER, leading=14)),
        Paragraph(f"📅 Analysis Span<br/><b>{stats.get('span_days', 0)} days</b>",
                  ParagraphStyle("c", fontName="Helvetica", fontSize=9,
                                  textColor=_TEXT_DARK, alignment=TA_CENTER, leading=14)),
    ]]
    chip_tbl = Table(chip_data, colWidths=[(A4[0] - 4 * cm) / 4] * 4)
    chip_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _LIGHT_GREY),
        ("BOX",           (0, 0), (-1, -1), 1, _BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, _BORDER),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(chip_tbl)
    story.append(PageBreak())
    return story


# ── Table of Contents builder ─────────────────────────────────────────────────
def _toc_page(styles, chart_keys: list) -> list:
    story = []
    story.append(Spacer(1, 1 * cm))
    hdr = Table(
        [[Paragraph("Table of Contents", ParagraphStyle(
            "toch", fontName="Helvetica-Bold", fontSize=18,
            textColor=_WHITE, alignment=TA_LEFT))]],
        colWidths=[A4[0] - 4 * cm],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _DARK_NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [10]),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.5 * cm))

    entries = [
        ("Executive Summary", "KPI metrics and overview statistics"),
    ]
    for idx, key in enumerate(chart_keys, start=2):
        entries.append((
            f"Section {idx}: {_chart_label(key)}",
            f"{_chart_icon(key)} Graph + AI-generated explanation",
        ))

    for title, subtitle in entries:
        row_data = [[
            Paragraph(f"• {title}", styles["toc_entry"]),
            Paragraph(subtitle, ParagraphStyle(
                "toc_s", fontName="Helvetica", fontSize=9,
                textColor=colors.HexColor("#6B7280"))),
        ]]
        row = Table(row_data, colWidths=[9 * cm, A4[0] - 4 * cm - 9 * cm])
        row.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW",     (0, 0), (-1, -1), 0.4, _BORDER),
        ]))
        story.append(row)

    story.append(PageBreak())
    return story


# ── Executive summary builder ─────────────────────────────────────────────────
def _exec_summary(styles, stats: dict, city: str, ds, de) -> list:
    def _fmt(d):
        return d.strftime("%d %B %Y") if isinstance(d, date) else str(d)

    story = []
    story.append(Spacer(1, 1 * cm))
    hdr = Table([[
        Paragraph("Section 1: Executive Summary", ParagraphStyle(
            "sh", fontName="Helvetica-Bold", fontSize=16,
            textColor=_WHITE, alignment=TA_LEFT)),
    ]], colWidths=[A4[0] - 4 * cm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _DARK_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [10]),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.4 * cm))

    rows = [
        ("City / Region Analysed",  city,                             _MID_BLUE),
        ("Analysis Period",         f"{_fmt(ds)}  →  {_fmt(de)}",     _TEAL),
        ("Total Tweets",            f"{stats.get('total', 0):,}",      _MID_BLUE),
        ("Positive Tweets",         f"{stats.get('positive', 0):,}  ({stats.get('pos_pct', 0)}%)", _GREEN),
        ("Negative Tweets",         f"{stats.get('negative', 0):,}  ({stats.get('neg_pct', 0)}%)", _RED),
        ("Neutral Tweets",          f"{stats.get('neutral', 0):,}  ({stats.get('neu_pct', 0)}%)",  _AMBER),
        ("Average VADER Score",     str(stats.get("avg_score", 0)),    _TEAL),
        ("Cities Covered",          str(stats.get("cities_n", 0)),     _PURPLE),
        ("Top City by Volume",      stats.get("top_city", "—"),        _MID_BLUE),
        ("Dominant Emotion",        stats.get("top_emotion", "—"),     _PURPLE),
        ("Most Discussed Topic",    stats.get("top_topic", "—"),       _RED),
        ("Average Words / Tweet",   str(stats.get("avg_words", 0)),    _TEAL),
        ("Active Day Span",         f"{stats.get('span_days', 0)} days", _MID_BLUE),
    ]

    tbl_data = []
    for metric, value, col in rows:
        tbl_data.append([
            Paragraph(metric, ParagraphStyle(
                "m", fontName="Helvetica-Bold", fontSize=9.5,
                textColor=_TEXT_DARK)),
            Paragraph(value, ParagraphStyle(
                "v", fontName="Helvetica", fontSize=9.5,
                textColor=col)),
        ])

    tbl = Table(tbl_data, colWidths=[9 * cm, A4[0] - 4 * cm - 9 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",       (0, 0), (-1, -1), _WHITE),
        ("ROWBACKGROUNDS",   (0, 0), (-1, -1), [_WHITE, _VERY_LIGHT]),
        ("BOX",              (0, 0), (-1, -1), 1.2, _BORDER),
        ("INNERGRID",        (0, 0), (-1, -1), 0.5, _BORDER),
        ("TOPPADDING",       (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING",    (0, 0), (-1, -1), 9),
        ("LEFTPADDING",      (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",     (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS",   [10]),
    ]))
    story.append(tbl)
    story.append(PageBreak())
    return story


# ── Single chart section builder ──────────────────────────────────────────────
def _chart_section(
    styles,
    section_idx: int,
    chart_key: str,
    png_bytes: bytes,
    explanation: str,
    page_width: float,
) -> list:
    story = []
    story.append(Spacer(1, 0.8 * cm))

    label = _chart_label(chart_key)
    icon  = _chart_icon(chart_key)

    # Section header bar
    hdr = Table([[
        Paragraph(
            f"Section {section_idx}: {icon}  {label}",
            ParagraphStyle("sh", fontName="Helvetica-Bold", fontSize=15,
                           textColor=_WHITE, alignment=TA_LEFT),
        ),
    ]], colWidths=[page_width])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _DARK_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 13),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [10]),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.35 * cm))

    # Chart image
    try:
        img_buf = io.BytesIO(png_bytes)
        img = Image(img_buf, width=page_width, height=page_width * 0.55)
        img.hAlign = "CENTER"
        img_wrapper = Table(
            [[img]],
            colWidths=[page_width],
        )
        img_wrapper.setStyle(TableStyle([
            ("BOX",           (0, 0), (-1, -1), 1, _BORDER),
            ("BACKGROUND",    (0, 0), (-1, -1), _WHITE),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("ROUNDEDCORNERS", [8]),
        ]))
        story.append(img_wrapper)
    except Exception as exc:
        story.append(Paragraph(
            f"[Chart image unavailable: {exc}]",
            ParagraphStyle("err", fontName="Helvetica", fontSize=9,
                           textColor=_RED),
        ))

    story.append(Spacer(1, 0.3 * cm))

    # AI explanation badge
    ai_badge = Table([[
        Paragraph(
            "🤖  AI-Generated Explanation  (FLAN-T5 Small)",
            ParagraphStyle("aib", fontName="Helvetica-Bold", fontSize=8.5,
                           textColor=_WHITE),
        ),
    ]], colWidths=[page_width])
    ai_badge.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#7C3AED")),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(ai_badge)

    # Explanation text box
    expl_text = explanation or "No explanation was generated for this chart."
    expl_box = Table([[
        Paragraph(expl_text, styles["explanation"]),
    ]], colWidths=[page_width])
    expl_box.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FAF5FF")),
        ("BOX",           (0, 0), (-1, -1), 1, colors.HexColor("#DDD6FE")),
        ("TOPPADDING",    (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(expl_box)
    story.append(PageBreak())
    return story


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def generate_pdf(
    output_path: str,
    stats: dict,
    city: str,
    date_start,
    date_end,
    chart_bytes: Dict[str, bytes],
    explanations: Optional[Dict[str, str]] = None,
) -> tuple[bool, str]:
    """
    Generate the full PDF report.

    Parameters
    ----------
    output_path  : str  — destination file path (.pdf)
    stats        : dict — from data_manager.compute_stats()
    city         : str
    date_start   : date
    date_end     : date
    chart_bytes  : dict — { chart_key: PNG bytes }
    explanations : dict — { chart_key: explanation_text } | None

    Returns
    -------
    (True, success_message) | (False, error_message)
    """
    if explanations is None:
        explanations = {}

    try:
        W, H = A4
        margin = 2 * cm
        page_content_width = W - 2 * margin

        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=margin,
            rightMargin=margin,
            topMargin=3 * cm,      # space for header on non-cover pages
            bottomMargin=2 * cm,   # space for footer
            title="ClimateIQ — Climate Sentiment Report",
            author="ClimateIQ v3.0",
        )

        styles = _build_styles()
        story  = []

        # 1. Cover page
        story += _cover_page(styles, city, date_start, date_end, stats)

        # 2. Table of contents
        chart_keys = list(chart_bytes.keys())
        story += _toc_page(styles, chart_keys)

        # 3. Executive summary
        story += _exec_summary(styles, stats, city, date_start, date_end)

        # 4. Dynamic chart sections — one per chart, no hardcoding
        for section_idx, key in enumerate(chart_keys, start=2):
            png   = chart_bytes.get(key, b"")
            expl  = explanations.get(key, "")
            story += _chart_section(
                styles, section_idx, key, png, expl, page_content_width
            )

        # Build the document
        doc.build(
            story,
            onFirstPage=_on_first_page,
            onLaterPages=_on_later_pages,
        )

        return True, (
            f"PDF report saved successfully.\n\n"
            f"Path: {output_path}\n"
            f"Charts included: {len(chart_keys)}\n"
            f"AI explanations: {len(explanations)}"
        )

    except Exception:
        return False, traceback.format_exc()
