"""Engo account, device licensing and signed-entitlement client.

No administrative Supabase credentials are accepted by this module. Only the
public anon key is used by the desktop client; all privileged operations live
inside Supabase Edge Functions.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import platform
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except Exception:  # pragma: no cover - checked at runtime when signed licenses are used
    Ed25519PublicKey = None  # type: ignore[assignment]


APP_VERSION_FALLBACK = "2.3.6"
KNOWN_FEATURES = (
    "pdf_merge", "app_themes", "smart_theme", "text_chat",
    "voice_chat", "voice_board_docx", "tags", "tag_units", "translations", "ai_search",
    "open_other_formats",
)


class LicenseError(RuntimeError):
    """Base error for account and license failures."""


class ConfigurationError(LicenseError):
    pass


class SecureStorageError(LicenseError):
    pass


class NetworkError(LicenseError):
    pass


class OfflineError(NetworkError):
    """The device could not reach the account server because network access failed."""


class SignatureError(LicenseError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def canonical_json(value: Any) -> bytes:
    """Canonical JSON shared with the Supabase Edge Functions."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _app_data_dir() -> Path:
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(root) / "Engo"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "Engo"
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "engo"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _candidate_config_paths() -> list[Path]:
    paths: list[Path] = []
    try:
        paths.append(Path(sys.executable).resolve().parent / "engo_license.json")
    except Exception:
        pass
    paths.append(Path(__file__).resolve().parents[1] / "engo_license.json")
    paths.append(_app_data_dir() / "engo_license.json")
    # De-duplicate without changing search order.
    result: list[Path] = []
    for item in paths:
        if item not in result and item.is_file():
            result.append(item)
    return result


@dataclass(frozen=True)
class LicenseConfig:
    supabase_url: str = ""
    anon_key: str = ""
    public_key_b64: str = ""
    request_timeout: float = 12.0
    oauth_timeout: int = 180
    oauth_redirect_uri: str = ""
    app_version: str = APP_VERSION_FALLBACK
    expected_signer_thumbprint: str = ""
    google_desktop_client_id: str = ""
    # Google issues a client secret for Desktop clients too. Native clients cannot
    # keep it confidential, but some token exchanges may still require it.
    google_desktop_client_secret: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.anon_key)

    @classmethod
    def load(cls, app_version: str | None = None) -> "LicenseConfig":
        values: dict[str, Any] = {}
        for path in _candidate_config_paths():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    values.update(loaded)
                    break
            except Exception:
                continue

        def setting(env_name: str, json_name: str, default: Any = "") -> Any:
            env_value = os.environ.get(env_name)
            return env_value if env_value is not None else values.get(json_name, default)

        url = str(setting("ENGO_SUPABASE_URL", "supabase_url")).strip().rstrip("/")
        # Supabase's current public key is called a Publishable key. Keep the old
        # ANON variable/JSON name as a backwards-compatible alias for existing installs.
        publishable = os.environ.get("ENGO_SUPABASE_PUBLISHABLE_KEY") or values.get("supabase_publishable_key")
        anon_legacy = os.environ.get("ENGO_SUPABASE_ANON_KEY") or values.get("supabase_anon_key")
        anon = str(publishable or anon_legacy or "").strip()
        public_key = str(setting("ENGO_LICENSE_PUBLIC_KEY_B64", "license_public_key_b64")).strip()
        try:
            timeout = max(3.0, min(45.0, float(setting("ENGO_LICENSE_TIMEOUT", "request_timeout", 12))))
        except (TypeError, ValueError):
            timeout = 12.0
        try:
            oauth_timeout = max(30, min(600, int(setting("ENGO_OAUTH_TIMEOUT", "oauth_timeout", 180))))
        except (TypeError, ValueError):
            oauth_timeout = 180
        redirect = str(setting("ENGO_OAUTH_REDIRECT_URI", "oauth_redirect_uri")).strip()
        google_desktop_client_id = str(setting("ENGO_GOOGLE_DESKTOP_CLIENT_ID", "google_desktop_client_id")).strip()
        # Keep compatibility with the previously working Desktop OAuth setup.
        # The Desktop client secret is read from local config/environment and is
        # used only for Google's token exchange; it is never sent to Supabase.
        google_desktop_client_secret = str(setting(
            "ENGO_GOOGLE_DESKTOP_CLIENT_SECRET", "google_desktop_client_secret"
        )).strip()
        version = str(app_version or setting("ENGO_APP_VERSION", "app_version", APP_VERSION_FALLBACK)).strip()
        signer = str(setting("ENGO_SIGNER_THUMBPRINT", "expected_signer_thumbprint")).replace(" ", "").upper()
        if url and not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
            url = ""
        return cls(url, anon, public_key, timeout, oauth_timeout, redirect,
                   version or APP_VERSION_FALLBACK, signer, google_desktop_client_id,
                   google_desktop_client_secret)


class SecureStore:
    """DPAPI-backed secret store on Windows; OS keyring fallback elsewhere."""

    SERVICE = "EngoPDFViewer.Auth"
    ACCOUNT = "session-v1"

    def __init__(self, path: Path | None = None):
        self.path = path or (_app_data_dir() / "auth-session.dpapi")

    @staticmethod
    def _dpapi_encrypt(raw: bytes) -> bytes:
        if os.name != "nt":
            raise SecureStorageError("Windows DPAPI is unavailable")
        try:
            import win32crypt  # type: ignore
            return win32crypt.CryptProtectData(raw, "Engo session", None, None, None, 0)
        except Exception as exc:
            raise SecureStorageError(f"Windows credential protection failed: {exc}") from exc

    @staticmethod
    def _dpapi_decrypt(raw: bytes) -> bytes:
        if os.name != "nt":
            raise SecureStorageError("Windows DPAPI is unavailable")
        try:
            import win32crypt  # type: ignore
            result = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
            return result[1] if isinstance(result, tuple) else result
        except Exception as exc:
            raise SecureStorageError(f"Windows credential decryption failed: {exc}") from exc

    def save(self, value: dict[str, Any]) -> None:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if os.name == "nt":
            try:
                encrypted = self._dpapi_encrypt(raw)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd, temp_name = tempfile.mkstemp(prefix=".engo-auth-", dir=str(self.path.parent))
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(b"ENGODP1\0" + encrypted)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp_name, self.path)
                finally:
                    try:
                        os.unlink(temp_name)
                    except OSError:
                        pass
                return
            except SecureStorageError:
                # Credential Manager remains an acceptable protected fallback.
                pass
        try:
            import keyring  # type: ignore
            keyring.set_password(self.SERVICE, self.ACCOUNT, base64.b64encode(raw).decode("ascii"))
            verified = keyring.get_password(self.SERVICE, self.ACCOUNT)
            if not verified:
                raise RuntimeError("Keyring did not verify the saved session")
        except Exception as exc:
            raise SecureStorageError(f"Secure credential storage is unavailable: {exc}") from exc

    def load(self) -> dict[str, Any] | None:
        raw: bytes | None = None
        if os.name == "nt" and self.path.is_file():
            data = self.path.read_bytes()
            if not data.startswith(b"ENGODP1\0"):
                raise SecureStorageError("Stored session has an unknown format")
            raw = self._dpapi_decrypt(data[len(b"ENGODP1\0"):])
        else:
            try:
                import keyring  # type: ignore
                stored = keyring.get_password(self.SERVICE, self.ACCOUNT)
                if stored:
                    raw = base64.b64decode(stored, validate=True)
            except Exception:
                raw = None
        if raw is None:
            return None
        try:
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else None
        except Exception as exc:
            raise SecureStorageError("The saved account session could not be decoded") from exc

    def clear(self) -> None:
        if os.name == "nt":
            try:
                self.path.unlink(missing_ok=True)
            except OSError as exc:
                raise SecureStorageError(f"Could not remove the saved session: {exc}") from exc
        try:
            import keyring  # type: ignore
            keyring.delete_password(self.SERVICE, self.ACCOUNT)
        except Exception:
            pass


