from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plan_comparison_uses_a_real_pinned_wrapping_header():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert "class GroupedPlanHeader(QHeaderView)" in ui
    assert "self.comparison_table.setHorizontalHeader(GroupedPlanHeader(self.language, theme, self.comparison_table))" in ui
    assert "self.setFixedHeight(72)" in ui
    assert "self.comparison_table.setTextElideMode(Qt.TextElideMode.ElideNone)" in ui
    assert "self.comparison_table.setWordWrap(True)" in ui
    assert "QHeaderView.ResizeMode.ResizeToContents" in ui
    assert 'for free_status in ("unlimited", "limited", "unavailable")' in ui
    assert 'return {"unlimited": 1, "limited": 2, "unavailable": 3}[status]' in ui
    assert 'setColumnWidth(column, 136 if column in (1, 4) else 84)' in ui
    assert 'cell(positions[1], top_height, widths[1], full_height - top_height, unlimited)' in ui
    assert 'cell(positions[2], top_height, widths[2], full_height - top_height, limited)' in ui


def test_plan_labels_are_readable_and_free_is_translated():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert '"Contact and Pay"' in ui
    assert '"View Plans and Subscribe"' in ui
    assert 'plan_ar = "مميز" if state.is_premium else "مجاني"' in ui
    assert 'self.plan_label.setText(self._tr(f"الباقة: {plan_ar}", f"Plan: {plan_en}"))' in ui

def test_plan_header_and_home_account_use_semantic_plan_colors():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert '"unavailable": "#d94848"' in ui
    assert '"limited": "#d6a328"' in ui
    assert '"unlimited": "#239b62"' in ui
    assert 'free_color = "#4f8ee8"' in ui
    assert 'premium_color = "#d6a328"' in ui
    assert 'plan_color = "#d6a328" if state.is_premium else "#4f8ee8"' in main
    assert 'plan_lbl.setStyleSheet(' in main



def test_long_plan_feature_names_use_two_lines_and_keep_header_font_normal():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert '"المحادثة الصوتية\\nوالحصص الصوتية"' in ui
    assert '"Voice chat and\\nvoice lessons"' in ui
    assert '"تصدير لوحة الشرح الصوتية\\nإلى Word"' in ui
    assert '"Export voice lesson\\nboard to Word"' in ui
    assert "font.setPointSize(max(9, font.pointSize()))" in ui
    assert "font.setPointSize(max(7, font.pointSize() - 1))" not in ui
    assert "self.comparison_table.setTextElideMode(Qt.TextElideMode.ElideNone)" in ui
    assert "self.comparison_table.setWordWrap(True)" in ui
    assert "self.comparison_table.resizeRowsToContents()" in ui


def test_home_account_plan_label_has_slightly_larger_text():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "QLabel#homeAcctPlan { color: #607087; font-size: 9pt;" in main
    assert "QLabel#homeAcctPlan {{ color: {theme_tokens['muted']}; font-size: 9pt;" in main
    assert 'font-size: 9pt; font-weight: 700; background: transparent;' in main


def test_home_account_plan_label_is_prominent():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'font-size: 11pt; font-weight: 800; background: transparent;' in main

def test_page_recoloring_controls_and_entitlement_are_removed():
    main = (ROOT / "engo_main.py").read_text(encoding="utf-8")
    core = (ROOT / "engo_licensing" / "core.py").read_text(encoding="utf-8")
    usage = (ROOT / "supabase" / "functions" / "usage-consume" / "index.ts").read_text(encoding="utf-8")
    assert "PageThemeDialog" not in main
    assert "apply_page_theme_to_image" not in main
    assert "self.theme_btn" not in main
    assert '("page_themes"' not in core
    assert '"page_themes"' not in usage
    assert 'self.settings.setValue("ui_theme", "dark")' in main
    assert "self.smart_page_theme = False" in main


def test_guest_message_does_not_claim_sign_in_is_for_plan_limits():
    main = (ROOT / "engo_main.py").read_text(encoding="utf-8")
    assert "Please sign in to your account before using this feature." in main
    assert "استخدام هذه الميزة يتطلب تسجيل الدخول بحسابك أولًا." in main
    assert "تطبيق حدود الخطة" not in main
    assert "plan limits enforced" not in main


def test_update_info_panel_edge_function_and_schema_are_wired():
    main = (ROOT / "engo_main.py").read_text(encoding="utf-8")
    core = (ROOT / "engo_licensing" / "core.py").read_text(encoding="utf-8")
    admin = (ROOT / "engo_admin.py").read_text(encoding="utf-8")
    edge = (ROOT / "supabase" / "functions" / "app-update-info" / "index.ts").read_text(encoding="utf-8")
    migration = (ROOT / "supabase" / "migrations" / "20261112223234_add_app_update_settings.sql").read_text(encoding="utf-8")
    assert "side.insertWidget(side.indexOf(browser) + 1, self.update_notice_btn)" in main
    assert "QDesktopServices.openUrl(target)" in main
    assert "30 * 60 * 1000" in main
    assert "def get_app_update_info(self)" in core
    assert "class UpdatesTab(QWidget)" in admin
    assert 'self.tabs.addTab(self.updates_tab, "إعدادات التحديثات")' in admin
    assert "update_available" in edge and "new URL(updateUrl)" in edge
    assert "public.app_update_settings" in migration
    assert "enable row level security" in migration.lower()
    assert "grant all on table public.app_update_settings to service_role" in migration.lower()


def test_unsupported_build_blocks_only_finite_free_limits_before_consumption():
    core = (ROOT / "engo_licensing" / "core.py").read_text(encoding="utf-8")
    usage = (ROOT / "supabase" / "functions" / "usage-consume" / "index.ts").read_text(encoding="utf-8")
    condition = "featureIsLimited = enabled && entitlement?.limit !== null && entitlement?.limit !== undefined"
    assert condition in usage
    assert 'message: "update_required"' in usage
    assert usage.index('message: "update_required"') < usage.index('admin.rpc("consume_feature_usage_v1"')
    assert 'entitlement.get("limit") is not None' in core
    assert '"message": "update_required"' in core


def test_next_release_version_is_trusted_and_update_settings_start_disabled():
    main = (ROOT / "engo_main.py").read_text(encoding="utf-8")
    core = (ROOT / "engo_licensing" / "core.py").read_text(encoding="utf-8")
    migration = (ROOT / "supabase" / "migrations" / "20261112223234_add_app_update_settings.sql").read_text(encoding="utf-8")
    assert 'APP_VERSION = "2.3.6"' in main
    assert 'APP_VERSION_FALLBACK = "2.3.6"' in core
    assert "'2.3.6', true" in migration
    assert "true, false, '2.3.6'" in migration
