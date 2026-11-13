import base64
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from engo_licensing.core import (
    LicenseConfig, LicenseService, NetworkError, OfflineError, SignatureError, canonical_json,
    is_expected_free_startup, LicenseState,
)


class DummyStore:
    def load(self):
        return None
    def save(self, value):
        pass
    def clear(self):
        pass


class MemoryOfflineStore:
    def __init__(self, value=None):
        self.value = value

    def load(self):
        return self.value

    def save(self, value):
        self.value = json.loads(json.dumps(value))

    def clear(self):
        self.value = None


def _resign_envelope(envelope, private):
    envelope["signature"] = base64.b64encode(
        private.sign(canonical_json(envelope["payload"]))
    ).decode("ascii")
    return envelope


def make_service_and_envelope(offline_store=None):
    private = Ed25519PrivateKey.generate()
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": "user-1", "device_id": "device-1", "plan_id": "premium",
        "entitlements": {"text_chat": {"enabled": True, "limit": None}},
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "app_version": "2.3.6", "license_status": "active",
    }
    signature = private.sign(canonical_json(payload))
    config = LicenseConfig(
        supabase_url="https://example.supabase.co", anon_key="public-anon",
        public_key_b64=base64.b64encode(public_raw).decode("ascii"), app_version="2.3.6",
    )
    service = LicenseService(
        config=config, secure_store=DummyStore(), device_id="device-1",
        offline_store=offline_store,
    )
    envelope = {"payload": payload, "signature": base64.b64encode(signature).decode("ascii")}
    return service, envelope, private


def test_canonical_json_has_stable_key_order_and_utf8():
    assert canonical_json({"b": 2, "a": "عربي"}) == '{"a":"عربي","b":2}'.encode("utf-8")


def test_valid_ed25519_license_response_is_accepted():
    service, envelope, _private = make_service_and_envelope()
    payload = service._verify_signed_response(envelope)
    state = service._apply_payload(payload, {"id": "user-1"})
    assert state.is_premium is True
    assert state.plan_id == "premium"


def test_signed_license_preserves_free_unlimited_launch_mode():
    service, envelope, private = make_service_and_envelope()
    envelope["payload"]["free_unlimited_mode"] = True
    envelope["signature"] = base64.b64encode(
        private.sign(canonical_json(envelope["payload"]))
    ).decode("ascii")

    payload = service._verify_signed_response(envelope)
    state = service._apply_payload(payload, {"id": "user-1"})

    assert state.verified is True
    assert state.authenticated is True
    assert state.free_unlimited_mode is True


