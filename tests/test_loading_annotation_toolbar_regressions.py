from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_opening_queue_runs_document_preparation_off_thread_and_waits_for_session_queue():
    main = read("main.py")
    assert "ServiceActionWorker(" in main
    assert "lambda value=source_path: prepare_document_for_viewer(value)" in main
    assert "def _document_prepare_completed(" in main
    assert "def _wait_for_document_open_queue(" in main
    assert "self._wait_for_document_open_queue()" in main
    assert "QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents" in main


def test_recent_file_rows_are_twice_the_previous_height():
    main = read("main.py")
    start = main.index("def _refresh_files_home(self):")
    end = main.index("\n    def ", start + 10)
    assert "item.setSizeHint(0, QSize(0, 84))" in main[start:end]


def test_eye_protection_is_after_translate_in_the_main_toolbar_only():
    main = read("main.py")
    translate = main.index('self.translate_btn = self._button("Translate"')
    eye = main.index("self.eye_protection_toolbar_btn = self._button(", translate)
    present = main.index('self.present_btn = self._button("Present"', eye)
    assert translate < eye < present
    assert "self.eye_protection_toolbar_btn.clicked.connect(self.open_eye_protection_settings)" in main
    document = read("engo_document.py")
    assert "self.eye_protection_btn =" not in document


def test_annotation_palette_exposes_pen_and_highlighter_width_and_theme_sharing():
    base = read("engo_base.py")
    widgets = read("engo_widgets.py")
    main = read("main.py")
    assert '"pen_width": 3' in base
    assert '"highlight_width": 12' in base
    assert '("pen_width", 1, 12, 3)' in widgets
    assert '("highlight_width", 2, 30, 12)' in widgets
    assert "Apply annotation colors across all app themes" in widgets
    assert "تطبيق ألوان التعليقات التوضيحية على كل ثيمات البرنامج" in widgets
    assert "annotation_colors_by_theme" in main
    assert "annotation_colors_apply_to_themes" in main


def test_manual_highlighter_preserves_dark_ink_with_multiply_blending():
    document = read("engo_document.py")
    start = document.index("def add_highlighter_ink(")
    end = document.index("\n    def ", start + 10)
    method = document[start:end]
    assert 'get("highlight_width", 12)' in method
    assert 'annot.set_blendmode("Multiply")' in method
    assert "annot.set_opacity(0.72)" in method


def test_shape_recognition_distinguishes_oval_curvature_from_wobbly_rectangles():
    widgets = read("engo_widgets.py")
    start = widgets.index("def _recognize_pen_shape(")
    end = widgets.index("\n\ndef ", start + 10)
    method = widgets[start:end]
    assert "curve_deviation" in method
    assert "curve_deviation >= 0.035" in method
    assert "radial_error <= 0.16" in method
    assert method.index("if looks_like_oval:") < method.index("# Rough rectangles / squares")
    assert method.index("# Rough rectangles / squares") < method.index("if len(simplified) == 4:")


def test_text_highlight_edit_adds_or_removes_selected_words_not_resize_handles():
    document = read("engo_document.py")
    assert 'selection_tool="highlight_edit"' in document
    assert "def edit_text_highlight_words(" in document
    method_start = document.index("def edit_text_highlight_words(")
    method_end = document.index("\n    def ", method_start + 10)
    method = document[method_start:method_end]
    assert "highlighted_indexes - selected_indexes" in method
    assert "highlighted_indexes | selected_indexes" in method
    assert "page.delete_annot(old)" in method
    control_start = document.index("def _selected_annotation_control_at(")
    control_end = document.index("\n    def ", control_start + 10)
    control = document[control_start:control_end]
    assert 'getattr(fitz, "PDF_ANNOT_HIGHLIGHT", 8)' in control
    assert "return str(self._resize_handle_at(bounds, pos, geometry) or \"\")" in control


def test_freetext_updates_preserve_bold_italic_in_pdf_rich_text():
    document = read("engo_document.py")
    assert "def _freetext_style_from_xref(" in document
    start = document.index("def update_freetext_annotation(")
    end = document.index("\n    def update_text_note(", start + 10)
    method = document[start:end]
    assert "richtext=True" in method
    assert 'self.doc.xref_set_key(new_xref, "Contents"' in method
    assert 'self.doc.xref_set_key(new_xref, "T"' in method
    assert ".set_info(" not in method


def test_fullscreen_and_chat_focus_use_the_corner_only_restore_icon():
    widgets = read("engo_widgets.py")
    start = widgets.index('elif name == "minimize":')
    end = widgets.index('elif name == "plus":', start)
    minimize = widgets[start:end]
    assert minimize.count("path(") == 4
    assert "line(" not in minimize
    main = read("main.py")
    chat = read("engo_ai_chat.py")
    assert 'make_icon("minimize" if active else "fullscreen"' in main
    assert 'make_icon("minimize", "#b7c6dc", 16)' in chat
    assert 'make_icon("fullscreen", "#b7c6dc", 16)' in chat
