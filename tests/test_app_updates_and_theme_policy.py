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



def test_plan_comparison_shows_requested_table_only_feature_statuses():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert '("page_themes", "ثيمات الصفحات", "Page themes")' in ui
    assert '("smart_theme", "الثيم الذكي", "Smart Theme")' in ui
    assert '("كل أدوات التعديل والملاحظات", "All editing and annotation tools")' in ui
    assert '"app_themes": "limited"' in ui
    assert '"translations": "limited"' in ui
    assert '"page_themes": "limited"' in ui
    assert '"smart_theme": "unavailable"' in ui
    assert 'premium_unlimited_overrides = {"smart_theme", "open_other_formats"}' in ui
    assert "do not alter the actual entitlement data or runtime feature enforcement" in ui



def test_non_pdf_documents_require_premium_gate_before_opening():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    start = main.index("    def open_pdf(self, path):")
    end = main.index("    def _open_supported_document", start)
    opener = main[start:end]
    assert 'Path(source_path).suffix.lower() != ".pdf"' in opener
    assert '"open_other_formats"' in opener
    assert "self._request_feature_access(" in opener
    assert "self._open_supported_document(value)" in opener


def test_other_file_formats_are_server_enforced_premium_only():
    core = (ROOT / "engo_licensing" / "core.py").read_text(encoding="utf-8")
    usage = (ROOT / "supabase" / "functions" / "usage-consume" / "index.ts").read_text(encoding="utf-8")
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert '"open_other_formats"' in core
    assert '"open_other_formats"' in usage
    assert 'feature === "open_other_formats"' in usage
    assert 'context.license_status !== "active"' in usage
    assert '.eq("plan_id", "premium")' in usage
    assert '("open_other_formats", "فتح الملفات بصيغ أخرى", "Open other file formats")' in ui
    assert '"open_other_formats": "unavailable"' in ui
    assert '"open_other_formats"' in ui.split("premium_unlimited_overrides = ", 1)[1].splitlines()[0]


def test_guest_limited_and_unavailable_features_require_sign_in():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    start = main.index("    def _request_feature_access(")
    end = main.index("    def _license_gate_thread_finished", start)
    gate = main[start:end]
    assert "if not service.state.authenticated:" in gate
    assert "self.open_account_dialog()" in gate
    assert "service.consume_feature(feature_key" in gate
    assert 'result.get("tracked") is True' in gate



def test_other_file_format_entitlement_is_seeded_for_free_and_premium():
    migration = (ROOT / "supabase" / "migrations" / "20261113150000_add_premium_only_other_file_formats.sql").read_text(encoding="utf-8")
    assert "('free', 'open_other_formats', false, 0, null, 'lifetime')" in migration
    assert "('premium', 'open_other_formats', true, null, null, 'lifetime')" in migration
    assert "on conflict (plan_id, feature_key) do update" in migration.lower()



def test_subscription_price_label_has_arabic_and_english_prefixes():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert 'self._tr(f"السعر: {formatted_price}", f"Price: {formatted_price}")' in ui
    assert 'self._tr("السعر: بيانات السعر لم تصل", "Price: data not loaded")' in ui
    assert 'self._tr("السعر: لم يحدد بعد", "Price: not configured yet")' in ui



def test_offline_feature_access_messages_are_friendly_and_localized():
    core = (ROOT / "engo_licensing" / "core.py").read_text(encoding="utf-8")
    main = (ROOT / "engo_main.py").read_text(encoding="utf-8")
    assert "class OfflineError(NetworkError)" in core
    assert 'except OfflineError:' in core
    assert '"offline_feature_unavailable"' in core
    assert "الميزة اتقفلت لأن جهازك غير متصل بالإنترنت." in main
    assert "This feature is locked because your device is offline." in main
    assert "getaddrinfo failed" in main


def test_offline_fallback_is_limited_to_per_file_tags_and_tag_units():
    core = (ROOT / "engo_licensing" / "core.py").read_text(encoding="utf-8")
    assert 'OFFLINE_FILE_FEATURES = frozenset({"tags", "tag_units"})' in core
    assert "def _consume_offline_file_feature(" in core
    assert 'feature_key not in self.OFFLINE_FILE_FEATURES' in core
    assert "allow_expired=True" in core
    assert 'self._verify_signed_response(envelope, allow_expired=True)' in core
    assert "offline_feature_unavailable" in core


def test_account_overview_returns_authoritative_per_file_tag_usage_snapshot():
    edge = (ROOT / "supabase" / "functions" / "account-overview" / "index.ts").read_text(encoding="utf-8")
    core = (ROOT / "engo_licensing" / "core.py").read_text(encoding="utf-8")
    assert 'from("usage_counters")' in edge
    assert '.in("feature_key", ["tags", "tag_units"])' in edge
    assert '.neq("scope_key", "")' in edge
    assert "tag_usage: tagUsageAvailable ? tagUsage : null" in edge
    assert 'result.get("tag_usage")' in core


def test_text_chat_reopens_and_reactivates_at_the_latest_message():
    chat = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    start = chat.index("    def showEvent(self, event):", chat.index("class AIChatPanel"))
    end = chat.index("    def _reflow_after_show", start)
    show_event = chat[start:end]
    assert "self._scroll_to_latest_if_active(key)" in show_event
    assert "(0, 120, 300, 520)" in show_event
    assert "def _scroll_to_latest_if_active(self, page_key=None):" in chat

    start = chat.index("    def _activate_transcript_page")
    end = chat.index("    def _activate_chat_for_document", start)
    activate = chat[start:end]
    assert "self._scroll_to_latest_if_active(k)" in activate
    assert "saved_scroll = int(entry.get(\"scroll\", 0))" not in activate
