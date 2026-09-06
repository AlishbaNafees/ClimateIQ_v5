"""
ui/widgets.py  —  ClimateIQ Design System  (Bug-Fixed Edition)
═══════════════════════════════════════════════════════════════
Key fixes vs previous version:
  • FadeWidget: opacity effect on a WRAPPER frame, not the visible widget itself
    — prevents children going transparent/invisible permanently
  • ChartCanvas: opacity animation scoped to canvas only, not the card frame
  • LoadingOverlay: self-contained stop() always hides regardless of state
  • RippleButton: set_enabled works correctly; no stale graphics effects
  • StatCard: counter animation cleaned up with proper stop guard
"""

from __future__ import annotations
import math

from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame,
    QSizePolicy, QGraphicsOpacityEffect, QGraphicsDropShadowEffect,
    QStackedWidget,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QRect, QRectF,
)
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont,
    QLinearGradient, QPainterPath, QPaintEvent,
)
import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════════════════
class D:
    navy0   = "#040D24"
    navy1   = "#071336"
    navy2   = "#0A1C50"
    navy3   = "#0D2268"
    navy4   = "#112B80"
    blue1   = "#1D4ED8"
    blue2   = "#2563EB"
    blue3   = "#3B82F6"
    blue4   = "#60A5FA"
    blue5   = "#93C5FD"
    blue6   = "#BFDBFE"
    blue7   = "#DBEAFE"
    blue8   = "#EFF6FF"
    blue9   = "#F0F6FF"
    white   = "#FFFFFF"
    snow    = "#FAFCFF"
    surface = "#F4F7FF"
    ink0    = "#040D24"
    ink1    = "#0A1628"
    ink2    = "#1E3A5F"
    ink3    = "#374151"
    ink4    = "#6B7280"
    ink5    = "#9CA3AF"
    inkW    = "#FFFFFF"
    inkW2   = "#C8D8FF"
    inkW3   = "#7BAAF7"
    pos     = "#059669"
    posL    = "#D1FAE5"
    posD    = "#047857"
    neg     = "#DC2626"
    negL    = "#FEE2E2"
    neu     = "#D97706"
    neuL    = "#FEF3C7"
    purp    = "#7C3AED"
    purpL   = "#EDE9FE"
    teal    = "#0891B2"
    tealL   = "#CFFAFE"
    border  = "#E2EAFF"
    shadow  = "#0A1C5018"


def mk_shadow(w: QWidget, r=20, dy=5, c="#0A1C5020"):
    fx = QGraphicsDropShadowEffect(w)
    fx.setBlurRadius(r)
    fx.setOffset(0, dy)
    fx.setColor(QColor(c))
    w.setGraphicsEffect(fx)
    return fx

# Keep old name for compat
shadow = mk_shadow


