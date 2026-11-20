# ADR-0002: Evaluate a unified PDF engine before selecting the production renderer

- **Status:** Evaluation in progress — no production engine decision
- **Date:** 2026-11-20

## Context

The first viewer increment currently uses two separate components:

- Windows.Data.Pdf for read-only page rendering.
- PdfPig 0.1.16 for text extraction and text search.

This is a deliberately small initial implementation, but Engo needs much more: annotations, save/reopen, search navigation, thumbnails, document merge, text context for AI, and robust handling of real-world study PDFs.

## Candidate under evaluation: Aspose.PDF FOSS for .NET

The NuGet package `Aspose.PDF.FOSS` 26.11.0 is listed as MIT-licensed and targets .NET 8+, .NET Standard 2.0, and .NET Framework 4.8. The package documentation describes page rendering to PNG/JPEG/BMP/TIFF/SVG, text extraction and search, PDF annotation editing, document security, signatures, and page/document management.

References:
- NuGet package: https://www.nuget.org/packages/Aspose.PDF.FOSS/26.11.0
- License: https://docs.aspose.org/pdf/net/getting-started/license/
- Text extraction: https://docs.aspose.org/pdf/net/developer-guide/text-extraction/
- Rendering: https://docs.aspose.org/pdf/net/developer-guide/devices-rendering/
- Annotations: https://docs.aspose.org/pdf/net/developer-guide/annotations-forms/

The MIT license permits commercial distribution, subject to retaining the required copyright and license notice. This is materially different from libraries whose free license excludes commercial use.

## Why it is not selected as production yet

A broad API surface and an open-source license do not prove that it is the right engine for Engo. It is a relatively new package line, and the current repository cannot yet run a Windows/.NET build in the authoring environment.

The separate `Engo.PdfEngineSpike` console project checks package restore/compile and can render one chosen page, extract text, and search text in a supplied PDF. It is isolated from the shipping app so an unverified candidate cannot destabilize the current viewer.

## Required validation before adoption

Use a legally distributable, non-sensitive fixture set covering:

1. Arabic text with RTL paragraphs, ligatures, mixed Arabic/Latin lines, and embedded fonts.
2. English multi-column and academic layouts.
3. Scanned/image-only pages, where ordinary text extraction must correctly return no text rather than invent content.
4. Large PDFs (hundreds or thousands of pages) and memory-intensive pages.
5. Encrypted PDFs, malformed-but-recoverable PDFs, page rotation, crop boxes, and mixed page sizes.
6. Existing highlights, comments, ink, shapes, links, bookmarks, forms, and metadata.
7. Adding an annotation, saving a copy, reopening it in a second independent viewer, and verifying geometry and appearance.
8. Rendering quality and page latency at screen and print resolutions.
9. x64 and ARM64 package/runtime compatibility and output size.

## Acceptance thresholds

- Correct page count and page boundaries for all fixture documents.
- Search and extraction quality must be no worse than the current PDF engine reference for Arabic and English fixtures.
- No missing or displaced existing annotations after round-trip save.
- No UI-thread blocking; rendering and text processing must be cancellable and run off the UI thread.
- Memory and latency must remain acceptable on large study PDFs.
- The library's exact license and all transitive notices must be included in the release attribution inventory.

## Decision rule

Keep Windows.Data.Pdf + PdfPig until this evaluation passes. If Aspose.PDF FOSS passes, migrate behind a single `IPdfDocumentEngine` abstraction and remove duplicate engines only after the same fixture suite passes against the new adapter. Otherwise, compare another commercially compatible engine or license a commercial PDF SDK.

## Concurrency note

Treat a mutable `Document` instance as a single-operation object unless the library explicitly documents safe concurrent access. Use one document instance per worker or serialize operations on a shared instance.
