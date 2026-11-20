# Engo — C# / WinUI 3 migration workspace

This directory contains the **new Windows-native C# implementation** of Engo. It is intentionally isolated from the existing Python application.

> **Migration safety:** the existing Python application on `main` remains the production/reference implementation. This branch does not replace it. A capability is considered migrated only after its C# implementation, regression coverage, and parity checks are complete.

## Technology baseline

- C# and .NET 11
- WinUI 3 on Windows App SDK 2.7.0 (stable)
- Layered architecture: Domain, Application, Infrastructure, and UI
- Windows desktop target: `net11.0-windows10.0.26100.0`
- Minimum supported OS for this initial target: Windows 10 version 2004 (10.0.19041)
- Explicit x64 and ARM64 application configurations

## Repository layout

```text
Engo.WinUI/
  Engo.WinUI.sln
  global.json
  Directory.Build.props
  Directory.Packages.props
  src/
    Engo.Domain/
    Engo.Application/
    Engo.Infrastructure/
    Engo.App/
  docs/
```

## Prerequisites

- Windows 10 version 2004 or later (Windows 11 recommended).
- .NET 11 SDK.
- Visual Studio 2026 with the **WinUI application development** workload, or an equivalent Windows SDK + .NET command-line environment.
- A Windows machine for the actual WinUI build and run.

## Build

Run from this directory:

```powershell
dotnet --info
dotnet restore .\Engo.WinUI.sln -p:Platform=x64
dotnet build .\Engo.WinUI.sln --configuration Debug -p:Platform=x64
```

To launch the desktop application after a successful build, open the solution in Visual Studio and select the **x64** configuration, or run the app project with the x64 platform selected.

## Current implementation status

The first migration increment establishes the solution, project boundaries, WinUI application shell, document domain model, recent-document application contract, and JSON persistence adapter. The initial PDF slice uses the Windows PDF API for read-only page rendering and previous/next navigation. Apache-2.0 PdfPig 0.1.16 is used separately for page text extraction and text search. Search results can navigate to the matching page. This is **not** a feature-complete replacement: OCR for scanned pages, visual search highlighting, annotations, Office rendering, AI, voice, licensing, Supabase, and release packaging are tracked in `docs/FEATURE_PARITY.md`.

## Engineering rules

1. Do not delete or rewrite Python modules as part of this migration branch.
2. Keep secrets, signing private keys, API credentials, and Supabase service-role credentials out of the repository.
3. Keep WinUI types inside `Engo.App`; Domain and Application must remain UI-independent.
4. Migrate one vertical feature at a time and keep the legacy implementation as the behavior reference.
5. Do not mark a feature complete until it has automated tests where practical and a documented manual parity check.
6. Preserve the existing Engo brand assets; do not redraw or replace the original logo.
7. Do not merge this branch into `main` until the migration acceptance criteria are met.

## Deployment note

The initial app project is unpackaged so development remains independent of the installer decision. The Windows App SDK runtime deployment strategy and integration with the existing NSIS installer must be finalized and tested before distributing a C# build.