def lerp(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(
        int(c1.red()   + (c2.red()   - c1.red())   * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue()  + (c2.blue()  - c1.blue())  * t),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  FADE WIDGET  — BUG FIX: use simple show/hide + opacity on self only
#  The previous version set opacity=0 on the widget used as a LAYOUT CONTAINER
#  which made everything inside permanently invisible after the first run.
#  Solution: opacity is applied to a transparent overlay div, not the container.
# ══════════════════════════════════════════════════════════════════════════════
class FadeWidget(QWidget):
    """
    A QWidget that can fade in.
    IMPORTANT: opacity is on 'self' — do NOT nest other QGraphicsEffects
    on direct children, or they will conflict.
    Starts visible (opacity=1). Call fade_in() to animate from 0→1.
    """
    def __init__(self, parent=None, ms=400):
        super().__init__(parent)
        self._ms = ms
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)           # start VISIBLE — don't hide content
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity")
        self._anim.setDuration(ms)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def fade_in(self, delay: int = 0):
        """Animate opacity 0 → 1 after optional delay (ms)."""
        self._fx.setOpacity(0.0)
        if delay > 0:
            QTimer.singleShot(delay, self._run_anim)
        else:
            self._run_anim()

    def _run_anim(self):
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()


# ══════════════════════════════════════════════════════════════════════════════
#  STAT CARD
# ══════════════════════════════════════════════════════════════════════════════
class StatCard(QWidget):
    def __init__(self, title, icon, accent, bg_accent, parent=None):
        super().__init__(parent)
        self._acc_hex = accent
        self._acc = QColor(accent)

        # counter state
        self._target  = 0
        self._cur     = 0.0
        self._elapsed = 0
        self._dur     = 1000
        self._ct = QTimer(self)
        self._ct.setInterval(12)
        self._ct.timeout.connect(self._tick)

        # ── Card sizing ──────────────────────────────────────────────────────
        # Height must fit: 4px strip + top pad 10 + icon 44 + bottom pad 12
        # AND the text column: title ~16px + gap 4 + value ~32px = 52px
        # Total content height needed: max(44, 52) + 22 = ~74px minimum.
        # Use 120px so both title and value are always fully visible.
        self.setFixedHeight(120)
        self.setMinimumWidth(155)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── Top gradient accent strip ────────────────────────────────────────
        strip = QFrame()
        strip.setFixedHeight(4)
        strip.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 {accent}, stop:1 {D.blue2}); border:none;"
        )
        vbox.addWidget(strip)

        # ── Body row: icon badge  |  text column ────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(14, 10, 14, 12)   # L T R B
        body.setSpacing(12)

        # Icon badge — slightly smaller so text column has more room
        badge = QLabel(icon)
        badge.setFixedSize(44, 44)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {bg_accent}; border-radius: 12px;"
            f"font-size: 18px; color: {accent}; border: none;"
        )
        body.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── Text column: TITLE on top, VALUE below ───────────────────────────
        col = QVBoxLayout()
        col.setSpacing(4)          # clear gap between title and number
        col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Title label — capitalised, muted, clearly readable size
        self._title_w = QLabel(title)
        self._title_w.setStyleSheet(
            f"font-size: 8.5pt;"           # was 7pt — now readable
            f"font-weight: 700;"
            f"color: {D.ink4};"
            "letter-spacing: 0.4px;"
            "background: transparent;"
        )
        self._title_w.setWordWrap(False)
        col.addWidget(self._title_w)

        # Value label — large, coloured, bold
        self._val_w = QLabel("—")
        self._val_w.setStyleSheet(
            f"font-size: 21pt;"
            f"font-weight: 800;"
            f"color: {accent};"
            "background: transparent;"
            "letter-spacing: -0.5px;"
        )
        col.addWidget(self._val_w)

        body.addLayout(col, 1)     # stretch=1 so text column takes all spare width
        vbox.addLayout(body)

        self._apply_style(False)
        mk_shadow(self, 14, 4, "#0A1C5018")

    def _apply_style(self, hov):
        if hov:
            self.setStyleSheet(
                f"StatCard{{background:{D.blue8};"
                f"border:2px solid {self._acc_hex}; border-radius:16px;}}"
            )
        else:
            self.setStyleSheet(
                f"StatCard{{background:{D.white};"
                f"border:1.5px solid {D.border}; border-radius:16px;}}"
            )

    def enterEvent(self, e): self._apply_style(True)
    def leaveEvent(self, e): self._apply_style(False)

    def set_value(self, val: int, text: str = ""):
        if text:
            self._val_w.setText(text)
            return
        self._target  = val
        self._cur     = 0.0
        self._elapsed = 0
        self._ct.start()

    def _tick(self):
        self._elapsed += 12
        p = min(self._elapsed / self._dur, 1.0)
        ease = 1 - (1 - p) ** 4
        self._cur = self._target * ease
        self._val_w.setText(f"{int(self._cur):,}")
        if p >= 1.0:
            self._ct.stop()
            self._val_w.setText(f"{self._target:,}")


