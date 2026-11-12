#!/usr/bin/env python3
"""Generate an Engo Ed25519 production signing keypair locally.

The private key is written to .secrets and never printed. Keep that directory
out of source control and back it up using an encrypted secret store.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=".secrets", help="Private output directory (default: .secrets)")
    parser.add_argument("--force", action="store_true", help="Replace existing key files")
    parser.add_argument("--rotate-existing-public-key", action="store_true",
                        help="Explicitly rotate a public key already present in the app config")
    parser.add_argument("--config", default="engo_license.json", help="Public app config to update (default: engo_license.json)")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    existing_public_key = ""
    if config_path.is_file():
        try:
            current_config = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(current_config, dict):
                existing_public_key = str(current_config.get("license_public_key_b64") or "").strip()
        except (OSError, json.JSONDecodeError):
            parser.error(f"Could not read the public app config: {config_path}")
    if existing_public_key and not args.rotate_existing_public_key:
        parser.error(
            "A public signing key already exists in the app config. Restore the matching private keypair; "
            "only pass --rotate-existing-public-key when intentionally rotating the production key."
        )

    out = Path(args.out_dir).resolve()
    private_path = out / "engo-license-signing-private.pkcs8.b64"
    public_path = out / "engo-license-signing-public.raw.b64"
    if not args.force and not args.rotate_existing_public_key and (private_path.exists() or public_path.exists()):
        parser.error(f"Key files already exist in {out}; do not replace them blindly")
    if args.rotate_existing_public_key:
        args.force = True

    out.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        # Remove inherited directory ACLs and grant full control only to the
        # current Windows identity. New files inherit this restricted ACL.
        identity = subprocess.run(["whoami"], capture_output=True, text=True, check=True).stdout.strip()
        secured = subprocess.run(
            ["icacls", str(out), "/inheritance:r", "/grant:r", f"{identity}:(OI)(CI)F"],
            capture_output=True, text=True, check=False,
        )
        if secured.returncode != 0:
            raise RuntimeError("Could not restrict the signing-key directory ACL: " + secured.stderr.strip())
    else:
        os.chmod(out, 0o700)

    private_key = Ed25519PrivateKey.generate()
    private_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_b64 = base64.b64encode(private_der).decode("ascii")
    public_b64 = base64.b64encode(public_raw).decode("ascii")

    private_path.write_text(private_b64 + "\n", encoding="ascii")
    public_path.write_text(public_b64 + "\n", encoding="ascii")
    if os.name != "nt":
        for path in (private_path, public_path):
            os.chmod(path, 0o600)

    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("app config must be a JSON object")
            config["license_public_key_b64"] = public_b64
            temp_config = config_path.with_suffix(config_path.suffix + ".tmp")
            temp_config.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temp_config, config_path)
            if os.name != "nt":
                os.chmod(config_path, 0o600)
            print(f"Updated public verification key in: {config_path}")
        except Exception as exc:
            raise RuntimeError(f"Could not update public app config {config_path}: {exc}") from exc
    else:
        print(f"No app config found at {config_path}; copy the public key below into license_public_key_b64 after generation.")

    print("Ed25519 keypair generated.")
    print(f"PRIVATE key: stored locally at {private_path} (never copy to the desktop app or EXE)")
    print(f"PUBLIC key (safe to put in engo_license.json -> license_public_key_b64):\n{public_b64}")
    print("Keep .secrets/ backed up in an encrypted secret manager and never commit it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
