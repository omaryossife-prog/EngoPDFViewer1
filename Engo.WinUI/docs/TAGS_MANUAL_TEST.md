# Shared tags — manual Windows checks

The tag catalogue is shared across PDF tabs and saved locally in `%LOCALAPPDATA%\\Engo\\Engo.WinUI\\tag-library.json`. Assigning a tag creates a pending region draft; use **حفظ نسخة PDF** to embed it into a new PDF copy. The source PDF must remain unchanged.

1. Open a PDF, select **وسم منطقة** in the annotation tool, then select an existing tag from the **الوسم** list.
2. Drag a rectangle over a page region. Confirm the preview shows the selected tag name and its color.
3. Save an annotated copy, reopen that copy in Engo and in another desktop PDF viewer. Confirm the region remains a square annotation with the tag name in its annotation properties.
4. Open **إدارة الوسوم**. Create a tag, select it and rename it, recolor it from the palette, and delete it using the two-step confirmation.
5. Close Engo and reopen it. Confirm tags remain in the shared list, independent of the PDF currently open.
6. Assign tags to regions in two different PDFs. Confirm both tabs use the same catalogue and that changing the selected tag does not change the source files.
7. Confirm deleting a tag from the catalogue does not rewrite or damage any original PDF. Existing tag assignments in older PDFs are retained as metadata; full cleanup/reconciliation is a later parity task.

Automated smoke tests cover the JSON catalogue's create/rename/recolor/delete/alias behavior and the PDF annotation save/reopen round trip. They do not replace the visual checks above or verify every third-party PDF viewer's annotation appearance.
