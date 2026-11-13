from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plan_button_fetches_fresh_account_overview_before_showing_dialog():
    source = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    start = source.index("    def _open_plans(self):")
    end = source.index("    def _plans_worker_finished(self):", start)
    open_block = source[start:end]
    assert "self.service.account_overview" in open_block
    assert "_plans_overview_completed" in open_block

    start = source.index("    def _plans_overview_completed(self, data: Any, error: str):")
    end = source.index("    def _overview_completed(self, data: Any, error: str):", start)
    completed_block = source[start:end]
    assert "self._overview_completed(data, \"\")" in completed_block
    assert "PlansDialog(self.service, self.account_data" in completed_block
    assert completed_block.index("self._overview_completed(data, \"\")") < completed_block.index("PlansDialog(")


def test_missing_entitlement_rows_are_not_misreported_as_disabled_features():
    source = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert 'if not isinstance(row, dict) or not row:' in source
    assert 'self._tr("لم تصل البيانات", "Not loaded")' in source
    assert "Deploy the updated account-overview function" in source


def test_document_tabs_do_not_show_the_application_icon():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tab_icon_lines = [line.strip() for line in source.splitlines() if "doc_tabbar.setTabIcon(" in line]
    assert len(tab_icon_lines) == 3
    assert all("QIcon()" in line for line in tab_icon_lines)
    assert all("engopdfviewer.ico" not in line for line in tab_icon_lines)


def test_account_overview_edge_function_returns_prices_and_entitlements():
    source = (ROOT / "supabase" / "functions" / "account-overview" / "index.ts").read_text(encoding="utf-8")
    assert 'from("subscription_prices")' in source
    assert 'from("feature_entitlements")' in source
    assert "prices: prices.data ?? []" in source
    assert "entitlements: entitlements.data ?? []" in source


def test_subscription_request_reads_the_server_side_price():
    source = (ROOT / "supabase" / "functions" / "subscription-request" / "index.ts").read_text(encoding="utf-8")
    assert 'from("subscription_prices")' in source
    assert '.eq("is_active", true)' in source
    assert 'from("payment_transactions").insert' in source



def test_account_overview_tag_usage_snapshot_filters_per_file_tag_features():
    edge = (ROOT / "supabase" / "functions" / "account-overview" / "index.ts").read_text(encoding="utf-8")
    assert 'select("feature_key,scope_key,used")' in edge
    assert '.in("feature_key", ["tags", "tag_units"])' in edge
    assert "tag_usage: tagUsageAvailable ? tagUsage : null" in edge

def test_provider_model_status_requires_a_successful_real_request_for_green():
    source = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    assert 'if plan_access == "denied":' in source
    assert 'return "unavailable", "plan"' in source
    assert 'if plan_access != "allowed":' in source
    assert 'return "unknown", "plan_unknown"' in source
    assert 'health_state == "success"' in source
    assert 'return "available", "request_success"' in source
    assert 'return "unknown", "catalog_only"' in source
    assert 'return "available", "provider_catalog"' not in source
    assert 'return "unavailable", "model_not_listed"' in source


def test_provider_model_health_is_scoped_to_the_api_key_without_storing_it():
    source = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    assert 'hashlib.sha256(secret.encode("utf-8", errors="replace")).hexdigest()[:20]' in source
    assert 'ai_model_health_v1_{provider}_{fingerprint}' in source
    assert '_get_provider_key(self.settings, provider)' in source
    assert 'json.dumps(records, ensure_ascii=False)' in source


def test_provider_model_status_uses_only_user_request_results_not_background_probes():
    chat = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'def record_provider_model_result(' in chat
    assert 'worker.provider, worker.model, worker.api_key, success=True' in main
    assert 'success=False, error=str(error)' in main
    assert 'No background probe requests are sent.' in chat


def test_zero_quota_and_retry_after_update_the_model_health_temporarily():
    source = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    assert 'r"retry\\s+in\\s+' in source
    assert 'r"\\blimit\\s*:\\s*0\\b"' in source
    assert '"state": "quota_blocked"' in source
    assert '"state": "rate_limited"' in source
    assert 'expires_at' in source


def test_chat_model_menu_shows_status_icons_without_changing_model_ids():
    source = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    assert 'self.model_combo.addItem(_provider_model_status_icon(status), model_id, model_id)' in source
    assert 'self.model_combo.setItemData(' in source
    assert 'self.model_combo.popupAboutToShow.connect(self._refresh_provider_model_menu)' in source
    assert 'class AIModelSelectorCombo(QComboBox):' in source
    assert 'self.popupAboutToShow.emit()' in source
    assert 'self.model_combo.setIconSize(QSize(13, 13))' in source


def test_provider_model_catalog_is_marked_verified_only_after_success():
    source = (ROOT / "engo_ai_core.py").read_text(encoding="utf-8")
    loaded = source.split('    def _on_models_loaded(self, provider, model_ids):', 1)[1].split('    def _on_models_failed', 1)[0]
    failed = source.split('    def _on_models_failed(self, provider, message):', 1)[1].split('    def _on_models_worker_finished', 1)[0]
    assert 'ai_models_catalog_verified_{provider}", True' in loaded
    assert 'ai_models_catalog_checked_at_{provider}", time.time()' in loaded
    assert 'ai_models_catalog_key_fingerprint_{provider}' in loaded
    assert 'ai_models_catalog_verified_{provider}", False' in failed
    assert "import time" in source
    assert "import hashlib" in source


def test_provider_model_catalog_is_bound_to_the_current_api_key():
    chat = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    core = (ROOT / "engo_ai_core.py").read_text(encoding="utf-8")
    assert 'ai_models_catalog_key_fingerprint_{provider}' in chat
    assert 'cached_fingerprint != fingerprint' in chat
    assert 'hashlib.sha256(' in core


