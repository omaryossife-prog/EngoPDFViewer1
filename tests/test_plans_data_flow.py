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
    assert 'ai_models_catalog_verified_{provider}", False' in failed


def test_provider_model_status_is_ui_only_and_keeps_application_version_unchanged():
    chat = (ROOT / "engo_ai_chat.py").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'self.model_combo = AIModelSelectorCombo()' in chat
    assert 'self._chat_text_plan_access()' in chat
    assert 'APP_VERSION = "2.3.6"' in main
