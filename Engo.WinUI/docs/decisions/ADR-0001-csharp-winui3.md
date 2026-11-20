# ADR-0001: C# and WinUI 3 for the native Windows rewrite

- **Status:** Accepted for the migration branch
- **Date:** 2026-11-20

## Context

Engo is a Windows desktop product with a broad UI surface, PDF and Office workflows, Windows integration, AI/voice features, account/licensing logic, and an established Python implementation. The rewrite must improve native Windows integration without risking the currently working release.

## Decision

Use C# with WinUI 3, delivered through the Windows App SDK. Use a layered solution with separate Domain, Application, Infrastructure, and WinUI App projects.

The initial baseline targets .NET 11 and Windows App SDK 2.7.0 stable. The application project is initially unpackaged so the installer and runtime deployment strategy can be evaluated independently.

## Rationale

- WinUI 3 is Microsoft's recommended native UI framework for new Windows desktop applications.
- C# provides direct access to Windows APIs and a mature .NET ecosystem.
- The layered design keeps business behavior and service integrations testable outside the UI.
- An isolated branch and side-by-side rollout protect the existing Python release.

## Consequences

- Existing Python code is a behavioral reference, not a source dependency of the C# app.
- PDF rendering, annotation, Office, AI, speech, authentication, licensing, and packaging libraries require explicit selection and proof-of-concept validation.
- The first scaffold does not claim feature parity.
- Deployment must decide how the Windows App SDK runtime is shipped and how existing NSIS upgrade/data-preservation behavior is retained.

## References

- https://learn.microsoft.com/en-us/windows/apps/winui
- https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/release-notes/windows-app-sdk-2-0
- https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/system-requirements
