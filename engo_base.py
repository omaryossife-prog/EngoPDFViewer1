# Auto-split from main.py (verbatim move; do not reformat).
from __future__ import annotations

import os
import base64
import sys
import tempfile
import re
import time
import faulthandler
import traceback
from pathlib import Path
from PyQt6.QtCore import QObject, Qt, QSize, QSizeF, QRect, QRectF, QPoint, QPointF, QEvent, QTimer, QPropertyAnimation, QParallelAnimationGroup, QVariantAnimation, QEasingCurve, QSettings, QUrl, QThread, QRunnable, QThreadPool, QMarginsF, QStandardPaths, QDir, pyqtSignal, QBuffer, QByteArray, QIODevice, QMimeData, QSignalBlocker
from PyQt6.QtGui import QColor, QPalette, QImage, QPixmap, QIcon, QFileSystemModel, QPainter, QPen, QBrush, QKeySequence, QShortcut, QAction, QCursor, QPolygonF, QPainterPath, QPainterPathStroker, QDesktopServices, QPdfWriter, QPageSize, QTextDocument, QTextCursor, QFont, QDrag, QContextMenuEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QToolButton, QBoxLayout,
    QCheckBox, QColorDialog, QFileDialog, QHBoxLayout, QVBoxLayout, QScrollArea, QAbstractScrollArea,
    QListWidget, QListWidgetItem, QListView, QAbstractItemView, QTreeWidget, QTreeWidgetItem, QTreeView, QSpinBox,
    QSizePolicy, QStatusBar, QMessageBox, QSplitter, QTabWidget, QDialog,
    QDialogButtonBox, QInputDialog, QButtonGroup, QLineEdit, QStackedWidget, QTabBar, QMenu, QComboBox,
    QTextBrowser, QTextEdit, QProgressBar, QGridLayout, QStyledItemDelegate, QStyle, QSlider, QWidgetAction, QToolTip, QGraphicsOpacityEffect
)


HOME_FOOTER_TEXT = "Version 2.3.6\nYour study space\nPDFs · Notes · AI Teacher\nProgrammed by: Eng. Omar jouusef"
APP_NAME = "Engo PDF Viewer & AI Study Agent"
APP_DATA_NAME = "Engo PDF Viewer"  # Keep existing user-data folder and saved study data
APP_ORG = "Engo"
DEFAULT_BG = "#1e1e1e"
DEFAULT_INK = "#e0e0e0"
DEFAULT_ANNOTATION_COLORS = {
    "pen": "#3679e8",
    "highlight": "#f5d34e",
    "note": "#a78bfa",
    "text_ink": "#263247",
    "text_fill": "#fff4bf",
}
IPC_SERVER_NAME = "EngoPDFViewer_SingleInstance_v15_28"
UI_BG = "#151820"
UI_PANEL = "#1d222c"
UI_PANEL2 = "#252c38"
UI_BORDER = "#333c4a"
UI_TEXT = "#e9edf5"
UI_MUTED = "#9aa6b8"
UI_ACCENT = "#5b8cff"


# One source of truth for the interface palette. Widgets, menus, status/help bars,
# and the native Windows caption buttons all read from these named tokens.
_ENGO_UI_THEME_TOKENS = {
    "dark": {
        # Neutral graphite scale, intentionally aligned with the AI chat surfaces.
        # The light gray toolbar/home actions are only slightly darker than the panels.
        "window": "#171717", "panel": "#202020", "panel_alt": "#262626",
        "raised": "#303030", "input": "#161616", "border": "#383838",
        "border_strong": "#4a4a4a", "text": "#eeeeee", "muted": "#aaaaaa",
        "accent": "#7798cb", "accent_hover": "#8caad5",
        "selection": "#3b4148", "selection_text": "#ffffff",
        "hover": "#353535", "pressed": "#111111",
        "titlebar": "#202020", "titlebar_text": "#eeeeee",
        "titlebar_border": "#3a3a3a", "status": "#1c1c1c",
        "card": "#242424", "scrollbar": "#555555",
    },
    "midnight": {
        "window": "#101a2b", "panel": "#15243a", "panel_alt": "#1c2f4c",
        "raised": "#243b5b", "input": "#0c1728", "border": "#30496b",
        "border_strong": "#49678f", "text": "#e6efff", "muted": "#9aacca",
        "accent": "#76a9ff", "accent_hover": "#91b9ff",
        "selection": "#294b79", "selection_text": "#ffffff",
        "hover": "#294365", "pressed": "#0b1422",
        "titlebar": "#15243a", "titlebar_text": "#e6efff",
        "titlebar_border": "#30496b", "status": "#122038",
        "card": "#1a2b45", "scrollbar": "#405875",
    },
    "light": {
        "window": "#f1f4f8", "panel": "#ffffff", "panel_alt": "#f6f8fb",
        "raised": "#e8eef6", "input": "#ffffff", "border": "#aab8c9",
        "border_strong": "#8396ad", "text": "#243247", "muted": "#64748b",
        "accent": "#386fd3", "accent_hover": "#285fc2",
        "selection": "#d7e7ff", "selection_text": "#14365f",
        "hover": "#e7eef8", "pressed": "#dbe4ef",
        "titlebar": "#e9eef5", "titlebar_text": "#243247",
        "titlebar_border": "#aab8c9", "status": "#f4f6f9",
        "card": "#ffffff", "scrollbar": "#b5c2d2",
    },
    "grass": {
        "window": "#101a13", "panel": "#17251b", "panel_alt": "#203126",
        "raised": "#293b2e", "input": "#101a13", "border": "#354d3d",
        "border_strong": "#4b6c54", "text": "#e3f0e5", "muted": "#a3b6a7",
        "accent": "#6bbf7b", "accent_hover": "#84d18f",
        "selection": "#2d5739", "selection_text": "#ffffff",
        "hover": "#2a3e2f", "pressed": "#0c140f",
        "titlebar": "#17251b", "titlebar_text": "#e3f0e5",
        "titlebar_border": "#354d3d", "status": "#142118",
        "card": "#1c2c21", "scrollbar": "#54725c",
    },
    "pink": {
        "window": "#1c1219", "panel": "#281924", "panel_alt": "#34212e",
        "raised": "#432a3b", "input": "#1b1118", "border": "#54374a",
        "border_strong": "#6b465e", "text": "#f6eaf1", "muted": "#c3a8b7",
        "accent": "#dc78a5", "accent_hover": "#ed91b9",
        "selection": "#63364f", "selection_text": "#ffffff",
        "hover": "#4a2c40", "pressed": "#170e14",
        "titlebar": "#281924", "titlebar_text": "#f6eaf1",
        "titlebar_border": "#54374a", "status": "#22151d",
        "card": "#30202b", "scrollbar": "#80536a",
    },
    "orange": {
        "window": "#1d160f", "panel": "#281d14", "panel_alt": "#352519",
        "raised": "#44301f", "input": "#19130e", "border": "#59412c",
        "border_strong": "#765434", "text": "#fff0df", "muted": "#c6ad91",
        "accent": "#e99a45", "accent_hover": "#f5ad61",
        "selection": "#704522", "selection_text": "#ffffff",
        "hover": "#503720", "pressed": "#17110b",
        "titlebar": "#281d14", "titlebar_text": "#fff0df",
        "titlebar_border": "#59412c", "status": "#21180f",
        "card": "#302318", "scrollbar": "#80603f",
    },
}

