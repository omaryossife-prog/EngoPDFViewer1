# Engo — C# / WinUI 3 migration workspace

This directory contains the **new Windows-native C# implementation** of Engo. It is intentionally isolated from the existing Python application.

> **Migration safety:** the existing Python application on `main` remains the production/reference implementation. This branch does not replace it. A capability is considered migrated only after its C# implementation, regression coverage, and parity checks are complete.

## Technology baseline

- C# and .NET 11
- WinUI 3 on Windows App SDK 2.7.0 (stable)
- MVVM-oriented application architecture with separate Domain, Application, Infrastructure, and UI projects
- Windows desktop target: `net11.0-windows10.0.26100.0`
- Minimum supported OS for this initial application target: Windows 10 version 2004 (10.0.19041)

The Windows App SDK version is centrally pinned in `Directory.Packages.props`. Review the Microsoft release notes before updating it.

## Repository layout

```text
Engo.WinUI/
  Engo.WinUI.sln
  global.json
  Directory.Build.props
  Directory.Packages.props
  src/
    Engo.Domain/          Domain models; no UI or Windows SDK dependency
    Engo.Application/     Use cases and service contracts
    Engo.Infrastructure/  Persistence and external-system adapters
    Engo.App/             WinUI 3 desktop application
  docs/
    ARCHITECTURE.md
    MIGRATION_PLAN.md
    FEATURE_PARITY.md
    decisions/
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
dotnet restore .\Engo.WinUI.sln
dotnet build .\Engo.WinUI.sln --configuration Debug
```

To launch the desktop application after a successful build:

```powershell
dotnet run --project .\src\Engo.App\Engo.App.csproj
```

## Current implementation status

The first migration increment establishes the solution, project boundaries, WinUI application shell, document domain model, recent-document application contract, and JSON persistence adapter. It is **not** a feature-complete replacement yet. PDF rendering, annotations, Office rendering, AI, voice, licensing, Supabase, and release packaging are tracked explicitly in `docs/FEATURE_PARITY.md`.

## Important engineering rules

1. Do not delete or rewrite Python modules as part of this migration branch.
2. Keep secrets, signing private keys, API credentials, and Supabase service-role credentials out of the repository.
3. Keep WinUI types inside `Engo.App`; the Domain and Application projects must remain UI-independent.
4. Migrate one vertical feature at a time and keep the legacy implementation as the behavior reference.
5. Do not mark a feature complete until it has automated tests where practical and a documented manual parity check.
6. Preserve the existing Engo brand assets; do not redraw or replace the original logo.
7. Do not merge this branch into `main` until the acceptance criteria in the migration plan are met.

## Deployment note

The initial app project is unpackaged to keep development independent of the future installer decision. The Windows App SDK runtime deployment strategy and integration with the existing NSIS installer must be finalized and tested before distributing a C# build.
