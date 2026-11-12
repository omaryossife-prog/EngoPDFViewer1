from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_devices_table_is_declared_before_its_indexes():
    sql = (ROOT / "supabase/migrations/20261111004326_engo_accounts_licensing.sql").read_text(encoding="utf-8")
    create_pos = sql.index("create table if not exists public.devices")
    index_pos = sql.index("devices_one_active_per_user")
    assert create_pos < index_pos
    assert "create table if not exists public.usage_counters" in sql
    assert ";\n (" not in sql


def test_usage_counter_is_account_scoped_and_consolidates_legacy_rows():
    sql = (ROOT / "supabase/migrations/20261111004326_engo_accounts_licensing.sql").read_text(encoding="utf-8")
    assert "sum(used)::bigint as total_used" in sql
    assert "usage_counters_account_feature_window" in sql
    assert "on public.usage_counters(user_id, feature_key, window_start)" in sql


def test_edge_functions_support_current_supabase_key_maps():
    common = (ROOT / "supabase/functions/_shared/common.ts").read_text(encoding="utf-8")
    assert 'SUPABASE_PUBLISHABLE_KEYS' in common
    assert 'SUPABASE_SECRET_KEYS' in common
    assert 'SUPABASE_SERVICE_ROLE_KEY' in common  # legacy fallback only
    assert 'ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64' in common


def test_client_example_contains_public_values_only():
    config = json.loads((ROOT / "engo_license.example.json").read_text(encoding="utf-8"))
    serialized = json.dumps(config).lower()
    assert "supabase_publishable_key" in config
    assert "private" not in serialized
    assert "service_role" not in serialized
    # Desktop OAuth secret is a blank local-only setting, never a shipped value.
    assert config.get("google_desktop_client_secret", "") == ""
    assert not any("secret" in key.lower() and value for key, value in config.items())


def test_google_genai_version_remains_pinned():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "google-genai==2.34.0" in requirements
    assert "google-genai>=" not in requirements


def test_deploy_script_requires_explicit_target_confirmation():
    script = (ROOT / "tools/deploy_supabase_production.ps1").read_text(encoding="utf-8")
    assert "Type the project ref exactly to continue" in script
    assert "supabase db push --remote --yes" in script
    assert "supabase secrets set --env-file $TempEnv --yes" in script
    assert "supabase functions deploy $FunctionName --remote=$ProjectRef --yes" in script
    assert "finally" in script.lower()


def test_device_activation_refuses_suspended_accounts():
    sql = (ROOT / "supabase/migrations/20261111004326_engo_accounts_licensing.sql").read_text(encoding="utf-8")
    assert "account_status <> 'active'" in sql
    assert "'account_suspended'" in sql


def test_project_specific_runtime_config_contains_only_public_values():
    config = json.loads((ROOT / "engo_license.json").read_text(encoding="utf-8"))
    assert config["supabase_url"] == "https://milksrcwbqmkczlhjfsi.supabase.co"
    assert config["supabase_publishable_key"].startswith("sb_publishable_")
    assert config["oauth_redirect_uri"] == "http://127.0.0.1:43821/callback"
    assert "private" not in json.dumps(config).lower()
    assert config.get("google_desktop_client_secret", "") == ""


def test_edge_function_supabase_js_import_is_pinned():
    common = (ROOT / "supabase/functions/_shared/common.ts").read_text(encoding="utf-8")
    assert "@supabase/supabase-js@2.119.0" in common


def test_release_build_embeds_public_license_runtime_config():
    script = (ROOT / "build_release.ps1").read_text(encoding="utf-8-sig")
    assert "engo_license.example.json" in script
    assert "=engo_license.json" in script
    assert "RuntimeLicenseConfigPath" in script