def test_refresh_session_reuses_a_newer_rotated_session(monkeypatch):
    service, _envelope, _private = make_service_and_envelope()
    old_session = {
        "access_token": "old-access", "refresh_token": "old-refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    newer_session = {
        "access_token": "new-access", "refresh_token": "new-refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    service._session = newer_session

    def unexpected_refresh(*_args, **_kwargs):
        pytest.fail("A stale refresh token must not be sent after a newer session exists")

    monkeypatch.setattr(service, "_request", unexpected_refresh)
    assert service._refresh_session(old_session) == newer_session


def test_authenticated_edge_recovers_when_parallel_worker_rotated_session(monkeypatch):
    service, _envelope, _private = make_service_and_envelope()
    old_session = {
        "access_token": "old-access", "refresh_token": "old-refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    newer_session = {
        "access_token": "new-access", "refresh_token": "new-refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    service._session = old_session
    used_tokens = []

    def fake_edge(_name, _body, access_token=None):
        used_tokens.append(access_token)
        if access_token == "old-access":
            # Simulate a concurrent account worker completing the refresh.
            service._session = newer_session
            raise NetworkError("Server returned HTTP 401: Authentication required")
        return {"ok": True}

    monkeypatch.setattr(service, "_edge", fake_edge)
    assert service._authenticated_edge("account-overview", {}) == {"ok": True}
    assert used_tokens == ["old-access", "new-access"]


def test_tampered_entitlement_is_rejected():
    service, envelope, _private = make_service_and_envelope()
    envelope["payload"]["plan_id"] = "free"
    with pytest.raises(SignatureError):
        service._verify_signed_response(envelope)


def test_wrong_device_is_rejected_even_with_valid_signature():
    service, envelope, private = make_service_and_envelope()
    envelope["payload"]["device_id"] = "another-device"
    envelope["signature"] = base64.b64encode(private.sign(canonical_json(envelope["payload"]))).decode("ascii")
    with pytest.raises(SignatureError, match="different device"):
        service._verify_signed_response(envelope)


def test_expired_license_is_rejected_even_with_valid_signature():
    service, envelope, private = make_service_and_envelope()
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    envelope["payload"]["issued_at"] = (past - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    envelope["payload"]["expires_at"] = past.isoformat().replace("+00:00", "Z")
    envelope["signature"] = base64.b64encode(private.sign(canonical_json(envelope["payload"]))).decode("ascii")
    with pytest.raises(SignatureError, match="expired"):
        service._verify_signed_response(envelope)


def test_untrusted_status_never_becomes_premium():
    service, envelope, private = make_service_and_envelope()
    envelope["payload"]["license_status"] = "untrusted_build"
    envelope["signature"] = base64.b64encode(private.sign(canonical_json(envelope["payload"]))).decode("ascii")
    state = service._apply_payload(service._verify_signed_response(envelope), {"id": "user-1"})
    assert state.is_premium is False
    assert state.plan_id == "free"


def test_unconfigured_startup_is_free_without_network():
    config = LicenseConfig()
    service = LicenseService(config=config, secure_store=DummyStore(), device_id="device-1")
    state = service.verify_startup()
    assert state.plan_id == "free"
    assert state.is_premium is False
    assert state.verified is False


def test_inactive_signed_license_blocks_metered_feature(monkeypatch):
    service, envelope, private = make_service_and_envelope()
    envelope["payload"]["license_status"] = "device_not_active"
    envelope["payload"]["plan_id"] = "free"
    envelope["signature"] = base64.b64encode(private.sign(canonical_json(envelope["payload"]))).decode("ascii")
    service._session = {
        "access_token": "access", "refresh_token": "refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    monkeypatch.setattr(service, "_edge", lambda *_args, **_kwargs: {
        "allowed": False, "message": "Device is not active", "license": envelope,
    })
    result = service.consume_feature("text_chat")
    assert result["allowed"] is False
    assert result["tracked"] is False
    assert service.state.is_premium is False
    assert service.state.plan_id == "free"


def test_guest_cannot_consume_metered_feature():
    service = LicenseService(
        config=LicenseConfig(supabase_url="https://example.supabase.co", anon_key="public-anon",
                             public_key_b64="", app_version="2.3.6"),
        secure_store=DummyStore(), device_id="device-1",
    )
    result = service.consume_feature("text_chat")
    assert result["allowed"] is False
    assert result["tracked"] is False
    assert "sign in" in result["message"].lower()


def test_unconfigured_service_cannot_consume_metered_feature():
    service = LicenseService(config=LicenseConfig(), secure_store=DummyStore(), device_id="device-1")
    result = service.consume_feature("text_chat")
    assert result["allowed"] is False
    assert result["tracked"] is False


def test_usage_server_error_blocks_feature(monkeypatch):
    service, _envelope, _private = make_service_and_envelope()
    service._session = {
        "access_token": "access", "refresh_token": "refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    def fail(*_args, **_kwargs):
        raise RuntimeError("Ed25519 signing key is not configured on the server")
    monkeypatch.setattr(service, "_edge", fail)
    result = service.consume_feature("text_chat")
    assert result["allowed"] is False
    assert result["tracked"] is False
    assert "signing key" in result["message"].lower()


def test_untrusted_build_is_metered_against_free_quota(monkeypatch):
    service, envelope, private = make_service_and_envelope()
    envelope["payload"]["license_status"] = "untrusted_build"
    envelope["payload"]["plan_id"] = "free"
    envelope["payload"]["entitlements"] = {"text_chat": {"enabled": True, "limit": 1}}
    envelope["signature"] = base64.b64encode(private.sign(canonical_json(envelope["payload"]))).decode("ascii")
    service._session = {
        "access_token": "access", "refresh_token": "refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    monkeypatch.setattr(service, "_edge", lambda *_args, **_kwargs: {
        "allowed": False, "used": 1, "limit": 1,
        "message": "Usage limit reached", "license": envelope,
    })
    result = service.consume_feature("text_chat")
    assert result["allowed"] is False
    assert result["tracked"] is True
    assert result["limit"] == 1
    assert service.state.plan_id == "free"
    assert service.state.is_premium is False


def test_mock_server_startup_quota_and_transfer():
    import threading
    from tools.mock_licensing_server import ACCESS_TOKEN, PUBLIC_KEY_B64, create_server

    server = create_server("127.0.0.1", 0, plan="free", free_limit=1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        config = LicenseConfig(
            supabase_url=f"http://{host}:{port}", anon_key="mock-anon",
            public_key_b64=PUBLIC_KEY_B64, app_version="2.3.6", request_timeout=3,
        )

        class SessionStore(DummyStore):
            def __init__(self):
                self.value = {
                    "access_token": ACCESS_TOKEN, "refresh_token": "engo-local-mock-refresh-token",
                    "expires_at": int(time.time()) + 3600,
                    "user": {"id": "00000000-0000-4000-8000-000000000001", "email": "student@engo.local"},
                }
            def load(self):
                return self.value

        first = LicenseService(config, SessionStore(), device_id="11111111-1111-4111-8111-111111111111")
        state = first.verify_startup()
        assert state.verified is True and state.license_status == "active"
        assert state.plan_id == "free"
        assert first.consume_feature("text_chat")["allowed"] is True
        assert first.consume_feature("text_chat")["allowed"] is False

        second = LicenseService(config, SessionStore(), device_id="22222222-2222-4222-8222-222222222222")
        conflict = second.verify_startup()
        assert conflict.plan_id == "free"
        assert "another device" in conflict.reason.lower()
        moved = second.transfer_device_and_check()
        assert moved.license_status == "active"
        # Transferring to a new device does not reset the account-level Free cap.
        assert second.consume_feature("text_chat")["allowed"] is False
        revoked = first.heartbeat()
        assert revoked.plan_id == "free" and revoked.is_premium is False

        # The Premium plan has no Engo-side usage cap even if a mock Free cap exists.
        server.state.plan = "premium"
        premium_state = second.heartbeat()
        assert premium_state.is_premium is True
        assert second.consume_feature("text_chat")["allowed"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_mock_server_exercises_google_pkce_without_real_google(monkeypatch):
    import threading
    import urllib.request
    from engo_licensing import core as licensing_core
    from tools.mock_licensing_server import PUBLIC_KEY_B64, create_server

    server = create_server("127.0.0.1", 0, plan="free", free_limit=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        service = LicenseService(
            LicenseConfig(supabase_url=f"http://{host}:{port}", anon_key="mock-anon",
                          public_key_b64=PUBLIC_KEY_B64, app_version="2.3.6", request_timeout=3, oauth_timeout=8),
            DummyStore(), device_id="33333333-3333-4333-8333-333333333333",
        )
        def simulated_browser(url, **_kwargs):
            parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(url)
            params = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(parsed.query)
            callback_url = params["redirect_to"][0]
            callback_params = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(
                __import__("urllib.parse", fromlist=["urlparse"]).urlparse(callback_url).query
            )
            assert "state" not in params  # GoTrue owns the provider-level state.
            assert callback_params.get("state", [""])[0]  # Engo nonce is bound to redirect_to.
            def visit():
                # An unrelated local process must not be able to cancel the
                # pending login by probing the loopback callback with a bad state.
                bad_query = list(__import__("urllib.parse", fromlist=["parse_qsl"]).parse_qsl(
                    __import__("urllib.parse", fromlist=["urlparse"]).urlparse(callback_url).query,
                    keep_blank_values=True))
                bad_query = [(key, "forged" if key == "state" else value) for key, value in bad_query]
                bad_callback = __import__("urllib.parse", fromlist=["urlunparse"]).urlunparse(
                    __import__("urllib.parse", fromlist=["urlparse"]).urlparse(callback_url)._replace(
                        query=__import__("urllib.parse", fromlist=["urlencode"]).urlencode(bad_query)))
                try:
                    urllib.request.urlopen(bad_callback, timeout=2).read()
                except Exception:
                    pass
                try:
                    with urllib.request.urlopen(url, timeout=4) as response:
                        response.read()
                except Exception:
                    pass
            threading.Thread(target=visit, daemon=True).start()
            return True
        monkeypatch.setattr(licensing_core.webbrowser, "open", simulated_browser)
        session = service.login_google()
        assert session["user"]["email"] == "student@engo.local"
        assert session["access_token"] == "engo-local-mock-access-token"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_network_failure_fails_closed_to_free():
    class SessionStore(DummyStore):
        def load(self):
            return {
                "access_token": "test-access", "refresh_token": "test-refresh",
                "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
            }
    service = LicenseService(
        LicenseConfig(supabase_url="http://127.0.0.1:1", anon_key="mock",
                      public_key_b64="", app_version="2.3.6", request_timeout=1),
        SessionStore(), device_id="device-1",
    )
    service.state.plan_id = "premium"
    service.state.license_status = "active"
    service.state.verified = True
    state = service.heartbeat()
    assert state.plan_id == "free"
    assert state.is_premium is False
    assert state.verified is False


def test_usage_requires_a_signed_license_envelope(monkeypatch):
    service, _envelope, _private = make_service_and_envelope()
    service._session = {
        "access_token": "access", "refresh_token": "refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    monkeypatch.setattr(service, "_edge", lambda *_args, **_kwargs: {
        "allowed": True, "used": 1, "limit": None,
    })
    result = service.consume_feature("text_chat")
    assert result["allowed"] is False
    assert result["tracked"] is False
    assert service.state.is_premium is False


def test_usage_signed_license_must_match_authenticated_user(monkeypatch):
    service, envelope, private = make_service_and_envelope()
    envelope["payload"]["user_id"] = "another-user"
    envelope["signature"] = base64.b64encode(private.sign(canonical_json(envelope["payload"]))).decode("ascii")
    service._session = {
        "access_token": "access", "refresh_token": "refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    monkeypatch.setattr(service, "_edge", lambda *_args, **_kwargs: {
        "allowed": True, "used": 1, "limit": None, "license": envelope,
    })
    result = service.consume_feature("text_chat")
    assert result["allowed"] is False
    assert result["tracked"] is False
    assert service.state.is_premium is False



def test_license_config_prefers_current_publishable_key_name(monkeypatch):
    monkeypatch.setenv("ENGO_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("ENGO_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_example")
    monkeypatch.delenv("ENGO_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setenv("ENGO_LICENSE_PUBLIC_KEY_B64", "public-key-placeholder")
    config = LicenseConfig.load(app_version="2.3.6")
    assert config.anon_key == "sb_publishable_example"
    assert config.configured is True



def test_publishable_key_is_sent_only_in_apikey_header():
    config = LicenseConfig(anon_key="sb_publishable_example")
    service = LicenseService(config=config, secure_store=DummyStore(), device_id="device-1")
    headers = service._headers()
    assert headers["apikey"] == "sb_publishable_example"
    assert "Authorization" not in headers
    authenticated = service._headers("user-access-jwt")
    assert authenticated["Authorization"] == "Bearer user-access-jwt"


def test_untrusted_build_startup_opens_local_free_mode():
    state = LicenseState(authenticated=True, license_status="untrusted_build", plan_id="free", verified=True)
    assert is_expected_free_startup(state, service_configured=True) is True
    assert state.is_premium is False


def test_suspended_or_inactive_account_keeps_local_free_access():
    for status in ("account_suspended", "device_not_active", "free"):
        state = LicenseState(authenticated=True, license_status=status, plan_id="free", verified=True)
        assert is_expected_free_startup(state, service_configured=True) is True
        assert state.is_premium is False


def test_unknown_verified_license_state_is_not_silently_accepted():
    state = LicenseState(authenticated=True, license_status="invalid_state", plan_id="free", verified=True)
    assert is_expected_free_startup(state, service_configured=True) is False


def test_unconfigured_or_signed_out_startup_is_expected_free():
    assert is_expected_free_startup(LicenseState(), service_configured=False) is True
    signed_out = LicenseState(authenticated=False, reason="No account is signed in; continuing in Free mode")
    assert is_expected_free_startup(signed_out, service_configured=True) is True


def test_license_config_loads_google_desktop_client_id(monkeypatch):
    monkeypatch.setenv("ENGO_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("ENGO_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_example")
    monkeypatch.setenv("ENGO_GOOGLE_DESKTOP_CLIENT_ID", "desktop.apps.googleusercontent.com")
    monkeypatch.setenv("ENGO_GOOGLE_DESKTOP_CLIENT_SECRET", "desktop-secret-test-value")
    config = LicenseConfig.load(app_version="2.3.6")
    assert config.google_desktop_client_id == "desktop.apps.googleusercontent.com"
    # The installed client must never load an OAuth secret from JSON or env.
    assert config.google_desktop_client_secret == ""


def test_google_desktop_oauth_returns_to_engo_and_exchanges_id_token(monkeypatch):
    import json
    import threading
    import urllib.parse
    import urllib.request
    from engo_licensing import core as licensing_core

    config = LicenseConfig(
        supabase_url="https://example.supabase.co", anon_key="sb_publishable_example",
        app_version="2.3.6", oauth_timeout=5,
        google_desktop_client_id="engo-desktop.apps.googleusercontent.com",
    )
    service = LicenseService(config, DummyStore(), device_id="55555555-5555-4555-8555-555555555555")
    observed = {}

    def fake_browser(url, **_kwargs):
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        assert parsed.netloc == "accounts.google.com"
        assert params["client_id"] == [config.google_desktop_client_id]
        assert params["response_type"] == ["code"]
        assert params["scope"] == ["openid email profile"]
        assert params["code_challenge_method"] == ["S256"]
        assert len(params["nonce"][0]) == 64  # SHA-256 hex sent to Google.
        assert "client_secret" not in params
        callback = params["redirect_uri"][0]
        assert callback.startswith("http://127.0.0.1:")
        observed["auth_params"] = params

        def visit():
            callback_url = callback + "/?code=google-code&state=" + urllib.parse.quote(params["state"][0])
            with urllib.request.urlopen(callback_url, timeout=3) as response:
                response.read()
        threading.Thread(target=visit, daemon=True).start()
        return True

    def fake_exchange(code, verifier, redirect_uri):
        observed["exchange"] = {"code": code, "verifier": verifier, "redirect_uri": redirect_uri}
        return {"id_token": "fake-google-id-token", "access_token": "not-used-here"}

    def fake_request(method, path, body=None, access_token=None, timeout=None):
        observed["supabase"] = {"method": method, "path": path, "body": body, "access_token": access_token}
        return {
            "access_token": "supabase-access-token", "refresh_token": "supabase-refresh-token",
            "expires_in": 3600, "user": {"id": "google-user", "email": "student@example.test"},
        }

    monkeypatch.setattr(licensing_core.webbrowser, "open", fake_browser)
    monkeypatch.setattr(service, "_exchange_google_desktop_code", fake_exchange)
    monkeypatch.setattr(service, "_request", fake_request)
    session = service.login_google()

    assert session["access_token"] == "supabase-access-token"
    assert observed["exchange"]["code"] == "google-code"
    assert len(observed["exchange"]["verifier"]) >= 43
    assert observed["exchange"]["redirect_uri"] == observed["auth_params"]["redirect_uri"][0]
    supabase_call = observed["supabase"]
    assert supabase_call["method"] == "POST"
    assert supabase_call["path"] == "/auth/v1/token?grant_type=id_token"
    assert supabase_call["body"]["provider"] == "google"
    assert supabase_call["body"]["id_token"] == "fake-google-id-token"
    assert supabase_call["body"]["access_token"] == "not-used-here"
    original_nonce = supabase_call["body"]["nonce"]
    assert original_nonce != observed["auth_params"]["nonce"][0]
    assert __import__("hashlib").sha256(original_nonce.encode("utf-8")).hexdigest() == observed["auth_params"]["nonce"][0]


def test_google_desktop_code_exchange_uses_server_edge_function_and_never_sends_secret(monkeypatch):
    config = LicenseConfig(
        supabase_url="https://example.supabase.co", anon_key="sb_publishable_example",
        google_desktop_client_id="desktop.apps.googleusercontent.com",
    )
    service = LicenseService(config, DummyStore(), device_id="66666666-6666-4666-8666-666666666666")
    captured = {}

    def fake_edge(name, body, access_token=None):
        captured.update({"name": name, "body": body, "access_token": access_token})
        return {"id_token": "verified-by-supabase-later", "access_token": "optional-access-token"}

    monkeypatch.setattr(service, "_edge", fake_edge)
    result = service._exchange_google_desktop_code("code-1", "verifier-1", "http://127.0.0.1:40001")
    assert result["id_token"] == "verified-by-supabase-later"
    assert captured["name"] == "google-oauth-exchange"
    assert captured["body"]["client_id"] == "desktop.apps.googleusercontent.com"
    assert captured["body"]["code"] == "code-1"
    assert captured["body"]["code_verifier"] == "verifier-1"
    assert captured["body"]["redirect_uri"] == "http://127.0.0.1:40001"
    assert "client_secret" not in captured["body"]
    assert captured["access_token"] is None


def test_google_desktop_client_secret_is_never_read_or_sent_by_desktop(monkeypatch):
    config = LicenseConfig(
        supabase_url="https://example.supabase.co", anon_key="sb_publishable_example",
        google_desktop_client_id="desktop.apps.googleusercontent.com",
        google_desktop_client_secret="must-not-leave-the-client",
    )
    service = LicenseService(config, DummyStore(), device_id="77777777-7777-4777-8777-777777777777")
    captured = {}

    def fake_edge(name, body, access_token=None):
        captured.update({"name": name, "body": body})
        return {"id_token": "id-token"}

    monkeypatch.setattr(service, "_edge", fake_edge)
    service._exchange_google_desktop_code("code", "verifier", "http://127.0.0.1:40001")
    assert captured["name"] == "google-oauth-exchange"
    assert "client_secret" not in captured["body"]
    assert "must-not-leave-the-client" not in repr(captured)


def test_google_secret_error_is_reported_from_server_exchange(monkeypatch):
    from engo_licensing.core import LicenseError

    config = LicenseConfig(
        supabase_url="https://example.supabase.co", anon_key="sb_publishable_example",
        google_desktop_client_id="desktop.apps.googleusercontent.com",
    )
    service = LicenseService(config, DummyStore(), device_id="88888888-8888-4888-8888-888888888888")

    def fail(*_args, **_kwargs):
        raise LicenseError("Google Desktop OAuth is not configured on the Engo server")

    monkeypatch.setattr(service, "_edge", fail)
    with pytest.raises(LicenseError, match="not configured on the Engo server"):
        service._exchange_google_desktop_code("code", "verifier", "http://127.0.0.1:40001")



def _prepare_offline_file_quota(
    service, envelope, private, offline_store, feature_limit=2,
    feature_key="tags", scope_key="pdf:scope-1", server_used=0, pending=0,
    snapshot_complete=True, expires_delta=timedelta(minutes=5),
):
    now = datetime.now(timezone.utc)
    envelope["payload"]["issued_at"] = (now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    envelope["payload"]["expires_at"] = (now + expires_delta).isoformat().replace("+00:00", "Z")
    envelope["payload"]["plan_id"] = "free"
    envelope["payload"]["entitlements"] = {
        "tags": {"enabled": True, "limit": 2, "reset_period": "per_file", "plan_id": "free"},
        "tag_units": {"enabled": True, "limit": 8, "reset_period": "per_file", "plan_id": "free"},
        "text_chat": {"enabled": True, "limit": 2, "reset_period": "daily", "plan_id": "free"},
    }
    _resign_envelope(envelope, private)
    service._session = {
        "access_token": "access", "refresh_token": "refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    service._offline_cache = {
        "version": 1,
        "user_id": "user-1",
        "license_envelope": envelope,
        "license_cached_at": int(time.time()),
        "usage_snapshot_complete": snapshot_complete,
        "usage": {
            f"{feature_key}:{scope_key}": {
                "server_used": server_used,
                "pending": pending,
            }
        } if scope_key else {},
    }
    service._save_offline_cache()
    service._free_state("Device is offline", authenticated=True)


def test_offline_tags_enforce_last_signed_per_file_limit_and_keep_separate_files(monkeypatch):
    store = MemoryOfflineStore()
    service, envelope, private = make_service_and_envelope(offline_store=store)
    scope = "pdf:scope-1"
    _prepare_offline_file_quota(
        service, envelope, private, store, feature_key="tags",
        scope_key=scope, server_used=1, feature_limit=2,
    )

    def offline(*_args, **_kwargs):
        raise OfflineError("Could not contact the Engo account server")

    monkeypatch.setattr(service, "_edge", offline)
    first = service.consume_feature("tags", scope_key=scope)
    second = service.consume_feature("tags", scope_key=scope)
    other_file = service.consume_feature("tags", scope_key="pdf:scope-2")

    assert first["allowed"] is True and first["offline"] is True
    assert first["used"] == 2 and first["limit"] == 2
    assert second["allowed"] is False and second["used"] == 2
    assert other_file["allowed"] is True and other_file["used"] == 1
    assert store.value["usage"]["tags:pdf:scope-1"]["pending"] == 1


def test_offline_tag_units_use_eight_unit_per_file_snapshot(monkeypatch):
    store = MemoryOfflineStore()
    service, envelope, private = make_service_and_envelope(offline_store=store)
    scope = "pdf:scope-units"
    _prepare_offline_file_quota(
        service, envelope, private, store, feature_key="tag_units",
        scope_key=scope, server_used=7, feature_limit=8,
    )

    monkeypatch.setattr(
        service, "_edge",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OfflineError("network offline")),
    )
    allowed = service.consume_feature("tag_units", scope_key=scope)
    denied = service.consume_feature("tag_units", scope_key=scope)
    assert allowed["allowed"] is True and allowed["used"] == 8 and allowed["limit"] == 8
    assert denied["allowed"] is False and denied["used"] == 8


def test_offline_finite_tag_quota_denies_without_complete_usage_snapshot(monkeypatch):
    store = MemoryOfflineStore()
    service, envelope, private = make_service_and_envelope(offline_store=store)
    _prepare_offline_file_quota(
        service, envelope, private, store, feature_key="tags",
        scope_key="", snapshot_complete=False,
    )
    monkeypatch.setattr(
        service, "_edge",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OfflineError("network offline")),
    )
    result = service.consume_feature("tags", scope_key="pdf:unknown")
    assert result["allowed"] is False
    assert result["tracked"] is False
    assert result["message"] == "offline_feature_unavailable"


def test_only_tags_and_tag_units_can_use_offline_cache(monkeypatch):
    store = MemoryOfflineStore()
    service, envelope, private = make_service_and_envelope(offline_store=store)
    _prepare_offline_file_quota(
        service, envelope, private, store, feature_key="tags",
        scope_key="pdf:scope-1", snapshot_complete=True,
    )
    monkeypatch.setattr(
        service, "_edge",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OfflineError("network offline")),
    )
    result = service.consume_feature("text_chat")
    assert result["allowed"] is False
    assert result["tracked"] is False
    assert result["message"] == "offline_feature_unavailable"


def test_expired_signed_license_is_only_reused_for_offline_file_features(monkeypatch):
    store = MemoryOfflineStore()
    service, envelope, private = make_service_and_envelope(offline_store=store)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    envelope["payload"]["issued_at"] = (old - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    envelope["payload"]["expires_at"] = (old + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    envelope["payload"]["plan_id"] = "free"
    envelope["payload"]["entitlements"] = {
        "tags": {"enabled": True, "limit": 2, "reset_period": "per_file"},
        "text_chat": {"enabled": True, "limit": None, "reset_period": "daily"},
    }
    _resign_envelope(envelope, private)
    service._session = {
        "access_token": "access", "refresh_token": "refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    service._offline_cache = {
        "version": 1, "user_id": "user-1", "license_envelope": envelope,
        "usage_snapshot_complete": True,
        "usage": {"tags:pdf:scope-1": {"server_used": 0, "pending": 0}},
    }
    service._save_offline_cache()
    monkeypatch.setattr(
        service, "_edge",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OfflineError("network offline")),
    )
    result = service.consume_feature("tags", scope_key="pdf:scope-1")
    assert result["allowed"] is True and result["offline"] is True
    with pytest.raises(SignatureError, match="expired"):
        service._verify_signed_response(envelope)


def test_pending_offline_tag_usage_is_synced_before_next_online_action():
    store = MemoryOfflineStore()
    service, envelope, private = make_service_and_envelope(offline_store=store)
    scope = "pdf:sync-me"
    envelope["payload"]["entitlements"] = {
        "tags": {"enabled": True, "limit": 8, "reset_period": "per_file"},
    }
    _resign_envelope(envelope, private)
    service._session = {
        "access_token": "access", "refresh_token": "refresh",
        "expires_at": int(time.time()) + 3600, "user": {"id": "user-1"},
    }
    service._offline_cache = {
        "version": 1, "user_id": "user-1", "license_envelope": envelope,
        "usage_snapshot_complete": True,
        "usage": {"tags:pdf:sync-me": {"server_used": 1, "pending": 2}},
    }
    service._save_offline_cache()
    calls = []

    def accept(name, body, token):
        calls.append((name, body, token))
        return {"allowed": True, "used": 4, "limit": 8, "license": envelope}

    service._edge = accept
    result = service.consume_feature("tags", amount=1, scope_key=scope)
    assert result["allowed"] is True
    assert calls[0][1]["amount"] == 3
    assert store.value["usage"]["tags:pdf:sync-me"]["server_used"] == 4
    assert store.value["usage"]["tags:pdf:sync-me"]["pending"] == 0


def test_offline_feature_cache_is_persisted_and_cleared_on_logout():
    store = MemoryOfflineStore()
    service, envelope, private = make_service_and_envelope(offline_store=store)
    _prepare_offline_file_quota(
        service, envelope, private, store, feature_key="tags",
        scope_key="pdf:scope-1", snapshot_complete=True,
    )
    restored = LicenseService(
        config=service.config, secure_store=DummyStore(), device_id="device-1",
        offline_store=store,
    )
    assert restored._offline_cache["user_id"] == "user-1"
    assert restored._offline_cache["license_envelope"]["signature"] == envelope["signature"]
    restored.logout()
    assert store.value is None
