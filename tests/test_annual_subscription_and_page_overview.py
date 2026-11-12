from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_page_overview_wheel_matches_normal_reader_scroll_amount():
    source = (ROOT / "engo_document.py").read_text(encoding="utf-8")
    grid_start = source.index("class PageOverviewGrid(")
    grid_end = source.index("class BookSpreadThumbnailList(", grid_start)
    grid = source[grid_start:grid_end]
    assert "def set_wheel_scroll_line_step(self, step: int)" in grid
    assert "lines = max(3, int(round(self._wheel_line_step * 3)))" in grid
    assert "amount = int((angle_delta / 120.0) * lines)" in grid
    assert "amount = pixel_delta" in grid
    assert "self.page_overview_grid.set_wheel_scroll_line_step(self.scroll.verticalScrollBar().singleStep())" in source


def test_page_overview_cards_follow_landscape_or_portrait_document_ratio():
    source = (ROOT / "engo_document.py").read_text(encoding="utf-8")
    grid_start = source.index("class PageOverviewGrid(")
    grid_end = source.index("class BookSpreadThumbnailList(", grid_start)
    grid = source[grid_start:grid_end]
    assert "def set_page_aspect_ratio(self, aspect_ratio: float)" in grid
    assert "icon_height = max(96, int(round(icon_width / self._page_aspect_ratio)))" in grid
    assert "self.page_overview_grid.setSpacing(0)" in source
    assert "def _page_overview_document_aspect_ratio(self) -> float:" in source
    assert "grid.set_page_aspect_ratio(self._page_overview_document_aspect_ratio())" in source


def test_annual_subscription_is_available_from_the_client_and_admin():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    admin = (ROOT / "engo_admin.py").read_text(encoding="utf-8")
    edge = (ROOT / "supabase" / "functions" / "subscription-request" / "index.ts").read_text(encoding="utf-8")
    assert 'PERIODS = ("monthly", "quarterly", "semiannual", "annual")' in ui
    assert 'self.period_combo.addItem(self._tr("سنوي", "Annual"), "annual")' in ui
    assert '("annual", "سنوي", 12)' in admin
    assert 'QTableWidget(4,6)' in admin
    assert '"annual": "سنوي"' in admin
    assert '("monthly", "quarterly", "semiannual", "annual")' in admin
    assert 'annual: { months: 12 }' in edge


def test_annual_database_migration_adds_12_month_activation_support():
    migration = (ROOT / "supabase" / "migrations" / "20261112214055_add_annual_subscription_period.sql").read_text(encoding="utf-8")
    assert "'annual'::text" in migration
    assert "duration_months = 12" in migration
    assert "('premium', 'annual', 12, 0, 'EGP', true)" in migration
    assert "when 'annual' then 12" in migration



def test_plan_comparison_restores_grouped_free_and_single_premium_header():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert "self.comparison_table.setSpan(0, 1, 1, 3)" in ui
    assert 'self._tr("مجاني", "Free")' in ui
    assert 'self._tr("مميز", "Premium")' in ui
    assert 'self._tr("متاح بلا حدود", "Available without limits")' in ui
    assert "self.comparison_table.setItem(1, 4, item)" in ui
    assert "Premium\\\\nUnavailable" not in ui
    assert "self.comparison_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)" in ui
    assert "self.comparison_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)" in ui
    assert "self.comparison_table.setFixedHeight(total_height + 2)" in ui
    assert "self._put_status_dot(row_index, 4, \"unlimited\")" in ui
    assert "grouped: dict[str, list" not in ui



def test_comparison_has_no_extra_basic_features_section_banner():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert "الميزات الأساسية المتاحة بلا حدود في جميع الخطط" not in ui
    assert "المميزات المتاحة بلا حدود في المجاني" not in ui
    assert '("فتح وعرض ملفات PDF", "Open and view PDF files")' in ui
    assert '("تدوير الصفحات", "Rotate pages")' in ui