class OfflineFeatureCacheStore:
    """Protected local cache for the last verified per-file tag entitlements and usage."""

    SERVICE = "EngoPDFViewer.OfflineFeatureCache"
    ACCOUNT = "offline-feature-cache-v1"

    def __init__(self, path: Path | None = None):
        self.path = path or (_app_data_dir() / "offline-feature-cache.dpapi")

    def save(self, value: dict[str, Any]) -> None:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if os.name == "nt":
            try:
                encrypted = SecureStore._dpapi_encrypt(raw)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd, temp_name = tempfile.mkstemp(prefix=".engo-offline-", dir=str(self.path.parent))
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(b"ENGOFC1\0" + encrypted)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp_name, self.path)
                finally:
                    try:
                        os.unlink(temp_name)
                    except OSError:
                        pass
                return
            except SecureStorageError:
                # Credential Manager is an acceptable protected fallback.
                pass
        try:
            import keyring  # type: ignore
            encoded = base64.b64encode(raw).decode("ascii")
            keyring.set_password(self.SERVICE, self.ACCOUNT, encoded)
            if keyring.get_password(self.SERVICE, self.ACCOUNT) != encoded:
                raise RuntimeError("Keyring did not verify the offline cache")
        except Exception as exc:
            raise SecureStorageError(f"Protected offline quota storage is unavailable: {exc}") from exc

    def load(self) -> dict[str, Any] | None:
        raw: bytes | None = None
        if os.name == "nt" and self.path.is_file():
            data = self.path.read_bytes()
            if not data.startswith(b"ENGOFC1\0"):
                raise SecureStorageError("Stored offline quota cache has an unknown format")
            raw = SecureStore._dpapi_decrypt(data[len(b"ENGOFC1\0"):])
        else:
            try:
                import keyring  # type: ignore
                stored = keyring.get_password(self.SERVICE, self.ACCOUNT)
                if stored:
                    raw = base64.b64decode(stored, validate=True)
            except Exception:
                raw = None
        if raw is None:
            return None
        try:
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else None
        except Exception as exc:
            raise SecureStorageError("The offline quota cache could not be decoded") from exc

    def clear(self) -> None:
        if os.name == "nt":
            try:
                self.path.unlink(missing_ok=True)
            except OSError as exc:
                raise SecureStorageError(f"Could not remove the offline quota cache: {exc}") from exc
        try:
            import keyring  # type: ignore
            keyring.delete_password(self.SERVICE, self.ACCOUNT)
        except Exception:
            pass


@dataclass
class LicenseState:
    authenticated: bool = False
    user: dict[str, Any] = field(default_factory=dict)
    plan_id: str = "free"
    license_status: str = "free"
    entitlements: dict[str, dict[str, Any]] = field(default_factory=dict)
    issued_at: str = ""
    expires_at: str = ""
    reason: str = ""
    verified: bool = False
    free_unlimited_mode: bool = False
    device_id: str = ""
    app_version: str = APP_VERSION_FALLBACK

    @property
    def is_premium(self) -> bool:
        return bool(self.verified and self.license_status == "active" and self.plan_id == "premium")

    @property
    def plan_label(self) -> str:
        return "Premium" if self.is_premium else "Free"


def is_expected_free_startup(state: LicenseState, service_configured: bool) -> bool:
    """Return whether startup should open Engo in local Free mode without blocking documents.

    A signed response can be valid while the current binary is not yet approved,
    the account is suspended, or the device is inactive. Those states must never
    grant Premium, but they also must not block local PDF access. Unknown errors
    and failed signature/network verification remain visible to the user.
    """
    if not service_configured:
        return True
    if not state.authenticated and "No account is signed in" in str(state.reason):
        return True
    return bool(state.verified and state.license_status in {
        "untrusted_build", "account_suspended", "device_not_active", "free",
    })