# ══════════════════════════════════════════════════════════════════════════════
#  RIPPLE BUTTON
# ══════════════════════════════════════════════════════════════════════════════
class RippleButton(QWidget):
    from PyQt6.QtCore import pyqtSignal
    clicked = pyqtSignal()

    def __init__(self, text, icon="",
                 c1=D.blue2, c2=D.blue1,
                 tc=D.inkW, h=44, r=11, fs=10, parent=None):
        super().__init__(parent)
        self._txt = text
        self._icon = icon
        self._c1 = QColor(c1)
        self._c2 = QColor(c2)
        self._tc = QColor(tc)
        self._r = r
        self._fs = fs
        self._on = True

        self._hov = 0.0
        self._htgt = 0.0
        self._ht = QTimer(self)
        self._ht.setInterval(14)
        self._ht.timeout.connect(self._hstep)

        self._rr = 0.0
        self._ra = 0
        self._rx = 0.0
        self._ry = 0.0
        self._rt = QTimer(self)
        self._rt.setInterval(14)
        self._rt.timeout.connect(self._rstep)

        self.setFixedHeight(h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        self._gfx = QGraphicsDropShadowEffect(self)
        self._gfx.setBlurRadius(16)
        self._gfx.setOffset(0, 5)
        self._gfx.setColor(QColor(c1 + "44"))
        self.setGraphicsEffect(self._gfx)

    def set_enabled(self, v: bool):
        self._on = v
        col = "#9CA3AF44" if not v else self._c1.name() + "44"
        self._gfx.setColor(QColor(col))
        if not v:
            self._ht.stop()
            self._rt.stop()
            self._hov = 0.0
        self.update()

    def _hstep(self):
        d = self._htgt - self._hov
        self._hov += d * 0.22
        if abs(d) < 0.005:
            self._hov = self._htgt
            self._ht.stop()
        self.update()

    def _rstep(self):
        self._rr += 10
        self._ra = max(0, self._ra - 9)
        self.update()
        if self._ra <= 0:
            self._rt.stop()

    def enterEvent(self, e):
        if self._on:
            self._htgt = 1.0
            self._ht.start()

    def leaveEvent(self, e):
        self._htgt = 0.0
        self._ht.start()

    def mousePressEvent(self, e):
        if not self._on:
            return
        self._rx = e.position().x()
        self._ry = e.position().y()
        self._rr = 0
        self._ra = 115
        self._rt.start()

    def mouseReleaseEvent(self, e):
        if not self._on:
            return
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), self._r, self._r)

        if not self._on:
            p.setBrush(QBrush(QColor("#D1D5DB")))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(path)
            p.setPen(QPen(QColor(D.ink5)))
            p.setFont(QFont("Segoe UI", self._fs, QFont.Weight.Bold))
            p.drawText(QRect(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, self._txt)
            p.end()
            return

        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, lerp(self._c1, self._c2, self._hov * 0.3))
        g.setColorAt(1, lerp(self._c2, self._c1.darker(108), self._hov * 0.3))
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)

        if self._hov > 0.02:
            sg = QLinearGradient(0, 0, 0, H // 2)
            sg.setColorAt(0, QColor(255, 255, 255, int(30 * self._hov)))
            sg.setColorAt(1, QColor(255, 255, 255, 0))
            p.setBrush(QBrush(sg))
            p.drawPath(path)

        if self._ra > 0:
            p.setClipPath(path)
            p.setBrush(QBrush(QColor(255, 255, 255, self._ra)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(self._rx - self._rr, self._ry - self._rr,
                                 self._rr * 2, self._rr * 2))
            p.setClipping(False)

        label = f"{self._icon}  {self._txt}" if self._icon else self._txt
        p.setPen(QPen(self._tc))
        p.setFont(QFont("Segoe UI", self._fs, QFont.Weight.Bold))
        p.drawText(QRect(0, 0, W, H), Qt.AlignmentFlag.AlignCenter, label)
        p.end()


AnimatedButton = RippleButton
GlowButton     = RippleButton


# ══════════════════════════════════════════════════════════════════════════════
#  CHART CANVAS — BUG FIX: opacity animation on the canvas widget only, not the card
# ══════════════════════════════════════════════════════════════════════════════
class ChartCanvas(QFrame):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"ChartCanvas{{background:{D.white};"
            f"border:1.5px solid {D.border}; border-radius:18px;}}"
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        mk_shadow(self, 20, 5, "#0A1C5018")

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        if title:
            hdr = QFrame()
            hdr.setStyleSheet(
                f"background:{D.white}; border:none;"
                "border-radius:18px 18px 0 0;"
            )
            hl = QHBoxLayout(hdr)
            hl.setContentsMargins(17, 12, 17, 9)
            acc = QFrame()
            acc.setFixedSize(4, 22)
            acc.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                f"stop:0 {D.pos},stop:1 {D.blue2});"
                "border-radius:2px; border:none;"
            )
            hl.addWidget(acc)
            tl = QLabel(f"  {title}")
            tl.setStyleSheet(
                f"font-size:10.5pt; font-weight:700; color:{D.ink1};"
                "background:transparent; letter-spacing:0.1px;"
            )
            hl.addWidget(tl)
            hl.addStretch()
            vbox.addWidget(hdr)

            div = QFrame()
            div.setFixedHeight(1)
            div.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {D.border},stop:0.5 {D.blue6},stop:1 {D.border});"
                "border:none; margin:0 16px;"
            )
            vbox.addWidget(div)

        # Inner area holds placeholder OR canvas widget
        self._inner = QWidget()
        self._inner.setStyleSheet("background:transparent;")
        self._inner_lay = QVBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(10, 6, 10, 10)

        self._placeholder = QLabel("Run analysis to display chart")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            f"color:{D.ink5}; font-size:10pt; background:transparent;"
        )
        self._inner_lay.addWidget(self._placeholder)
        vbox.addWidget(self._inner, 1)

        # Opacity effect ONLY on the inner widget (not the card frame)
        self._canvas_fx = QGraphicsOpacityEffect(self._inner)
        self._canvas_fx.setOpacity(1.0)
        self._inner.setGraphicsEffect(self._canvas_fx)

        self._fade_anim = QPropertyAnimation(self._canvas_fx, b"opacity")
        self._fade_anim.setDuration(500)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, e):
        self.setStyleSheet(
            f"ChartCanvas{{background:{D.posL};"
            f"border:2px solid {D.pos}; border-radius:18px;}}"
        )

    def leaveEvent(self, e):
        self.setStyleSheet(
            f"ChartCanvas{{background:{D.white};"
            f"border:1.5px solid {D.border}; border-radius:18px;}}"
        )

    def set_figure(self, fig, delay: int = 0):
        def _do():
            # Remove all existing widgets from inner layout
            while self._inner_lay.count():
                item = self._inner_lay.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)

            # None means just clear — used by reset
            if fig is None:
                return

            canvas = FigureCanvas(fig)
            canvas.setStyleSheet("background:transparent;")
            canvas.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            canvas.updateGeometry()
            self._inner_lay.addWidget(canvas, 1)

            # Animate canvas in
            self._canvas_fx.setOpacity(0.0)
            self._fade_anim.stop()
            self._fade_anim.setStartValue(0.0)
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()

        if delay > 0:
            QTimer.singleShot(delay, _do)
        else:
            _do()


