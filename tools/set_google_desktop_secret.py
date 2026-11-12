#!/usr/bin/env python3
"""Set the local Google Desktop OAuth client secret without echoing it to the console."""
from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
from pathlib import Path


def resolve_config_path() -> Path:
    # Prefer the project folder when running from source; for a packaged app,
    # set --config to the directory containing the EXE's engo_license.json.
    return Path(__file__).resolve().parents[1] / "engo_license.json"


def main() -> int:
    config_path = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else resolve_config_path()
    if not config_path.is_file():
        print(f"Config file not found: {config_path}")
        print("Pass the full path to engo_license.json as the first argument.")
        return 2

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read configuration: {exc}")
        return 2
    if not isinstance(config, dict):
        print("Invalid engo_license.json format.")
        return 2
    if not str(config.get("google_desktop_client_id", "")).strip():
        print("google_desktop_client_id is empty. Add the Desktop Client ID first.")
        return 2

    print("Paste the client_secret from the 'Engo Windows Desktop' OAuth JSON.")
    print("Do NOT use the Web application's secret. Input is hidden.")
    first = getpass.getpass("Desktop client secret: ").strip()
    if not first:
        print("No value entered; configuration was not changed.")
        return 1
    second = getpass.getpass("Confirm desktop client secret: ").strip()
    if first != second:
        print("The two values do not match; configuration was not changed.")
        return 1

    secret_dir = config_path.parent / ".secrets"
    secret_path = secret_dir / "engo-google-desktop-client-secret.txt"
    config["google_desktop_client_secret"] = ""
    try:
        secret_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            identity = subprocess.run(["whoami"], capture_output=True, text=True, check=True).stdout.strip()
            secured = subprocess.run(
                ["icacls", str(secret_dir), "/inheritance:r", "/grant:r", f"{identity}:(OI)(CI)F"],
                capture_output=True, text=True, check=False,
            )
            if secured.returncode != 0:
                raise OSError("Could not restrict .secrets directory permissions")
        else:
            os.chmod(secret_dir, 0o700)

        secret_path.write_text(first + "\n", encoding="utf-8")
        if os.name == "nt":
            secured_file = subprocess.run(
                ["icacls", str(secret_path), "/inheritance:r", "/grant:r", f"{identity}:F"],
                capture_output=True, text=True, check=False,
            )
            if secured_file.returncode != 0:
                secret_path.unlink(missing_ok=True)
                raise OSError("Could not restrict Google secret file permissions")
        else:
            os.chmod(secret_path, 0o600)
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Could not save the local owner secret securely: {exc}")
        return 2

    print("Desktop OAuth client secret saved to the ignored .secrets folder. The value was not displayed.")
    print("The deployment script uploads it to Supabase Edge Function secrets; it is not embedded in Engo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