def engo_ui_theme_tokens(value) -> dict:
    """Return a fresh, normalized palette dictionary for the requested UI theme."""
    theme = normalize_ui_theme(value)
    return dict(_ENGO_UI_THEME_TOKENS.get(theme, _ENGO_UI_THEME_TOKENS["dark"]))


def normalize_ui_theme(value) -> str:
    """Normalize persisted UI theme names to one of Engo's six palettes."""
    raw = str(value or "dark").strip().lower().replace("_", "-")
    if raw in {"light", "light theme", "فاتح"} or "light" in raw or "فاتح" in raw:
        return "light"
    if "midnight" in raw or "منتصف الليل" in raw or "navy" in raw:
        return "midnight"
    if "grass" in raw or "green" in raw or "عشبي" in raw or "أخضر" in raw or "اخضر" in raw:
        return "grass"
    if "pink" in raw or "rose" in raw or "وردي" in raw or "روز" in raw:
        return "pink"
    if "orange" in raw or "amber" in raw or "برتقالي" in raw or "اورانج" in raw or "أورانج" in raw:
        return "orange"
    return "dark"


_GOOGLE_BRAND_PNG_B64 = (
    "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"
)
_GOOGLE_BRAND_ICON = None


def google_brand_icon(size: int = 20) -> QIcon:
    """Return the supplied transparent Google G asset as a scalable Qt icon."""
    global _GOOGLE_BRAND_ICON
    # Callers control display size through QWidget.setIconSize(). Keep the source
    # at a larger resolution so Qt can render it cleanly on high-DPI displays.
    _ = max(16, int(size))
    if _GOOGLE_BRAND_ICON is None:
        pixmap = QPixmap()
        if pixmap.loadFromData(base64.b64decode(_GOOGLE_BRAND_PNG_B64)):
            _GOOGLE_BRAND_ICON = QIcon(pixmap)
        else:
            _GOOGLE_BRAND_ICON = QIcon()
    return _GOOGLE_BRAND_ICON

