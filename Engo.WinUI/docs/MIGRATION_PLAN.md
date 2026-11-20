# Migration plan

## Guiding strategy

This is a phased rewrite, not a one-shot language conversion. The Python application on `main` remains the behavioral reference and must stay usable throughout the migration. Each phase is delivered as a working vertical slice with tests and a parity checklist.

## Phase 0 — Foundation

**Status: scaffolded; Windows build verification still required.**

- [x] Create an isolated C# / WinUI 3 solution.
- [x] Establish Domain, Application, Infrastructure, and App project boundaries.
- [x] Pin the .NET and Windows App SDK baseline.
- [x] Add an initial native WinUI window and migration dashboard.
- [x] Add a recent-document domain model, application contract, and JSON persistence adapter.
- [ ] Build and launch on Windows 10/11.
- [ ] Add automated tests for the recent-document service and persistence adapter.
- [ ] Add Arabic/English resource-based localization and the application theme system.

## Phase 1 — Document foundation

**Status: first PDF viewing slice scaffolded; Windows build and behavior verification pending.**

- [x] Native PDF file picker wired to the WinUI window.
- [x] Initial read-only PDF page rendering and previous/next navigation using Windows.Data.Pdf.
- [ ] Validate the viewer against representative PDF fixtures on Windows.
- [ ] Select and benchmark the long-term PDF engine for search, text extraction, annotations, and advanced rendering.
- Native file picker and supported-format detection.
- Page navigation, zoom, fit modes, text extraction, and search.
- Multi-document tabs and session restoration.
- Recent files, thumbnails, and large-document performance.

**Exit gate:** representative PDFs render correctly; page counts, navigation, search, and tab/session behavior match the legacy app; memory and responsiveness are measured.

## Phase 2 — Editing and annotations

- Text selection, comments, highlights, pen, shapes, and eraser.
- Annotation color and size preferences.
- Save, Save As, and reload round-trip validation.
- Correct shape geometry and resize handles.

**Exit gate:** annotations remain visually and structurally correct after save/reopen and on different zoom levels.

## Phase 3 — Other document formats

- Word and PowerPoint import/render strategy.
- Supported image formats, zoom, pan, and fit behavior.
- Merge and document utility workflows.

**Exit gate:** supported file matrix is documented and each format has representative fixtures.

## Phase 4 — AI study features

- Provider configuration and secure API-key storage.
- Chat panel, conversation persistence, and document context.
- Selection-based questions, summaries, explanations, and translation.
- Provider error handling, retry policy, usage measurement, and cancellation.

**Exit gate:** provider requests, document context, and usage accounting are covered by automated tests and manual Arabic/English checks.

## Phase 5 — Voice and study tools

- Speech input and playback.
- Live voice tutor and interruption/cancellation.
- Spoken page explanations and follow-up questions.
- Tags, notes, and study organization.

**Exit gate:** Arabic speech workflows, device changes, and network interruptions are tested.

## Phase 6 — Accounts, licensing, and services

- Google sign-in and branded account experience.
- Supabase Auth/Database/Storage integration.
- Ed25519 server-side signing verification.
- Free/premium entitlement rules, offline behavior, usage limits, and admin statistics.
- Terms acceptance and subscription/contact workflows.

**Exit gate:** premium access cannot be bypassed by offline mode or verification failures; existing launch-mode and account-display rules are preserved.

## Phase 7 — Release engineering

- Reproducible Release builds for x64 and ARM64.
- Windows App SDK runtime deployment decision.
- NSIS installer integration or a separately approved MSIX strategy.
- Application icon and original Engo branding integration.
- Update delivery, rollback, signing, and upgrade-preservation tests.

**Exit gate:** clean-machine install/upgrade/uninstall tests pass and user data remains intact.

## Merge policy

Do not merge this branch into `main` and do not replace the current installer until all user-facing features in `FEATURE_PARITY.md` have an accepted replacement, automated coverage where practical, and a successful Windows release candidate.
