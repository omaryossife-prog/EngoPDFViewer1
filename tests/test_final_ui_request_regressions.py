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


def test_all_toolbar_dropdowns_start_with_the_highlight_card_style():
    main = read("main.py")
    for menu_name in ("rotate_page_menu", "select_tool_menu", "highlight_tool_menu", "tag_menu"):
        assert f"self._apply_toolbar_dropdown_style(self.{menu_name})" in main


def test_note_tool_is_removed_from_the_annotation_toolbar():
    main = read("main.py")
    tool_items = main[main.index("tool_items = ["):main.index("]", main.index("tool_items = ["))]
    assert '("note", "Note"' not in tool_items


def test_eye_protection_has_arabic_and_english_context_help():
    main = read("main.py")
    assert '"eye_protection_toolbar_btn": ("فعّل حماية العين' in main
    assert '"Open Eye Protection to warm page colors' in main


def test_translation_icon_uses_two_language_speech_cards():
    widgets = read("engo_widgets.py")
    start = widgets.index('elif name == "translate":')
    end = widgets.index('\n    elif name == "ocr":', start)
    icon = widgets[start:end]
    assert '"A"' in icon and '"文"' in icon
    assert "drawRoundedRect" in icon


def test_light_theme_book_and_chat_focus_icons_use_dark_foreground():
    main = read("main.py")
    chat = read("engo_ai_chat.py")
    assert 'book_icon_color = "#111111" if current_theme == "light"' in main
    assert 'book_color = "#111111" if book_theme == "light"' in main
    assert "def _focus_mode_icon_color(self):" in chat
    assert 'if theme == "light":\n                return "#111111"' in chat
    assert 'focus_icon_color = "#111111" if current_theme == "light"' in main
    assert 'engo_ui_theme_tokens(theme)["text"]' in chat


def test_startup_splash_logo_is_larger():
    splash = read("engo_licensing/ui.py")
    assert "self.logo.setFixedSize(76, 76)" in splash
    assert "pixmap(QSize(56, 56))" in splash


def test_recent_files_table_uses_real_tall_rows_and_stretches_to_window():
    main = read("main.py")
    start = main.index("self.recent_files_table = QTreeWidget()")
    end = main.index("root.addWidget(self.recent_files_table, 1)", start)
    table_setup = main[start:end]
    assert "setUniformRowHeights(False)" in table_setup
    assert "QHeaderView.ResizeMode.Stretch" in table_setup
    assert "self.recent_files_table.setMinimumHeight(300)" in table_setup
    refresh_start = main.index("def _refresh_files_home(self):")
    refresh_end = main.index("\n    def ", refresh_start + 10)
    refresh = main[refresh_start:refresh_end]
    assert '["النوع", "اسم الملف", "المكان", "ع", "آخر فتح", "فتح"]' in refresh
    assert '["Type", "File name", "Location", "n", "Last opened", "Open"]' in refresh
    assert "item.setSizeHint(0, QSize(0, 76))" in refresh


def test_annotation_settings_name_note_and_fixed_preview_rows():
    widgets = read("engo_widgets.py")
    assert 'إعدادات التعليقات التوضيحية' in widgets
    assert 'Click the circle beside an option to change its color.' in widgets
    assert 'يمكنك تغيير اللون بالضغط على الدائرة بجانب الخيار.' in widgets
    assert 'container_size=64 if is_resizable_swatch else None' in widgets
    assert 'value * self._display_scale' in widgets


def test_annotation_and_eye_sliders_have_transparent_track_and_rtl_direction():
    widgets = read("engo_widgets.py")
    assert 'QSlider::groove:horizontal {\n            height:5px; background:transparent; border:0;' in widgets
    assert "slider.setInvertedAppearance(self._is_ar)" in widgets
    assert "self.warmth_slider.setInvertedAppearance(self._is_ar)" in widgets
    assert "self.brightness_slider.setInvertedAppearance(self._is_ar)" in widgets
