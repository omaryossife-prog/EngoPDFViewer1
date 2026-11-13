"""PyQt6 splash and account UI for Engo licensing."""
from __future__ import annotations

import traceback
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable

from PyQt6.QtCore import Qt, QRect, QThread, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QSize, QUrl
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QLinearGradient, QBrush, QPen, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
    QListWidget, QMessageBox, QPushButton, QProgressBar, QVBoxLayout, QWidget,
    QComboBox, QScrollArea, QPlainTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QAbstractScrollArea, QSizePolicy, QButtonGroup,
)

from .core import LicenseService, LicenseState

# ── theme helpers (imported lazily to avoid circular imports) ──────────────
def _get_theme_tokens(theme: str = "dark") -> dict:
    try:
        from engo_base import engo_ui_theme_tokens
        return engo_ui_theme_tokens(theme)
    except Exception:
        return {
            "window": "#111722", "panel": "#161e2c", "panel_alt": "#1c2840",
            "raised": "#1e2c3f", "input": "#0c1728", "border": "#2a3a52",
            "border_strong": "#3a5070", "text": "#e6efff", "muted": "#6a82a0",
            "accent": "#76a9ff", "accent_hover": "#91b9ff",
            "hover": "#263650", "pressed": "#0b1422",
            "card": "#1a2b45",
        }


def _fmt_date_only(value: Any) -> str:
    """Render an ISO timestamp as a short, human date (no time, no microseconds)."""
    if not value or not isinstance(value, str):
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return value[:10] if len(value) >= 10 else value


def _fmt_datetime_local(value: Any) -> str:
    """Render an ISO timestamp in the computer's local timezone, without seconds."""
    if not value or not isinstance(value, str):
        return "—"
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, OverflowError):
        return "—"


class StartupVerifierWorker(QThread):
    stage_changed = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, service: LicenseService, parent=None):
        super().__init__(parent)
        self.service = service

    def run(self):
        state = self.service.verify_startup(self.stage_changed.emit)
        self.completed.emit(state)


class ServiceActionWorker(QThread):
    completed = pyqtSignal(object, str)

    def __init__(self, action: Callable[[], Any], parent=None):
        super().__init__(parent)
        self.action = action

    def run(self):
        try:
            self.completed.emit(self.action(), "")
        except Exception as exc:
            self.completed.emit(None, str(exc))


class EngoSplashScreen(QWidget):
    retry_requested = pyqtSignal()
    continue_free_requested = pyqtSignal()

    _STAGES = {
        "starting": ("جاري تشغيل Engo", "Starting Engo"),
        "integrity": ("جاري التحقق من سلامة البرنامج", "Checking application integrity"),
        "session": ("جاري التحقق من الحساب", "Checking account"),
        "device": ("جاري التحقق من الجهاز", "Checking device"),
        "subscription": ("جاري التحقق من الاشتراك", "Checking subscription"),
        "entitlements": ("جاري تحميل الصلاحيات", "Loading entitlements"),
        "ready": ("مرحبًا بك في Engo", "Welcome to Engo"),
        "failed": ("تعذر إكمال التحقق", "Verification could not be completed"),
    }

    def __init__(self, icon_path: str = "", language: str = "en", parent=None, theme: str = "dark"):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("engoStartupSplash")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(520, 380)
        self.language = "ar" if str(language).lower().startswith("ar") else "en"
        self._worker: StartupVerifierWorker | None = None
        self._allow_close = False

        t = _get_theme_tokens(theme)
        win   = t["window"]
        panel = t["panel"]
        bdr   = t["border"]
        bdr2  = t["border_strong"]
        txt   = t["text"]
        muted = t["muted"]
        raised = t["raised"]
        hover  = t["hover"]
        acc    = t["accent"]
        card   = t.get("card", panel)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        self.card = QFrame(self)
        self.card.setObjectName("splashCard")
        self.card.setStyleSheet(f"""
            QFrame#splashCard {{
                background: {win};
                border:1px solid {bdr};
                border-radius:20px;
            }}
            QLabel#splashBrand {{
                color:{txt};
                font-size:28px;
                font-weight:900;
                letter-spacing:3px;
            }}
            QLabel#splashTagline {{ color:{muted}; font-size:9.5pt; }}
            QLabel#splashStatus {{ color:{txt}; font-size:9.5pt; font-weight:650; }}
            QLabel#splashSmall {{ color:{muted}; font-size:8pt; letter-spacing:1px; }}
            QProgressBar {{
                border:0; border-radius:3px; background:{panel};
                min-height:4px; max-height:4px;
            }}
            QProgressBar::chunk {{ background:{acc}; border-radius:3px; }}
            QPushButton {{
                color:{txt}; background:{raised}; border:1px solid {bdr};
                border-radius:9px; min-height:34px; padding:0 18px;
                font-weight:700; font-size:9.5pt;
            }}
            QPushButton:hover {{ background:{hover}; border-color:{bdr2}; }}
            QPushButton#freeButton {{
                color:{win}; background:{acc}; border-color:{acc};
                font-weight:750;
            }}
            QPushButton#freeButton:hover {{ background:{t['accent_hover']}; border-color:{t['accent_hover']}; }}
        """)
        outer.addWidget(self.card)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(42, 32, 42, 28)
        layout.setSpacing(10)
        layout.addStretch(1)

        self.logo = QLabel("E")
        self.logo.setObjectName("splashLogo")
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setFixedSize(64, 64)
        self._logo_icon = QIcon(icon_path) if icon_path else QIcon()
        if not self._logo_icon.isNull():
            self.logo.setText("")
            self.logo.setPixmap(self._logo_icon.pixmap(QSize(42, 42)))
        self._splash_accent = acc
        self._splash_panel = panel
        self._splash_bdr = bdr
        self.logo.setStyleSheet(f"background:{panel}; border:2px solid {bdr}; border-radius:24px; color:{acc}; font-size:38px; font-weight:900;")
        logo_row = QHBoxLayout()
        logo_row.addStretch(1)
        logo_row.addWidget(self.logo)
        logo_row.addStretch(1)
        layout.addLayout(logo_row)

        self.brand = QLabel("ENGO")
        self.brand.setObjectName("splashBrand")
        self.brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.brand)
        self.tagline = QLabel("PDF Workspace · AI Study Companion")
        self.tagline.setObjectName("splashTagline")
        self.tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.tagline)
        layout.addSpacing(18)

        self.status = QLabel()
        self.status.setObjectName("splashStatus")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.detail = QLabel("SECURE STARTUP")
        self.detail.setObjectName("splashSmall")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detail)

        self.actions = QWidget()
        action_row = QHBoxLayout(self.actions)
        action_row.setContentsMargins(0, 10, 0, 0)
        action_row.setSpacing(10)
        self.retry_button = QPushButton("إعادة المحاولة" if self.language == "ar" else "Retry")
        self.free_button = QPushButton("متابعة بالنسخة المجانية" if self.language == "ar" else "Continue with Free")
        self.free_button.setObjectName("freeButton")
        self.retry_button.clicked.connect(self.retry_requested.emit)
        self.free_button.clicked.connect(self.continue_free_requested.emit)
        action_row.addWidget(self.retry_button)
        action_row.addWidget(self.free_button)
        self.actions.hide()
        layout.addWidget(self.actions)
        layout.addStretch(1)

        self._fade = QGraphicsOpacityEffect(self.card)
        self.card.setGraphicsEffect(self._fade)
        self._fade_animation = QPropertyAnimation(self._fade, b"opacity", self)
        self._fade_animation.setDuration(480)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_animation.start()

        self._logo_scale = 0
        self._logo_opacity = QGraphicsOpacityEffect(self.logo)
        self.logo.setGraphicsEffect(self._logo_opacity)
        self._logo_fade_animation = QPropertyAnimation(self._logo_opacity, b"opacity", self)
        self._logo_fade_animation.setDuration(520)
        self._logo_fade_animation.setStartValue(0.0)
        self._logo_fade_animation.setEndValue(1.0)
        self._logo_fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._logo_fade_animation.start()
        self._logo_animation = QTimer(self)
        self._logo_animation.setInterval(35)
        self._logo_animation.timeout.connect(self._animate_logo)
        self._logo_animation.start()
        self._glow_phase = 0
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(110)
        self._glow_timer.timeout.connect(self._pulse_logo_glow)
        self._glow_timer.start()
        self._set_stage("starting")
        self._center_on_screen()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            self.move(geometry.center() - self.rect().center())

    def _animate_logo(self):
        self._logo_scale = min(100, self._logo_scale + 7)
        size = 64 + round(26 * self._logo_scale / 100)
        self.logo.setFixedSize(size, size)
        if not self._logo_icon.isNull():
            self.logo.setPixmap(self._logo_icon.pixmap(QSize(max(32, size - 24), max(32, size - 24))))
        else:
            acc = getattr(self, "_splash_accent", "#76a9ff")
            panel = getattr(self, "_splash_panel", "#15243a")
            bdr = getattr(self, "_splash_bdr", "#30496b")
            self.logo.setStyleSheet(
                f"background:{panel}; border:2px solid {bdr}; "
                f"border-radius:{max(18, round(size * .31))}px; color:{acc}; "
                f"font-size:{38 + int(self._logo_scale * .10)}px; font-weight:900;"
            )
        if self._logo_scale >= 100:
            self._logo_animation.stop()

    def _pulse_logo_glow(self):
        self._glow_phase = (self._glow_phase + 9) % 100
        pulse = abs(50 - self._glow_phase) / 50.0
        alpha = 48 + int(58 * pulse)
        acc = getattr(self, "_splash_accent", "#76a9ff")
        panel = getattr(self, "_splash_panel", "#15243a")
        bdr = getattr(self, "_splash_bdr", "#30496b")
        self.logo.setStyleSheet(
            f"background:{panel}; "
            f"border:2px solid {bdr}; "
            f"border-radius:24px; color:{acc};"
        )

    def _set_stage(self, stage: str):
        arabic, english = self._STAGES.get(stage, self._STAGES["starting"])
        self.status.setText(arabic if self.language == "ar" else english)

    def set_stage(self, stage: str):
        self._set_stage(stage)
        if stage == "ready":
            self.detail.setText("ENGO · READY")

    def show_failure(self, reason: str):
        self._set_stage("failed")
        self.progress.hide()
        raw = str(reason or "License verification failed")
        lowered = raw.lower()
        if self.language == "ar":
            if "another device" in lowered:
                message = "هذا الحساب مرتبط بجهاز آخر. يمكنك نقل الحساب من شاشة الحساب."
            elif "not configured" in lowered:
                message = "لم يتم إعداد خدمة الحسابات بعد. يمكنك المتابعة بالنسخة المجانية."
            elif "no account" in lowered or "sign in" in lowered:
                message = "لم يتم تسجيل الدخول. سجّل الدخول لاحقًا من قسم الحساب."
            elif any(token in lowered for token in ("could not contact", "timeout", "http ", "server returned", "connection")):
                message = "تعذر الاتصال بخادم التحقق. تحقق من اتصال الإنترنت ثم أعد المحاولة."
            elif any(token in lowered for token in ("signature", "expired", "untrusted_build", "invalid")):
                message = "تعذر التحقق من صحة الترخيص أو اعتماد هذا الإصدار."
            else:
                message = "تعذر إكمال التحقق. يمكنك إعادة المحاولة أو متابعة استخدام النسخة المجانية."
        else:
            message = raw
        self.detail.setText(message[:240])
        self.actions.show()
        self.retry_button.setEnabled(True)

    def begin_retry(self):
        self.actions.hide()
        self.progress.show()
        self.progress.setRange(0, 0)
        self.detail.setText("SECURE STARTUP")
        self._set_stage("starting")

    def fade_out(self):
        if getattr(self, "_fade_out_animation", None) is not None:
            return
        self._fade_out_animation = QPropertyAnimation(self._fade, b"opacity", self)
        self._fade_out_animation.setDuration(300)
        self._fade_out_animation.setStartValue(float(self._fade.opacity()))
        self._fade_out_animation.setEndValue(0.0)
        self._fade_out_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._fade_out_animation.finished.connect(self.permit_close)
        self._fade_out_animation.start()

    def permit_close(self):
        self._allow_close = True
        self.close()

    def closeEvent(self, event):  # noqa: N802
        if self._allow_close:
            event.accept()
        else:
            event.ignore()


