# Feature parity tracker

This checklist is the source of truth for migration completeness. Status values mean:

- **Scaffolded** — architecture or project boundary exists; the user feature is not complete.
- **In progress** — implementation is underway.
- **Verified** — implementation and parity checks have passed.
- **Not started** — no C# implementation exists yet.

| Existing Engo capability | C# target area | Status | Acceptance evidence |
|---|---|---|---|
| Windows desktop shell, navigation, theme | Engo.App | In progress | WinUI shell, home navigation, PDF open toolbar, recent-PDF list and native document tabs; launch/theme verification pending |
| PDF open, render, page navigation | Windows.Data.Pdf / PdfViewerPage | In progress | Native file picker, read-only page render, previous/next navigation scaffolded; Windows build and fixture parity still pending |
| Recent documents | RecentDocumentsService / HomePage | In progress | Local JSON store records PDFs and images; home page lists/reopens existing supported files; smoke coverage added, UI tests pending |
| Multiple PDF tabs | WinUI TabView / MainWindow | In progress | Opens multiple files in independent tabs, reuses an already-open path, supports close without changing a different active tab; Windows UI tests pending |
| Document session restoration | DocumentSessionService / JsonDocumentSessionRepository | In progress | Saves supported PDF/image paths and active tab to an atomic local JSON file; startup restores existing files and ignores missing files; Windows relaunch test pending |
| PDF search and text extraction | PdfPigTextService / PdfViewerPage | In progress | Page-level extraction, text-query snippets, result-to-page navigation, and background work wired; Arabic reading-order and fixture verification pending |
| OCR for scanned PDF pages | Windows.Media.Ocr / PdfViewerPage | In progress | User-triggered OCR on current page for Arabic or English with language-availability and image-size checks; batch OCR and search indexing not implemented |
| PDF engine consolidation | Aspose.PDF FOSS / Engo.PdfEngineSpike | Evaluation | Aspose.PDF FOSS 26.11.0 is now used for native annotation writes; full rendering/search consolidation remains an evaluation pending fixture parity and Windows builds |
| Persistence and PDF annotation smoke coverage | Engo.SmokeTests | In progress | Tests recent-file deduplication, file-type filtering, session snapshot restore, atomic JSON cleanup, three annotation types round-tripped to a separate PDF copy, source preservation, PDF merge page count/source preservation, and overlap/stroke eraser hit testing; latest Windows x64 CI build and smoke checks passed |
| Zoom, thumbnails, full-page view | PdfViewerPage / Windows.Data.Pdf | In progress | Progressive 12-page thumbnail groups, direct-click page navigation, previous/next group controls, and focused full-page reading mode with an exit control implemented; latest full-page Windows build pending, with large-document performance and manual UI verification still required |
| Text selection and contextual questions | AI / Document services | Not started | Selected-text context tests |
| PDF highlights, freehand ink, rectangles, and eraser | AsposePdfAnnotationService / PdfViewerPage | In progress | Native PDF highlight/ink/rectangle annotations, live overlay preview, undo, pending-annotation eraser, separate-copy saving, CropBox/rotation mapping, and close-with-unsaved-warning wired; round-trip smoke coverage added, Windows visual verification pending |
| Merge PDFs | AsposePdfMergeService / MainWindow | In progress | Multi-file picker, user-selected destination, output opened in a tab; smoke test verifies combined page count, input order and source preservation; Windows UI verification pending |
| Word and PowerPoint support | Office adapter | Not started | DOCX/PPTX fixture suite |
| Image viewing, zoom, and pan | ImageViewerPage / Windows imaging codecs | In progress | PNG/JPEG/BMP/GIF/TIFF/WebP file picker, image tab, pixel dimensions, zoom, fit-image and scroll/pan scaffolded; codec availability and UI fixture tests pending |
| AI chat and conversation history | AI services | Not started | Provider contract and persistence tests |
| Summaries, explanations, and translation | AI application use cases | Not started | Arabic/English response tests |
| Live voice tutor and speech playback | Voice services | Not started | Device/network interruption tests |
| Tags, notes, and study organization | Domain / Application | Not started | Data migration and persistence tests |
| Google login and account window | Identity adapter / App | Not started | Auth flow and recovery tests |
| Supabase database and storage | Infrastructure | Not started | RLS, storage, and integration tests |
| Premium entitlements and usage limits | Licensing services | Not started | Offline and tamper-resistance tests |
| Ed25519 license verification | Licensing infrastructure | Not started | Signature verification test vectors |
| Terms acceptance | App / licensing | Not started | Decline, upgrade, and version-change tests |
| QR subscription/contact flow | Account UI / storage | Not started | QR retrieval and fallback tests |
| Admin usage statistics | Infrastructure / admin UI | Not started | Aggregation and access-control tests |
| Updates and installer | Release engineering | Not started | Clean install, upgrade, rollback tests |

A row must not be marked **Verified** solely because a button or placeholder screen exists.
