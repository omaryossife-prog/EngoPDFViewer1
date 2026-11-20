"""Versioned Engo Terms & Conditions loading and acceptance records."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TERMS_VERSION = "1.0.0"
_LOCAL_VERSION_KEY = "legal/terms_accepted_version"
_LOCAL_SHA256_KEY = "legal/terms_accepted_sha256"
_LOCAL_ACCEPTED_AT_KEY = "legal/terms_accepted_at_utc"
_LOCAL_APP_VERSION_KEY = "legal/terms_accepted_app_version"
_LOCAL_LANGUAGE_KEY = "legal/terms_accepted_language"
_INSTALLER_REGISTRY_KEY = r"Software\Engo\EngoPDFViewerAIStudyAgent"


def load_terms_documents(directory: str | Path) -> dict[str, str]:
    """Load the Arabic and English source agreements from the bundled LEGAL folder."""
    root = Path(directory)
    documents: dict[str, str] = {}
    for language, filename in (
        ("ar", "TERMS_AND_CONDITIONS_AR.md"),
        ("en", "TERMS_AND_CONDITIONS_EN.md"),
    ):
        path = root / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required Engo terms document is missing: {path}")
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Engo terms document is empty: {path}")
        documents[language] = content
    return documents


def terms_content_sha256(documents: dict[str, str]) -> str:
    """Return one stable digest for the Arabic and English agreement contents."""
    if not isinstance(documents, dict) or not documents.get("ar") or not documents.get("en"):
        raise ValueError("Both Arabic and English terms documents are required.")
    arabic = str(documents["ar"]).replace("\r\n", "\n").replace("\r", "\n").strip()
    english = str(documents["en"]).replace("\r\n", "\n").replace("\r", "\n").strip()
    payload = b"ar\0" + arabic.encode("utf-8") + b"\0en\0" + english.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_terms_acceptance_current(settings: Any, terms_version: str, content_sha256: str) -> bool:
    try:
        return (
            str(settings.value(_LOCAL_VERSION_KEY, "")) == str(terms_version)
            and str(settings.value(_LOCAL_SHA256_KEY, "")) == str(content_sha256)
        )
    except Exception:
        return False


def save_terms_acceptance(
    settings: Any, *, terms_version: str, content_sha256: str,
    app_version: str, language: str,
) -> dict[str, str]:
    """Persist the accepted agreement version, digest, date, app version, and language."""
    accepted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    record = {
        _LOCAL_VERSION_KEY: str(terms_version),
        _LOCAL_SHA256_KEY: str(content_sha256),
        _LOCAL_ACCEPTED_AT_KEY: accepted_at,
        _LOCAL_APP_VERSION_KEY: str(app_version),
        _LOCAL_LANGUAGE_KEY: "ar" if str(language).lower().startswith("ar") else "en",
    }
    for key, value in record.items():
        settings.setValue(key, value)
    settings.sync()
    if (
        str(settings.value(_LOCAL_VERSION_KEY, "")) != str(terms_version)
        or str(settings.value(_LOCAL_SHA256_KEY, "")) != str(content_sha256)
    ):
        raise OSError("Engo could not save the Terms & Conditions acceptance record.")
    return record


def is_installer_terms_acceptance_current(terms_version: str, content_sha256: str) -> bool:
    """Check the consent stored by the official Windows installer."""
    if os.name != "nt":
        return False
    try:
        import winreg
        access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _INSTALLER_REGISTRY_KEY, 0, access) as key:
            saved_version, _ = winreg.QueryValueEx(key, "TermsAcceptedVersion")
            saved_digest, _ = winreg.QueryValueEx(key, "TermsAcceptedSha256")
        return str(saved_version) == str(terms_version) and str(saved_digest) == str(content_sha256)
    except (ImportError, OSError, ValueError, TypeError):
        return False
