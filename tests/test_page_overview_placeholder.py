"""Regression checks for stable, full-size placeholders in the page overview."""
import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "engo_document.py"
MODULE = ast.parse(SOURCE.read_text(encoding="utf-8"))
DOCUMENT_TAB = next(
    node for node in MODULE.body
    if isinstance(node, ast.ClassDef) and node.name == "DocumentTab"
)
METHODS = {
    node.name: node for node in DOCUMENT_TAB.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
}


def _calls(method, name):
    return [
        node for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and ((isinstance(node.func, ast.Name) and node.func.id == name)
             or (isinstance(node.func, ast.Attribute) and node.func.attr == name))
    ]


def test_placeholder_is_scaled_to_the_gallery_icon_size():
    method = METHODS["_page_overview_placeholder_icon"]
    source = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), method)
    assert "self.page_overview_grid.iconSize()" in source
    assert "source_pixmap.scaled(" in source
    assert "Qt.AspectRatioMode.KeepAspectRatio" in source
    assert "QPixmap(target_size)" in source


def test_visible_placeholders_are_prepared_when_gallery_opens():
    method = METHODS["show_page_overview"]
    calls = [
        node.func.attr for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert calls.index("show") < calls.index("_prepare_page_overview_visible_placeholders")
    assert calls.index("_prepare_page_overview_visible_placeholders") < calls.index("_schedule_page_overview_preview_refresh")


def test_scroll_prepares_newly_visible_placeholders_immediately():
    method = METHODS["_on_page_overview_scroll"]
    calls = [
        node.func.attr for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "_prepare_page_overview_visible_placeholders" in calls
    assert "_schedule_page_overview_preview_refresh" in calls


def test_page_items_track_placeholder_and_final_preview_separately():
    method = METHODS["show_page_overview"]
    source = ast.get_source_segment(SOURCE.read_text(encoding="utf-8"), method)
    assert "Qt.ItemDataRole.UserRole + 1" in source
    assert "Qt.ItemDataRole.UserRole + 2" in source