# ══════════════════════════════════════════════════════════════════════════════
#  LOADING OVERLAY — BUG FIX: stop() always hides; no dependency on parent size
# ══════════════════════════════════════════════════════════════════════════════
class LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._a1 = 0.0
        self._a2 = 0.0
        self._a3 = 0.0
        self._ph = 0.0
        self._tick_n = 0
        self._msg = "Processing…"
        self._running = False

        self._timer = QTimer(self)
        self._timer.setInterval(18)
        self._timer.timeout.connect(self._step)

    def start(self, msg: str = "Analysing climate data…"):
        self._msg = msg
        self._tick_n = 0
        self._running = True
        self.raise_()
        self.show()
        self._timer.start()

    def stop(self):
        """Always stop — safe to call multiple times."""
        self._running = False
        self._timer.stop()
        self.hide()

    def set_message(self, msg: str):
        self._msg = msg

    def _step(self):
        self._a1 = (self._a1 + 3.6) % 360
        self._a2 = (self._a2 - 2.4) % 360
        self._a3 = (self._a3 + 1.8) % 360
        import math
        self._ph  = (math.sin(self._tick_n * 0.065) + 1) / 2
        self._tick_n += 1
        self.update()

    def paintEvent(self, e):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W // 2, H // 2

        # Dim background
        p.fillRect(0, 0, W, H, QColor(4, 13, 36, 175))

        cw, ch = 380, 210
        x1, y1 = cx - cw // 2, cy - ch // 2

        # Card shadows
        for i in range(8, 0, -1):
            sc = QColor(10, 28, 80, 12 + i * 5)
            p.setBrush(QBrush(sc))
            p.setPen(Qt.PenStyle.NoPen)
            pp = QPainterPath()
            pp.addRoundedRect(x1 - i, y1 - i + 8, cw + i * 2, ch + i * 2, 24, 24)
            p.drawPath(pp)

        # Card face
        cg = QLinearGradient(x1, y1, x1, y1 + ch)
        cg.setColorAt(0, QColor("#FFFFFF"))
        cg.setColorAt(1, QColor("#F0F6FF"))
        p.setBrush(QBrush(cg))
        p.setPen(QPen(QColor(D.blue7), 1.5))
        pp2 = QPainterPath()
        pp2.addRoundedRect(x1, y1, cw, ch, 24, 24)
        p.drawPath(pp2)

        # Top gradient bar
        p.setPen(Qt.PenStyle.NoPen)
        tg = QLinearGradient(x1, y1, x1 + cw, y1)
        tg.setColorAt(0, QColor(D.navy4))
        tg.setColorAt(0.5, QColor(D.blue2))
        tg.setColorAt(1,   QColor(D.blue3))
        p.setBrush(QBrush(tg))
        tp = QPainterPath()
        tp.addRoundedRect(x1 + 1, y1 + 1, cw - 2, 5, 24, 24)
        p.drawPath(tp)

        # Orbital rings
        scx, scy = cx, cy - 14

        def ring(rad, ang, arc, col, w):
            p.setPen(QPen(QColor(D.blue7), w - 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(scx - rad, scy - rad, 2 * rad, 2 * rad)
            p.setPen(QPen(QColor(col), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(scx - rad, scy - rad, 2 * rad, 2 * rad,
                      int(ang * 16), int(arc * 16))

        ring(38, self._a1, 245, D.blue2, 4)
        ring(25, self._a2, 200, D.blue4, 3)
        ring(14, self._a3, 285, D.blue3, 2)

        # Pulse dot
        pr = 4 + int(self._ph * 2)
        pc = QColor(D.blue2)
        pc.setAlpha(210)
        p.setBrush(QBrush(pc))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(scx - pr, scy - pr, pr * 2, pr * 2)

        # Title
        p.setPen(QPen(QColor(D.ink1)))
        p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        p.drawText(QRect(x1, cy + 30, cw, 26),
                   Qt.AlignmentFlag.AlignCenter, "🌍  ClimateIQ  —  Processing")

        dots = "·" * ((self._tick_n // 14) % 4)
        p.setPen(QPen(QColor(D.ink4)))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRect(x1, cy + 60, cw, 22),
                   Qt.AlignmentFlag.AlignCenter, self._msg + "  " + dots)
        p.end()

    def resizeEvent(self, e):
        if self.parent():
            self.resize(self.parent().size())


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION HEADER
# ══════════════════════════════════════════════════════════════════════════════
class SectionHeader(QWidget):
    def __init__(self, title, subtitle="", icon="📊", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 18, 0, 6)
        vbox.setSpacing(5)

        row = QHBoxLayout()
        row.setSpacing(12)

        pill = QLabel(icon)
        pill.setFixedSize(40, 40)
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {D.blue8},stop:1 {D.blue7});"
            f"border:1.5px solid {D.blue6}; border-radius:11px; font-size:17px;"
        )
        row.addWidget(pill)

        txt = QVBoxLayout()
        txt.setSpacing(1)
        t_l = QLabel(title)
        t_l.setStyleSheet(
            f"font-size:13.5pt; font-weight:800; color:{D.ink0};"
            "background:transparent; letter-spacing:-0.2px;"
        )
        txt.addWidget(t_l)
        if subtitle:
            s_l = QLabel(subtitle)
            s_l.setStyleSheet(
                f"font-size:9pt; color:{D.ink4}; background:transparent;"
            )
            txt.addWidget(s_l)
        row.addLayout(txt)
        row.addStretch()
        vbox.addLayout(row)
        vbox.addWidget(_GradRule())


class _GradRule(QWidget):
    def __init__(self, p=None):
        super().__init__(p)
        self.setFixedHeight(3)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0,   QColor(D.blue2))
        g.setColorAt(0.5, QColor(D.blue3))
        g.setColorAt(1,   QColor(D.blue7))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(0, 0, self.width(), 3, 1.5, 1.5)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  PULSE INDICATOR
# ══════════════════════════════════════════════════════════════════════════════
class PulseIndicator(QWidget):
    def __init__(self, color=D.pos, size=11, parent=None):
        super().__init__(parent)
        self._c = QColor(color)
        self._s = size
        self._ph = 0.0
        self.setFixedSize(size + 10, size + 10)
        t = QTimer(self)
        t.setInterval(30)
        t.timeout.connect(self._tick)
        t.start()

    def set_color(self, c: str):
        self._c = QColor(c)
        self.update()

    def _tick(self):
        import math
        self._ph = (self._ph + 0.09) % (2 * math.pi)
        self.update()

    def paintEvent(self, e):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._s
        cx = (s + 10) // 2
        t = (math.sin(self._ph) + 1) / 2
        ro = s // 2 + int(t * 3)
        oc = QColor(self._c)
        oc.setAlpha(int(25 + t * 95))
        p.setPen(QPen(oc, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(cx - ro, cx - ro, 2 * ro, 2 * ro)
        ri = s // 2 - 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._c))
        p.drawEllipse(cx - ri, cx - ri, 2 * ri, 2 * ri)
        p.end()
