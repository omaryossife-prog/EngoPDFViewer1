from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plan_comparison_has_a_sticky_header_and_requested_column_order():
    source = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert "QTableWidget(0, 5)" in source
    assert "comparison_header.setVisible(True)" in source
    assert "comparison_header.setFixedHeight(62)" in source
    assert "self.comparison_table.setFixedHeight(430)" in source
    assert "self.comparison_table.setVerticalScrollBarPolicy" in source
    assert 'self._tr("مجاني\\nمتاح بلا حدود", "Free\\nUnlimited")' in source
    assert 'self._tr("مجاني\\nمتاح بحدود", "Free\\nLimited")' in source
    assert 'self._tr("مجاني\\nغير متاح", "Free\\nUnavailable")' in source
    assert 'self._tr("مميز\\nمتاح بلا حدود", "Premium\\nUnlimited")' in source
    assert '("unlimited": 1, "limited": 2, "unavailable": 3)' in source
    assert 'for status in ("unlimited", "limited", "unavailable")' in source
    assert "المميزات المتاحة بلا حدود في جميع الخطط" in source
    assert "المميزات غير المتاحة في المجاني" in source


def test_voice_board_word_export_is_authorized_by_a_premium_entitlement():
    live = (ROOT / "engo_live.py").read_text(encoding="utf-8")
    core = (ROOT / "engo_licensing" / "core.py").read_text(encoding="utf-8")
    usage = (ROOT / "supabase" / "functions" / "usage-consume" / "index.ts").read_text(encoding="utf-8")
    entitlement_sql = (ROOT / "SUPABASE_VOICE_BOARD_DOCX_FEATURE.sql").read_text(encoding="utf-8")

    assert 'self.export_docx_btn.clicked.connect(self._request_export_board_docx)' in live
    assert 'request_access(\n            "voice_board_docx"' in live
    assert "from docx import Document" in live
    assert '"voice_board_docx"' in core
    assert '"voice_board_docx"' in usage
    assert "('free', 'voice_board_docx', false, 0, null, 'lifetime'" in entitlement_sql
    assert "('premium', 'voice_board_docx', true, null, null, 'lifetime'" in entitlement_sql
