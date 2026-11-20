# Feature parity tracker

This checklist is the source of truth for migration completeness. Status values mean:

- **Scaffolded** — architecture or project boundary exists; the user feature is not complete.
- **In progress** — implementation is underway.
- **Verified** — implementation and parity checks have passed.
- **Not started** — no C# implementation exists yet.

| Existing Engo capability | C# target area | Status | Acceptance evidence |
|---|---|---|---|
| Windows desktop shell, navigation, theme | Engo.App | In progress | WinUI shell, home navigation, PDF open toolbar, recent-PDF list; launch/theme verification pending |
| PDF open, render, page navigation | Windows.Data.Pdf / PdfViewerPage | In progress | Native file picker, read-only page render, previous/next navigation scaffolded; Windows build and fixture parity still pending |
| Recent PDF documents | RecentDocumentsService / HomePage | In progress | Local JSON store records opened PDFs and the home page lists/reopens existing files; UI persistence tests pending |\n| PDF tabs and session restoration | Engo.App / Application | Not started | Multi-file and relaunch tests |
| PDF search and text extraction | PdfPigTextService / PdfViewerPage | In progress | Page-level extraction, text-query snippets, result-to-page navigation, and background work wired; Arabic/scanned-PDF and fixture verification pending |
| Zoom, thumbnails, full-page view | Engo.App / Document engine | Not started | DPI, scrolling, and large-file checks |
| Text selection and contextual questions | AI / Document services | Not started | Selected-text context tests |
| Highlights, comments, pen, shapes, eraser | Annotation services | Not started | Save/reopen geometry tests |
| Merge PDFs | Document services | Not started | Output integrity tests |
| Word and PowerPoint support | Office adapter | Not started | DOCX/PPTX fixture suite |
| Image viewing, zoom, and pan | Image viewer | Not started | Image format and input tests |
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
