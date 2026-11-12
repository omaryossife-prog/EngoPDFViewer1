from .core import LicenseConfig, LicenseService, LicenseState, is_expected_free_startup

# Keep core licensing and tests importable when optional desktop UI dependencies
# are not installed in a build or CI environment.
try:
    from .ui import AccountDialog, EngoSplashScreen, ServiceActionWorker, StartupVerifierWorker
except ImportError:  # pragma: no cover - PyQt6 is a runtime dependency of the desktop app
    AccountDialog = EngoSplashScreen = ServiceActionWorker = StartupVerifierWorker = None

__all__ = ["LicenseConfig", "LicenseService", "LicenseState", "AccountDialog",
           "EngoSplashScreen", "ServiceActionWorker", "StartupVerifierWorker",
           "is_expected_free_startup"]
