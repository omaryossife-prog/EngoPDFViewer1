# Architecture

## Project responsibilities

### Engo.Domain
Contains business concepts and invariants such as document identity and document kind. It must not reference WinUI, Windows App SDK, Supabase, Gemini, or storage implementations.

### Engo.Application
Contains use cases and abstractions (ports) consumed by the UI. It coordinates domain operations and must not depend on WinUI or infrastructure implementations.

### Engo.Infrastructure
Implements persistence and adapters for external systems. Adapters include PDF engines and a read-only Office Open XML preview reader; planned adapters include AI HTTP clients, Supabase, secure credential storage, and additional Windows-specific services.

### Engo.App
Contains WinUI 3 views, view models, window lifetime, navigation, dialogs, and dependency composition. UI code calls Application contracts rather than reaching into databases or external APIs directly.

## Dependency direction

```text
Engo.App ───────────────┐
                       v
Engo.Infrastructure -> Engo.Application -> Engo.Domain
        (implements Application ports)
```

The Domain project has no project references. Infrastructure implements interfaces declared by Application. The UI is not the place to store licensing rules, AI provider logic, PDF parsing, or persistence behavior.

## Cross-cutting requirements

- Use asynchronous I/O and cancellation for file, network, and database operations.
- Keep expensive PDF rendering, OCR, AI, and Office package parsing/conversion work off the UI thread.
- Treat DOCX/PPTX as untrusted ZIP/XML packages: prohibit DTDs and external entities, enforce package-size limits, ignore external relationships, HTML-encode text, and render script-disabled local WebView2 previews only.
- Store the shared tag catalogue separately from document files using atomic JSON writes; persist each selected PDF tag region as a standard, named square annotation in a saved copy. Keep aliases/tombstones so renamed/deleted names are not silently reintroduced when old PDFs are revisited.
- Keep API keys and private signing material out of source control. Use Windows Credential Manager / DPAPI for user secrets and server-side secrets for signing.
- Centralize localization resources for Arabic and English and set RTL per localized view.
- Keep telemetry and usage accounting explicit and testable.
- Preserve user settings and study data when upgrading the application.
- Treat offline license verification as a defined policy, not as an accidental fallback.

## Migration adapter strategy

The first C# document and AI engines will be chosen through small proof-of-concept comparisons. Selection criteria include rendering fidelity, annotation support, supported formats, redistribution terms, native dependency footprint, performance, and long-term maintenance. No PDF or AI library is declared equivalent to the existing Python implementation until the comparison is complete.