class _OAuthHandler(http.server.BaseHTTPRequestHandler):
    callback_result: dict[str, str] = {}
    expected_state: str = ""
    callback_path: str = "/callback"

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != self.callback_path:
            self.send_error(404)
            return
        query = urllib.parse.parse_qs(parsed.query)
        received_state = str((query.get("state") or [""])[0])
        if not secrets.compare_digest(received_state, self.expected_state):
            # Ignore a local request with a missing/incorrect nonce. Do not let
            # a process that can probe the loopback port cancel the real login.
            body = b"Engo sign-in response was not accepted."
            self.send_response(400)
        else:
            type(self).callback_result = {
                "code": str((query.get("code") or [""])[0]),
                "error": str((query.get("error_description") or query.get("error") or [""])[0]),
            }
            body = b"Engo sign-in response received. You may close this window and return to Engo."
            self.send_response(200 if type(self).callback_result.get("code") else 400)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class LicenseService:
    """Application-facing licensing service; all premium grants require a signature."""

    OFFLINE_FILE_FEATURES = frozenset({"tags", "tag_units"})

    def __init__(self, config: LicenseConfig | None = None, secure_store: SecureStore | None = None,
                 device_id: str | None = None, offline_store: OfflineFeatureCacheStore | None = None):
        self.config = config or LicenseConfig.load()
        self.secure_store = secure_store or SecureStore()
        self.offline_store = offline_store or OfflineFeatureCacheStore()
        try:
            cached = self.offline_store.load()
        except Exception:
            cached = None
        self._offline_cache: dict[str, Any] = cached if isinstance(cached, dict) else {
            "version": 1, "usage": {}, "usage_snapshot_complete": False,
        }
        self.device_id = device_id or self._load_or_create_device_id()
        self.state = LicenseState(device_id=self.device_id, app_version=self.config.app_version)
        self._session: dict[str, Any] | None = None
        self._lock = threading.RLock()
        self._last_signed_payload: dict[str, Any] | None = None

    @staticmethod
    def _load_or_create_device_id() -> str:
        path = _app_data_dir() / "device-id.txt"
        try:
            value = path.read_text(encoding="ascii").strip()
            uuid.UUID(value)
            return value
        except Exception:
            value = str(uuid.uuid4())
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".tmp")
            temp.write_text(value, encoding="ascii")
            try:
                os.replace(temp, path)
            except OSError:
                pass
            return value

    def _headers(self, access_token: str | None = None) -> dict[str, str]:
        # Publishable API keys belong only in the apikey header. New sb_publishable_
        # keys are not JWTs and must never be sent as Authorization bearer tokens.
        headers = {"apikey": self.config.anon_key, "Content-Type": "application/json", "Accept": "application/json"}
        token = str(access_token or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None,
                 access_token: str | None = None, timeout: float | None = None) -> Any:
        if not self.config.configured:
            raise ConfigurationError("Supabase is not configured. Add the public project URL and anon key.")
        url = self.config.supabase_url + path
        raw = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=raw, headers=self._headers(access_token), method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.config.request_timeout) as response:
                content = response.read()
                if not content:
                    return {}
                try:
                    return json.loads(content.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise NetworkError("Server returned invalid JSON") from exc
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:1200]
            except Exception:
                pass
            raise NetworkError(f"Server returned HTTP {exc.code}: {detail or exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OfflineError(f"Could not contact the Engo account server: {exc}") from exc

    def _edge(self, name: str, body: dict[str, Any] | None = None,
              access_token: str | None = None) -> dict[str, Any]:
        result = self._request("POST", f"/functions/v1/{name}", body or {}, access_token)
        if not isinstance(result, dict):
            raise NetworkError("Server returned an unexpected response")
        if result.get("error"):
            raise LicenseError(str(result["error"]))
        return result

    def get_app_update_info(self) -> dict[str, Any]:
        """Fetch public release information; this endpoint contains no account data."""
        return self._edge("app-update-info", {"app_version": self.config.app_version})


    def _load_session(self) -> dict[str, Any] | None:
        if self._session is not None:
            return self._session
        try:
            self._session = self.secure_store.load()
        except SecureStorageError:
            self._session = None
            raise
        return self._session

    def _persist_session(self, session: dict[str, Any]) -> None:
        access_token = str(session.get("access_token") or "").strip()
        refresh_token = str(session.get("refresh_token") or "").strip()
        if not access_token or not refresh_token:
            raise LicenseError("Authentication response did not contain a refreshable session")
        expires_in = int(session.get("expires_in") or 3600)
        expires_at = int(session.get("expires_at") or (time.time() + expires_in))
        normalized = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": str(session.get("token_type") or "bearer"),
            "expires_at": expires_at,
            "user": session.get("user") if isinstance(session.get("user"), dict) else {},
        }
        self.secure_store.save(normalized)
        self._session = normalized

    def _refresh_session(self, session: dict[str, Any]) -> dict[str, Any]:
        """Refresh once, reusing a newer session if another worker already rotated it.

        Supabase refresh tokens are single-use. Several account UI workers can
        receive an expired-JWT response at nearly the same time. Serialize refresh
        operations and compare the caller's token with the latest in-memory
        session before attempting another exchange.
        """
        with self._lock:
            supplied_refresh_token = str(session.get("refresh_token") or "").strip()
            current = self._load_session() or session
            current_refresh_token = str(current.get("refresh_token") or "").strip()
            current_access_token = str(current.get("access_token") or "").strip()
            current_expiry = int(current.get("expires_at") or 0)

            # A parallel request already refreshed this exact session. Do not
            # replay the old refresh token and accidentally invalidate the chain.
            if (
                current_refresh_token
                and supplied_refresh_token
                and current_refresh_token != supplied_refresh_token
                and current_access_token
                and current_expiry > int(time.time()) + 5
            ):
                return current

            refresh_token = current_refresh_token or supplied_refresh_token
            if not refresh_token:
                raise LicenseError("Saved session has no refresh token; sign in again")
            updated = self._request(
                "POST", "/auth/v1/token?grant_type=refresh_token",
                {"refresh_token": refresh_token},
            )
            if not isinstance(updated, dict):
                raise LicenseError("Token refresh returned invalid data")
            if not updated.get("user") and updated.get("access_token"):
                try:
                    user = self._request(
                        "GET", "/auth/v1/user",
                        access_token=str(updated["access_token"]).strip(),
                    )
                    updated["user"] = user if isinstance(user, dict) else {}
                except Exception:
                    updated["user"] = current.get("user") or session.get("user") or {}
            self._persist_session(updated)
            return self._session or updated

    def get_session(self, refresh: bool = True) -> dict[str, Any] | None:
        with self._lock:
            session = self._load_session()
            if not session:
                return None
            expiry = int(session.get("expires_at") or 0)
            if refresh and expiry <= int(time.time()) + 90:
                return self._refresh_session(session)
            return session

    def login_google(self) -> dict[str, Any]:
        """Sign in with Google; prefer the native Desktop OAuth path when configured.

        The native path sends Google directly back to Engo over a loopback listener,
        then exchanges the verified Google ID token for a Supabase Auth session.
        This avoids presenting the Supabase project hostname as the OAuth app.
        """
        if not self.config.configured:
            raise ConfigurationError("Configure Supabase before enabling Google sign-in")
        if self.config.google_desktop_client_id:
            return self._login_google_desktop()
        return self._login_google_via_supabase()

    def _login_google_desktop(self) -> dict[str, Any]:
        """Run Google's installed-app OAuth flow with PKCE, state and OIDC nonce."""
        client_id = self.config.google_desktop_client_id.strip()
        if not client_id.endswith(".apps.googleusercontent.com"):
            raise ConfigurationError("Google Desktop Client ID is invalid. Check engo_license.json.")

        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        nonce = secrets.token_urlsafe(32)
        # Supabase expects the original nonce while Google receives its SHA-256
        # hexadecimal digest in the ID token claim.
        google_nonce = hashlib.sha256(nonce.encode("utf-8")).hexdigest()

        handler = type("EngoDesktopOAuthHandler", (_OAuthHandler,), {
            "callback_result": {}, "expected_state": state, "callback_path": "/",
        })
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        server.timeout = self.config.oauth_timeout
        _host, port = server.server_address
        redirect_uri = f"http://127.0.0.1:{port}"
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": google_nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
        try:
            webbrowser.open(auth_url, new=1, autoraise=True)
            deadline = time.monotonic() + self.config.oauth_timeout
            while not handler.callback_result:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                server.timeout = min(5.0, remaining)
                server.handle_request()
        finally:
            server.server_close()

        callback = handler.callback_result
        if not callback:
            raise NetworkError("Google sign-in timed out. Return to Engo and try again.")
        if callback.get("error"):
            raise LicenseError(callback["error"])
        code = callback.get("code", "")
        if not code:
            raise LicenseError("Google sign-in did not return an authorization code")

        google_tokens = self._exchange_google_desktop_code(code, verifier, redirect_uri)

        id_token = str(google_tokens.get("id_token") or "")
        if not id_token:
            raise LicenseError("Google did not return an OpenID ID token")
        auth_payload = {"provider": "google", "id_token": id_token, "nonce": nonce}
        google_access_token = str(google_tokens.get("access_token") or "").strip()
        if google_access_token:
            # Supabase checks the ID token's at_hash claim when one is present.
            auth_payload["access_token"] = google_access_token
        session = self._request(
            "POST", "/auth/v1/token?grant_type=id_token", auth_payload,
        )
        if not isinstance(session, dict):
            raise LicenseError("Supabase returned invalid session data")
        self._persist_session(session)
        return self._session or session

    def _exchange_google_desktop_code(self, code: str, verifier: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange a Google Desktop authorization code using PKCE.

        Preserve the previously working flow: use the Desktop OAuth client's
        own optional secret locally when Google requires it. The secret is sent
        only to Google's token endpoint, never to the Engo/Supabase server.
        """
        form = {
            "client_id": self.config.google_desktop_client_id,
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        desktop_secret = str(self.config.google_desktop_client_secret or "").strip()
        if desktop_secret:
            form["client_secret"] = desktop_secret
        payload = urllib.parse.urlencode(form).encode("ascii")
        request = urllib.request.Request(
            "https://oauth2.googleapis.com/token", data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:800]
            except Exception:
                detail = str(exc.reason)
            if "client_secret is missing" in detail.lower() and not desktop_secret:
                raise ConfigurationError(
                    "Google requires the Desktop OAuth client's own client_secret. "
                    "Set google_desktop_client_secret in engo_license.json. "
                    "Do not use the Web application's secret."
                ) from exc
            raise NetworkError(f"Google token exchange failed (HTTP {exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise NetworkError(f"Could not exchange Google sign-in code: {exc}") from exc
        if not isinstance(result, dict):
            raise LicenseError("Google returned invalid token data")
        return result

    def _login_google_via_supabase(self) -> dict[str, Any]:
        """Legacy hosted OAuth fallback; it shows the Supabase project domain."""
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        handler = type("EngoOAuthHandler", (_OAuthHandler,), {"callback_result": {}, "expected_state": state})
        server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        server.timeout = self.config.oauth_timeout
        host, port = server.server_address
        redirect_uri = self.config.oauth_redirect_uri or f"http://127.0.0.1:{port}/callback"
        parsed_redirect = urllib.parse.urlparse(redirect_uri)
        if parsed_redirect.scheme != "http" or parsed_redirect.hostname not in ("127.0.0.1", "localhost"):
            server.server_close()
            raise ConfigurationError("OAuth redirect must use a loopback localhost URL for the desktop PKCE flow")
        if self.config.oauth_redirect_uri:
            try:
                fixed_port = parsed_redirect.port
                if not fixed_port or parsed_redirect.path not in ("/callback", ""):
                    raise ValueError("Unsupported callback path or port")
                server.server_close()
                server = http.server.HTTPServer(("127.0.0.1", fixed_port), handler)
                server.timeout = self.config.oauth_timeout
                redirect_host = parsed_redirect.hostname or "127.0.0.1"
                redirect_uri = f"http://{redirect_host}:{fixed_port}/callback"
            except Exception as exc:
                try: server.server_close()
                except Exception: pass
                raise ConfigurationError(f"Could not bind configured OAuth callback: {exc}") from exc
        # Supabase Auth creates and validates its own OAuth provider state. Preserve
        # an independent Engo nonce inside redirect_to instead of sending a top-level
        # `state` parameter (GoTrue reserves/overwrites that parameter). The PKCE
        # callback preserves redirect_to query parameters when it appends `code`.
        callback_query = dict(urllib.parse.parse_qsl(parsed_redirect.query, keep_blank_values=True))
        callback_query["state"] = state
        redirect_uri = urllib.parse.urlunparse(parsed_redirect._replace(query=urllib.parse.urlencode(callback_query)))
        params = {
            "provider": "google", "redirect_to": redirect_uri,
            "code_challenge": challenge, "code_challenge_method": "s256",
        }
        auth_url = self.config.supabase_url + "/auth/v1/authorize?" + urllib.parse.urlencode(params)
        try:
            webbrowser.open(auth_url, new=1, autoraise=True)
            # Ignore unrelated local requests (e.g. a browser probing the port);
            # wait only for the OAuth callback carrying the matching state.
            deadline = time.monotonic() + self.config.oauth_timeout
            while not handler.callback_result:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                server.timeout = min(5.0, remaining)
                server.handle_request()
        finally:
            server.server_close()
        callback = handler.callback_result
        if not callback:
            raise NetworkError("Google sign-in timed out. Return to Engo and try again.")
        if callback.get("error"):
            raise LicenseError(callback["error"])
        code = callback.get("code", "")
        if not code:
            raise LicenseError("Google sign-in did not return an authorization code")
        session = self._request("POST", "/auth/v1/token?grant_type=pkce",
                                {"auth_code": code, "code_verifier": verifier})
        if not isinstance(session, dict):
            raise LicenseError("Google sign-in returned invalid session data")
        self._persist_session(session)
        return self._session or session

    def logout(self) -> None:
        session = self.get_session(refresh=False)
        if session and self.config.configured:
            try:
                self._request("POST", "/auth/v1/logout", {}, str(session.get("access_token") or ""))
            except Exception:
                pass
        self.secure_store.clear()
        try:
            self.offline_store.clear()
        except Exception:
            pass
        self._offline_cache = {"version": 1, "usage": {}, "usage_snapshot_complete": False}
        self._session = None
        self._last_signed_payload = None
        self.state = LicenseState(device_id=self.device_id, app_version=self.config.app_version,
                                  reason="Signed out; using Free mode")

    def activate_device(self, allow_transfer: bool = False) -> dict[str, Any]:
        session = self.get_session()
        if not session:
            raise LicenseError("Sign in before activating this device")
        result = self._edge("device-transfer" if allow_transfer else "device-activate", {
            "device_id": self.device_id,
            "device_name": platform.node() or "Windows PC",
            "app_version": self.config.app_version,
        }, str(session["access_token"]))
        if result.get("status") == "device_conflict":
            return result
        if result.get("status") not in ("active", "activated", "transferred"):
            raise LicenseError(str(result.get("message") or "This device could not be activated"))
        return result

    def _verify_signed_response(self, envelope: dict[str, Any], allow_expired: bool = False) -> dict[str, Any]:
        payload = envelope.get("payload")
        signature_value = envelope.get("signature")
        if not isinstance(payload, dict) or not isinstance(signature_value, str):
            raise SignatureError("The server response is missing its signed license payload")
        if Ed25519PublicKey is None:
            raise SignatureError("The cryptography package is unavailable; license signature cannot be verified")
        if not self.config.public_key_b64:
            raise SignatureError("The Ed25519 public verification key is not configured")
        try:
            public_raw = base64.b64decode(self.config.public_key_b64, validate=True)
            signature = base64.b64decode(signature_value, validate=True)
            if len(public_raw) != 32 or len(signature) != 64:
                raise ValueError("Unexpected Ed25519 key or signature length")
            public_key = Ed25519PublicKey.from_public_bytes(public_raw)
            public_key.verify(signature, canonical_json(payload))
        except Exception as exc:
            raise SignatureError(f"License signature is invalid: {exc}") from exc

        now = _utc_now()
        issued = _parse_iso(payload.get("issued_at"))
        expires = _parse_iso(payload.get("expires_at"))
        if not issued or not expires:
            raise SignatureError("The signed license has invalid timestamps")
        if issued.timestamp() > now.timestamp() + 120:
            raise SignatureError("The signed license was issued in the future")
        if expires <= now and not allow_expired:
            raise SignatureError("The signed license has expired")
        if expires <= issued:
            raise SignatureError("The signed license expiry is invalid")
        if str(payload.get("device_id") or "") != self.device_id:
            raise SignatureError("The signed license belongs to a different device")
        if str(payload.get("app_version") or "") != self.config.app_version:
            raise SignatureError("The signed license does not match this application version")
        return payload

    def _save_offline_cache(self) -> bool:
        try:
            self.offline_store.save(self._offline_cache)
            return True
        except Exception:
            return False

    @staticmethod
    def _offline_usage_key(feature_key: str, scope_key: str) -> str:
        return f"{feature_key}:{scope_key}"

    def _remember_offline_license(
        self, envelope: dict[str, Any], payload: dict[str, Any], user_id: str,
    ) -> None:
        """Keep the last verified signed entitlements for the two offline per-file features."""
        user_id = str(user_id or "").strip()
        if not user_id or not isinstance(envelope, dict):
            return
        previous_user = str(self._offline_cache.get("user_id") or "")
        if previous_user and previous_user != user_id:
            self._offline_cache["usage"] = {}
            self._offline_cache["usage_snapshot_complete"] = False
        self._offline_cache.update({
            "version": 1,
            "user_id": user_id,
            "license_envelope": envelope,
            "license_cached_at": int(time.time()),
        })
        self._save_offline_cache()

    def _cache_offline_usage_snapshot(self, rows: Any, user_id: str) -> bool:
        """Cache authoritative per-file usage rows returned by the authenticated account API."""
        user_id = str(user_id or "").strip()
        if not user_id or user_id != str(self._offline_cache.get("user_id") or ""):
            return False
        if not isinstance(rows, list):
            return False
        previous = self._offline_cache.get("usage")
        previous = previous if isinstance(previous, dict) else {}
        refreshed: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            feature = str(row.get("feature_key") or "").strip()
            scope = str(row.get("scope_key") or "").strip()
            if feature not in self.OFFLINE_FILE_FEATURES or not scope or len(scope) > 128:
                continue
            try:
                server_used = max(0, int(row.get("used") or 0))
            except (TypeError, ValueError):
                continue
            key = self._offline_usage_key(feature, scope)
            old = previous.get(key) if isinstance(previous.get(key), dict) else {}
            try:
                pending = max(0, int(old.get("pending") or 0))
            except (TypeError, ValueError):
                pending = 0
            refreshed[key] = {"server_used": server_used, "pending": pending}
        # Preserve offline actions not yet reflected in the server's snapshot.
        for key, old in previous.items():
            if key in refreshed or not isinstance(old, dict):
                continue
            try:
                pending = max(0, int(old.get("pending") or 0))
                old_server_used = max(0, int(old.get("server_used") or 0))
            except (TypeError, ValueError):
                continue
            if pending:
                refreshed[str(key)] = {"server_used": old_server_used, "pending": pending}
        self._offline_cache["usage"] = refreshed
        self._offline_cache["usage_snapshot_complete"] = True
        self._offline_cache["usage_snapshot_at"] = int(time.time())
        return self._save_offline_cache()

    def _offline_pending_usage(self, feature_key: str, scope_key: str) -> int:
        if feature_key not in self.OFFLINE_FILE_FEATURES or not scope_key:
            return 0
        usage = self._offline_cache.get("usage")
        record = usage.get(self._offline_usage_key(feature_key, scope_key)) if isinstance(usage, dict) else None
        try:
            return max(0, int(record.get("pending") or 0)) if isinstance(record, dict) else 0
        except (TypeError, ValueError):
            return 0

    def _record_online_file_usage(
        self, feature_key: str, scope_key: str, response: dict[str, Any],
        pending_before: int, requested_amount: int, batch_amount: int, accepted: bool,
    ) -> None:
        if feature_key not in self.OFFLINE_FILE_FEATURES or not scope_key:
            return
        usage = self._offline_cache.get("usage")
        if not isinstance(usage, dict):
            usage = {}
            self._offline_cache["usage"] = usage
        key = self._offline_usage_key(feature_key, scope_key)
        old = usage.get(key) if isinstance(usage.get(key), dict) else {}
        try:
            server_used = max(0, int(response.get("used"))) if response.get("used") is not None else max(0, int(old.get("server_used") or 0))
        except (TypeError, ValueError):
            server_used = max(0, int(old.get("server_used") or 0))
        pending_after = (
            max(0, pending_before + requested_amount - batch_amount)
            if accepted else max(0, pending_before)
        )
        usage[key] = {"server_used": server_used, "pending": pending_after}
        self._save_offline_cache()

    def _sync_pending_offline_usage(
        self, feature_key: str, scope_key: str, session: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Commit previously accepted offline file usage before reserving new usage."""
        pending = self._offline_pending_usage(feature_key, scope_key)
        if pending <= 0:
            return None
        user = session.get("user") if isinstance(session.get("user"), dict) else {}
        expected_user_id = str(user.get("id") or "")
        access_token = str(session.get("access_token") or "")
        if not expected_user_id or not access_token:
            return {"allowed": False, "tracked": False, "message": "offline_feature_unavailable"}
        while pending > 0:
            batch = min(1000, pending)
            response = self._edge("usage-consume", {
                "device_id": self.device_id,
                "app_version": self.config.app_version,
                "feature_key": feature_key,
                "amount": batch,
                "scope_key": scope_key,
            }, access_token)
            envelope = response.get("license")
            if not isinstance(envelope, dict):
                raise SignatureError("Offline usage sync did not include a signed license")
            payload = self._verify_signed_response(envelope)
            if str(payload.get("user_id") or "") != expected_user_id:
                raise SignatureError("Offline usage sync belongs to a different account")
            self._remember_offline_license(envelope, payload, expected_user_id)
            self._apply_payload(payload, user)
            entitlements = payload.get("entitlements")
            entitlement = entitlements.get(feature_key) if isinstance(entitlements, dict) else None
            if str(payload.get("license_status") or "") != "active":
                return {
                    "allowed": False, "tracked": False,
                    "message": "The account or this device is not authorized. Feature access is blocked.",
                }
            if not isinstance(entitlement, dict) or not bool(entitlement.get("enabled")):
                return {
                    "allowed": False, "tracked": True,
                    "message": "This feature is not enabled for the current plan",
                    "used": response.get("used"), "limit": response.get("limit"),
                }
            if response.get("allowed") is not True:
                self._record_online_file_usage(
                    feature_key, scope_key, response, pending, 0, batch, False,
                )
                return {
                    "allowed": False, "tracked": True,
                    "message": str(response.get("message") or "The usage limit has been reached"),
                    "used": response.get("used"), "limit": response.get("limit"),
                }
            self._record_online_file_usage(
                feature_key, scope_key, response, pending, 0, batch, True,
            )
            pending -= batch
        return None

    def _consume_offline_file_feature(
        self, feature_key: str, amount: int, scope_key: str,
    ) -> dict[str, Any] | None:
        """Consume tags/tag_units against the last signed entitlement and per-file usage snapshot.

        None means there is no trustworthy local snapshot; callers must deny access.
        """
        if feature_key not in self.OFFLINE_FILE_FEATURES or not scope_key or len(scope_key) > 128:
            return None
        try:
            session = self.get_session(refresh=False)
        except Exception:
            session = self._session
        session_user = session.get("user", {}) if isinstance(session, dict) else {}
        user_id = str(session_user.get("id") or "") if isinstance(session_user, dict) else ""
        if not user_id or user_id != str(self._offline_cache.get("user_id") or ""):
            return None
        envelope = self._offline_cache.get("license_envelope")
        if not isinstance(envelope, dict):
            return None
        try:
            payload = self._verify_signed_response(envelope, allow_expired=True)
        except Exception:
            return None
        if str(payload.get("user_id") or "") != user_id:
            return None
        if str(payload.get("device_id") or "") != self.device_id:
            return None
        if str(payload.get("app_version") or "") != self.config.app_version:
            return None
        if str(payload.get("license_status") or "") != "active":
            return None
        entitlements = payload.get("entitlements")
        entitlement = entitlements.get(feature_key) if isinstance(entitlements, dict) else None
        if not isinstance(entitlement, dict) or not bool(entitlement.get("enabled")):
            return {"allowed": False, "tracked": True, "message": "This feature is not enabled for the current plan"}
        raw_limit = entitlement.get("limit")
        if raw_limit is None:
            limit = None
        else:
            try:
                limit = max(0, int(raw_limit))
            except (TypeError, ValueError):
                return None
        usage = self._offline_cache.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        key = self._offline_usage_key(feature_key, scope_key)
        record = usage.get(key) if isinstance(usage.get(key), dict) else None
        snapshot_complete = bool(self._offline_cache.get("usage_snapshot_complete", False))
        if record is None and limit is not None and not snapshot_complete:
            return None
        try:
            server_used = max(0, int(record.get("server_used") or 0)) if record else 0
            pending = max(0, int(record.get("pending") or 0)) if record else 0
        except (TypeError, ValueError):
            return None
        used_before = server_used + pending
        if limit is not None and used_before + amount > limit:
            return {
                "allowed": False, "tracked": True,
                "message": "The usage limit has been reached",
                "used": used_before, "limit": limit, "offline": True,
            }
        usage[key] = {"server_used": server_used, "pending": pending + amount}
        self._offline_cache["usage"] = usage
        if not self._save_offline_cache():
            return None
        return {
            "allowed": True, "tracked": True, "message": "offline_cached_usage",
            "used": used_before + amount, "limit": limit, "offline": True,
        }

    def _apply_payload(self, payload: dict[str, Any], user: dict[str, Any] | None = None) -> LicenseState:
        license_status = str(payload.get("license_status") or "invalid")
        plan_id = str(payload.get("plan_id") or "free").lower()
        if license_status != "active" or plan_id not in ("free", "premium"):
            plan_id = "free"
        raw_entitlements = payload.get("entitlements")
        entitlements = raw_entitlements if isinstance(raw_entitlements, dict) else {}
        self.state = LicenseState(
            authenticated=bool(user), user=user or {}, plan_id=plan_id,
            license_status=license_status, entitlements=entitlements,
            free_unlimited_mode=bool(payload.get("free_unlimited_mode", False)),
            issued_at=str(payload.get("issued_at") or ""),
            expires_at=str(payload.get("expires_at") or ""),
            reason=str(payload.get("message") or ""), verified=True,
            device_id=self.device_id, app_version=self.config.app_version,
        )
        self._last_signed_payload = payload
        return self.state

    def _free_state(self, reason: str, authenticated: bool | None = None) -> LicenseState:
        session = self._session
        if authenticated is None:
            authenticated = bool(session)
        user = session.get("user", {}) if session and isinstance(session.get("user"), dict) else {}
        self.state = LicenseState(
            authenticated=bool(authenticated), user=user, plan_id="free", license_status="free",
            entitlements={}, reason=str(reason or "Using Free mode"), verified=False,
            device_id=self.device_id, app_version=self.config.app_version,
        )
        self._last_signed_payload = None
        return self.state

    def _check_server_license(self, endpoint: str = "license-check") -> LicenseState:
        session = self.get_session()
        if not session:
            return self._free_state("Sign in to activate your account", authenticated=False)
        envelope = self._edge(endpoint, {
            "device_id": self.device_id, "app_version": self.config.app_version,
        }, str(session["access_token"]))
        payload = self._verify_signed_response(envelope)
        user = session.get("user") or {}
        user_id = str(user.get("id") or "")
        if str(payload.get("user_id") or "") != user_id:
            raise SignatureError("The signed license does not match the authenticated account")
        self._remember_offline_license(envelope, payload, user_id)
        state = self._apply_payload(payload, user)
        if state.license_status != "active":
            state.plan_id = "free"
            state.reason = state.reason or f"License status: {state.license_status}"
        return state

    def check_published_build_integrity(self) -> tuple[bool, str]:
        """Require a valid Windows Authenticode signature for frozen EXE releases.

        Source-code development runs are not Authenticode-signed and are permitted
        to run in Free mode. The trusted_builds table remains the server-side release
        allow-list; this local check is an additional signal, not anti-tamper proof.
        """
        if not getattr(sys, "frozen", False) or os.name != "nt":
            return True, "Development/source launch; Authenticode check not applicable"
        executable = str(Path(sys.executable).resolve())
        command = (
            "$s = Get-AuthenticodeSignature -LiteralPath $env:ENGO_EXE_TO_CHECK; "
            "[pscustomobject]@{Status=[string]$s.Status;Subject=[string]$s.SignerCertificate.Subject;Thumbprint=[string]$s.SignerCertificate.Thumbprint} "
            "| ConvertTo-Json -Compress"
        )
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True, timeout=8,
                env={**os.environ, "ENGO_EXE_TO_CHECK": executable}, check=False,
            )
            if completed.returncode != 0:
                return False, "Could not verify the published application's Authenticode signature"
            result = json.loads(completed.stdout.strip() or "{}")
            if str(result.get("Status", "")) != "Valid":
                return False, "The published application does not have a valid Authenticode signature"
            signer_thumbprint = str(result.get("Thumbprint") or "").replace(" ", "").upper()
            if self.config.expected_signer_thumbprint and signer_thumbprint != self.config.expected_signer_thumbprint:
                return False, "The published application was signed by an unrecognized publisher certificate"
            return True, "Authenticode signature is valid"
        except Exception as exc:
            return False, f"Application signature verification failed: {exc}"

    def verify_startup(self, stage_callback: Callable[[str], None] | None = None) -> LicenseState:
        def stage(value: str) -> None:
            if stage_callback:
                try:
                    stage_callback(value)
                except Exception:
                    pass
        stage("integrity")
        integrity_ok, integrity_reason = self.check_published_build_integrity()
        if not integrity_ok:
            return self._free_state(integrity_reason, authenticated=bool(self._session))
        if not self.config.configured:
            return self._free_state("Account service is not configured; continuing in Free mode", authenticated=False)
        try:
            stage("session")
            session = self.get_session()
            if not session:
                return self._free_state("No account is signed in; continuing in Free mode", authenticated=False)
            stage("device")
            activation = self.activate_device(allow_transfer=False)
            if activation.get("status") == "device_conflict":
                return self._free_state("This account is active on another device", authenticated=True)
            stage("subscription")
            stage("entitlements")
            state = self._check_server_license()
            # Fetch the authoritative per-PDF usage counters for offline tag limits.
            # This optional data request must never turn a successful license check into a startup failure.
            try:
                self.account_overview()
            except Exception:
                pass
            return state
        except Exception as exc:
            return self._free_state(str(exc), authenticated=bool(self._session))

    def transfer_device_and_check(self) -> LicenseState:
        """Atomically move the account to this install, then fetch a fresh signed license."""
        self.activate_device(allow_transfer=True)
        return self._check_server_license()

    def heartbeat(self) -> LicenseState:
        """Refresh access and require a fresh signed server approval; never grant offline Premium."""
        integrity_ok, integrity_reason = self.check_published_build_integrity()
        if not integrity_ok:
            return self._free_state(integrity_reason, authenticated=bool(self._session))
        if not self.config.configured:
            return self._free_state("Account service is not configured", authenticated=False)
        try:
            return self._check_server_license("device-heartbeat")
        except Exception as exc:
            return self._free_state(str(exc), authenticated=bool(self._session))

    def consume_feature(self, feature_key: str, amount: int = 1, scope_key: str | None = None) -> dict[str, Any]:
        """Reserve metered access on the server, with a narrow offline tag exception.

        All metered features require a signed server decision except tags and
        tag_units, which may use a protected last-verified entitlement and usage
        snapshot scoped to the current PDF. No other feature has an offline path.
        """
        feature_key = str(feature_key or "").strip()
        if feature_key not in KNOWN_FEATURES:
            return {"allowed": False, "tracked": False, "message": "Unknown feature key"}
        amount = max(1, min(int(amount or 1), 1000))
        scope_key = str(scope_key or "").strip()[:128]
        if not self.config.configured:
            self._free_state("Account service is not configured; sign in and verify your account", authenticated=False)
            return {"allowed": False, "tracked": False,
                    "message": "Account service is not configured. This feature is locked until account verification is available."}
        try:
            session = self.get_session()
            if not session or not session.get("access_token"):
                self._free_state("Sign in is required to use this feature", authenticated=False)
                return {"allowed": False, "tracked": False,
                        "message": "Sign in with Google to use this feature. Guest access is disabled."}

            if feature_key in self.OFFLINE_FILE_FEATURES:
                sync_result = self._sync_pending_offline_usage(feature_key, scope_key, session)
                if sync_result is not None:
                    return sync_result
            pending_offline = 0
            batch_amount = amount
            response = self._edge("usage-consume", {
                "device_id": self.device_id, "app_version": self.config.app_version,
                "feature_key": feature_key, "amount": batch_amount,
                "scope_key": scope_key,
            }, str(session["access_token"]))
            envelope = response.get("license")
            if not isinstance(envelope, dict):
                raise SignatureError("Usage response did not include a signed license")
            payload = self._verify_signed_response(envelope)
            expected_user_id = str((session.get("user") or {}).get("id") or "")
            if not expected_user_id or str(payload.get("user_id") or "") != expected_user_id:
                raise SignatureError("The signed usage response does not match the authenticated account")

            user = session.get("user") or {}
            self._remember_offline_license(envelope, payload, str(user.get("id") or ""))
            state = self._apply_payload(payload, user)
            license_status = str(payload.get("license_status") or "")
            entitlements = payload.get("entitlements") if isinstance(payload.get("entitlements"), dict) else {}
            entitlement = entitlements.get(feature_key) if isinstance(entitlements, dict) else None
            enabled = isinstance(entitlement, dict) and bool(entitlement.get("enabled"))
            free_unlimited = bool(payload.get("free_unlimited_mode", False))
            feature_is_unlimited = isinstance(entitlement, dict) and entitlement.get("limit") is None
            server_allowed = response.get("allowed") is True

            # An unsupported release may keep enabled unlimited Free features,
            # but any feature with a finite Free limit is blocked until updating.
            if (license_status == "untrusted_build" and not free_unlimited
                    and enabled and isinstance(entitlement, dict) and entitlement.get("limit") is not None):
                return {"allowed": False, "tracked": False, "message": "update_required"}

            if license_status != "active" and not (
                    license_status == "untrusted_build" and (free_unlimited or (enabled and feature_is_unlimited))
            ):
                self._free_state(str(payload.get("message") or license_status or "License unavailable"), authenticated=True)
                return {"allowed": False, "tracked": False,
                        "message": "The account or this device is not authorized. Feature access is blocked."}
            if not enabled:
                self._record_online_file_usage(
                    feature_key, scope_key, response, pending_offline, amount, batch_amount, False,
                )
                return {"allowed": False, "tracked": True,
                        "message": "This feature is not enabled for the current plan",
                        "used": response.get("used"), "limit": response.get("limit")}
            if not server_allowed:
                self._record_online_file_usage(
                    feature_key, scope_key, response, pending_offline, amount, batch_amount, False,
                )
                return {"allowed": False, "tracked": True,
                        "message": str(response.get("message") or "The usage limit has been reached"),
                        "used": response.get("used"), "limit": response.get("limit")}

            self._record_online_file_usage(
                feature_key, scope_key, response, pending_offline, amount, batch_amount, True,
            )
            # Only a signed license plus an affirmative server reservation grants access.
            reservation_id = (
                str(response.get("reservation_id") or "").strip()
                if feature_key == "text_chat" else ""
            )
            if feature_key == "text_chat" and response.get("used") is not None and not reservation_id:
                # A metered chat must carry its one-time settlement token.
                # Never start a provider request if the reservation cannot be refunded.
                return {
                    "allowed": False, "tracked": False,
                    "message": "The server did not return a text-chat usage reservation. Please retry.",
                }
            return {
                "allowed": True, "tracked": True,
                "message": str(response.get("message") or ""),
                "used": response.get("used"), "limit": response.get("limit"),
                "reservation_id": reservation_id or None,
            }
        except OfflineError:
            self._free_state("Device is offline", authenticated=bool(self._session))
            if feature_key in self.OFFLINE_FILE_FEATURES:
                offline_result = self._consume_offline_file_feature(feature_key, amount, scope_key)
                if offline_result is not None:
                    return offline_result
            return {"allowed": False, "tracked": False, "message": "offline_feature_unavailable"}
        except Exception as exc:
            self._free_state(str(exc), authenticated=bool(self._session))
            return {"allowed": False, "tracked": False,
                    "message": f"Feature access could not be verified: {exc}"}

    def settle_text_chat_usage(self, reservation_id: str, outcome: str) -> dict[str, Any]:
        """Commit a successful text-chat reservation or refund a failed/cancelled one.

        The server binds the opaque reservation to the authenticated user and
        device, then makes settlement idempotent so a request can never be
        refunded more than once.
        """
        reservation_id = str(reservation_id or "").strip()
        outcome = str(outcome or "").strip().lower()
        if not reservation_id:
            raise LicenseError("A text-chat reservation ID is required")
        if outcome not in {"success", "failure"}:
            raise LicenseError("Invalid text-chat settlement outcome")
        response = self._authenticated_edge("usage-settle", {
            "device_id": self.device_id,
            "reservation_id": reservation_id,
            "outcome": outcome,
        })
        if response.get("settled") is not True:
            raise LicenseError("The text-chat usage reservation could not be settled")
        return response

    def _authenticated_edge(self, name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call an account Edge Function with a current, non-empty user JWT.

        A legacy/corrupt saved session can contain an empty or whitespace-only access
        token even though the UI still has an authenticated LicenseState. In that
        case (or when the server explicitly reports a missing/expired bearer token),
        refresh once from the securely stored refresh token and retry. Never fall
        back to the publishable key as Authorization and never bypass authentication.
        """
        session = self.get_session(refresh=True)
        if not session:
            raise LicenseError("Sign in before accessing account information")

        access_token = str(session.get("access_token") or "").strip()
        if not access_token:
            session = self._refresh_session(session)
            access_token = str(session.get("access_token") or "").strip()
        if not access_token:
            raise LicenseError("The saved account session has no access token. Sign in again.")

        try:
            return self._edge(name, body or {}, access_token)
        except NetworkError as exc:
            message = str(exc).lower()
            auth_failure = (
                "authentication required" in message
                or "invalid or expired account session" in message
                or "jwt expired" in message
                or "invalid jwt" in message
            )
            if not auth_failure:
                raise
            refreshed = self._refresh_session(session)
            fresh_token = str(refreshed.get("access_token") or "").strip()
            if not fresh_token:
                raise LicenseError("Could not refresh the account session. Sign in again.") from exc
            try:
                return self._edge(name, body or {}, fresh_token)
            except NetworkError as retry_exc:
                retry_message = str(retry_exc).lower()
                if ("authentication required" in retry_message
                        or "invalid or expired account session" in retry_message
                        or "jwt expired" in retry_message
                        or "invalid jwt" in retry_message):
                    raise LicenseError(
                        "The renewed sign-in session was rejected by the account server. "
                        f"Server response: {retry_exc}"
                    ) from retry_exc
                raise

    def account_overview(self) -> dict[str, Any]:
        session = self.get_session(refresh=True)
        if not session:
            return {"authenticated": False, "devices": []}
        result = self._authenticated_edge("account-overview", {})
        self._cache_offline_usage_snapshot(
            result.get("tag_usage"), str((session.get("user") or {}).get("id") or ""),
        )
        return result

    def request_subscription_payment(self, billing_period: str) -> dict[str, Any]:
        """Create a pending manual-QR subscription request using server-side pricing."""
        billing_period = str(billing_period or "").strip().lower()
        if billing_period not in {"monthly", "quarterly", "semiannual", "annual"}:
            raise LicenseError("Invalid subscription period")
        return self._authenticated_edge("subscription-request", {"billing_period": billing_period})


__all__ = [
    "APP_VERSION_FALLBACK", "KNOWN_FEATURES", "LicenseConfig", "LicenseError",
    "ConfigurationError", "SecureStorageError", "NetworkError", "OfflineError", "SignatureError",
    "LicenseState", "SecureStore", "OfflineFeatureCacheStore", "LicenseService", "canonical_json",
    "is_expected_free_startup",
]
