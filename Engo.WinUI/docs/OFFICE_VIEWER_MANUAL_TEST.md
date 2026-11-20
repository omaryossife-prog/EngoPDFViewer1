# Word and PowerPoint reader — manual Windows checks

The initial C# Office implementation is read-only. It parses common Open XML text, tables and embedded raster pictures into local HTML preview files and displays those files with WinUI WebView2. It does not write back to the source DOCX/PPTX.

1. Open a DOCX containing a title, Heading 1/2 paragraphs, bold/italic text, right-to-left Arabic, a table and embedded PNG/JPEG images. Compare paragraph order, basic formatting, table content and image placement with Word.
2. Open a DOCX containing hyperlinks. Confirm link text remains readable and clicking content cannot navigate to an external website.
3. Open a PPTX with multiple slides, different slide backgrounds, text boxes and pictures. Use **السابق** and **التالي** and confirm the order matches PowerPoint's slide sorter rather than filenames.
4. Open a PPTX containing a table and chart. Confirm supported table text is visible; record chart/SmartArt/animation omissions for the next fidelity pass.
5. Open large DOCX/PPTX files. Check that the UI remains responsive while parsing and that closing the tab cancels pending work.
6. Close Office tabs and confirm the generated preview folders are removed from `%LOCALAPPDATA%\\Engo\\Engo.WinUI\\OfficePreviews` when the WebView2 file handle has released them.
7. Repeat after removing the Microsoft Edge WebView2 Runtime in a test VM (or a clean Windows image). Confirm Engo presents a readable error rather than crashing.

Automated smoke tests verify package parsing, HTML escaping, embedded-image extraction, presentation slide order, and session persistence. They do not establish full Microsoft Office rendering fidelity or replace these manual checks.
