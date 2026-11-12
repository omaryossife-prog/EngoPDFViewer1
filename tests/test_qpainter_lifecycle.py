from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_document_canvas_painter_is_non_reentrant_and_finalized():
    source = (ROOT / "engo_document.py").read_text(encoding="utf-8")
    start = source.index("    def paintEvent(self, event):", source.index("class DocumentCanvas(QWidget):"))
    end = source.index("    def _paint_document_scene(self, event, painter):", start)
    wrapper = source[start:end]
    assert "_paint_event_active" in wrapper
    assert "painter.isActive()" in wrapper
    assert "finally:" in wrapper
    assert "painter.end()" in wrapper

def test_page_theme_preview_painter_is_finalized():
    source = (ROOT / "engo_widgets.py").read_text(encoding="utf-8")
    start = source.index("    def paintEvent(self, event):", source.index("class PageThemePreview(QFrame):"))
    end = source.index("class PageThemeCard(QFrame):", start)
    body = source[start:end]
    assert "_paint_event_active" in body
    assert "finally:" in body
    assert "painter.end()" in body

def test_book_spread_overlay_painter_is_finalized():
    source = (ROOT / "engo_document.py").read_text(encoding="utf-8")
    start = source.index("    def paintEvent(self, event):", source.index("class BookSpreadThumbnailList(QListWidget):"))
    end = source.index("class DocumentTab(QWidget):", start)
    body = source[start:end]
    assert "_spread_paint_active" in body
    assert "finally:" in body
    assert "painter.end()" in body
