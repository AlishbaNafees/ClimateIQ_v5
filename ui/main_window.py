"""
ui/main_window.py  —  ClimateIQ v5  (AI Explanations + Dynamic PDF)
═════════════════════════════════════════════════════════════════════

Changes over v3
───────────────
1. _PdfWorker now calls generate_all_explanations() via FLAN-T5 Small
   BEFORE calling generate_pdf(), so every chart gets a paragraph-length
   AI explanation in the PDF.

2. An _AiWorker / _AiThread pair runs the FLAN-T5 inference off the main
   thread with a live progress overlay so the UI never freezes.

3. The PDF generation flow is:
       User clicks "Export PDF"
           ↓
       _AiThread  — FLAN-T5 generates explanations for ALL charts
           ↓
       _PdfThread — ReportLab builds the PDF with charts + explanations
           ↓
       Success / error dialog

4. All other GUI code is UNCHANGED from v3.
"""

from __future__ import annotations
from datetime import date, datetime
from typing   import Optional, Dict

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QScrollArea, QSizePolicy,
    QFileDialog, QMessageBox,
    QComboBox, QDateEdit, QSpacerItem,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore  import (
    Qt, QDate, QThread, pyqtSignal, QObject,
    QTimer, QRectF,
)
from PyQt6.QtGui   import (
    QFont, QColor, QPainter, QPen, QBrush,
    QLinearGradient, QPainterPath, QPaintEvent,
)

from core.db_manager import db_manager as data_manager
from core.chart_engine  import generate_all_charts
from core.pdf_reporter  import generate_pdf
from ui.widgets import (
    D, shadow, FadeWidget, StatCard, RippleButton,
    ChartCanvas, LoadingOverlay, SectionHeader, PulseIndicator,
)


# ══════════════════════════════════════════════════════════════════════════════
#  WORKER: ANALYSIS  (unchanged from v3)
# ══════════════════════════════════════════════════════════════════════════════
class _Worker(QObject):
    done = pyqtSignal(object, object, object)
    err  = pyqtSignal(str)

    def __init__(self, city, s, e):
        super().__init__()
        self._city = city; self._s = s; self._e = e

    def run(self):
        try:
            df = data_manager.filter_data(self._city, self._s, self._e, limit=3_000_000)
            stats  = data_manager.compute_stats(df)
            charts = generate_all_charts(df)
            self.done.emit(df, stats, charts)
        except Exception:
            import traceback
            self.err.emit(traceback.format_exc())


class _WThread(QThread):
    def __init__(self, worker):
        super().__init__()
        self._w = worker
        self._w.moveToThread(self)
        self.started.connect(self._w.run)


# ══════════════════════════════════════════════════════════════════════════════
#  WORKER: AI EXPLANATIONS  (NEW)
# ══════════════════════════════════════════════════════════════════════════════
class _AiWorker(QObject):
    """
    Runs FLAN-T5 inference off the main thread.
    Emits progress(current, total, chart_key) after each chart,
    then done(explanations_dict) or err(traceback_str).
    """
    progress = pyqtSignal(int, int, str)
    done     = pyqtSignal(dict)
    err      = pyqtSignal(str)

    def __init__(self, charts, stats, df, city, ds, de):
        super().__init__()
        self._charts = charts
        self._stats  = stats
        self._df     = df
        self._city   = city
        self._ds     = ds
        self._de     = de

    def run(self):
        try:
            from core.ai_explainer import generate_all_explanations

            def _cb(idx, total, key):
                self.progress.emit(idx, total, key)

            explanations = generate_all_explanations(
                self._charts, self._stats, self._df,
                self._city, self._ds, self._de,
                progress_callback=_cb,
            )
            self.done.emit(explanations)
        except Exception:
            import traceback
            self.err.emit(traceback.format_exc())


class _AiThread(QThread):
    def __init__(self, worker: _AiWorker):
        super().__init__()
        self._w = worker
        self._w.moveToThread(self)
        self.started.connect(self._w.run)


# ══════════════════════════════════════════════════════════════════════════════
#  WORKER: PDF GENERATION  (updated — receives explanations)
# ══════════════════════════════════════════════════════════════════════════════
class _PdfWorker(QObject):
    done = pyqtSignal(bool, str)

    def __init__(self, path, stats, city, ds, de, chart_bytes, explanations):
        super().__init__()
        self._path         = path
        self._stats        = stats
        self._city         = city
        self._ds           = ds
        self._de           = de
        self._chart_bytes  = chart_bytes
        self._explanations = explanations

    def run(self):
        try:
            ok, msg = generate_pdf(
                self._path, self._stats,
                self._city, self._ds, self._de,
                self._chart_bytes,
                self._explanations,
            )
            self.done.emit(ok, msg)
        except Exception:
            import traceback
            self.done.emit(False, traceback.format_exc())


class _PdfThread(QThread):
    def __init__(self, worker: _PdfWorker):
        super().__init__()
        self._w = worker
        self._w.moveToThread(self)
        self.started.connect(self._w.run)


