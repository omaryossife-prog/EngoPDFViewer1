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
