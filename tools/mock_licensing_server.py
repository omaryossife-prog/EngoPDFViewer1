"""Local-only mock Auth + Engo Edge Functions for development and UI tests.

This intentionally uses a deterministic, public test signing key. NEVER reuse it
for production and never expose this server beyond loopback.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

USER_ID = "00000000-0000-4000-8000-000000000001"
ACCESS_TOKEN = "engo-local-mock-access-token"
REFRESH_TOKEN = "engo-local-mock-refresh-token"
APP_VERSION_DEFAULT = "2.3.6"
FEATURES = (
    "pdf_merge", "page_themes", "app_themes", "smart_theme", "text_chat",
    "voice_chat", "tags", "tag_units", "translations", "ai_search",
)
# Test-only seed. The matching public key is stable so the desktop config stays put.
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"ENGO MOCK ONLY - NEVER USE IN PRODUCTION").digest())
PUBLIC_KEY_B64 = base64.b64encode(PRIVATE_KEY.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw
)).decode("ascii")


class MockState:
    def __init__(self, plan: str = "free", free_limit: int = 0):
        self.plan = "premium" if plan.lower() == "premium" else "free"
        self.free_limit = max(0, int(free_limit))  # 0 = unlimited in local mock
        self.active_device: str | None = None
        self.devices: dict[str, dict[str, Any]] = {}
        self.usage: dict[tuple[str, str], int] = {}
        self.pkce_challenges: dict[str, str] = {}
        self.lock = threading.RLock()

    def license_payload(self, device_id: str, app_version: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        active = self.active_device == device_id and device_id in self.devices
        plan = self.plan if active else "free"
        status = "active" if active else "device_not_active"
        if active:
            self.devices[device_id]["last_seen"] = now.isoformat().replace("+00:00", "Z")
        entitlements = {
            key: {"enabled": True, "limit": None if plan == "premium" or not self.free_limit else self.free_limit,
                  "reset_period": "daily" if key in ("text_chat", "voice_chat", "translations", "ai_search") else "lifetime",
                  "plan_id": plan}
            for key in FEATURES
        }
        return {
            "user_id": USER_ID,
            "device_id": device_id,
            "plan_id": plan,
            "entitlements": entitlements,
            "expires_at": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
            "issued_at": now.isoformat().replace("+00:00", "Z"),
            "app_version": app_version,
            "license_status": status,
            "message": "" if active else "Device is not active in the mock server",
        }

    def signed(self, device_id: str, app_version: str) -> dict[str, Any]:
        payload = self.license_payload(device_id, app_version)
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        signature = base64.b64encode(PRIVATE_KEY.sign(canonical)).decode("ascii")
        return {"payload": payload, "signature": signature}


class MockHandler(BaseHTTPRequestHandler):
    server_version = "EngoMockLicensing/1.0"

    @property
    def state(self) -> MockState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, _format, *args):
        print("[mock] " + (_format % args))

    def _json(self, status: int, value: Any, headers: dict[str, str] | None = None):
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for key, val in (headers or {}).items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        value = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        if not isinstance(value, dict):
            raise ValueError("JSON object expected")
        return value

    def _authenticated(self) -> bool:
        authorization = self.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        return token == ACCESS_TOKEN

    def _auth_required(self) -> bool:
        if self._authenticated():
            return True
        self._json(401, {"error": "Invalid mock session"})
        return False

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "authorization, apikey, content-type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/auth/v1/authorize":
            redirect_to = (query.get("redirect_to") or [""])[0]
            challenge = (query.get("code_challenge") or [""])[0]
            method = (query.get("code_challenge_method") or [""])[0]
            target = urllib.parse.urlparse(redirect_to)
            target_state = (urllib.parse.parse_qs(target.query).get("state") or [""])[0]
            if target.scheme != "http" or target.hostname not in ("127.0.0.1", "localhost") or not target.port or not target_state or method.lower() != "s256":
                self._json(400, {"error": "Invalid mock PKCE authorization request"})
                return
            with self.state.lock:
                self.state.pkce_challenges["mock-code"] = challenge
            # Supabase's social-auth callback appends its PKCE code to the original
            # redirect_to, preserving the app's own callback nonce.
            callback_query = urllib.parse.parse_qsl(target.query, keep_blank_values=True)
            callback_query.append(("code", "mock-code"))
            callback = urllib.parse.urlunparse(target._replace(query=urllib.parse.urlencode(callback_query)))
            self.send_response(302)
            self.send_header("Location", callback)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path == "/auth/v1/user":
            if not self._auth_required():
                return
            self._json(200, self._user())
            return
        self._json(404, {"error": "Unknown mock endpoint"})

    def _user(self):
        return {
            "id": USER_ID,
            "email": "student@engo.local",
            "user_metadata": {"full_name": "Engo Local Test User", "name": "Engo Local Test User"},
        }

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        try:
            body = self._body()
        except Exception as exc:
            self._json(400, {"error": f"Invalid JSON: {exc}"})
            return

        if parsed.path == "/auth/v1/token":
            mode = (urllib.parse.parse_qs(parsed.query).get("grant_type") or [""])[0]
            if mode == "pkce":
                verifier = str(body.get("code_verifier") or "")
                expected = self.state.pkce_challenges.pop("mock-code", "")
                actual = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
                if body.get("auth_code") != "mock-code" or not expected or actual != expected:
                    self._json(400, {"error": "Mock PKCE verifier mismatch"})
                    return
            elif mode == "refresh_token":
                if body.get("refresh_token") != REFRESH_TOKEN:
                    self._json(400, {"error": "Invalid mock refresh token"})
                    return
            else:
                self._json(400, {"error": "Unsupported mock grant type"})
                return
            self._json(200, {
                "access_token": ACCESS_TOKEN, "refresh_token": REFRESH_TOKEN,
                "token_type": "bearer", "expires_in": 3600,
                "expires_at": int(time.time()) + 3600, "user": self._user(),
            })
            return

        if parsed.path == "/auth/v1/logout":
            self._json(200, {})
            return

        if not self._auth_required():
            return
        try:
            if parsed.path in ("/functions/v1/device-activate", "/functions/v1/device-transfer"):
                device_id = str(body.get("device_id") or "")
                app_version = str(body.get("app_version") or APP_VERSION_DEFAULT)
                name = str(body.get("device_name") or "Windows PC")
                if not device_id:
                    self._json(400, {"error": "Missing device_id"})
                    return
                transfer = parsed.path.endswith("device-transfer")
                with self.state.lock:
                    if self.state.active_device and self.state.active_device != device_id and not transfer:
                        self._json(200, {"status": "device_conflict", "active_device": self.state.devices.get(self.state.active_device, {})})
                        return
                    self.state.active_device = device_id
                    self.state.devices[device_id] = {
                        "device_id": device_id, "device_name": name, "status": "active",
                        "activated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "last_seen": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "app_version": app_version,
                    }
                self._json(200, {"status": "transferred" if transfer else "active", "device_id": device_id})
                return

            if parsed.path in ("/functions/v1/license-check", "/functions/v1/device-heartbeat"):
                device_id = str(body.get("device_id") or "")
                app_version = str(body.get("app_version") or APP_VERSION_DEFAULT)
                self._json(200, self.state.signed(device_id, app_version))
                return

            if parsed.path == "/functions/v1/usage-consume":
                device_id = str(body.get("device_id") or "")
                feature = str(body.get("feature_key") or "")
                app_version = str(body.get("app_version") or APP_VERSION_DEFAULT)
                amount = int(body.get("amount") or 1)
                with self.state.lock:
                    active = self.state.active_device == device_id
                    if not active:
                        self._json(200, {"allowed": False, "message": "Device is not active", "license": self.state.signed(device_id, app_version)})
                        return
                    # Feature quotas are account-scoped, not installation-scoped.
                    counter_key = ("account", feature)
                    used = self.state.usage.get(counter_key, 0)
                    limit = self.state.free_limit if self.state.plan == "free" else 0
                    allowed = limit <= 0 or used + amount <= limit
                    if allowed:
                        used += amount
                        self.state.usage[counter_key] = used
                    self._json(200, {
                        "allowed": allowed, "used": used,
                        "limit": limit if limit > 0 and self.state.plan == "free" else None,
                        "message": "" if allowed else "Usage limit reached",
                        "license": self.state.signed(device_id, app_version),
                    })
                return

            if parsed.path == "/functions/v1/account-overview":
                with self.state.lock:
                    devices = list(self.state.devices.values())
                    subscription = None
                    if self.state.plan == "premium":
                        now = datetime.now(timezone.utc)
                        subscription = {
                            "plan_id": "premium", "status": "active",
                            "starts_at": (now - timedelta(days=30)).isoformat().replace("+00:00", "Z"),
                            "ends_at": (now + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
                        }
                self._json(200, {
                    "profile": {"display_name": "Engo Local Test User", "avatar_url": None},
                    "devices": devices, "subscription": subscription,
                    "email": "student@engo.local",
                })
                return
            self._json(404, {"error": "Unknown mock endpoint"})
        except Exception as exc:
            self._json(500, {"error": str(exc)})


def create_server(host: str = "127.0.0.1", port: int = 8787, plan: str = "free", free_limit: int = 0):
    server = ThreadingHTTPServer((host, port), MockHandler)
    server.state = MockState(plan=plan, free_limit=free_limit)  # type: ignore[attr-defined]
    return server


def main():
    parser = argparse.ArgumentParser(description="Run Engo's loopback-only mock licensing service")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback only; do not expose this service")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--plan", choices=("free", "premium"), default="free")
    parser.add_argument("--free-limit", type=int, default=0, help="Per-feature lifetime cap for mock Free; 0 disables the cap")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        parser.error("The mock service must bind to loopback only")
    server = create_server(args.host, args.port, args.plan, args.free_limit)
    print("Engo mock licensing server: http://%s:%s" % server.server_address)
    print("Plan: %s | mock Free cap: %s" % (args.plan, args.free_limit or "unlimited"))
    print("MOCK PUBLIC KEY (base64):", PUBLIC_KEY_B64)
    print("OAuth is simulated with PKCE; use this server only on your own computer.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping mock licensing server…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
