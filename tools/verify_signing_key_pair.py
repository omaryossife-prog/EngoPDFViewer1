#!/usr/bin/env python3
"""Verify that the local Ed25519 signing key matches the app's public key.

This check is intended to run immediately before uploading the private key to
Supabase. It never prints or returns key material.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def verify_pair(project_root: Path) -> None:
    secret_path = project_root / ".secrets" / "engo-license-signing-private.pkcs8.b64"
    config_path = project_root / "engo_license.json"
    if not config_path.is_file():
        config_path = project_root / "engo_license.example.json"
    if not secret_path.is_file() or not config_path.is_file():
        raise ValueError("Signing key or public app config is missing")

    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Public app config is invalid")
    expected_public = base64.b64decode(
        str(config.get("license_public_key_b64") or "").strip(), validate=True
    )
    if len(expected_public) != 32:
        raise ValueError("The app config does not contain a valid Ed25519 public key")

    private_der = base64.b64decode(secret_path.read_text(encoding="ascii").strip(), validate=True)
    private_key = serialization.load_der_private_key(private_der, password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("The local private key is not Ed25519")
    actual_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    if actual_public != expected_public:
        raise ValueError("The local private key does not match the public key in engo_license.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    try:
        verify_pair(Path(args.project_root).expanduser().resolve())
    except Exception:
        print("Ed25519 keypair validation failed. No signing key should be uploaded.")
        return 1
    print("Ed25519 keypair matches the public key configured for this Engo release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