def engo_theme_qpalette(base_palette: QPalette, theme) -> QPalette:
    """Build the complete Qt palette from the same semantic tokens used by QSS."""
    tokens = engo_ui_theme_tokens(theme)
    palette = QPalette(base_palette)
    roles = {
        QPalette.ColorRole.Window: tokens["window"],
        QPalette.ColorRole.WindowText: tokens["text"],
        QPalette.ColorRole.Base: tokens["input"],
        QPalette.ColorRole.AlternateBase: tokens["panel"],
        QPalette.ColorRole.ToolTipBase: tokens["panel"],
        QPalette.ColorRole.ToolTipText: tokens["text"],
        QPalette.ColorRole.Text: tokens["text"],
        QPalette.ColorRole.Button: tokens["raised"],
        QPalette.ColorRole.ButtonText: tokens["text"],
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: tokens["selection"],
        QPalette.ColorRole.HighlightedText: tokens["selection_text"],
        QPalette.ColorRole.PlaceholderText: tokens["muted"],
        QPalette.ColorRole.Link: tokens["accent"],
        QPalette.ColorRole.LinkVisited: tokens["accent_hover"],
        QPalette.ColorRole.Light: tokens["panel_alt"],
        QPalette.ColorRole.Mid: tokens["border"],
        QPalette.ColorRole.Dark: tokens["window"],
        QPalette.ColorRole.Shadow: tokens["window"],
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
        for role, color in roles.items():
            if group == QPalette.ColorGroup.Disabled and role in (
                QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                QPalette.ColorRole.ButtonText, QPalette.ColorRole.ToolTipText,
            ):
                color = tokens["muted"]
            palette.setColor(group, role, QColor(color))
    return palette


# Shared translations for native Qt tooltips.  Keep the English source strings
# as keys so language switching is reversible and dynamically-created widgets
# can use the same translation path as the main interface.
_ENGO_TOOLTIP_TRANSLATIONS = {
    "Model ID for native, bidirectional Gemini Live voice sessions": "معرّف النموذج لجلسات Gemini Live الصوتية ثنائية الاتجاه.",
    "إضافة النص المحدد إلى سؤال جديد في نفس المحادثة": "إضافة النص المحدد إلى سؤال جديد في نفس المحادثة",
    "Summarize/review the whole PDF or ask about the current page": "لخّص ملف PDF بالكامل أو راجعه، أو اسأل عن الصفحة الحالية.",
    "Export this conversation as Markdown or a formatted PDF report": "تصدير هذه المحادثة بصيغة Markdown أو كتقرير PDF منسّق.",
    "Expand chat · hide the PDF and app controls (Ctrl+Shift+F)": "توسيع المحادثة وإخفاء ملف PDF وأدوات البرنامج (Ctrl+Shift+F).",
    "Configure provider API keys and exact model IDs": "إعداد مفاتيح API الخاصة بمزوّدي الذكاء الاصطناعي ومعرّفات النماذج بدقة.",
    "The current PDF provides context to questions when enabled": "يُستخدم ملف PDF الحالي كسياق للأسئلة عند تفعيل هذا الخيار.",
    "Choose the model for this chat. Refresh available models in AI provider settings.": "اختر النموذج المستخدم في هذه المحادثة. حدّث النماذج المتاحة من إعدادات مزوّد الذكاء الاصطناعي.",
    "Send message": "إرسال الرسالة.",
    "Stop the current AI response": "إيقاف استجابة الذكاء الاصطناعي الحالية.",
    "Read the latest AI answer aloud": "اقرأ أحدث إجابة من Engo AI بصوت مسموع.",
    "Stop the spoken answer": "إيقاف تشغيل الإجابة الصوتية.",
    "Record one spoken question, send it to the selected AI, and read its answer aloud": "سجّل سؤالك صوتيًا وأرسله إلى المساعد المحدد واستمع إلى إجابته.",
    "Show page thumbnails": "إظهار صور الصفحات المصغّرة.",
    "Show all PDF pages": "عرض جميع صفحات ملف PDF في شاشة واحدة.",
    "Close page overview": "إغلاق عرض جميع الصفحات.",
    "Show the document outline": "إظهار فهرس محتويات المستند.",
    "Save As…": "حفظ باسم…",
    "Save PDF": "حفظ ملف PDF",
    "Add an image, paste from clipboard, or select a region from the PDF": "إضافة صورة من ملف أو الحافظة، أو تحديد منطقة من ملف PDF.",
    "Book · show two pages side by side; can be combined with Scroll": "وضع الكتاب · عرض صفحتين متجاورتين، ويمكن استخدامه مع التمرير.",
    "Choose which AI service receives your question": "اختر خدمة الذكاء الاصطناعي التي ستستقبل سؤالك.",
    "Close conversation search": "إغلاق البحث داخل المحادثة.",
    "Go to parent folder": "الانتقال إلى المجلد الأب.",
    "Include PDF text or page previews. Current-page actions always include the current page.": "إرفاق نص PDF أو معاينات الصفحات. إجراءات الصفحة الحالية ترفقها دائمًا.",
    "Next match": "النتيجة التالية.",
    "Previous match": "النتيجة السابقة.",
    "Remove pending images, PDF regions, and selected chat text": "إزالة الصور ومناطق PDF والنصوص المحددة المرفقة.",
    "Remove selected chat text": "إزالة النص المحدد من المحادثة.",
    "Saved conversations for the current PDF": "المحادثات المحفوظة لملف PDF الحالي.",
    "Saved conversations for this linked PDF pair": "المحادثات المحفوظة لملفي PDF المرتبطين.",
    "Search inside this conversation": "البحث داخل هذه المحادثة.",
    "Start a new saved conversation for this PDF": "بدء محادثة محفوظة جديدة لهذا الملف.",
    "Start a new shared conversation for both linked PDFs": "بدء محادثة مشتركة جديدة لملفي PDF المرتبطين.",
    "Choose a tag to list all regions assigned to it": "اختر وسمًا لعرض جميع المناطق المرتبطة به.",
    "Hide this search window without clearing the selected PDF result": "إخفاء نافذة البحث دون إلغاء نتيجة PDF المحددة.",
    "Close search and clear all highlighted search results": "إغلاق البحث ومسح جميع نتائج البحث المظللة.",
    "Start one live lesson for the current PDF page": "بدء حصة مباشرة لشرح صفحة PDF الحالية.",
    "Update Gemini with both currently displayed PDF pages when a combined tab is active": "تحديث Gemini بمحتوى صفحتي PDF المعروضتين عند تفعيل تبويب الملفين.",
    "Hold the Space key or hold this button while speaking. Microphone audio is not sent when released.": "اضغط مطولًا على زر المسافة أو هذا الزر أثناء التحدث. لا يُرسل صوت الميكروفون عند ترك الزر.",
    "Pause the lesson without ending the session. Resume repeats the last point, then continues.": "إيقاف الحصة مؤقتًا دون إنهاء الجلسة. عند الاستئناف، يعيد المدرّس آخر نقطة ثم يكمل.",
    "Select the natural Gemini Live voice. Changes apply to the next session.": "اختر الصوت الطبيعي لـ Gemini Live. تُطبّق التغييرات في الجلسة التالية.",
    "Gemini native audio infers the spoken language; this choice guides its dialect and wording.": "يكتشف Gemini لغة الكلام تلقائيًا؛ ويساعده هذا الاختيار في تحديد اللهجة وطريقة الصياغة.",
    "شرح لتعلّم وفهم المحتوى بالكامل، أو مراجعة سريعة لاسترجاع أهم النقاط. Applies to the next session.": "شرح تفصيلي لفهم المحتوى بالكامل، أو مراجعة سريعة لاسترجاع أهم النقاط. يُطبّق في الجلسة التالية.",
    "Edit the AI teacher personality and extra instructions": "تعديل شخصية مدرّس الذكاء الاصطناعي وإضافة تعليمات خاصة.",
    "Enable, drag a box around text, handwriting, a formula, chart, or drawing, then ask by voice or text.": "فعّل الأداة واسحب لتحديد نص أو كتابة يدوية أو معادلة أو رسم بياني أو شكل، ثم اسأل بالصوت أو الكتابة.",
    "Previous page in the primary PDF": "الانتقال إلى الصفحة السابقة في ملف PDF الأساسي.",
    "Next page in the primary PDF": "الانتقال إلى الصفحة التالية في ملف PDF الأساسي.",
    "Previous page in supplementary PDF": "الانتقال إلى الصفحة السابقة في ملف PDF الإضافي.",
    "Next page in supplementary PDF": "الانتقال إلى الصفحة التالية في ملف PDF الإضافي.",
    "Save this board inside Engo, linked to the current PDF and page.": "حفظ لوحة الشرح داخل Engo وربطها بملف PDF والصفحة الحالية.",
    "Export the saved teaching boards for every page of this PDF into one Markdown file.": "تصدير لوحات الشرح المحفوظة لكل صفحات ملف PDF إلى ملف Markdown واحد.",
    "Export the saved teaching boards for every page of this PDF into one PDF file.": "تصدير لوحات الشرح المحفوظة لكل صفحات ملف PDF إلى ملف PDF واحد.",
    "Send a typed question or board instruction to Engo AI": "إرسال سؤال مكتوب أو تعليمات لتعديل لوحة الشرح إلى Engo AI.",
    "Read the latest AI answer aloud": "اقرأ أحدث إجابة من Engo AI بصوت مسموع.",
    "Stop the spoken answer": "إيقاف تشغيل الإجابة الصوتية.",
    "Scroll to the latest message in this conversation": "انتقل إلى أحدث رسالة في هذه المحادثة.",
    "Show page thumbnails": "إظهار صور الصفحات المصغّرة.",
    "Show the document outline": "إظهار فهرس محتويات المستند.",
    "Open PDF in a new tab (Ctrl+O)": "فتح ملف PDF في تبويب جديد (Ctrl+O).",
    "Link two open PDFs as one study conversation: primary + supplementary": "ربط ملفي PDF مفتوحين في محادثة دراسية واحدة: أساسي + إضافي.",
    "Home · recent PDFs, settings, and last session": "الرئيسية · ملفات PDF الأخيرة والإعدادات والجلسة السابقة.",
    "Select annotations, read, or activate links": "تحديد نص PDF أو التعليقات التوضيحية أو فتح الروابط. ابدأ السحب من النص لتحديده.",
    "Draw freehand ink on the page": "الرسم أو الكتابة بخط اليد مباشرةً على الصفحة.",
    "Highlight selectable text or mark a scanned area": "ابدأ السحب فوق النص لتظليله كنص، أو ابدأ من منطقة غير نصية لتظليلها كمربع فقط.",
    "Add a sticky-note comment": "إضافة ملاحظة لاصقة إلى الصفحة.",
    "Place editable text on the page": "إضافة مربع نص قابل للتحرير إلى الصفحة.",
    "Draw an internal link to another page": "رسم رابط داخلي ينقلك إلى صفحة أخرى.",
    "Save changes · use the arrow for Save As": "حفظ التغييرات · استخدم السهم لاختيار حفظ باسم.",
    "Save a copy to another PDF path (Ctrl+Shift+S)": "حفظ نسخة في مسار PDF آخر (Ctrl+Shift+S).",
    "Search this entire PDF · exact text or AI search for concepts, handwriting, and images": "البحث في ملف PDF بالكامل · بحث نصي دقيق أو بحث بالذكاء الاصطناعي عن المفاهيم والكتابة اليدوية والصور.",
    "Show or hide page thumbnails and table of contents": "إظهار أو إخفاء صور الصفحات المصغّرة وفهرس المحتويات.",
    "Scroll · connect pages vertically; turn off to show one page/spread at a time": "التمرير · عرض الصفحات متصلة رأسيًا؛ أوقفه لعرض صفحة أو صفحتين في كل مرة.",
    "Zoom out (Ctrl + mouse wheel down / Ctrl+-)": "تصغير العرض (Ctrl + عجلة الماوس لأسفل / Ctrl+-).",
    "Current zoom level": "مستوى التكبير الحالي.",
    "Zoom in (Ctrl + mouse wheel up / touchpad pinch)": "تكبير العرض (Ctrl + عجلة الماوس لأعلى / ضم إصبعين على لوحة اللمس).",
    "Fit page to the available width": "ملاءمة عرض الصفحة مع المساحة المتاحة.",
    "Fit the complete page inside the window": "إظهار الصفحة كاملة داخل النافذة.",
    "Previous page (Left / Page Up)": "الصفحة السابقة (السهم الأيسر / Page Up).",
    "Jump to page number": "الانتقال مباشرةً إلى رقم صفحة.",
    "Next page (Right / Page Down)": "الصفحة التالية (السهم الأيمن / Page Down).",
    "Rotate the current PDF page 90° clockwise; use the arrow for the whole file": "تدوير صفحة PDF الحالية 90 درجة مع عقارب الساعة؛ استخدم السهم لتدوير الملف بالكامل.",
    "Tag region · drag over an area to assign the selected tag; use the arrow to choose or edit tags": "وسم منطقة · اسحب فوق جزء من الصفحة لإسناد الوسم المحدد إليه، أو استخدم السهم لاختيار الوسوم وتعديلها.",
    "Undo last PDF edit (Ctrl+Z)": "التراجع عن آخر تعديل في PDF (Ctrl+Z).",
    "Redo the last undone edit (Ctrl+Y)": "إعادة آخر تعديل تم التراجع عنه (Ctrl+Y).",
    "Delete the selected annotation (Delete key)": "حذف التعليق التوضيحي المحدد (زر Delete).",
    "Annotation colors · pen, highlight, note, and text box": "ألوان التعليقات التوضيحية · القلم والتظليل والملاحظة ومربع النص.",
    "Page Theme · dark mode and custom document colors": "مظهر الصفحة · الوضع الداكن وألوان المستند المخصصة.",
    "Open the AI study chat for summaries, explanations, translation, and OCR": "فتح محادثة Engo AI للتلخيص والشرح والترجمة والتعرّف على النصوص (OCR).",
    "Lesson with AI · open a live spoken AI teacher with the PDF page and lesson board": "حصة صوتية مع AI · فتح مدرس صوتي مباشر يستخدم صفحة PDF ولوحة الشرح.",
    "Audio lesson with AI · a live spoken lesson based on the current PDF page": "حصة صوتية مع AI · حصة صوتية مباشرة تعتمد على صفحة PDF الحالية.",
    "Translate a selected PDF region in Engo · choose a region, then see a popup card": "ترجمة منطقة محددة من PDF داخل Engo · حدد المنطقة لعرض الترجمة في نافذة منبثقة.",
    "Presentation mode (F5)": "وضع العرض التقديمي (F5).",
    "Toggle distraction-free full screen (F11)": "التبديل إلى وضع ملء الشاشة دون مشتتات (F11).",
    "Unpin toolbar · it will auto-hide when the pointer leaves": "إلغاء تثبيت شريط الأدوات · سيختفي تلقائيًا عند إبعاد مؤشر الماوس.",
    "Enter a folder path and press Enter": "أدخل مسار مجلد ثم اضغط Enter.",
    "Zoom in (Ctrl + mouse wheel up / touchpad pinch). Mouse wheel without Ctrl turns pages.": "تكبير العرض (Ctrl + عجلة الماوس لأعلى / ضم إصبعين). استخدم عجلة الماوس دون Ctrl للتنقل بين الصفحات.",
    "Fetch the models your API key can currently access from the provider.": "جلب النماذج التي يستطيع مفتاح API الوصول إليها حاليًا من المزوّد.",
    "Copy this answer": "نسخ هذه الإجابة.",
    "Copied": "تم النسخ.",
    "Exit chat focus mode · show the PDF and app controls (Esc)": "الخروج من وضع تركيز المحادثة وإظهار ملف PDF وأدوات البرنامج (Esc).",
    "One conversation includes the current page from both PDFs.\nPrimary: {primary}\nSupplementary: {supplementary}": "تتضمن المحادثة الصفحة الحالية من ملفي PDF.\nالأساسي: {primary}\nالإضافي: {supplementary}",
    "Microphone is active. Tap to stop and keep the recognized text in the chat box; it will not be sent automatically.": "الميكروفون يعمل. اضغط للإيقاف والاحتفاظ بالنص المتعرّف عليه في مربع المحادثة؛ لن يُرسل تلقائيًا.",
    "Record your speech and insert the transcription into the chat box. Press Send when ready.": "سجّل كلامك لإدراج النص الناتج في مربع المحادثة. اضغط إرسال عندما تكون جاهزًا.",
    "Finishing the current speech phrase and placing it in the chat box": "جارٍ إنهاء العبارة الصوتية الحالية وإضافتها إلى مربع المحادثة.",
}


def _engo_translate_tooltip(source, language="en"):
    """Translate a tooltip without losing the original English text on language switches."""
    text = str(source or "")
    if not text:
        return text
    lang = "ar" if str(language or "en").lower().startswith("ar") else "en"
    if lang == "ar":
        exact = _ENGO_TOOLTIP_TRANSLATIONS.get(text)
        if exact is not None:
            return exact
        match = re.fullmatch(r"Model for this conversation · (\d+) model\(s\) available\. Refresh the list in AI provider settings\.", text)
        if match:
            return f"نموذج هذه المحادثة · يتوفر {match.group(1)} نموذجًا. حدّث القائمة من إعدادات مزوّد الذكاء الاصطناعي."
        match = re.fullmatch(r"Open the official (.+) key page in your browser", text)
        if match:
            providers = {"Gemini":"Gemini", "OpenAI":"OpenAI", "Claude":"Claude", "DeepSeek":"DeepSeek"}
            return f"فتح صفحة مفاتيح {providers.get(match.group(1), match.group(1))} الرسمية في المتصفح."
        match = re.fullmatch(r"Page (\d+)", text)
        if match:
            return f"صفحة {match.group(1)}"
        match = re.fullmatch(r"(.+) · Page (\d+)", text)
        if match:
            return f"{match.group(1)} · صفحة {match.group(2)}"
        match = re.fullmatch(r"Unable to browse folder: (.+)", text)
        if match:
            return f"تعذّر استعراض المجلد: {match.group(1)}"
        match = re.fullmatch(r"Unpin toolbar · it will auto-hide when the pointer leaves", text)
        if match:
            return "إلغاء تثبيت شريط الأدوات · سيختفي تلقائيًا عند إبعاد مؤشر الماوس."
        if text == "Pin toolbar open · keep it visible":
            return "تثبيت شريط الأدوات وإبقاؤه ظاهرًا."
        match = re.fullmatch(r"Tag region · current tag: (.+)\. Drag over an area to assign the tag, or use the arrow to choose or edit tags\.", text)
        if match:
            return f"وسم منطقة · الوسم الحالي: {match.group(1)}. اسحب فوق المنطقة لإسناد الوسم، أو استخدم السهم لاختيار الوسوم وتعديلها."
        match = re.fullmatch(r"Rename (.+) everywhere in the tag library", text)
        if match:
            return f"إعادة تسمية {match.group(1)} في مكتبة الوسوم بالكامل."
        match = re.fullmatch(r"Change the shared color for (.+)", text)
        if match:
            return f"تغيير اللون المشترك للوسم {match.group(1)}."
        match = re.fullmatch(r"Delete (.+) from the global tag library", text)
        if match:
            return f"حذف {match.group(1)} من مكتبة الوسوم العامة."
        match = re.fullmatch(r"(.+) · use the menu to switch to Hand/Pan", text)
        if match:
            base = match.group(1)
            return f"{base} · استخدم القائمة للتبديل إلى أداة اليد/التحريك."
        if text.endswith(" · saved with this message"):
            return text[:-len(" · saved with this message")] + " · محفوظ مع هذه الرسالة"
        if text.startswith("Remove this attachment"):
            return "إزالة هذا المرفق"
        if text.startswith("Close "):
            return "إغلاق " + text[6:]
        return text
    reverse = {arabic: english for english, arabic in _ENGO_TOOLTIP_TRANSLATIONS.items()}
    if text in reverse:
        return reverse[text]
    match = re.fullmatch(r"نموذج هذه المحادثة · يتوفر (\d+) نموذجًا\. حدّث القائمة من إعدادات مزوّد الذكاء الاصطناعي\.", text)
    if match:
        return f"Model for this conversation · {match.group(1)} model(s) available. Refresh the list in AI provider settings."
    match = re.fullmatch(r"صفحة (\d+)", text)
    if match:
        return f"Page {match.group(1)}"
    match = re.fullmatch(r"(.+) · صفحة (\d+)", text)
    if match:
        return f"{match.group(1)} · Page {match.group(2)}"
    match = re.fullmatch(r"إغلاق (.+)", text)
    if match:
        return f"Close {match.group(1)}"
    match = re.fullmatch(r"وسم منطقة · الوسم الحالي: (.+)\. اسحب فوق المنطقة لإسناد الوسم، أو استخدم السهم لاختيار الوسوم وتعديلها\.", text)
    if match:
        return f"Tag region · current tag: {match.group(1)}. Drag over an area to assign the tag, or use the arrow to choose or edit tags."
    match = re.fullmatch(r"إعادة تسمية (.+) في مكتبة الوسوم بالكامل\.", text)
    if match:
        return f"Rename {match.group(1)} everywhere in the tag library"
    match = re.fullmatch(r"تغيير اللون المشترك للوسم (.+)\.", text)
    if match:
        return f"Change the shared color for {match.group(1)}"
    match = re.fullmatch(r"حذف (.+) من مكتبة الوسوم العامة\.", text)
    if match:
        return f"Delete {match.group(1)} from the global tag library"
    if text.endswith(" · استخدم القائمة للتبديل إلى أداة اليد/التحريك."):
        return text[:-len(" · استخدم القائمة للتبديل إلى أداة اليد/التحريك.")] + " · use the menu to switch to Hand/Pan"
    if text.endswith(" · محفوظ مع هذه الرسالة"):
        return text[:-len(" · محفوظ مع هذه الرسالة")] + " · saved with this message"
    if text == "تثبيت شريط الأدوات وإبقاؤه ظاهرًا.":
        return "Pin toolbar open · keep it visible"
    if text == "إلغاء تثبيت شريط الأدوات · سيختفي تلقائيًا عند إبعاد مؤشر الماوس.":
        return "Unpin toolbar · it will auto-hide when the pointer leaves"
    if text == "إزالة هذا المرفق":
        return "Remove this attachment"
    if text.startswith("تعذّر استعراض المجلد: "):
        return "Unable to browse folder: " + text.partition(": ")[2]
    return text


class EngoTooltipTranslationFilter(QObject):
    """Translate Qt hover tips at display time, including widgets created later."""
    def eventFilter(self, watched, event):
        try:
            if event.type() == QEvent.Type.ToolTip and isinstance(watched, QWidget):
                current = str(watched.toolTip() or "").strip()
                if current:
                    original = watched.property("engoOriginalToolTip")
                    rendered = watched.property("engoRenderedToolTip")
                    if original is None:
                        original = current
                    else:
                        original = str(original or "")
                        # setToolTip() is often called again by dynamic controls (Send/Stop,
                        # voice recording, linked-document labels). Treat a value that is
                        # neither the source nor one of its known translations as a new source.
                        known_values = {original, str(rendered or ""),
                                        _engo_translate_tooltip(original, "ar"),
                                        _engo_translate_tooltip(original, "en")}
                        if current not in known_values:
                            original = current
                    watched.setProperty("engoOriginalToolTip", original)

                    # Dialogs may be separate top-level windows. Walk their parent chain
                    # to find the owning MainWindow settings instead of defaulting to English.
                    settings = None
                    node = watched
                    while node is not None and settings is None:
                        settings = getattr(node, "settings", None)
                        try:
                            node = node.parentWidget()
                        except (RuntimeError, AttributeError):
                            node = None
                    if settings is None:
                        app = QApplication.instance()
                        settings = getattr(app, "_engo_settings", None) if app is not None else None
                    try:
                        language = settings.value("interface_language", "en", type=str) if settings is not None else "en"
                    except Exception:
                        language = "en"
                    translated = _engo_translate_tooltip(original, language)
                    watched.setProperty("engoRenderedToolTip", translated)
                    if translated != current:
                        watched.setToolTip(translated)
        except (RuntimeError, AttributeError, TypeError):
            pass
        return super().eventFilter(watched, event)


# ---------------------------------------------------------------------------
# Engo popup/dialog consistency layer
# Keeps every modal window visually related: predictable size classes,
# consistent action-button geometry, theme-aware controls and RTL order.
# ---------------------------------------------------------------------------
_ENGO_DIALOG_BUTTON_AR = {
    QMessageBox.StandardButton.Ok: "موافق",
    QMessageBox.StandardButton.Cancel: "إلغاء",
    QMessageBox.StandardButton.Yes: "نعم",
    QMessageBox.StandardButton.No: "لا",
    QMessageBox.StandardButton.Save: "حفظ",
    QMessageBox.StandardButton.Discard: "تجاهل",
    QMessageBox.StandardButton.Apply: "تطبيق",
    QMessageBox.StandardButton.Close: "إغلاق",
    QMessageBox.StandardButton.Retry: "إعادة المحاولة",
    QMessageBox.StandardButton.Abort: "إيقاف",
    QMessageBox.StandardButton.Ignore: "تجاهل",
    QMessageBox.StandardButton.Help: "مساعدة",
    QMessageBox.StandardButton.RestoreDefaults: "استعادة الافتراضي",
}
_ENGO_DIALOG_DEFAULT_LABELS = {
    "OK", "Ok", "Cancel", "Yes", "No", "Save", "Discard", "Apply",
    "Close", "Retry", "Abort", "Ignore", "Help", "Restore Defaults",
}


def _engo_dialog_host_settings(dialog):
    node = dialog
    while node is not None:
        settings = getattr(node, "settings", None)
        if settings is not None and hasattr(settings, "value"):
            return settings
        try:
            node = node.parentWidget()
        except Exception:
            break
    try:
        return QSettings(APP_ORG, "EngoPDFViewer")
    except Exception:
        return None


def _engo_apply_windows_caption_theme(widget, theme=None, settings=None):
    """Tint the native Windows caption for every Engo top-level window.

    Qt stylesheets cannot paint the operating-system title bar or its native
    minimize/maximize/close buttons. DWM caption attributes let Windows keep
    those native controls while matching the active Engo palette.
    """
    if sys.platform != "win32":
        return False
    try:
        if settings is None:
            settings = _engo_dialog_host_settings(widget)
        if theme is None:
            raw_theme = settings.value("ui_theme", "dark", type=str) if settings is not None else "dark"
            theme = normalize_ui_theme(raw_theme)
        else:
            theme = normalize_ui_theme(theme)
        tokens = engo_ui_theme_tokens(theme)

        import ctypes
        from ctypes import wintypes

        hwnd_value = int(widget.winId())
        if not hwnd_value:
            return False
        hwnd = wintypes.HWND(hwnd_value)
        dwmapi = ctypes.WinDLL("dwmapi")
        set_attribute = dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        set_attribute.restype = ctypes.c_long

        def colorref(hex_color):
            color = QColor(str(hex_color))
            return (int(color.red()) | (int(color.green()) << 8) | (int(color.blue()) << 16))

        # Prefer the modern attribute, then use the compatibility attribute
        # for Windows builds that expose the earlier dark-caption flag.
        dark_caption = ctypes.c_int(0 if theme == "light" else 1)
        hr = set_attribute(hwnd, 20, ctypes.byref(dark_caption), ctypes.sizeof(dark_caption))
        if hr != 0:
            set_attribute(hwnd, 19, ctypes.byref(dark_caption), ctypes.sizeof(dark_caption))

        applied = False
        for attribute, key in ((35, "titlebar"), (36, "titlebar_text"), (34, "titlebar_border")):
            value = ctypes.c_uint32(colorref(tokens[key]))
            result = set_attribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
            if result == 0:
                applied = True
        return applied
    except Exception:
        # Non-Windows platforms and unsupported Windows/DWM builds keep their
        # normal native title bar; the Qt dialog content remains fully themed.
        return False


def _engo_menu_colors(theme):
    tokens = engo_ui_theme_tokens(theme)
    return {
        "bg": tokens["panel"],
        "fg": tokens["text"],
        "border": tokens["border"],
        "hover": tokens["hover"],
        "selected": tokens["selection"],
        "selected_fg": tokens["selection_text"],
        "muted": tokens["muted"],
    }


def _engo_menu_stylesheet(colors):
    """Minimal Qt-supported rules for native popup menus."""
    return f"""
        QMenu {{ background-color: {colors['bg']}; color: {colors['fg']};
            border: 1px solid {colors['border']}; padding: 4px; }}
        QMenu::item {{ color: {colors['fg']}; padding: 7px 12px; }}
        QMenu::item:selected {{ background-color: {colors['selected']};
            color: {colors['selected_fg']}; }}
    """


def _engo_apply_menu_consistency(menu, theme=None, is_ar=None):
    """Apply the active Engo theme to any native QMenu, including combo popups."""
    if not isinstance(menu, QMenu):
        return
    try:
        settings = _engo_dialog_host_settings(menu)
        if theme is None:
            try:
                settings.sync()
            except Exception:
                pass
            theme = settings.value("ui_theme", "dark", type=str) if settings is not None else "dark"
        if is_ar is None:
            language = settings.value("interface_language", "en", type=str) if settings is not None else "en"
            is_ar = str(language or "en").lower().startswith("ar")
        colors = _engo_menu_colors(theme)
        palette = QPalette(menu.palette())
        for role, key in (
            (QPalette.ColorRole.Window, "bg"),
            (QPalette.ColorRole.WindowText, "fg"),
            (QPalette.ColorRole.Base, "bg"),
            (QPalette.ColorRole.AlternateBase, "bg"),
            (QPalette.ColorRole.Text, "fg"),
            (QPalette.ColorRole.Button, "bg"),
            (QPalette.ColorRole.ButtonText, "fg"),
            (QPalette.ColorRole.Highlight, "selected"),
            (QPalette.ColorRole.HighlightedText, "selected_fg"),
            (QPalette.ColorRole.ToolTipBase, "bg"),
            (QPalette.ColorRole.ToolTipText, "fg"),
        ):
            palette.setColor(role, QColor(colors[key]))
        menu.setPalette(palette)
        menu.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if is_ar else Qt.LayoutDirection.LeftToRight
        )
        menu.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        menu.setAutoFillBackground(True)
        menu.setStyleSheet(_engo_menu_stylesheet(colors))
    except (RuntimeError, AttributeError, TypeError):
        return


