from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_editing_a_drawn_annotation_switches_to_select_tool():
    source = (ROOT / "engo_document.py").read_text(encoding="utf-8")
    start = source.index(
        "if self._annotation_edit_button_rect(selected_bounds_pre).contains(pos):"
    )
    end = source.index(
        "hit = self._annotation_at(index, pos)",
        start,
    )
    edit_branch = source[start:end]
    assert "self._annotation_edit_mode = not self._annotation_edit_mode" in edit_branch
    assert "if self._annotation_edit_mode:" in edit_branch
    assert "self._activate_select_for_annotation_edit()" in edit_branch


def test_first_run_theme_picker_keeps_three_basic_themes_and_points_to_settings():
    source = (ROOT / "engo_app_dialogs.py").read_text(encoding="utf-8")
    assert 'enumerate(("light", "dark", "midnight"))' in source
    assert "More themes are available in Settings." in source
    assert "تتوفر ثيمات أخرى في إعدادات البرنامج." in source