def test_provider_model_status_is_ui_only_and_keeps_application_version_unchanged():
    chat = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'self.model_combo = AIModelSelectorCombo()' in chat
    assert 'self._chat_text_plan_access()' in chat
    assert 'APP_VERSION = "2.3.6"' in main


def test_chat_imports_provider_key_helper_before_model_catalog_check():
    source = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    imports = source.split("from engo_ai_core import (", 1)[1].split(")", 1)[0]
    assert "_get_provider_key" in imports
    assert "current_key = _get_provider_key(self.settings, provider)" in source


def test_model_selector_expands_popup_without_resizing_the_closed_control():
    source = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    selector = source.split("class AIModelSelectorCombo", 1)[1].split("class AIChatPanel", 1)[0]
    assert "view.setTextElideMode(Qt.TextElideMode.ElideNone)" in selector
    assert "metrics.horizontalAdvance" in selector
    assert "popup.resize(desired_width, current_geometry.height())" in selector
    assert "self.model_combo.setMaximumWidth(225)" in source


def test_exhausted_provider_credits_stay_red_until_a_successful_request():
    source = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    assert '"you have no credits remaining"' in source
    assert '"insufficient_quota"' in source
    assert 'record_key = "_account"' in source
    assert 'record = {"state": "billing_blocked", "checked_at": now}' in source
    assert 'if str(record.get("state") or "") == "billing_blocked":' in source
    assert 'provider_health.get("_account") or provider_health.get(model_id)' in source
    assert 'if health_state == "billing_blocked":' in source
    assert 'records.pop("_account", None)' in source
    assert 'record = {"state": "billing_blocked", "checked_at": now, "expires_at":' not in source

def test_reset_preserves_provider_api_keys_without_deleting_keyring_credentials():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    dialogs = (ROOT / "engo_app_dialogs.py").read_text(encoding="utf-8")
    start = main.index("    def _continue_reset_shutdown(self, reset_dialog):")
    end = main.index("    def _animate_theme_transition(self):", start)
    reset_block = main[start:end]
    assert 'key.startswith("ai_key_")' in reset_block
    assert "preserved_provider_keys" in reset_block
    assert "self.settings.clear()" in reset_block
    assert "self.settings.setValue(key, value)" in reset_block
    assert "reset_dialog._delete_provider_credentials()" not in reset_block
    assert "Your AI provider API keys will be kept." in dialogs
    assert "مع الاحتفاظ بمفاتيح API" in dialogs


def test_reset_still_triggers_first_run_even_when_api_keys_are_preserved():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    init = main.split("class MainWindow(QMainWindow):", 1)[1].split(
        "# PDF linking is an explicit", 1
    )[0]
    assert 'key.startswith("ai_key_")' in init
    assert "has_completed_setup or has_legacy_setup" in init
    assert 'self.settings.value("first_run_complete", False, type=bool)' in init
    assert "not key.startswith" in init


def test_first_run_has_language_theme_and_google_or_guest_steps():
    dialogs = (ROOT / "engo_app_dialogs.py").read_text(encoding="utf-8")
    wizard = dialogs.split("class FirstRunSetupDialog(QDialog):", 1)[1].split(
        "class _SettingsNoWheelSlider", 1
    )[0]
    assert "STEP 1 OF 3" in wizard
    assert "STEP 2 OF 3" in wizard
    assert "STEP 3 OF 3" in wizard
    assert "google_sign_in_requested = pyqtSignal()" in wizard
    assert "self.google_signin_button.clicked.connect(self.google_sign_in_requested.emit)" in wizard
    assert "self.guest_button.clicked.connect(self._continue_as_guest)" in wizard
    assert 'self.account_choice = "guest"' in wizard


def test_first_run_uses_same_free_premium_theme_gate_as_application_settings():
    dialogs = (ROOT / "engo_app_dialogs.py").read_text(encoding="utf-8")
    wizard = dialogs.split("class FirstRunSetupDialog(QDialog):", 1)[1].split(
        "class _SettingsNoWheelSlider", 1
    )[0]
    assert 'FREE_UI_THEMES = {"light", "dark", "midnight"}' in dialogs
    assert 'is_locked = value not in FREE_UI_THEMES and not self._is_premium' in wizard
    assert "locked=is_locked" in wizard
    assert "self.theme_group.addButton(card)" in wizard
    assert "self._show_theme_locked_prompt(key)" in wizard


def test_google_brand_icon_is_used_in_first_run_and_account_dialogs():
    base = (ROOT / "engo_base.py").read_text(encoding="utf-8")
    dialogs = (ROOT / "engo_app_dialogs.py").read_text(encoding="utf-8")
    account = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    assert "def google_brand_icon(size: int = 20)" in base
    assert all(color in base for color in ("#EA4335", "#FBBC05", "#34A853", "#4285F4"))
    assert "self.google_signin_button.setIcon(google_brand_icon(22))" in dialogs
    assert "self.signin_button.setIcon(google_brand_icon(22))" in account
    assert "🔵" not in account


def test_startup_splash_can_be_cancelled_before_main_window_opens():
    ui = (ROOT / "engo_licensing" / "ui.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    splash = ui.split("class EngoSplashScreen(QWidget):", 1)[1].split(
        "class GroupedPlanHeader", 1
    )[0]
    assert "cancel_requested = pyqtSignal()" in splash
    assert 'QPushButton("×")' in splash
    assert "self.close_button.clicked.connect(self.cancel_requested.emit)" in splash
    assert "splash.cancel_requested.connect(cancel_startup)" in main
    assert 'launch_state["cancelled"] = True' in main
    assert 'if launch_state["started"] or launch_state["cancelled"]:' in main
    assert 'if launch_state["cancelled"]:' in main