# ══════════════════════════════════════════════════════════════════════════════
#  CUSTOM PAINTED WIDGETS  (unchanged from v3)
# ══════════════════════════════════════════════════════════════════════════════
class _HeaderBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(66)

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        g = QLinearGradient(0, 0, W, 0)
        g.setColorAt(0,    QColor("#2E1065"))
        g.setColorAt(0.35, QColor("#4C1D95"))
        g.setColorAt(0.7,  QColor("#7C3AED"))
        g.setColorAt(1,    QColor("#1D4ED8"))
        p.fillRect(0, 0, W, H, QColor(D.navy0))
        p.setBrush(QBrush(g)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(0, 0, W, H)
        ag = QLinearGradient(0, H - 2, W, H - 2)
        ag.setColorAt(0,   QColor(D.navy4))
        ag.setColorAt(0.5, QColor(D.blue2))
        ag.setColorAt(1,   QColor(D.blue3))
        p.setBrush(QBrush(ag)); p.drawRect(0, H - 2, W, 2)
        p.end()


class _SidebarFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(272)

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        W, H = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0,   QColor("#022C22"))
        g.setColorAt(0.6, QColor("#064E3B"))
        g.setColorAt(1,   QColor("#065F46"))
        p.fillRect(0, 0, W, H, QColor(D.navy0))
        p.setBrush(QBrush(g)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(0, 0, W, H)
        rg = QLinearGradient(W - 3, 0, W, 0)
        rg.setColorAt(0, QColor(D.blue2 + "30"))
        rg.setColorAt(1, QColor("#00000000"))
        p.setBrush(QBrush(rg)); p.drawRect(W - 3, 0, 3, H)
        p.end()


def _sec(text):
    l = QLabel(text)
    l.setStyleSheet(
        f"font-size:7.5pt; font-weight:700; color:{D.blue4};"
        "background:transparent; padding:10px 0 4px 0; letter-spacing:0.8px;"
    )
    return l

def _lbl(text):
    l = QLabel(text)
    l.setStyleSheet(
        f"font-size:9pt; color:{D.inkW3}; background:transparent; padding:1px 0;"
    )
    return l

def _div():
    d = QFrame()
    d.setFixedHeight(1)
    d.setStyleSheet(
        "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        f"stop:0 {D.navy2}, stop:0.5 {D.blue2}44, stop:1 {D.navy2});"
        "border:none; margin:5px 0;"
    )
    return d


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🌍  ClimateIQ  —  Climate Sentiment Dashboard")
        self.setMinimumSize(1300, 800)
        self.resize(1460, 900)

        self._df            = None
        self._stats         = {}
        self._bytes         = {}
        self._charts        = {}       # full chart dict (for AI worker)
        self._explanations  = {}       # AI explanations cache
        self._thread: Optional[_WThread]   = None
        self._ai_thread: Optional[_AiThread] = None
        self._pdf_thread: Optional[_PdfThread] = None

        central = QWidget()
        central.setStyleSheet("background: #EFF6FF;")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_content(), 1)
        root.addLayout(body, 1)

        root.addWidget(self._build_statusbar())

        self._overlay = LoadingOverlay(central)
        self._overlay.hide()

        clk = QTimer(self)
        clk.setInterval(1000)
        clk.timeout.connect(self._tick_clock)
        clk.start()

        # ── Auto-initialise the embedded SQLite database on startup ──────────
        QTimer.singleShot(200, self._init_database)

    # ═══════════════════════════════════════════════════════════════════════
    #  HEADER  (unchanged)
    # ═══════════════════════════════════════════════════════════════════════
    def _build_header(self) -> QWidget:
        hdr = _HeaderBar()
        hl  = QHBoxLayout(hdr)
        hl.setContentsMargins(0, 0, 20, 0)
        hl.setSpacing(0)

        logo_wrap = QFrame()
        logo_wrap.setFixedWidth(272)
        logo_wrap.setStyleSheet("background:transparent; border:none;")
        lw = QHBoxLayout(logo_wrap)
        lw.setContentsMargins(20, 0, 0, 0)
        lw.setSpacing(10)
        lw.addWidget(QLabel("🌡️", styleSheet="font-size:24px; background:transparent;"))
        ltxt = QVBoxLayout()
        ltxt.setSpacing(0)
        ltxt.addWidget(QLabel("ClimateIQ", styleSheet=
            "font-size:15pt; font-weight:800; color:#FFFFFF; background:transparent;"))
        ltxt.addWidget(QLabel("Sentiment Intelligence Platform", styleSheet=
            f"font-size:7.5pt; color:{D.inkW3}; background:transparent;"))
        lw.addLayout(ltxt)
        hl.addWidget(logo_wrap)

        sep = QFrame(); sep.setFixedSize(1, 38)
        sep.setStyleSheet(f"background:{D.navy4}55; border:none;")
        hl.addWidget(sep)

        tv = QVBoxLayout(); tv.setContentsMargins(22, 0, 0, 0); tv.setSpacing(1)
        tv.addWidget(QLabel("Advanced Climate Sentiment Analysis Dashboard", styleSheet=
            "font-size:16pt; font-weight:800; color:#FFFFFF; background:transparent;"))
        tv.addWidget(QLabel(
            "VADER NLP  ·  Lexical Analysis  ·  Multi-City  ·  FLAN-T5 AI  ·  PyQt6 + Matplotlib",
            styleSheet=f"font-size:8.5pt; color:{D.inkW3}; background:transparent;"))
        hl.addLayout(tv)
        hl.addStretch()

        self._badge = QLabel("◉  Ready")
        self._badge.setStyleSheet(self._badge_style("#4ADE80"))
        hl.addWidget(self._badge)
        hl.addSpacerItem(QSpacerItem(14, 0))

        cv = QVBoxLayout(); cv.setSpacing(1)
        cv.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._clk_lbl = QLabel(datetime.now().strftime("%H:%M:%S"))
        self._clk_lbl.setStyleSheet(
            "font-size:13pt; font-weight:700; color:#FFFFFF;"
            "background:transparent; letter-spacing:1px;")
        self._clk_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._date_lbl = QLabel(datetime.now().strftime("%d %B %Y"))
        self._date_lbl.setStyleSheet(
            f"font-size:8pt; color:{D.inkW3}; background:transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        cv.addWidget(self._clk_lbl); cv.addWidget(self._date_lbl)
        hl.addLayout(cv)
        return hdr

    def _badge_style(self, color):
        return (
            f"background:{D.navy3}; color:{color};"
            f"border:1px solid {color}44; border-radius:12px;"
            "font-size:8.5pt; font-weight:700; padding:5px 14px;"
        )

    def _tick_clock(self):
        self._clk_lbl.setText(datetime.now().strftime("%H:%M:%S"))

    # ═══════════════════════════════════════════════════════════════════════
    #  SIDEBAR  (unchanged except for "Export PDF" button label tweak)
    # ═══════════════════════════════════════════════════════════════════════
    def _build_sidebar(self) -> QWidget:
        sb = _SidebarFrame()
        vb = QVBoxLayout(sb)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background:transparent; border:none; }"
            "QScrollBar:vertical { background:#ffffff; width:5px; border-radius:3px; }"
            "QScrollBar::handle:vertical { background:#3B82F6; border-radius:3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
        )

        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(14, 10, 14, 14)
        iv.setSpacing(0)

        brand = QFrame()
        brand.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {D.navy3},stop:1 {D.navy4});"
            f"border:1px solid {D.blue2}44; border-radius:14px;")
        bl = QVBoxLayout(brand); bl.setContentsMargins(14, 12, 14, 14); bl.setSpacing(4)
        gi = QLabel("🌍"); gi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gi.setStyleSheet("font-size:34px; background:transparent;")
        bl.addWidget(gi)
        bh = QLabel("Climate Analysis"); bh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bh.setStyleSheet(f"font-size:11pt; font-weight:700; color:{D.blue7}; background:transparent;")
        bs = QLabel("Sentiment Intelligence v5.0"); bs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bs.setStyleSheet(f"font-size:8pt; color:{D.inkW3}; background:transparent;")
        bl.addWidget(bh); bl.addWidget(bs)
        iv.addWidget(brand)
        iv.addSpacerItem(QSpacerItem(0, 10))

        iv.addWidget(_sec("🗄️   DATA SOURCE"))
        self._db_info = QLabel("Connecting to database…")
        self._db_info.setWordWrap(True)
        self._db_info.setStyleSheet(
            f"font-size:8pt; color:{D.inkW3}; background:{D.navy3};"
            f"border:1px solid {D.navy4}; border-radius:9px;"
            "padding:7px 10px; margin-bottom:6px;")
        iv.addWidget(self._db_info)
        iv.addSpacerItem(QSpacerItem(0, 8)); iv.addWidget(_div())

        iv.addWidget(_sec("🔍   FILTERS"))
        iv.addWidget(_lbl("City / Region"))
        self._city_combo = QComboBox()
        self._city_combo.addItem("All Cities")
        iv.addWidget(self._city_combo)
        iv.addSpacerItem(QSpacerItem(0, 6))
        iv.addWidget(_lbl("Start Date"))
        self._d_start = QDateEdit()
        self._d_start.setCalendarPopup(True)
        self._d_start.setDate(QDate.currentDate().addYears(-1))
        self._d_start.setDisplayFormat("yyyy-MM-dd")
        iv.addWidget(self._d_start)
        iv.addSpacerItem(QSpacerItem(0, 4))
        iv.addWidget(_lbl("End Date"))
        self._d_end = QDateEdit()
        self._d_end.setCalendarPopup(True)
        self._d_end.setDate(QDate.currentDate())
        self._d_end.setDisplayFormat("yyyy-MM-dd")
        iv.addWidget(self._d_end)
        iv.addSpacerItem(QSpacerItem(0, 12))

        self._btn_analyse = RippleButton("Run Analysis", "🔍", c1="#059669", c2="#047857", h=44, fs=10)
        self._btn_analyse.clicked.connect(self._on_analyse)
        iv.addWidget(self._btn_analyse)
        iv.addSpacerItem(QSpacerItem(0, 6))
        iv.addWidget(_div())

        iv.addWidget(_sec("📄   EXPORT"))
        self._btn_pdf = RippleButton("Export PDF + AI", "🤖", c1=D.purp, c2="#6D28D9", h=44, fs=10)
        self._btn_pdf.set_enabled(False)
        self._btn_pdf.clicked.connect(self._on_pdf)
        iv.addWidget(self._btn_pdf)
        iv.addSpacerItem(QSpacerItem(0, 6))

        self._btn_reset = RippleButton("Reset Dashboard", "🔄", c1=D.navy2, c2=D.navy3, h=38, fs=9)
        self._btn_reset.clicked.connect(self._on_reset)
        iv.addWidget(self._btn_reset)
        iv.addSpacerItem(QSpacerItem(0, 10)); iv.addWidget(_div())

        iv.addWidget(_sec("📊   QUICK STATS"))
        self._qs: Dict[str, QLabel] = {}
        for key, label in [("total","Total Tweets"),("pos","Positive"),
                            ("neg","Negative"),("span","Date Span")]:
            iv.addWidget(_lbl(label))
            ql = QLabel("—")
            ql.setStyleSheet(
                f"font-size:10pt; font-weight:700; color:{D.inkW};"
                "background:transparent; padding:1px 0;")
            iv.addWidget(ql)
            self._qs[key] = ql
        iv.addStretch()
        scroll.setWidget(inner)
        vb.addWidget(scroll)
        return sb

    # ═══════════════════════════════════════════════════════════════════════
    #  CONTENT AREA  (unchanged from v3)
    # ═══════════════════════════════════════════════════════════════════════
    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setStyleSheet("background:transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background:transparent; border:none; }"
            "QScrollBar:vertical { background:#EFF6FF; width:7px; border-radius:4px; }"
            "QScrollBar::handle:vertical { background:#3B82F6; border-radius:4px; min-height:30px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
        )

        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(22, 18, 22, 22)
        iv.setSpacing(0)

        self._panel_welcome = self._build_welcome_panel()
        iv.addWidget(self._panel_welcome)

        self._panel_kpi = self._build_kpi_panel()
        self._panel_kpi.hide()
        iv.addWidget(self._panel_kpi)

        self._panel_chips = self._build_chips_panel()
        self._panel_chips.hide()
        iv.addWidget(self._panel_chips)

        self._panel_charts = self._build_charts_panel()
        self._panel_charts.hide()
        iv.addWidget(self._panel_charts)

        self._panel_table = self._build_table_panel()
        self._panel_table.hide()
        iv.addWidget(self._panel_table)

        scroll.setWidget(inner)
        cl.addWidget(scroll)
        return content

    def _build_welcome_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(panel)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.setSpacing(14)

        globe = QLabel("🌍")
        globe.setAlignment(Qt.AlignmentFlag.AlignCenter)
        globe.setStyleSheet("font-size:72px; background:transparent;")
        vl.addWidget(globe)

        h = QLabel("Welcome to ClimateIQ v5.0")
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setStyleSheet(f"font-size:22pt; font-weight:800; color:{D.navy2}; background:transparent;")
        vl.addWidget(h)

        s = QLabel(
            "Load a CSV file  →  Select filters  →  Run Analysis\n"
            "FLAN-T5 AI will explain every chart automatically."
        )
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setStyleSheet(f"font-size:11pt; color:{D.ink4}; background:transparent;")
        vl.addWidget(s)
        return panel

    def _build_kpi_panel(self) -> QWidget:
        panel = QWidget(); panel.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(panel); vl.setContentsMargins(0, 0, 0, 12); vl.setSpacing(8)
        vl.addWidget(SectionHeader(
            "Key Performance Indicators", "Real-time climate sentiment metrics", "📊"))
        hl = QHBoxLayout(); hl.setSpacing(14)
        configs = [
            ("Total Tweets",      "📝", D.blue2, D.blue8),
            ("Positive",          "😊", D.pos,   D.posL),
            ("Negative",          "😟", D.neg,   D.negL),
            ("Neutral",           "😐", D.neu,   D.neuL),
            ("Cities",            "🏙️", D.purp,  D.purpL),
            ("Avg Score",         "📈", D.teal,  D.tealL),
        ]
        self._stat_cards = []
        for title, icon, accent, bg in configs:
            card = StatCard(title, icon, accent, bg)
            hl.addWidget(card, 1)
            self._stat_cards.append(card)
        vl.addLayout(hl)
        return panel

    def _build_chips_panel(self) -> QWidget:
        panel = QWidget(); panel.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(panel); vl.setContentsMargins(0, 0, 0, 12); vl.setSpacing(8)
        vl.addWidget(SectionHeader("Key Insights", "Dominant patterns detected", "💡"))
        self._chips_hl = QHBoxLayout(); self._chips_hl.setSpacing(14)
        vl.addLayout(self._chips_hl)
        return panel

    def _build_charts_panel(self) -> QWidget:
        panel = QWidget(); panel.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(panel); cv.setContentsMargins(0, 0, 0, 12); cv.setSpacing(8)

        cv.addWidget(SectionHeader(
            "Sentiment & Emotion Analysis",
            "Donut distribution and emotion category breakdown", "🎯"))
        rA = QHBoxLayout(); rA.setSpacing(18)
        self._c_donut   = ChartCanvas("Sentiment Distribution")
        self._c_emotion = ChartCanvas("Emotion Analysis")
        self._c_donut.setMinimumHeight(430)
        self._c_emotion.setMinimumHeight(430)
        rA.addWidget(self._c_donut, 1); rA.addWidget(self._c_emotion, 2)
        cv.addLayout(rA); cv.addSpacing(8)

        cv.addWidget(SectionHeader(
            "Topic & Weather Distribution",
            "Most-discussed climate topics and weather-linked activity", "🌤️"))
        rB = QHBoxLayout(); rB.setSpacing(18)
        self._c_topic   = ChartCanvas("Climate Topic Frequency")
        self._c_weather = ChartCanvas("Tweet Volume by Weather Condition")
        self._c_topic.setMinimumHeight(430)
        self._c_weather.setMinimumHeight(430)
        rB.addWidget(self._c_topic, 1); rB.addWidget(self._c_weather, 1)
        cv.addLayout(rB); cv.addSpacing(8)

        cv.addWidget(SectionHeader(
            "Geographic Sentiment Comparison",
            "City-by-city breakdown of Positive / Neutral / Negative", "🗺️"))
        self._c_city = ChartCanvas("City vs Sentiment  (Clustered Bars)")
        self._c_city.setMinimumHeight(450)
        cv.addWidget(self._c_city); cv.addSpacing(8)

        cv.addWidget(SectionHeader(
            "Score Distribution & Temporal Activity",
            "Raw VADER score spread and daily tweet volume over time", "📈"))
        self._c_score = ChartCanvas("VADER Score Distribution")
        self._c_score.setMinimumHeight(430)
        cv.addWidget(self._c_score); cv.addSpacing(8)

        self._c_daily = ChartCanvas("Daily Tweet Activity  /  Word-Count Trend")
        self._c_daily.setMinimumHeight(430)
        cv.addWidget(self._c_daily)
        return panel

    def _build_table_panel(self) -> QWidget:
        panel = QWidget(); panel.setStyleSheet("background:transparent;")
        tv = QVBoxLayout(panel); tv.setContentsMargins(0, 0, 0, 0); tv.setSpacing(8)
        tv.addWidget(SectionHeader(
            "Analysis Summary Table", "Key metrics from the filtered dataset", "📋"))
        self._stats_table = self._build_table_widget()
        tv.addWidget(self._stats_table)
        return panel

    def _build_table_widget(self) -> QTableWidget:
        t = QTableWidget()
        t.setStyleSheet(
            f"QTableWidget {{ background:{D.white}; border:1.5px solid {D.border};"
            "border-radius:16px; gridline-color:#EFF6FF;"
            "alternate-background-color:#FAFCFF; }}"
            f"QTableWidget::item {{ border:none; }}"
            f"QTableWidget::item:selected {{ background:{D.blue8}; color:{D.navy2}; }}"
            f"QHeaderView::section {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            f"stop:0 {D.navy2},stop:1 {D.navy3}); color:white; font-weight:700;"
            "font-size:9.5pt; padding:9px 16px; border:none;"
            f"border-right:1px solid {D.navy4}; }}")
        t.setAlternatingRowColors(True)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setMinimumHeight(300)
        shadow(t, 16, 4, "#0A1C5018")
        return t

    def _build_statusbar(self) -> QFrame:
        bar = QFrame(); bar.setFixedHeight(34)
        bar.setStyleSheet(f"QFrame {{ background:{D.white}; border-top:1px solid {D.border}; }}")
        hl = QHBoxLayout(bar); hl.setContentsMargins(20, 0, 20, 0); hl.setSpacing(8)
        self._pulse = PulseIndicator(D.pos, 10)
        hl.addWidget(self._pulse)
        self._st_lbl = QLabel("Ready  —  Load a CSV file to begin")
        self._st_lbl.setStyleSheet(f"font-size:9pt; color:{D.ink4}; background:transparent;")
        hl.addWidget(self._st_lbl); hl.addStretch()
        pl = QLabel("PyQt6  ·  Matplotlib  ·  Seaborn  ·  ReportLab  ·  FLAN-T5")
        pl.setStyleSheet(f"font-size:7.5pt; color:{D.ink5}; background:transparent;")
        hl.addWidget(pl)
        return bar

    def _set_status(self, msg: str, kind: str = "ok"):
        self._st_lbl.setText(msg)
        col_map = {"ok": "#4ADE80", "warn": "#FCD34D", "err": "#F87171"}
        col = col_map.get(kind, "#4ADE80")
        self._pulse.set_color(D.pos if kind == "ok" else D.neg if kind == "err" else D.neu)
        self._badge.setStyleSheet(self._badge_style(col))
        txt_map = {"ok": "◉  Ready", "warn": "◉  Processing", "err": "◉  Error"}
        self._badge.setText(txt_map.get(kind, "◉  Ready"))

    # ═══════════════════════════════════════════════════════════════════════
    #  EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════════════════

    def _init_database(self):
        """Auto-called on startup. Connects to the embedded SQLite database."""
        self._db_info.setText("⏳  Connecting to database…")
        ok, msg = data_manager.initialise()

        if not ok:
            self._db_info.setText(f"❌  {msg}")
            self._db_info.setStyleSheet(
                "font-size:8pt; color:#F87171;"
                f"background:{D.navy3}; border:1px solid #7F1D1D55;"
                "border-radius:9px; padding:7px 10px; margin-bottom:6px;")
            self._set_status("Database not found — run scripts/csv_to_sqlite.py", "err")
            return

        # Populate city combo
        self._city_combo.clear()
        self._city_combo.addItem("All Cities")
        for c in data_manager.city_list():
            self._city_combo.addItem(c)

        # Set date pickers to data range
        mn, mx = data_manager.date_range()
        self._d_start.setDate(QDate(mn.year, mn.month, mn.day))
        self._d_end.setDate(QDate(mx.year, mx.month, mx.day))

        # Update status label
        records_part = msg.split("—")[-1].strip() if "—" in msg else msg
        self._db_info.setText(f"✅  climate_data.db\n    {records_part}")
        self._db_info.setStyleSheet(
            "font-size:8pt; color:#4ADE80;"
            f"background:{D.navy3}; border:1px solid #16653555;"
            "border-radius:9px; padding:7px 10px; margin-bottom:6px;")
        self._set_status(msg, "ok")

    def _on_analyse(self):
        if not data_manager.is_loaded:
            QMessageBox.warning(self, "No Data",
                "Database is not connected.\n\n"
                "Run  scripts/csv_to_sqlite.py  to initialise the database,\n"
                "then restart the application."); return

        # Stop any previous analysis thread before starting a new one
        t = getattr(self, "_thread", None)
        if t is not None and t.isRunning():
            t.quit()
            t.wait(2000)
        self._thread = None
        self._wo     = None

        city = self._city_combo.currentText()
        qs   = self._d_start.date(); qe = self._d_end.date()
        ds   = date(qs.year(), qs.month(), qs.day())
        de   = date(qe.year(), qe.month(), qe.day())

        if ds > de:
            QMessageBox.warning(self, "Date Error", "Start date must be before end date."); return

        self._overlay.start("Filtering and analysing climate sentiment data…")
        self._btn_analyse.set_enabled(False)
        self._set_status("Analysing — please wait…", "warn")

        self._wo = _Worker(city, ds, de)
        self._wo.done.connect(self._on_done)
        self._wo.err.connect(self._on_err)
        self._thread = _WThread(self._wo)
        self._thread.start()

    def _on_done(self, df, stats, charts):
        self._overlay.stop()
        self._btn_analyse.set_enabled(True)

        if df.empty:
            QMessageBox.information(self, "No Results",
                                    "No records match the selected filters.")
            self._set_status("No results — adjust filters", "warn"); return

        self._df     = df
        self._stats  = stats
        self._charts = charts
        self._bytes  = {k: v[1] for k, v in charts.items()}
        self._explanations = {}   # clear stale explanations

        self._panel_welcome.hide()
        self._panel_kpi.show()
        self._panel_chips.show()
        self._panel_charts.show()
        self._panel_table.show()

        QTimer.singleShot(0,   lambda: self._fill_kpi(stats))
        QTimer.singleShot(80,  lambda: self._fill_chips(stats))
        QTimer.singleShot(160, lambda: self._render_charts(charts))
        QTimer.singleShot(320, lambda: self._fill_table(stats))
        QTimer.singleShot(400, lambda: self._btn_pdf.set_enabled(True))

        n = stats.get("total", 0)
        self._set_status(f"✅  Analysis complete  —  {n:,} records processed", "ok")

    def _on_err(self, msg):
        self._overlay.stop()
        self._btn_analyse.set_enabled(True)
        QMessageBox.critical(self, "Analysis Error", msg)
        self._set_status("❌  Error during analysis", "err")

    # ── KPI / chips / charts / table  (unchanged from v3) ──────────────────

    def _fill_kpi(self, s):
        vals = [
            (s.get("total",    0), ""),
            (s.get("positive", 0), ""),
            (s.get("negative", 0), ""),
            (s.get("neutral",  0), ""),
            (s.get("cities_n", 0), ""),
            (0,                    str(s.get("avg_score", 0))),
        ]
        for card, (val, txt) in zip(self._stat_cards, vals):
            card.set_value(val, text=txt)
        self._qs["total"].setText(f"{s.get('total', 0):,}")
        self._qs["pos"].setText(f"{s.get('positive', 0):,}  ({s.get('pos_pct', 0)}%)")
        self._qs["neg"].setText(f"{s.get('negative', 0):,}  ({s.get('neg_pct', 0)}%)")
        self._qs["span"].setText(f"{s.get('span_days', 0)} days")

    def _fill_chips(self, s):
        while self._chips_hl.count():
            item = self._chips_hl.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        items = [
            ("🏙️", "Top City",    s.get("top_city",    "—"), D.blue2,  D.blue8),
            ("🔥", "Top Topic",   s.get("top_topic",   "—"), D.neg,    D.negL),
            ("🎭", "Top Emotion", s.get("top_emotion", "—"), D.purp,   D.purpL),
            ("📊", "Avg Score",   str(s.get("avg_score", 0)), D.teal,  D.tealL),
            ("😊", "Positive %",  f"{s.get('pos_pct', 0)}%",  D.pos,   D.posL),
            ("😟", "Negative %",  f"{s.get('neg_pct', 0)}%",  D.neg,   D.negL),
        ]
        for ico, lbl, val, col, bg in items:
            chip = QFrame()
            chip.setStyleSheet(
                f"QFrame {{ background:{D.white}; border:1.5px solid {D.border};"
                "border-radius:14px; }}")
            shadow(chip, 8, 3, "#0A1C5018")
            cl = QVBoxLayout(chip); cl.setContentsMargins(14, 10, 14, 12); cl.setSpacing(3)
            tr = QHBoxLayout(); tr.setSpacing(5)
            tr.addWidget(QLabel(ico, styleSheet="font-size:13px; background:transparent;"))
            tl = QLabel(lbl)
            tl.setStyleSheet(
                f"font-size:7.5pt; font-weight:600; color:{D.ink4};"
                "background:transparent; letter-spacing:0.4px;")
            tr.addWidget(tl); tr.addStretch(); cl.addLayout(tr)
            vl = QLabel(str(val)); vl.setWordWrap(True)
            vl.setStyleSheet(f"font-size:13pt; font-weight:800; color:{col}; background:transparent;")
            cl.addWidget(vl)
            bot = QFrame(); bot.setFixedHeight(3)
            bot.setStyleSheet(
                f"QFrame {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {col},stop:1 {D.blue3}); border:none; }}")
            cl.addWidget(bot)
            self._chips_hl.addWidget(chip, 1)

    def _render_charts(self, charts):
        mapping = {
            "sentiment_donut":    (self._c_donut,   0),
            "emotion_bar":        (self._c_emotion, 50),
            "topic_frequency":    (self._c_topic,   100),
            "weather_breakdown":  (self._c_weather, 150),
            "city_comparison":    (self._c_city,    200),
            "score_distribution": (self._c_score,   250),
            "daily_activity":     (self._c_daily,   300),
        }
        for key, (canvas, delay) in mapping.items():
            if key in charts:
                canvas.set_figure(charts[key][0], delay=delay)

    def _fill_table(self, s):
        rows = [
            ("Total Tweets Analysed",   f"{s.get('total', 0):,}",                           D.blue2),
            ("Positive Tweets",         f"{s.get('positive',0):,}  ({s.get('pos_pct',0)}%)", D.pos),
            ("Negative Tweets",         f"{s.get('negative',0):,}  ({s.get('neg_pct',0)}%)", D.neg),
            ("Neutral Tweets",          f"{s.get('neutral', 0):,}  ({s.get('neu_pct',0)}%)", D.neu),
            ("Average Sentiment Score", str(s.get("avg_score", 0)),                          D.teal),
            ("Number of Cities",        str(s.get("cities_n",  0)),                          D.purp),
            ("Top City by Volume",      str(s.get("top_city",  "—")),                        D.blue2),
            ("Dominant Emotion",        str(s.get("top_emotion","—")),                       D.purp),
            ("Most Discussed Topic",    str(s.get("top_topic", "—")),                        D.neg),
            ("Analysis Date Span",      f"{s.get('span_days', 0)} days",                     D.teal),
            ("Avg Words per Tweet",     str(s.get("avg_words", 0)),                          D.neu),
        ]
        t = self._stats_table
        t.setRowCount(len(rows)); t.setColumnCount(2)
        t.setHorizontalHeaderLabels(["  Metric", "  Value"])
        for r, (metric, value, col) in enumerate(rows):
            t.setRowHeight(r, 42)
            mi = QTableWidgetItem(f"   {metric}")
            mi.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            mi.setForeground(QColor(col))
            vi = QTableWidgetItem(f"   {value}")
            vi.setFont(QFont("Segoe UI", 10))
            vi.setForeground(QColor(D.ink2))
            t.setItem(r, 0, mi); t.setItem(r, 1, vi)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

    # ═══════════════════════════════════════════════════════════════════════
    #  PDF EXPORT FLOW  (UPDATED — two-stage: AI → PDF)
    # ═══════════════════════════════════════════════════════════════════════

    def _on_pdf(self):
        if not self._stats:
            QMessageBox.warning(self, "No Data", "Run analysis first."); return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF Report",
            "Climate_Sentiment_Report.pdf",
            "PDF Files (*.pdf)")
        if not path: return

        self._pdf_output_path = path

        # Stage 1 — FLAN-T5 AI explanations
        self._overlay.start("🤖  Loading FLAN-T5 AI model…")
        self._btn_pdf.set_enabled(False)

        city = self._city_combo.currentText()
        qs = self._d_start.date(); qe = self._d_end.date()
        ds = date(qs.year(), qs.month(), qs.day())
        de = date(qe.year(), qe.month(), qe.day())
        self._pdf_city = city
        self._pdf_ds   = ds
        self._pdf_de   = de

        self._ai_wo = _AiWorker(
            self._charts, dict(self._stats), self._df, city, ds, de
        )
        self._ai_wo.progress.connect(self._on_ai_progress)
        self._ai_wo.done.connect(self._on_ai_done)
        self._ai_wo.err.connect(self._on_ai_err)
        self._ai_thread = _AiThread(self._ai_wo)
        self._ai_thread.start()

    def _on_ai_progress(self, idx: int, total: int, key: str):
        label = key.replace("_", " ").title()
        self._overlay.set_message(
            f"🤖  Generating AI explanation {idx + 1}/{total}: {label}…")

    def _on_ai_done(self, explanations: dict):
        self._explanations = explanations
        # Stage 2 — build PDF
        self._overlay.set_message("📄  Building PDF report…")

        self._pdf_worker = _PdfWorker(
            self._pdf_output_path,
            dict(self._stats),
            self._pdf_city,
            self._pdf_ds,
            self._pdf_de,
            dict(self._bytes),
            dict(explanations),
        )
        self._pdf_worker.done.connect(self._pdf_done)
        self._pdf_thread = _PdfThread(self._pdf_worker)
        self._pdf_thread.start()

    def _on_ai_err(self, msg: str):
        self._overlay.stop()
        self._btn_pdf.set_enabled(True)
        QMessageBox.critical(self, "AI Error",
            f"FLAN-T5 failed to generate explanations.\n\n{msg}\n\n"
            "Tip: run  pip install transformers torch sentencepiece")
        self._set_status("❌  AI explanation failed", "err")

    def _pdf_done(self, success: bool, msg: str):
        self._overlay.stop()
        self._btn_pdf.set_enabled(True)
        if success:
            self._set_status("✅  PDF report exported successfully", "ok")
            QMessageBox.information(self, "PDF Saved", msg)
        else:
            self._set_status("❌  PDF export failed", "err")
            QMessageBox.critical(self, "PDF Error", msg)

    # ── Reset ───────────────────────────────────────────────────────────────
    def _on_reset(self):
        # ── Safely stop any running analysis thread ───────────────────────────
        for attr in ("_thread", "_ai_thread", "_pdf_thread"):
            t = getattr(self, attr, None)
            if t is not None and t.isRunning():
                t.quit()
                t.wait(2000)
            setattr(self, attr, None)

        # ── Clear worker references ───────────────────────────────────────────
        for attr in ("_wo", "_ai_wo", "_pdf_worker"):
            setattr(self, attr, None)

        # ── Clear data state ──────────────────────────────────────────────────
        self._df           = None
        self._stats        = {}
        self._bytes        = {}
        self._charts       = {}
        self._explanations = {}

        # ── Clear all chart canvases (prevent stale figures on re-render) ─────
        for canvas in (self._c_donut, self._c_emotion, self._c_topic,
                       self._c_weather, self._c_city, self._c_score, self._c_daily):
            try:
                canvas.set_figure(None)
            except Exception:
                pass

        # ── Reset UI panels ───────────────────────────────────────────────────
        self._panel_kpi.hide()
        self._panel_chips.hide()
        self._panel_charts.hide()
        self._panel_table.hide()
        self._panel_welcome.show()

        # ── Reset overlay if stuck ────────────────────────────────────────────
        try:
            self._overlay.stop()
        except Exception:
            pass

        # ── Reset buttons and quick-stats ─────────────────────────────────────
        self._btn_analyse.set_enabled(True)
        self._btn_pdf.set_enabled(False)
        for lbl in self._qs.values():
            lbl.setText("—")

        self._set_status("Dashboard reset — ready for new analysis", "ok")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.centralWidget():
            self._overlay.resize(self.centralWidget().size())