def _engo_set_dialog_theme_stylesheet(dialog, popup_qss):
    """Replace the shared popup QSS while preserving the dialog's latest local QSS."""
    current_style = str(dialog.styleSheet() or "")
    base_style = dialog.property("_engoDialogBaseStyle")
    last_composed_style = dialog.property("_engoDialogComposedStyle")

    if base_style is None:
        base_style = current_style
    else:
        expected_previous = str(last_composed_style or "")
        # A feature dialog may rebuild its own stylesheet during a theme change.
        # If it did, adopt that new local stylesheet rather than reviving the old one.
        if current_style != expected_previous:
            base_style = current_style

    base_style = str(base_style or "")
    composed_style = base_style + "\n" + str(popup_qss or "")
    dialog.setProperty("_engoDialogBaseStyle", base_style)
    dialog.setProperty("_engoDialogLastPopupStyle", str(popup_qss or ""))
    dialog.setProperty("_engoDialogComposedStyle", composed_style)
    if current_style != composed_style:
        dialog.setStyleSheet(composed_style)
    return composed_style


def _engo_apply_dialog_consistency(dialog, theme=None, is_ar=None):
    """Apply common Engo styling and sizing to any Qt popup/dialog."""
    if not isinstance(dialog, QDialog):
        return
    try:
        settings = _engo_dialog_host_settings(dialog)
        if theme is None:
            raw_theme = settings.value("ui_theme", "dark", type=str) if settings is not None else "dark"
            theme = normalize_ui_theme(raw_theme)
        else:
            theme = normalize_ui_theme(theme)
        if is_ar is None:
            raw_language = settings.value("interface_language", "en", type=str) if settings is not None else "en"
            is_ar = str(raw_language or "en").lower().startswith("ar")
        else:
            is_ar = bool(is_ar)

        # Dialogs consume the same semantic tokens as the main window. Keep
        # only this mapping layer here so adding a theme requires one palette.
        palette_tokens = engo_ui_theme_tokens(theme)
        c = {
            "bg": palette_tokens["window"],
            "fg": palette_tokens["text"],
            "panel": palette_tokens["panel"],
            "field": palette_tokens["input"],
            "border": palette_tokens["border"],
            "hover": palette_tokens["hover"],
            "hover_fg": palette_tokens["text"],
            "accent": palette_tokens["accent"],
            "accent_hover": palette_tokens["accent_hover"],
            "muted": palette_tokens["muted"],
            "selection": palette_tokens["selection"],
            "selection_fg": palette_tokens["selection_text"],
        }

        direction = (
            Qt.LayoutDirection.LeftToRight
            if bool(dialog.property("engoForceLTRLayout"))
            else (Qt.LayoutDirection.RightToLeft if is_ar else Qt.LayoutDirection.LeftToRight)
        )
        dialog.setLayoutDirection(direction)
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Apply a matching native palette as well as QSS. Several Windows controls
        # (especially standard message boxes and combo popup views) otherwise keep
        # the OS light palette even while the surrounding dialog is themed.
        dialog_palette = QPalette(dialog.palette())
        for role, color in (
            (QPalette.ColorRole.Window, c["bg"]),
            (QPalette.ColorRole.WindowText, c["fg"]),
            (QPalette.ColorRole.Base, c["field"]),
            (QPalette.ColorRole.AlternateBase, c["panel"]),
            (QPalette.ColorRole.Text, c["fg"]),
            (QPalette.ColorRole.Button, c["panel"]),
            (QPalette.ColorRole.ButtonText, c["fg"]),
            (QPalette.ColorRole.Highlight, c["selection"]),
            (QPalette.ColorRole.HighlightedText, c["selection_fg"]),
            (QPalette.ColorRole.ToolTipBase, c["panel"]),
            (QPalette.ColorRole.ToolTipText, c["fg"]),
            (QPalette.ColorRole.PlaceholderText, c["muted"]),
        ):
            dialog_palette.setColor(role, QColor(color))
        dialog.setPalette(dialog_palette)
        dialog.setAutoFillBackground(True)
        for child in dialog.findChildren(QWidget):
            try:
                child.setPalette(dialog_palette)
                # QLabel inherits QFrame in Qt. Do not enable native background
                # filling on labels: it turns ordinary captions into boxed fields.
                if isinstance(child, QLabel):
                    child.setAutoFillBackground(False)
                    child.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
                elif isinstance(child, (QFrame, QAbstractScrollArea)):
                    child.setAutoFillBackground(True)
                    child.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            except RuntimeError:
                continue

        # Keep large feature dialogs at their designed geometry; small utility
        # popups share a common minimum canvas, while native Qt utility dialogs
        # receive stable, purpose-sized defaults.
        if isinstance(dialog, QMessageBox):
            dialog.setMinimumSize(440, 180)
        elif isinstance(dialog, QInputDialog):
            dialog.setMinimumSize(460, 210)
        elif isinstance(dialog, QColorDialog):
            dialog.setMinimumSize(620, 420)
        elif isinstance(dialog, QFileDialog):
            dialog.setMinimumSize(760, 520)
        else:
            dialog.setMinimumSize(max(420, dialog.minimumWidth()), max(230, dialog.minimumHeight()))

        # Translate only standard Qt action labels; preserve descriptive custom
        # captions such as "Save settings" and the application's own wording.
        compact_action_buttons = bool(dialog.property("engoCompactDialogButtons"))
        for button_box in dialog.findChildren(QDialogButtonBox):
            button_box.setLayoutDirection(direction)
            layout = button_box.layout()
            if layout is not None:
                layout.setSpacing(8)
            for button in button_box.buttons():
                standard = button_box.standardButton(button)
                if is_ar and standard in _ENGO_DIALOG_BUTTON_AR and button.text().strip() in _ENGO_DIALOG_DEFAULT_LABELS:
                    button.setText(_ENGO_DIALOG_BUTTON_AR[standard])
                if compact_action_buttons:
                    # These two dialogs use the same slightly shorter action
                    # height as the rest of Engo's compact popup controls.
                    button.setMinimumWidth(90)
                    button.setFixedHeight(28)
                else:
                    button.setMinimumSize(90, 30)
                button.setProperty("engoDialogPrimary", button_box.buttonRole(button) in (
                    QDialogButtonBox.ButtonRole.AcceptRole,
                    QDialogButtonBox.ButtonRole.YesRole,
                    QDialogButtonBox.ButtonRole.ApplyRole,
                ))
                button.style().unpolish(button)
                button.style().polish(button)

        if isinstance(dialog, QMessageBox):
            for button in dialog.buttons():
                standard = dialog.standardButton(button)
                if is_ar and standard in _ENGO_DIALOG_BUTTON_AR and button.text().strip() in _ENGO_DIALOG_DEFAULT_LABELS:
                    button.setText(_ENGO_DIALOG_BUTTON_AR[standard])
                # Keep all five close/restore choices visually identical:
                # three exit actions and the two startup session actions.
                button.setMinimumWidth(96)
                button.setFixedHeight(28)
                button.setProperty("engoDialogPrimary", standard in (
                    QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Yes,
                    QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Apply,
                    QMessageBox.StandardButton.Retry,
                ))

        combo_arrow_asset = "combo_chevron_light.png" if theme == "light" else "combo_chevron_dark.png"
        combo_arrow_path = resource_path(combo_arrow_asset).replace("\\", "/")
        popup_qss = f"""
            QDialog {{ background: {c['bg']}; color: {c['fg']}; }}
            QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel, QColorDialog QLabel,
            QFileDialog QLabel {{ color: {c['fg']}; }}
            QDialog QLineEdit, QDialog QTextEdit, QDialog QPlainTextEdit,
            QDialog QTextBrowser, QDialog QComboBox, QInputDialog QLineEdit {{
                background: {c['field']}; color: {c['fg']}; border: 1px solid {c['border']};
                selection-background-color: {c['selection']}; selection-color: {c['selection_fg']};
                border-radius: 6px; padding: 5px 7px;
            }}
            QDialog QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right;
                width: 25px; background: {c['field']}; border-left: 1px solid {c['border']}; }}
            QDialog QComboBox::down-arrow {{ image: url("{combo_arrow_path}"); width: 12px; height: 8px; border: 0; }}
            QDialog QComboBox QAbstractItemView {{ background: {c['field']}; color: {c['fg']};
                selection-background-color: {c['selection']}; selection-color: {c['selection_fg']};
                border: 1px solid {c['border']}; outline: 0; }}
            QDialogButtonBox QPushButton, QMessageBox QPushButton, QInputDialog QPushButton,
            QColorDialog QPushButton, QFileDialog QPushButton {{
                min-width: 90px; min-height: 30px; padding: 4px 10px;
                border: 1px solid {c['border']}; border-radius: 7px;
                background: {c['panel']}; color: {c['fg']}; font-weight: 650;
            }}
            QMessageBox QPushButton {{ min-width:96px; min-height:28px; max-height:28px; padding-top:1px; padding-bottom:1px; }}
            QDialogButtonBox QPushButton:hover, QMessageBox QPushButton:hover,
            QInputDialog QPushButton:hover, QColorDialog QPushButton:hover,
            QFileDialog QPushButton:hover {{ background: {c['hover']}; color: {c['hover_fg']};
                border-color: {c['accent']}; }}
            QDialogButtonBox QPushButton:pressed, QMessageBox QPushButton:pressed,
            QInputDialog QPushButton:pressed, QColorDialog QPushButton:pressed,
            QFileDialog QPushButton:pressed {{ background: {c['selection']}; color: {c['selection_fg']}; }}
            QDialogButtonBox QPushButton:disabled, QMessageBox QPushButton:disabled {{
                color: {c['muted']}; background: {c['bg']}; border-color: {c['border']};
            }}
            QDialogButtonBox QPushButton[engoDialogPrimary="true"],
            QMessageBox QPushButton[engoDialogPrimary="true"], QPushButton#primary,
            QPushButton#aiSettingsSave {{ background: {c['accent']}; color: #ffffff;
                border-color: {c['accent']}; font-weight: 750; }}
            QDialogButtonBox QPushButton[engoDialogPrimary="true"]:hover,
            QMessageBox QPushButton[engoDialogPrimary="true"]:hover,
            QPushButton#primary:hover, QPushButton#aiSettingsSave:hover {{
                background: {c['accent_hover']}; color: #ffffff; }}
            QToolTip {{ background: {c['panel']}; color: {c['fg']};
                border: 1px solid {c['border']}; padding: 5px 7px; }}
        """
        # Keep a local dialog stylesheet separate from our shared popup layer.
        # The helper detects when the dialog itself rebuilt its local QSS and
        # replaces the previous shared layer instead of restoring stale colors.
        _engo_set_dialog_theme_stylesheet(dialog, popup_qss)

        # Native title bars are outside Qt's stylesheet system. Color every
        # modal/custom window too, not just the main Engo window, while retaining
        # the operating-system caption buttons. A second pass catches delayed HWND creation.
        _engo_apply_windows_caption_theme(dialog, theme, settings)
        QTimer.singleShot(
            90,
            lambda obj=dialog, current_theme=theme, host_settings=settings:
                _engo_apply_windows_caption_theme(obj, current_theme, host_settings),
        )
    except (RuntimeError, AttributeError, TypeError):
        # A popup can be destroyed while its deferred show event is processed.
        return


