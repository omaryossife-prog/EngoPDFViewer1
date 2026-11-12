import base64
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "generate_license_signing_keys.py"
SPEC = importlib.util.spec_from_file_location("engo_signing_key_generator", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_generator_refuses_implicit_rotation_when_public_key_is_already_shipped(tmp_path, monkeypatch):
    config_path = tmp_path / "engo_license.json"
    config_path.write_text(json.dumps({"license_public_key_b64": "existing-public-key"}), encoding="utf-8")
    output_dir = tmp_path / ".secrets"
    monkeypatch.setattr(sys, "argv", [str(MODULE_PATH), "--out-dir", str(output_dir), "--config", str(config_path)])

    with pytest.raises(SystemExit) as exc:
        MODULE.main()

    assert exc.value.code == 2
    assert not output_dir.exists()
    assert json.loads(config_path.read_text(encoding="utf-8"))["license_public_key_b64"] == "existing-public-key"


def test_generator_rotates_only_with_explicit_flag_and_keeps_keypair_matching(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "engo_license.json"
    config_path.write_text(json.dumps({"license_public_key_b64": "old-public-key"}), encoding="utf-8")
    output_dir = tmp_path / ".secrets"
    monkeypatch.setattr(sys, "argv", [
        str(MODULE_PATH), "--out-dir", str(output_dir), "--config", str(config_path),
        "--rotate-existing-public-key",
    ])

    assert MODULE.main() == 0
    capsys.readouterr()
    updated_config = json.loads(config_path.read_text(encoding="utf-8"))
    public_b64 = updated_config["license_public_key_b64"]
    private_b64 = (output_dir / "engo-license-signing-private.pkcs8.b64").read_text(encoding="ascii").strip()
    private_der = base64.b64decode(private_b64, validate=True)
    private_key = serialization.load_der_private_key(private_der, password=None)
    actual_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    assert base64.b64decode(public_b64, validate=True) == actual_public
    assert public_b64 != "old-public-key"
