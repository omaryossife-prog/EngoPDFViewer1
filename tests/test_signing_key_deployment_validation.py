import base64
import importlib.util
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "verify_signing_key_pair.py"
SPEC = importlib.util.spec_from_file_location("engo_signing_pair_validator", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write_pair(root: Path):
    secret_dir = root / ".secrets"
    secret_dir.mkdir(parents=True)
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
    (secret_dir / "engo-license-signing-private.pkcs8.b64").write_text(
        base64.b64encode(private_der).decode("ascii"), encoding="ascii"
    )
    config = {"license_public_key_b64": base64.b64encode(public_raw).decode("ascii")}
    (root / "engo_license.json").write_text(json.dumps(config), encoding="utf-8")
    return config, private_key


def test_deployment_validator_accepts_matching_private_and_release_public_key(tmp_path):
    _write_pair(tmp_path)
    MODULE.verify_pair(tmp_path)


def test_deployment_validator_rejects_mismatched_release_public_key(tmp_path):
    config, _ = _write_pair(tmp_path)
    other_key = Ed25519PrivateKey.generate()
    other_public = other_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    config["license_public_key_b64"] = base64.b64encode(other_public).decode("ascii")
    (tmp_path / "engo_license.json").write_text(json.dumps(config), encoding="utf-8")
    try:
        MODULE.verify_pair(tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("a mismatched Ed25519 keypair must not pass deployment validation")
