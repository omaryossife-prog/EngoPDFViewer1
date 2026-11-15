from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_save_as_uses_native_windows_save_picker():
    widgets = read("engo_widgets.py")
    document = read("engo_document.py")
    assert "QFileDialog.getSaveFileName(parent, _title, _raw, _filters)" in widgets
    assert 'save=True, native=True' in document


def test_in_app_file_browser_formats_page_count_with_square_brackets():
    widgets = read("engo_widgets.py")
    assert 'return f"{base} [{count}]"' in widgets


def test_eye_protection_sliders_use_active_theme_accent_fill():
    widgets = read("engo_widgets.py")
    assert "self.warmth_slider.setStyleSheet(_theme_slider_stylesheet(self._slider_tokens))" in widgets
    assert "self.brightness_slider.setStyleSheet(_theme_slider_stylesheet(self._slider_tokens))" in widgets
    assert "QSlider::sub-page:horizontal" in widgets


def test_manual_drawing_cursor_is_a_thickness_sized_circle():
    document = read("engo_document.py")
    assert "def _set_brush_cursor(self, page_index=None):" in document
    assert "QCursor(pixmap, side // 2, side // 2)" in document
    assert "self._set_brush_cursor(self._draw_page)" in document
