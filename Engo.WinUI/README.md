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

## Run during development (no installer)

The project is an **unpackaged WinUI 3 app**. You can build and launch it for testing without creating an installer or a release build.

1. Install Visual Studio 2026 with the **WinUI application development** workload, the .NET 11 SDK, and Windows SDK 10.0.26100 or later.
2. Install the Microsoft WinApp CLI if it is not already installed:

   ```powershell
   winget install Microsoft.winappcli --source winget
   ```

3. From the repository root, open PowerShell and run:

   ```powershell
   .\Engo.WinUI\run-dev.ps1
   ```

   The script checks for .NET 11 and WinApp CLI, installs WinApp CLI with WinGet if it is missing, restores dependencies, then builds the **Debug** configuration and launches Engo directly.

   You can also run the app manually after installing WinApp CLI:

   ```powershell
   winapp run .\Engo.WinUI\src\Engo.App\Engo.App.csproj -c Debug --arch x64
   ```

   This still compiles the C# code as a Debug build, as C# is a compiled language; it does **not** create a Release package, installer, or distribution build.

   For another architecture/configuration:

   ```powershell
   .\run-dev.ps1 -Configuration Debug -Architecture x64
   .\run-dev.ps1 -Configuration Debug -Architecture ARM64
   ```

The script restores the app project, builds Debug, and launches it with `winapp run`. It does not package, publish, sign, or install an Engo release. WinApp CLI handles the matching Windows App SDK runtime for the unpackaged app.

### Run from Visual Studio

1. Open `Engo.WinUI.sln`.
2. In Solution Explorer, right-click `Engo.App` and choose **Set as Startup Project**.
3. Select **x64** and the **Unpackaged** launch profile.
4. Press **F5** to debug or **Ctrl+F5** to run without the debugger.

Do not choose a package/MSIX profile for this project; it is intentionally configured with `WindowsPackageType=None`.

## Build

Run from this directory:

```powershell
dotnet --info
dotnet restore .\Engo.WinUI.sln -p:Platform=x64
dotnet build .\Engo.WinUI.sln --configuration Debug -p:Platform=x64
```

To launch the desktop application after a successful build, open the solution in Visual Studio and select the **x64** configuration, or run the app project with the x64 platform selected.

## Current implementation status

The first migration increment establishes the solution, project boundaries, WinUI application shell, document domain model, recent-document application contract, and JSON persistence adapter. The WinUI shell now hosts PDFs, common image files, DOCX documents, and PPTX presentations in independent native tabs, with a persistent Home tab, recent-document reopening, and local JSON session restoration. The image viewer uses Windows imaging codecs for read-only display, initial fit-to-window, mouse-wheel zoom anchored under the pointer, and drag panning; codec support depends on the Windows image decoder available on the target system. The first Office reader increment parses common Open XML text, Word tables, embedded pictures, and PowerPoint slide order into local read-only HTML previews, then displays them in WinUI WebView2. It does not yet edit Office files, save native Office highlights, preserve every advanced layout/chart/animation, or connect selected text to AI. The current CI run verifies the Windows build and fixture smoke tests for DOCX/PPTX parsing, embedded-media extraction, slide order, session persistence, PDF annotation save/reopen, PDF merging, and image viewport math. The initial PDF slice uses the Windows PDF API for read-only page rendering and previous/next navigation. Apache-2.0 PdfPig 0.1.16 is used separately for page text extraction and text search. Search results can navigate to the matching page. The viewer also has user-triggered current-page OCR using the Windows OCR API for Arabic and English when the corresponding recognition language is installed; it does not yet index OCR text across the whole file. Aspose.PDF FOSS 26.11.0 is now used by the first native annotation-writing adapter, while its broader role as a unified PDF rendering/search engine remains under evaluation. The viewer currently supports drawing highlight, freehand ink, and rectangles, with undo, an eraser for unsaved annotations, saving to a separate PDF copy, merging multiple PDFs into a new file, and progressive 12-page thumbnail groups for direct page navigation; the sticky-note tool was intentionally omitted; automated save/reopen checks pass in CI; manual visual parity in desktop PDF viewers is still pending. The `Engo.PdfEngineSpike` console project separately evaluates additional rendering and extraction capabilities. See `docs/decisions/ADR-0002-pdf-engine-evaluation.md` and `THIRD_PARTY_NOTICES.md`. This is **not** a feature-complete replacement: OCR text is not yet indexed across whole files, annotation editing/resizing, full-page reading mode (Windows x64 build and smoke checks pass; manual UI verification pending), full Office rendering fidelity and native Office editing/highlighting, AI, voice, licensing, Supabase, and release packaging remain tracked in `docs/FEATURE_PARITY.md`.

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