class GroupedPlanHeader(QHeaderView):
    """Pinned two-row plan header painted independently from the scrolling rows."""

    def __init__(self, language: str = "en", theme: str = "dark", parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.language = "ar" if str(language).lower().startswith("ar") else "en"
        self.tokens = _get_theme_tokens(theme)
        self.setFixedHeight(72)
        self.setSectionsClickable(False)
        self.setSectionsMovable(False)
        self.setHighlightSections(False)

    def set_theme(self, theme: str):
        self.tokens = _get_theme_tokens(theme)
        self.viewport().update()

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        background = QColor(self.tokens["raised"])
        foreground = QColor(self.tokens["text"])
        border = QColor(self.tokens["border_strong"])
        painter.fillRect(self.viewport().rect(), background)

        positions = [self.sectionViewportPosition(i) for i in range(5)]
        widths = [self.sectionSize(i) for i in range(5)]
        top_height = 30
        full_height = self.height()

        def cell(x, y, width, height, label, text_color=None):
            if width <= 0 or height <= 0:
                return
            rect = QRect(int(x), int(y), int(width), int(height))
            painter.fillRect(rect, background)
            painter.setPen(border)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.setPen(QColor(text_color) if text_color else foreground)
            font = self.font()
            font.setBold(y == 0)
            # Keep the application's normal header font size; shrinking this
            # custom-painted header made the pinned labels noticeably smaller.
            font.setPointSize(max(9, font.pointSize()))
            painter.setFont(font)
            flags = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)
            painter.drawText(rect.adjusted(4, 2, -4, -2), flags, label)

        feature = "الميزة" if self.language == "ar" else "Feature"
        free = "مجاني" if self.language == "ar" else "Free"
        premium = "مميز" if self.language == "ar" else "Premium"
        limited = "متاح بحدود" if self.language == "ar" else "Available with limits"
        unlimited = "متاح بلا حدود" if self.language == "ar" else "Available without limits"
        unavailable = "غير متاح" if self.language == "ar" else "Unavailable"
        status_colors = {
            "unavailable": "#d94848",
            "limited": "#d6a328",
            "unlimited": "#239b62",
        }
        free_color = "#4f8ee8"
        premium_color = "#d6a328"

        cell(positions[0], 0, widths[0], full_height, feature)
        free_left = min(positions[1], positions[2], positions[3])
        free_right = max(positions[1] + widths[1], positions[2] + widths[2],
                         positions[3] + widths[3])
        cell(free_left, 0, free_right - free_left, top_height, free, free_color)
        cell(positions[4], 0, widths[4], top_height, premium, premium_color)
        cell(positions[1], top_height, widths[1], full_height - top_height, unlimited, status_colors["unlimited"])
        cell(positions[2], top_height, widths[2], full_height - top_height, limited, status_colors["limited"])
        cell(positions[3], top_height, widths[3], full_height - top_height, unavailable, status_colors["unavailable"])
        cell(positions[4], top_height, widths[4], full_height - top_height, unlimited, status_colors["unlimited"])
        painter.end()