class EngoDialogConsistencyFilter(QObject):
    """App-wide hook: apply the same dialog system to built-in and custom popups."""
    def eventFilter(self, watched, event):
        try:
            if event.type() == QEvent.Type.Show:
                if isinstance(watched, QDialog):
                    # The first-run wizard previews six complete palettes before
                    # the user commits one. Its own theme-aware stylesheet/palette
                    # must not be overwritten by the app's not-yet-configured theme.
                    if not bool(watched.property("engoOwnThemePreview")):
                        _engo_apply_dialog_consistency(watched)
                        QTimer.singleShot(0, lambda obj=watched: (
                            _engo_apply_dialog_consistency(obj)
                            if not bool(obj.property("engoOwnThemePreview")) else None
                        ))
                elif isinstance(watched, QMenu):
                    _engo_apply_menu_consistency(watched)
                    QTimer.singleShot(0, lambda obj=watched: _engo_apply_menu_consistency(obj))
        except RuntimeError:
            pass
        return super().eventFilter(watched, event)

# Keep a crash log for native Qt/PyMuPDF faults that may terminate the process
# without printing anything to the run.bat console.  The handle must stay open
# for faulthandler to capture fatal signals such as access violations.
_CRASH_LOG_HANDLE = None

def _install_crash_logging():
    global _CRASH_LOG_HANDLE
    candidates = [
        Path(__file__).resolve().parent / "EngoPDFViewer_crash.log",
        Path(tempfile.gettempdir()) / "EngoPDFViewer_crash.log",
    ]
    for log_path in candidates:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            _CRASH_LOG_HANDLE = open(log_path, "a", encoding="utf-8", buffering=1)
            _CRASH_LOG_HANDLE.write(f"\n\n--- Engo session started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            _CRASH_LOG_HANDLE.flush()
            faulthandler.enable(file=_CRASH_LOG_HANDLE, all_threads=True)
            previous_hook = sys.excepthook

            def _logged_exception(exc_type, exc_value, exc_tb):
                try:
                    _CRASH_LOG_HANDLE.write("\n--- Unhandled Python exception ---\n")
                    traceback.print_exception(exc_type, exc_value, exc_tb, file=_CRASH_LOG_HANDLE)
                    _CRASH_LOG_HANDLE.flush()
                except Exception:
                    pass
                previous_hook(exc_type, exc_value, exc_tb)

            sys.excepthook = _logged_exception
            return str(log_path)
        except Exception:
            try:
                if _CRASH_LOG_HANDLE is not None:
                    _CRASH_LOG_HANDLE.close()
            except Exception:
                pass
            _CRASH_LOG_HANDLE = None
    return ""


_install_crash_logging()


IMAGE_DOCUMENT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
WORD_DOCUMENT_EXTENSIONS = {".docx"}
POWERPOINT_DOCUMENT_EXTENSIONS = {".pptx"}
OFFICE_DOCUMENT_EXTENSIONS = WORD_DOCUMENT_EXTENSIONS | POWERPOINT_DOCUMENT_EXTENSIONS
DOCUMENT_EXTENSIONS = IMAGE_DOCUMENT_EXTENSIONS | {".pdf"} | OFFICE_DOCUMENT_EXTENSIONS


def is_office_document(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() in OFFICE_DOCUMENT_EXTENSIONS


def is_supported_document(path: str) -> bool:
    return Path(str(path or "")).suffix.lower() in DOCUMENT_EXTENSIONS


def resource_path(name: str) -> str:
    """Resolve bundled assets in source, PyInstaller, and Nuitka-installed layouts."""
    asset_name = str(name or "").strip()
    if not asset_name:
        return os.path.dirname(os.path.abspath(__file__))

    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass))

    try:
        candidates.append(Path(__file__).resolve().parent)
    except Exception:
        pass
    try:
        executable_dir = Path(sys.argv[0]).resolve().parent
        candidates.extend((executable_dir, executable_dir / "_internal", executable_dir / "resources"))
    except Exception:
        pass
    try:
        executable_dir = Path(sys.executable).resolve().parent
        candidates.extend((executable_dir, executable_dir / "_internal", executable_dir / "resources"))
    except Exception:
        pass
    try:
        candidates.append(Path.cwd())
    except Exception:
        pass

    checked = set()
    for base in candidates:
        try:
            canonical = str(base.resolve())
            if canonical in checked:
                continue
            checked.add(canonical)
            candidate = base / asset_name
            if candidate.is_file():
                return str(candidate)
        except Exception:
            continue

    # Preserve the source-tree fallback so callers can still report a useful path
    # when an optional asset is genuinely missing.
    try:
        return str(Path(__file__).resolve().parent / asset_name)
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), asset_name)
