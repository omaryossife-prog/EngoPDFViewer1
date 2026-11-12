import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "set_google_desktop_secret.py"
SPEC = importlib.util.spec_from_file_location("engo_google_secret_setup", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

def test_secret_setup_writes_value_without_printing_it(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "engo_license.json"
    config_path.write_text(json.dumps({"google_desktop_client_id": "desktop.apps.googleusercontent.com", "google_desktop_client_secret": ""}), encoding="utf-8")
    values = iter(["GOCSPX-desktop-secret-test", "GOCSPX-desktop-secret-test"])
    monkeypatch.setattr(MODULE.getpass, "getpass", lambda *_args, **_kwargs: next(values))
    monkeypatch.setattr(MODULE.sys, "argv", [str(MODULE_PATH), str(config_path)])
    assert MODULE.main() == 0
    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert written["google_desktop_client_secret"] == ""
    secret_path = tmp_path / ".secrets" / "engo-google-desktop-client-secret.txt"
    assert secret_path.read_text(encoding="utf-8").strip() == "GOCSPX-desktop-secret-test"
    output = capsys.readouterr().out
    assert "saved to the ignored .secrets folder" in output
    assert "GOCSPX-desktop-secret-test" not in output

def test_secret_setup_rejects_mismatched_confirmation_without_saving(tmp_path, monkeypatch):
    config_path = tmp_path / "engo_license.json"
    config_path.write_text(json.dumps({"google_desktop_client_id": "desktop.apps.googleusercontent.com", "google_desktop_client_secret": ""}), encoding="utf-8")
    values = iter(["first", "second"])
    monkeypatch.setattr(MODULE.getpass, "getpass", lambda *_args, **_kwargs: next(values))
    monkeypatch.setattr(MODULE.sys, "argv", [str(MODULE_PATH), str(config_path)])
    assert MODULE.main() == 1
    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert written["google_desktop_client_secret"] == ""
    assert not (tmp_path / ".secrets" / "engo-google-desktop-client-secret.txt").exists()
