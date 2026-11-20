from pathlib import Path

import pytest

from engo_licensing.terms import (
    TERMS_VERSION,
    is_terms_acceptance_current,
    load_terms_documents,
    save_terms_acceptance,
    terms_content_sha256,
)


class MemorySettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=""):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        pass


def test_bilingual_terms_are_present_and_substantive():
    docs = load_terms_documents(Path(__file__).resolve().parents[1] / "LEGAL")
    assert "اتفاقية الاستخدام والشروط والأحكام" in docs["ar"]
    assert "Terms of Use and End User License Agreement" in docs["en"]
    assert "الخصوصية ومعالجة البيانات" in docs["ar"]
    assert "Privacy and data processing" in docs["en"]


def test_digest_changes_when_document_text_changes():
    docs = {"ar": "الشروط", "en": "Terms"}
    digest = terms_content_sha256(docs)
    assert digest != terms_content_sha256({"ar": "شروط جديدة", "en": "Terms"})
    assert digest != terms_content_sha256({"ar": "الشروط", "en": "New terms"})


def test_acceptance_is_bound_to_exact_version_and_digest():
    settings = MemorySettings()
    digest = terms_content_sha256({"ar": "الشروط", "en": "Terms"})
    record = save_terms_acceptance(
        settings, terms_version=TERMS_VERSION, content_sha256=digest,
        app_version="2.3.6", language="ar",
    )
    assert record["legal/terms_accepted_language"] == "ar"
    assert record["legal/terms_accepted_at_utc"].endswith("Z")
    assert is_terms_acceptance_current(settings, TERMS_VERSION, digest)
    assert not is_terms_acceptance_current(settings, "2.0.0", digest)
    assert not is_terms_acceptance_current(settings, TERMS_VERSION, "0" * 64)


def test_failed_persistence_does_not_create_a_valid_acceptance():
    class BrokenSettings(MemorySettings):
        def sync(self):
            self.values.clear()

    with pytest.raises(OSError):
        save_terms_acceptance(
            BrokenSettings(), terms_version=TERMS_VERSION,
            content_sha256="a" * 64, app_version="2.3.6", language="en",
        )