class PlansDialog(QDialog):
    """Free/Premium plan picker with a replaceable owner-provided QR image."""
    PERIODS = ("monthly", "quarterly", "semiannual", "annual")

    def __init__(self, service: LicenseService, account_data: dict, language: str = "en", parent=None, theme: str = "dark"):
        super().__init__(parent)
        self.service = service
        self.language = "ar" if str(language).lower().startswith("ar") else "en"
        self.account_data = account_data if isinstance(account_data, dict) else {}
        self._worker: ServiceActionWorker | None = None
        self._selected_billing_period = "monthly"
        self.period_cards: dict[str, QPushButton] = {}
        self._payment_button_text = self._tr("التواصل والدفع", "Contact and Pay")
        self._network_manager = QNetworkAccessManager(self)
        self.setWindowTitle(self._tr("خطط الاشتراك", "Subscription plans"))
        self.setMinimumSize(600, 650)
        self.resize(680, 820)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if self.language == "ar" else Qt.LayoutDirection.LeftToRight)
        t = _get_theme_tokens(theme)
        self.setStyleSheet(f"""
            QDialog {{ background:{t['window']}; color:{t['text']}; }}
            QLabel {{ color:{t['text']}; background:transparent; }}
            QFrame#planCard {{ background:{t['panel']}; border:1px solid {t['border']}; border-radius:12px; }}
            QLabel#planHeading {{ font-size:14pt; font-weight:850; }}
            QLabel#planMuted {{ color:{t['muted']}; }}
            QPushButton {{ background:{t['raised']}; color:{t['text']}; border:1px solid {t['border']}; border-radius:8px; padding:7px 12px; min-height:34px; font-weight:700; }}
            QPushButton:hover {{ background:{t['hover']}; border-color:{t['border_strong']}; }}
            QPushButton#planPrimary {{ background:{t['accent']}; color:white; border-color:{t['accent']}; }}
            QPushButton#periodCard {{ background:{t['raised']}; border:1px solid {t['border_strong']}; border-radius:9px; padding:7px 3px; min-height:58px; font-size:8.5pt; }}
            QPushButton#periodCard:hover {{ background:{t['hover']}; border-color:{t['accent']}; }}
            QPushButton#periodCard:checked {{ background:{t['selection']}; border:2px solid {t['accent']}; color:{t['text']}; }}
            QPushButton:disabled {{ color:{t['muted']}; background:{t['panel_alt']}; }}
            QComboBox {{ background:{t['input']}; color:{t['text']}; border:1px solid {t['border_strong']}; border-radius:7px; padding:6px 9px; min-height:30px; }}
            QPlainTextEdit {{ background:{t['panel_alt']}; border:1px solid {t['border']}; border-radius:8px; color:{t['text']}; padding:8px; }}
            QTableWidget {{ background:{t['panel_alt']}; alternate-background-color:{t['panel']}; color:{t['text']}; gridline-color:{t['border_strong']}; border:1px solid {t['border_strong']}; border-radius:7px; }}
            QHeaderView::section {{ background:{t['raised']}; color:{t['text']}; border:1px solid {t['border_strong']}; padding:6px; font-weight:700; }}
        """)
        shell = QVBoxLayout(self); shell.setContentsMargins(12,12,12,12); shell.setSpacing(8)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); root = QVBoxLayout(content); root.setContentsMargins(6,6,6,6); root.setSpacing(10)
        scroll.setWidget(content); shell.addWidget(scroll, 1)
        title = QLabel(self._tr("اختر خطتك", "Choose your plan")); title.setObjectName("planHeading"); root.addWidget(title)
        subtitle = QLabel(self._tr("اختر الخطة المجانية أو الخطة المميزة حسب احتياجك.", "Choose the Free or Premium plan that fits your needs.")); subtitle.setObjectName("planMuted"); root.addWidget(subtitle)
        self.data_warning = QLabel("")
        self.data_warning.setWordWrap(True)
        self.data_warning.setStyleSheet("color:#b45309; padding:4px 2px;")
        self.data_warning.hide()
        root.addWidget(self.data_warning)

        free = QFrame(); free.setObjectName("planCard"); fl = QVBoxLayout(free); fl.setContentsMargins(14,12,14,12)
        free_title = QLabel(self._tr("مجاني", "Free")); free_title.setObjectName("planHeading"); fl.addWidget(free_title)
        free_copy = QLabel(self._tr("الميزات الأساسية، مع حدود الميزات التي يحددها Engo.", "Core tools plus feature availability configured by Engo.")); free_copy.setWordWrap(True); fl.addWidget(free_copy)
        comparison_title = QLabel(self._tr("مقارنة المميزات", "Feature comparison")); comparison_title.setObjectName("planHeading")
        root.addWidget(comparison_title)
        self.comparison_table = QTableWidget(0, 5)
        # The native horizontal header stays pinned while feature rows scroll.
        self.comparison_table.setHorizontalHeader(GroupedPlanHeader(self.language, theme, self.comparison_table))
        self.comparison_table.verticalHeader().setVisible(False)
        self.comparison_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.comparison_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.comparison_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.comparison_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.comparison_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.comparison_table.setFixedHeight(420)
        self.comparison_table.setAlternatingRowColors(True)
        self.comparison_table.setWordWrap(True)
        self.comparison_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self._populate_comparison()
        root.addWidget(self.comparison_table)
        root.addWidget(free)

        premium = QFrame(); premium.setObjectName("planCard"); pl = QVBoxLayout(premium); pl.setContentsMargins(14,12,14,12)
        premium_title = QLabel(self._tr("مميز", "Premium")); premium_title.setObjectName("planHeading"); pl.addWidget(premium_title)
        premium_copy = QLabel(self._tr("إتاحة أوسع للميزات حسب إعدادات Engo.", "Expanded feature access as configured by Engo.")); premium_copy.setWordWrap(True); pl.addWidget(premium_copy)
        pl.addWidget(QLabel(self._tr("مدة الاشتراك:", "Billing period:")))
        period_cards_row = QHBoxLayout()
        period_cards_row.setSpacing(8)
        self.period_group = QButtonGroup(self)
        self.period_group.setExclusive(True)
        period_labels = (
            ("monthly", self._tr("شهري\\nشهر واحد", "Monthly\\n1 month")),
            ("quarterly", self._tr("ربع سنوي\\n3 أشهر", "Quarterly\\n3 months")),
            ("semiannual", self._tr("نصف سنوي\\n6 أشهر", "Semiannual\\n6 months")),
            ("annual", self._tr("سنوي\\n12 شهر", "Annual\\n12 months")),
        )
        for period, label in period_labels:
            button = QPushButton(label)
            button.setObjectName("periodCard")
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setMinimumHeight(62)
            self.period_group.addButton(button)
            button.clicked.connect(lambda checked=False, value=period: self._select_period(value))
            period_cards_row.addWidget(button, 1)
            self.period_cards[period] = button
        self.period_cards["monthly"].setChecked(True)
        pl.addLayout(period_cards_row)
        self.price_label=QLabel("—"); self.price_label.setObjectName("planHeading"); pl.addWidget(self.price_label)
        self.payment_button=QPushButton(self._payment_button_text); self.payment_button.setObjectName("planPrimary")
        self.payment_button.clicked.connect(self._request_payment); pl.addWidget(self.payment_button)
        root.addWidget(premium)

        disclaimer = QLabel(self._tr(
            "تنويه: Engo وسيط تقني يتيح الاتصال بمزوّدي خدمات الذكاء الاصطناعي، ولا يقدّم هذه الخدمات أو يتحكم في توافرها أو حدودها أو خططها. يخضع استخدامك لخطة وشروط المزوّد الذي تختاره، مثل Google أو OpenAI/ChatGPT أو غيرهما. اشتراكات المزوّدين وحدودهم مستقلة عن اشتراك Engo.",
            "Notice: Engo is a software intermediary that connects you to third-party AI providers. Engo does not provide or control those providers' availability, usage limits, or plans. Your use remains subject to the plan and terms of the provider you choose (such as Google, OpenAI/ChatGPT, or others). Provider subscriptions and limits are separate from an Engo subscription."
        ))
        disclaimer.setWordWrap(True)
        disclaimer.setObjectName("planMuted")
        root.addWidget(disclaimer)

        close=QPushButton(self._tr("إغلاق", "Close")); close.clicked.connect(self.accept); shell.addWidget(close)
        self._update_price()

    def _format_limit(self, row: dict | None, plan: str) -> str:
        if not isinstance(row, dict) or not row:
            return self._tr("لم تصل البيانات", "Not loaded")
        enabled = bool(row.get("enabled"))
        if not enabled:
            return self._tr("غير متاحة", "Unavailable")
        limit = row.get("premium_limit" if plan == "premium" else "free_limit")
        if limit is None:
            return self._tr("بلا حدود", "Unlimited")
        try:
            value = int(limit)
        except (TypeError, ValueError):
            # Do not expose internal quota values or reset windows in the
            # public comparison. The administrator still controls them.
            return self._tr("متاح بحدود", "Available with limits")
        if value <= 0:
            return self._tr("غير متاحة", "Unavailable")
        return self._tr("متاح بحدود", "Available with limits")

    def _populate_comparison(self):
        labels = [
            ("pdf_merge", "دمج ملفات PDF", "Merge PDF files"),
            ("app_themes", "ثيمات البرنامج", "App themes"),
            ("page_themes", "ثيمات الصفحات", "Page themes"),
            ("smart_theme", "الثيم الذكي", "Smart Theme"),
            ("text_chat", "المحادثة النصية", "Text chat"),
            ("voice_chat", "المحادثة الصوتية\nوالحصص الصوتية", "Voice chat and\nvoice lessons"),
            ("voice_board_docx", "تصدير لوحة الشرح الصوتية\nإلى Word", "Export voice lesson\nboard to Word"),
            ("tags", "الوسوم", "Tags"),
            ("tag_units", "وحدات الوسوم", "Tag units"),
            ("translations", "الترجمة", "Translations"),
            ("ai_search", "البحث بالذكاء الاصطناعي", "AI search"),
            ("open_other_formats", "فتح الملفات بصيغ أخرى", "Open other file formats"),
        ]
        rows = self.account_data.get("entitlements") or []
        by_key: dict[str, dict[str, dict]] = {}
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    by_key.setdefault(str(row.get("feature_key") or ""), {})[str(row.get("plan_id") or "")] = row
        elif isinstance(rows, dict):
            for key, value in rows.items():
                if isinstance(value, dict):
                    by_key.setdefault(str(key), {})[str(value.get("plan_id") or "free")] = value

        self.data_warning.setVisible(not bool(by_key))
        if not by_key:
            self.data_warning.setText(self._tr(
                "لم تصل بيانات المميزات من الخادم. تحقق من اتصال الحساب ثم أعد فتح الخطط.",
                "Feature data was not returned by the server. Deploy the updated account-overview function, then check the account connection and reopen plans."
            ))

        # Feature rows are grouped by Free availability. The two-level
        # column header is a real QHeaderView, so it remains fixed while rows scroll.
        self.comparison_table.setRowCount(0)

        basic_features = [
            ("فتح وعرض ملفات PDF", "Open and view PDF files"),
            ("حفظ الملفات والتغييرات", "Save files and changes"),
            ("البحث النصي داخل ملف PDF", "Text search within a PDF"),
            ("التنقل بين الصفحات والفهرس", "Page navigation and document outline"),
            ("عرض الصور المصغّرة للصفحات", "Page thumbnails"),
            ("التكبير والتصغير وملاءمة الصفحة", "Zoom and fit page"),
            ("تدوير الصفحات", "Rotate pages"),
            ("كل أدوات التعديل والملاحظات", "All editing and annotation tools"),
        ]
        grouped_features: dict[str, list[tuple[str, str, bool]]] = {
            "limited": [],
            "unlimited": [(label_ar, label_en, True) for label_ar, label_en in basic_features],
            "unavailable": [],
        }
        # These overrides affect the comparison table presentation only; they do
        # not alter the actual entitlement data or runtime feature enforcement.
        free_status_overrides = {
            "app_themes": "limited",
            "translations": "limited",
            "page_themes": "limited",
            "smart_theme": "unavailable",
            "open_other_formats": "unavailable",
        }
        premium_unlimited_overrides = {"smart_theme", "open_other_formats"}
        for key, label_ar, label_en in labels:
            free_row = by_key.get(key, {}).get("free")
            premium_row = by_key.get(key, {}).get("premium")
            free_status = free_status_overrides.get(key, self._free_status(free_row))
            premium_unlimited = key in premium_unlimited_overrides or self._premium_enabled(premium_row)
            grouped_features[free_status].append(
                (label_ar, label_en, premium_unlimited)
            )

        for free_status in ("unlimited", "limited", "unavailable"):
            for label_ar, label_en, premium_unlimited in grouped_features[free_status]:
                row_index = self.comparison_table.rowCount()
                self.comparison_table.insertRow(row_index)
                feature_item = QTableWidgetItem(self._tr(label_ar, label_en))
                feature_item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.comparison_table.setItem(row_index, 0, feature_item)
                self._put_status_dot(
                    row_index, self._free_status_column_for_status(free_status), free_status
                )
                if premium_unlimited:
                    self._put_status_dot(row_index, 4, "unlimited")

        header = self.comparison_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.comparison_table.setColumnWidth(column, 136 if column in (1, 4) else 84)
        self.comparison_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.comparison_table.resizeRowsToContents()

    def _free_status(self, row: dict | None) -> str:
        if not isinstance(row, dict) or not row or not bool(row.get("enabled")):
            return "unavailable"
        limit = row.get("free_limit")
        if limit is None:
            return "unlimited"
        try:
            return "limited" if int(limit) > 0 else "unavailable"
        except (TypeError, ValueError):
            return "limited"

    def _free_status_column(self, row: dict | None) -> int:
        return self._free_status_column_for_status(self._free_status(row))

    @staticmethod
    def _free_status_column_for_status(status: str) -> int:
        return {"unlimited": 1, "limited": 2, "unavailable": 3}[status]

    @staticmethod
    def _premium_enabled(row: dict | None) -> bool:
        return bool(isinstance(row, dict) and row and row.get("enabled"))

    def _put_status_dot(self, row: int, column: int, status: str):
        colors = {"unavailable": "#d94848", "limited": "#d6a328", "unlimited": "#239b62"}
        labels = {
            "unavailable": self._tr("غير متاح", "Unavailable"),
            "limited": self._tr("متاح بحدود", "Available with limits"),
            "unlimited": self._tr("متاح بلا حدود", "Available without limits"),
        }
        item = QTableWidgetItem("●")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setForeground(QColor(colors.get(status, "#87909b")))
        font = item.font(); font.setPointSize(16); font.setBold(True); item.setFont(font)
        item.setToolTip(labels.get(status, ""))
        self.comparison_table.setItem(row, column, item)

    def _tr(self, ar: str, en: str) -> str:
        return ar if self.language == "ar" else en

    def _select_period(self, period: str):
        if period not in self.PERIODS:
            return
        self._selected_billing_period = period
        self._update_price()

    def _selected_period(self) -> str:
        return self._selected_billing_period

    def _price_row(self) -> dict:
        period = self._selected_period()
        prices = self.account_data.get("prices") or []
        if not isinstance(prices, list):
            return {}
        return next((r for r in prices if isinstance(r, dict) and
                     str(r.get("billing_period") or "").strip().lower() == period), {})

    def _update_price(self):
        row = self._price_row()
        amount = row.get("amount")
        currency = str(row.get("currency") or "EGP")
        active = bool(row.get("is_active"))
        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            amount_value = 0.0
        prices_received = isinstance(self.account_data.get("prices"), list)
        if active and amount_value > 0:
            formatted_price = f"{amount_value:,.2f} {currency}"
            self.price_label.setText(self._tr(f"السعر: {formatted_price}", f"Price: {formatted_price}"))
        elif not prices_received:
            self.price_label.setText(self._tr("السعر: بيانات السعر لم تصل", "Price: data not loaded"))
        else:
            self.price_label.setText(self._tr("السعر: لم يحدد بعد", "Price: not configured yet"))
        self.payment_button.setEnabled(active and amount_value > 0 and self.service.state.authenticated)

    def _local_qr_pixmap(self) -> QPixmap:
        candidates = [
            Path(__file__).resolve().with_name("QR.png"),
            Path.cwd() / "QR.png",
            Path(sys.executable).resolve().parent / "QR.png",
        ]
        bundled_dir = getattr(sys, "_MEIPASS", None)
        if bundled_dir:
            candidates.insert(0, Path(bundled_dir) / "QR.png")
        for candidate in candidates:
            try:
                if candidate.is_file():
                    pixmap = QPixmap(str(candidate))
                    if not pixmap.isNull():
                        return pixmap
            except Exception:
                continue
        return QPixmap()

    def _show_qr_dialog(self, pixmap: QPixmap):
        if pixmap.isNull():
            QMessageBox.warning(
                self,
                self._tr("صورة QR غير متاحة", "QR image unavailable"),
                self._tr(
                    "لم يتم العثور على صورة QR.png صالحة. تأكد من رفع الصورة وربط رابطها في إعدادات الاشتراك.",
                    "A valid QR.png image was not found. Upload the image and set its URL in subscription settings.",
                ),
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("QR")
        dialog.setModal(True)
        dialog.setMinimumSize(360, 360)
        dialog.resize(620, 620)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setStyleSheet("background:#ffffff; border-radius:8px;")
        image.setPixmap(pixmap.scaled(
            580, 580,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        layout.addWidget(image)
        dialog.exec()

    def _open_qr_image(self, url: str = ""):
        """Open only the configured QR image; never render a contact URL as an image."""
        url = str(url or "").strip()
        path = QUrl(url).path().lower() if url.startswith("https://") else url.lower()
        is_image_url = url.startswith("https://") and path.endswith((".png", ".jpg", ".jpeg", ".webp"))
        if is_image_url:
            reply = self._network_manager.get(QNetworkRequest(QUrl(url)))
            reply.finished.connect(lambda r=reply: self._qr_downloaded(r))
            return

        # QR.png may also be bundled beside the app. The DB remains the source
        # of truth when it provides a real image URL.
        local_pixmap = self._local_qr_pixmap()
        if not local_pixmap.isNull():
            self._show_qr_dialog(local_pixmap)
            return
        self._show_qr_dialog(QPixmap())

    def _qr_downloaded(self, reply):
        try:
            raw = bytes(reply.readAll())
            pixmap = QPixmap()
            if raw and pixmap.loadFromData(raw):
                self._show_qr_dialog(pixmap)
            else:
                local_pixmap = self._local_qr_pixmap()
                self._show_qr_dialog(local_pixmap)
        finally:
            reply.deleteLater()

    def _request_payment(self):
        if self._worker and self._worker.isRunning():
            return
        period = self._selected_period()
        self.payment_button.setEnabled(False)
        self.payment_button.setText(self._tr("جاري إنشاء طلب الدفع…", "Creating payment request…"))
        self.period_group.setEnabled(False)
        self._worker = ServiceActionWorker(
            lambda: self.service.request_subscription_payment(period), self
        )
        self._worker.completed.connect(self._payment_created)
        self._worker.finished.connect(self._payment_worker_finished)
        self._worker.start()

    def _payment_worker_finished(self):
        self._worker = None

    def _payment_created(self, result, error: str):
        self.period_group.setEnabled(True)
        self.payment_button.setText(self._payment_button_text)
        self._update_price()
        if error:
            QMessageBox.warning(
                self,
                self._tr("تعذر إنشاء طلب الدفع", "Could not create payment request"),
                str(error),
            )
            return
        if not isinstance(result, dict):
            QMessageBox.warning(
                self,
                self._tr("خطأ", "Error"),
                self._tr("استجابة غير متوقعة من الخادم.", "Unexpected server response."),
            )
            return
        settings = self.account_data.get("payment_settings") if isinstance(self.account_data.get("payment_settings"), dict) else {}
        qr_url = result.get("qr_image_url") or settings.get("qr_image_url")
        self._open_qr_image(str(qr_url or ""))



class AccountDialog(QDialog):
    """Compact account and subscription panel; no PDF/chat content is uploaded."""

    def __init__(self, service: LicenseService, language: str = "en", parent=None, theme: str = "dark"):
        super().__init__(parent)
        self.service = service
        self.language = "ar" if str(language).lower().startswith("ar") else "en"
        self._worker: ServiceActionWorker | None = None
        self._plans_worker: ServiceActionWorker | None = None
        self.account_data: dict[str, Any] = {}
        # Seed the plans visibility from the fresh, Ed25519-verified startup
        # license. Keep plans hidden while the mode is not yet verified; the
        # asynchronous account overview is for profile/pricing details, not the
        # first source of truth for the launch mode.
        self._free_unlimited_mode = (
            bool(service.state.free_unlimited_mode) if service.state.verified else True
        )
        is_ar = self.language == "ar"
        self.setObjectName("engoAccountDialog")
        self.setWindowTitle("الحساب والاشتراك" if is_ar else "Account & Subscription")
        self.setMinimumWidth(500)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_ar else Qt.LayoutDirection.LeftToRight)

        t = _get_theme_tokens(theme)
        win   = t["window"]
        pnl   = t["panel"]
        bdr   = t["border"]
        bdr2  = t["border_strong"]
        txt   = t["text"]
        muted = t["muted"]
        raised = t["raised"]
        hover  = t["hover"]
        acc    = t["accent"]
        sel    = t["selection"]
        card   = t.get("card", pnl)

        # ── danger colors (same logic as AppSettingsDialog) ────────────────
        from engo_base import normalize_ui_theme
        _th = normalize_ui_theme(theme)
        danger       = "#c43f4d" if _th == "light" else "#e17b89"
        danger_soft  = {"light":"#fff0f1","midnight":"#3c2635","dark":"#332626","grass":"#26382a","pink":"#38252d","orange":"#3b2b1d"}.get(_th,"#332626")
        danger_bdr   = {"light":"#e8b9bf","midnight":"#754153","dark":"#69444a","grass":"#49634d","pink":"#70414d","orange":"#765332"}.get(_th,"#69444a")

        self.setStyleSheet(f"""
            QDialog#engoAccountDialog {{ background:{win}; color:{txt}; }}
            QDialog#engoAccountDialog QLabel {{ background:transparent; color:{txt}; font-size:9pt; }}
            QLabel#acctEyebrow {{ color:{acc}; font-size:7pt; font-weight:800; letter-spacing:1.2px; background:transparent; }}
            QLabel#acctHeroTitle {{ color:{txt}; font-size:15pt; font-weight:800; background:transparent; }}
            QLabel#acctHeroSub {{ color:{muted}; font-size:8.5pt; background:transparent; }}
            QFrame#acctCard {{ background:{card}; border:1px solid {bdr}; border-radius:12px; }}
            QLabel#acctName {{ color:{txt}; font-size:11pt; font-weight:800; background:transparent; }}
            QLabel#acctEmail {{ color:{muted}; font-size:8.5pt; background:transparent; }}
            QLabel#acctPlanRow {{ color:{muted}; font-size:8.5pt; font-weight:650; background:transparent; }}
            QFrame#acctDivider {{ background:{bdr}; border:none; }}
            QLabel#acctSectionTitle {{ color:{acc}; font-size:7pt; font-weight:800; letter-spacing:1.2px; background:transparent; }}
            QTableWidget {{
                background:{win}; border:1px solid {bdr}; border-radius:8px;
                color:{txt}; font-size:8.5pt; gridline-color:transparent;
                outline:0;
            }}
            QTableWidget::item {{ padding:5px 10px; border-bottom:1px solid {bdr}; }}
            QTableWidget::item:selected {{ background:{sel}; color:{txt}; }}
            QHeaderView::section {{
                background:{pnl}; color:{muted}; font-weight:700; font-size:8pt;
                border:none; border-bottom:1px solid {bdr}; padding:5px 10px;
            }}
            QLabel#acctMessage {{ color:{muted}; font-size:8pt; background:transparent; }}
            QPushButton {{
                background:{card}; color:{txt}; border:1px solid {bdr};
                border-radius:8px; padding:5px 14px; min-height:32px;
                font-weight:700; font-size:9pt;
            }}
            QPushButton:hover {{ background:{hover}; border-color:{bdr2}; }}
            QPushButton:disabled {{ background:{win}; color:{muted}; border-color:{bdr}; }}
            QPushButton#acctClose {{ background:{card}; color:{txt}; border:1px solid {bdr}; min-width:80px; }}
            QPushButton#acctClose:hover {{ background:{hover}; border-color:{acc}; }}
            QPushButton#acctSignout {{ background:{danger_soft}; color:{danger}; border:1px solid {danger_bdr}; min-width:110px; }}
            QPushButton#acctSignout:hover {{ border-color:{danger}; }}
            QPushButton#acctTransfer {{ background:{sel}; color:{txt}; border:1px solid {bdr}; }}
            QPushButton#acctTransfer:hover {{ background:{hover}; border-color:{acc}; }}
            QPushButton#acctGoogleBtn {{
                background:#ffffff; color:#3c4043; border:1px solid #dadce0;
                border-radius:10px; font-size:10.5pt; font-weight:700;
                padding:0 28px; min-height:44px; min-width:300px;
            }}
            QPushButton#acctGoogleBtn:hover {{ background:#f8f9fa; border-color:#bdc1c6; }}
            QPushButton#acctGoogleBtn:pressed {{ background:#e8eaed; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        # ── Hero header (like settings dialog) ────────────────────────────
        hero_row = QHBoxLayout()
        hero_row.setSpacing(14)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(2)
        hero_title = QLabel("الحساب والاشتراك" if is_ar else "Account & Subscription")
        hero_title.setObjectName("acctHeroTitle")
        hero_sub = QLabel(
            "إدارة حسابك والأجهزة المرتبطة." if is_ar
            else "Manage your account and linked devices."
        )
        hero_sub.setObjectName("acctHeroSub")
        hero_copy.addWidget(hero_title)
        hero_copy.addWidget(hero_sub)
        hero_row.addLayout(hero_copy, 1)
        root.addLayout(hero_row)

        # ── Profile card ──────────────────────────────────────────────────
        prof_card = QFrame()
        prof_card.setObjectName("acctCard")
        prof_layout = QVBoxLayout(prof_card)
        prof_layout.setContentsMargins(14, 12, 14, 12)
        prof_layout.setSpacing(0)

        # Avatar + name row
        av_row = QHBoxLayout()
        av_row.setSpacing(14)
        self.avatar_label = QLabel("?")
        self.avatar_label.setFixedSize(50, 50)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setStyleSheet(
            f"background:{raised}; color:{acc}; border:2px solid {bdr2}; "
            "border-radius:25px; font-size:18pt; font-weight:900;"
        )
        av_row.addWidget(self.avatar_label)
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        self.name_label = QLabel("—")
        self.name_label.setObjectName("acctName")
        self.email_label = QLabel("")
        self.email_label.setObjectName("acctEmail")
        name_col.addWidget(self.name_label)
        name_col.addWidget(self.email_label)
        av_row.addLayout(name_col, 1)
        prof_layout.addLayout(av_row)

        # Divider
        prof_layout.addSpacing(10)
        div1 = QFrame(); div1.setObjectName("acctDivider"); div1.setFixedHeight(1)
        prof_layout.addWidget(div1)
        prof_layout.addSpacing(8)

        # Plan rows
        self.plan_label   = QLabel(); self.plan_label.setObjectName("acctPlanRow")
        self.status_label = QLabel(); self.status_label.setObjectName("acctPlanRow")
        self.expiry_label = QLabel(); self.expiry_label.setObjectName("acctPlanRow")
        for lbl in (self.plan_label, self.status_label, self.expiry_label):
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            prof_layout.addWidget(lbl)
        self.plans_button = QPushButton("عرض الخطط والاشتراك" if is_ar else "View Plans and Subscribe")
        self.plans_button.setObjectName("acctPlans")
        self.plans_button.clicked.connect(self._open_plans)
        self.plans_button.setVisible(False)
        prof_layout.addWidget(self.plans_button)

        self._network_manager = QNetworkAccessManager(self)
        self._avatar_url_loaded = ""
        root.addWidget(prof_card)

        # ── Devices section ───────────────────────────────────────────────
        dev_title = QLabel("الأجهزة المرتبطة" if is_ar else "LINKED DEVICES")
        dev_title.setObjectName("acctSectionTitle")
        root.addWidget(dev_title)

        from PyQt6.QtWidgets import QTableWidget, QHeaderView
        self.devices_table = QTableWidget(0, 3)
        self.devices_table.setHorizontalHeaderLabels(
            ["الجهاز", "الحالة", "آخر اتصال"] if is_ar else ["Device", "Status", "Last Seen"]
        )
        self.devices_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.devices_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.devices_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.devices_table.verticalHeader().setVisible(False)
        self.devices_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.devices_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.devices_table.setMaximumHeight(120)
        self.devices_table.setShowGrid(False)
        self.devices_list = self.devices_table
        root.addWidget(self.devices_table)

        # ── Status message ────────────────────────────────────────────────
        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("acctMessage")
        root.addWidget(self.message_label)

        # ── Google sign-in button ─────────────────────────────────────────
        self.signin_container = QWidget()
        sc_lay = QVBoxLayout(self.signin_container)
        sc_lay.setContentsMargins(0, 4, 0, 4)
        self.signin_button = QPushButton(
            "  تسجيل الدخول باستخدام Google  🔵" if is_ar
            else "  Sign in with Google  🔵"
        )
        self.signin_button.setObjectName("acctGoogleBtn")
        self.signin_button.clicked.connect(self._start_login)
        sc_lay.addWidget(self.signin_button, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(self.signin_container)

        # ── Footer buttons ────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.transfer_button = QPushButton("نقل الحساب إلى هذا الجهاز" if is_ar else "Move to this device")
        self.transfer_button.setObjectName("acctTransfer")
        self.signout_button  = QPushButton("تسجيل الخروج" if is_ar else "Sign out")
        self.signout_button.setObjectName("acctSignout")
        self.close_button    = QPushButton("إغلاق" if is_ar else "Close")
        self.close_button.setObjectName("acctClose")
        self.signout_button.clicked.connect(self._sign_out)
        self.transfer_button.clicked.connect(self._transfer_here)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.transfer_button)
        footer.addStretch(1)
        footer.addWidget(self.signout_button)
        footer.addWidget(self.close_button)
        root.addLayout(footer)

        self._render_state()
        self.signout_button.setVisible(self.service.state.authenticated)
        self.signin_container.setVisible(not self.service.state.authenticated)
        self.transfer_button.setVisible(
            self.service.state.authenticated and
            "another device" in self.service.state.reason.lower()
        )
        self._load_overview()

    def _tr(self, ar: str, en: str) -> str:
        return ar if self.language == "ar" else en

    def _render_state(self):
        state = self.service.state
        user = state.user or {}
        metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
        name = metadata.get("full_name") or metadata.get("name") or user.get("email") or self._tr("زائر", "Guest")
        email = user.get("email") or self._tr("لم يتم تسجيل الدخول", "Not signed in")
        self.name_label.setText(str(name))
        self.email_label.setText(str(email))
        avatar_url = str(metadata.get("avatar_url") or metadata.get("picture") or "").strip()
        if avatar_url.startswith("https://") and avatar_url != self._avatar_url_loaded:
            self._avatar_url_loaded = avatar_url
            reply = self._network_manager.get(QNetworkRequest(QUrl(avatar_url)))
            reply.finished.connect(lambda r=reply: self._avatar_loaded(r))
        plan_ar = "مميز" if state.is_premium else "مجاني"
        plan_en = "Premium" if state.is_premium else "Free"
        self.plan_label.setText(self._tr(f"الباقة: {plan_ar}", f"Plan: {plan_en}"))
        status = str(state.license_status or "free")
        status_labels = {
            "active": ("نشط", "Active"), "free": ("مجاني", "Free"),
            "device_not_active": ("الجهاز غير نشط", "Device not active"),
            "untrusted_build": ("إصدار غير معتمد", "Untrusted build"),
            "account_suspended": ("الحساب موقوف", "Account suspended"),
            "expired": ("منتهي", "Expired"), "revoked": ("ملغى", "Revoked"),
        }
        status_ar, status_en = status_labels.get(status, (status, status))
        self.status_label.setText(self._tr(f"الحالة: {status_ar}", f"Status: {status_en}"))
        expiry_text = _fmt_datetime_local(state.expires_at)
        self.expiry_label.setText(self._tr(
            f"تنتهي صلاحية التحقق: {expiry_text}",
            f"License check expires: {expiry_text}",
        ))
        self.message_label.setText(state.reason or "")
        self.signout_button.setVisible(state.authenticated)
        self.signin_container.setVisible(not state.authenticated)
        self.transfer_button.setVisible(state.authenticated and "another device" in state.reason.lower())
        # Startup verification and post-login heartbeats return a signed state.
        # Apply it before rendering so the button does not wait for account-overview.
        if state.verified:
            self._free_unlimited_mode = bool(state.free_unlimited_mode)
        self.plans_button.setVisible(state.authenticated and not self._free_unlimited_mode)

    def closeEvent(self, event):  # noqa: N802
        # A pending sign-in/activation worker (e.g. waiting on a slow network or
        # an OAuth redirect that may take up to ENGO_OAUTH_TIMEOUT seconds) must
        # never block the window from closing. Previously this ignored the close
        # event while busy, which made the whole app feel frozen behind a dialog
        # the user couldn't dismiss. The worker keeps running in the background
        # and will update the account state normally whenever it finishes.
        event.accept()
        self.reject()  # emits `finished`, so the main window re-syncs its account widgets

    def _avatar_loaded(self, reply):
        try:
            raw = bytes(reply.readAll())
            pixmap = QPixmap()
            if raw and pixmap.loadFromData(raw):
                size = self.avatar_label.width()
                scaled = pixmap.scaled(size, size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation)
                from PyQt6.QtGui import QPainter, QBrush
                result = QPixmap(size, size)
                result.fill(Qt.GlobalColor.transparent)
                painter = QPainter(result)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setBrush(QBrush(scaled))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(0, 0, size, size)
                painter.end()
                self.avatar_label.setText("")
                self.avatar_label.setStyleSheet(
                    self.avatar_label.styleSheet() + " border:none; background:transparent;"
                )
                self.avatar_label.setPixmap(result)
        finally:
            reply.deleteLater()

    def _set_busy(self, busy: bool, message: str = ""):
        self.signin_button.setEnabled(not busy)
        self.signout_button.setEnabled(not busy)
        self.transfer_button.setEnabled(not busy)
        # The Close button stays enabled even while an action is running: the
        # user can always dismiss this window, and the pending worker finishes
        # in the background and updates the account state when it's done.
        self.message_label.setText(message or (self._tr("جارٍ تنفيذ العملية…", "Working…") if busy else ""))

    def _run_action(self, action: Callable[[], Any], on_done: Callable[[Any, str], None]):
        if self._worker and self._worker.isRunning():
            return
        self._set_busy(True)
        self._worker = ServiceActionWorker(action, self)
        self._worker.completed.connect(on_done)
        self._worker.start()

    def _start_login(self):
        self._run_action(self.service.login_google, self._login_completed)

    def _login_completed(self, session: Any, error: str):
        if error:
            self._set_busy(False, error)
            return
        def activate():
            return self.service.activate_device(allow_transfer=False)
        QTimer.singleShot(80, lambda: self._run_action(activate, self._activation_completed))

    def _activation_completed(self, result: Any, error: str):
        if error:
            self._set_busy(False, error)
            return
        if isinstance(result, dict) and result.get("status") == "device_conflict":
            message = self._tr(
                "هذا الحساب مرتبط بجهاز آخر. هل تريد نقل حسابك إلى هذا الجهاز؟",
                "This account is active on another device. Do you want to move it to this device?",
            )
            answer = QMessageBox.question(self, self._tr("نقل الحساب", "Move account"), message,
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                QTimer.singleShot(80, lambda: self._run_action(self.service.transfer_device_and_check, self._action_completed))
            else:
                self.service._free_state("Account is signed in but remains active on another device", authenticated=True)
                self._render_state()
                self._set_busy(False, self.service.state.reason)
            return
        QTimer.singleShot(80, lambda: self._run_action(self.service.heartbeat, self._action_completed))

    def _action_completed(self, state: Any, error: str):
        if error:
            self._set_busy(False, error)
            self._render_state()
            return
        self._render_state()
        self._set_busy(False, getattr(state, "reason", ""))
        QTimer.singleShot(100, self._load_overview)

    def _transfer_here(self):
        answer = QMessageBox.question(
            self, self._tr("نقل الحساب", "Move account"),
            self._tr("سيتم إلغاء تفعيل الجهاز القديم وتفعيل هذا الجهاز. هل تريد المتابعة؟",
                     "The old device will be deactivated and this device activated. Continue?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run_action(self.service.transfer_device_and_check, self._action_completed)

    def _sign_out(self):
        answer = QMessageBox.question(self, self._tr("تسجيل الخروج", "Sign out"),
                                      self._tr("هل تريد تسجيل الخروج من Engo؟", "Sign out of Engo?"),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_action(self.service.logout, self._signout_completed)

    def _signout_completed(self, _result: Any, error: str):
        if error:
            self._set_busy(False, error)
            return
        self._render_state()
        self.devices_table.setRowCount(0)
        self._set_busy(False, self.service.state.reason)

    def _load_overview(self):
        if not self.service.state.authenticated:
            return
        self._run_action(self.service.account_overview, self._overview_completed)

    def _open_plans(self):
        """Fetch current pricing/entitlements before showing the plan picker.

        The account overview is loaded asynchronously when AccountDialog opens.
        Previously the plan button could be clicked before that request finished,
        so the dialog received an empty cache and displayed all features as
        unavailable and every price as unset even though Supabase contained them.
        """
        if self._free_unlimited_mode:
            return
        if not self.service.state.authenticated:
            QMessageBox.information(
                self, self._tr("خطط الاشتراك", "Subscription plans"),
                self._tr("سجّل الدخول أولاً لتحميل أسعار وخيارات الاشتراك.",
                         "Sign in first to load current subscription prices and plan limits."),
            )
            return
        if self._plans_worker and self._plans_worker.isRunning():
            return
        self.plans_button.setEnabled(False)
        self.plans_button.setText(self._tr("جاري تحميل الخطط…", "Loading plans…"))
        self._plans_worker = ServiceActionWorker(self.service.account_overview, self)
        self._plans_worker.completed.connect(self._plans_overview_completed)
        self._plans_worker.finished.connect(self._plans_worker_finished)
        self._plans_worker.start()

    def _plans_worker_finished(self):
        # Release the QThread only after the native thread has fully stopped.
        self._plans_worker = None

    def _plans_overview_completed(self, data: Any, error: str):
        self.plans_button.setEnabled(True)
        self.plans_button.setText(self._tr("عرض الخطط والاشتراك", "View Plans and Subscribe"))
        if error:
            QMessageBox.warning(
                self, self._tr("تعذر تحميل الخطط", "Could not load plans"),
                self._tr(f"تعذر تحميل الأسعار والحدود من الخادم:\n{error}",
                         f"Could not load prices and plan limits from the server:\n{error}"),
            )
            return
        if not isinstance(data, dict):
            QMessageBox.warning(
                self, self._tr("تعذر تحميل الخطط", "Could not load plans"),
                self._tr("استجابة غير صالحة من الخادم.", "The server returned an invalid response."),
            )
            return

        # The admin can switch launch mode while the account window is open.
        if bool(data.get("free_unlimited_mode", False)):
            self._overview_completed(data, "")
            return
        # Refresh profile/device details too, then build the dialog from this
        # fresh response rather than an older value cached during construction.
        self._overview_completed(data, "")
        theme = "dark"
        try:
            from engo_base import normalize_ui_theme
            settings = getattr(self.parent(), "settings", None)
            theme = normalize_ui_theme(settings.value("ui_theme", "dark", type=str)) if settings is not None else "dark"
        except Exception:
            pass
        dialog = PlansDialog(self.service, self.account_data, self.language, self, theme=theme)
        dialog.exec()

    def _overview_completed(self, data: Any, error: str):
        if error:
            self._set_busy(False, error)
            return
        if not isinstance(data, dict):
            self._set_busy(False, self._tr("تعذر قراءة بيانات الحساب", "Could not read account details"))
            return
        self.account_data = data
        # Preserve the launch mode captured by the signed startup check for this
        # running session. If no signed state exists yet, use the authenticated
        # account-overview response as a fallback (missing field defaults closed).
        if self.service.state.verified:
            self._free_unlimited_mode = bool(self.service.state.free_unlimited_mode)
        else:
            self._free_unlimited_mode = bool(data.get("free_unlimited_mode", True))
        self.plans_button.setVisible(self.service.state.authenticated and not self._free_unlimited_mode)
        profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
        if profile:
            user = dict(self.service.state.user or {})
            metadata = dict(user.get("user_metadata") or {})
            if profile.get("display_name"):
                metadata.setdefault("full_name", profile.get("display_name"))
            if profile.get("avatar_url"):
                metadata.setdefault("avatar_url", profile.get("avatar_url"))
            user["user_metadata"] = metadata
            if data.get("email"):
                user["email"] = data.get("email")
            self.service.state.user = user
            self._render_state()
        subscription = data.get("subscription") if isinstance(data.get("subscription"), dict) else {}
        if self._free_unlimited_mode:
            self.plan_label.setText(self._tr("الباقة: مجاني · جميع الميزات بلا حدود", "Plan: Free · All features unlimited"))
            self.expiry_label.setText(self._tr("وضع الإطلاق المجاني مفعّل حاليًا.", "Free launch mode is currently enabled."))
        else:
            ends_raw = subscription.get("ends_at") if subscription else None
            if subscription and not ends_raw:
                self.expiry_label.setText(self._tr("الاشتراك: مدى الحياة", "Subscription: Lifetime"))
            elif subscription:
                self.expiry_label.setText(self._tr(
                    f"الاشتراك: حتى {_fmt_date_only(ends_raw)}",
                    f"Subscription: until {_fmt_date_only(ends_raw)}"))
            else:
                self.expiry_label.setText(self._tr("الاشتراك: مجاني", "Subscription: Free"))
        devices = data.get("devices") if isinstance(data.get("devices"), list) else []
        tbl = self.devices_table
        tbl.setRowCount(0)
        is_ar = self.language == "ar"
        if devices:
            for device in devices:
                if not isinstance(device, dict):
                    continue
                name = str(device.get("device_name") or device.get("device_id") or "Windows device")
                status_raw = str(device.get("status") or "—")
                status = {"active": "نشط", "revoked": "ملغى", "inactive": "غير نشط"}.get(status_raw, status_raw) if is_ar else \
                         {"active": "Active", "revoked": "Revoked", "inactive": "Inactive"}.get(status_raw, status_raw)
                last_seen = str(device.get("last_seen") or "—")[:19].replace("T", "  ")
                row = tbl.rowCount()
                tbl.insertRow(row)
                from PyQt6.QtWidgets import QTableWidgetItem
                tbl.setItem(row, 0, QTableWidgetItem(name))
                status_item = QTableWidgetItem(status)
                from PyQt6.QtGui import QColor
                if status_raw == "active":
                    status_item.setForeground(QColor("#6dbf8a"))
                elif status_raw == "revoked":
                    status_item.setForeground(QColor("#e07070"))
                tbl.setItem(row, 1, status_item)
                tbl.setItem(row, 2, QTableWidgetItem(last_seen))
        else:
            tbl.insertRow(0)
            from PyQt6.QtWidgets import QTableWidgetItem
            msg = self._tr("لا توجد أجهزة مسجلة", "No devices registered")
            tbl.setItem(0, 0, QTableWidgetItem(msg))
            tbl.setSpan(0, 0, 1, 3)
        self._set_busy(False, self.service.state.reason)


__all__ = ["StartupVerifierWorker", "EngoSplashScreen", "AccountDialog", "PlansDialog", "ServiceActionWorker"]
