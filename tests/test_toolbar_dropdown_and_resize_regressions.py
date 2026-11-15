from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_book_icon_uses_dark_contrast_in_light_theme():
    main = read("main.py")
    assert 'book_icon_color = "#172033" if current_theme == "light"' in main
    assert 'self.book_btn.setIcon(make_icon("book", book_icon_color, 18))' in main


def test_info_glyph_stays_on_physical_left_in_arabic_status_bar():
    main = read("main.py")
    start = main.index("if hasattr(self, \"context_help_label\"):")
    end = main.index("\n    @staticmethod", start)
    section = main[start:end]
    assert "self.status.setLayoutDirection(Qt.LayoutDirection.LeftToRight)" in section
    assert "self.context_help_label.setLayoutDirection(direction)" in section
    assert "Qt.AlignmentFlag.AlignRight if language == \"ar\" else Qt.AlignmentFlag.AlignLeft" in section


def test_highlight_select_rotate_and_tag_menus_share_one_toolbar_style():
    main = read("main.py")
    start = main.index("def _apply_toolbar_dropdown_style(")
    end = main.index("\n    def ", start + 10)
    helper = main[start:end]
    assert "QMenu::item:selected" in helper
    assert "QMenu::separator" in helper
    assert "tokens['panel']" in helper
    theme_refresh = main[main.index("for dropdown in (", main.index("def _apply_user_interface_preferences")):]
    for menu_name in ("highlight_tool_menu", "select_tool_menu", "rotate_page_menu", "tag_menu"):
        assert f'getattr(self, "{menu_name}", None)' in theme_refresh
    tag_refresh = main[main.index("def _refresh_tag_menu("):]
    assert "self._apply_toolbar_dropdown_style(self.tag_menu)" in tag_refresh


def test_vector_ink_shapes_resize_from_their_whole_bounds():
    document = read("engo_document.py")
    start = document.index("def _annotation_selection_geometry(")
    end = document.index("\n    def _geometry_with_vertex_preview", start)
    geometry = document[start:end]
    assert "bounds_resize_types = (type_line, type_polygon, type_polyline, type_ink)" in geometry
    assert '"anchor": QPointF(right, bottom), "mode": "bounds"' in geometry
    assert '"anchor": QPointF(left, top), "mode": "bounds"' in geometry
    for name in ('"tl"', '"tr"', '"bl"', '"br"', '"edge_top"', '"edge_bottom"', '"edge_left"', '"edge_right"'):
        assert name in geometry
    # The commit path remaps every original point to the resized bounding rectangle.
    transform_start = document.index("def transform_annotation(")
    transform_end = document.index("\n    def transform_annotations_group", transform_start)
    transform = document[transform_start:transform_end]
    assert "def remap_pdf_point(point):" in transform
    assert "mapped = [remap_pdf_point(point) for point in vertices]" in transform
    assert "updated.set_border(width=float(border.get(\"width\", 2.0)))" in transform


def test_selection_outline_uses_a_cosmetic_pen_during_live_resize():
    document = read("engo_document.py")
    assert "selection_outline_pen.setCosmetic(True)" in document
    assert "painter.setPen(selection_outline_pen)" in document


def test_resize_can_start_from_the_visible_annotation_frame_edge():
    document = read("engo_document.py")
    start = document.index("def _resize_handle_at(")
    end = document.index("\n    def ", start + 10)
    helper = document[start:end]
    assert "tolerance = 8.0" in helper
    assert 'return side' in helper
    assert 'geometry.get("kind") != "circle"' in helper
