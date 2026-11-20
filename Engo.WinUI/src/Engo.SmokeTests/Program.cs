using Engo.Application.Documents;
using Engo.Domain.Documents;
using Aspose.Pdf;
using Aspose.Pdf.Annotations;
using Engo.Infrastructure.Persistence;
using Engo.Infrastructure.Pdf;
using Engo.Infrastructure.Office;
using System.IO.Compression;
using System.Text;

var root = Path.Combine(
    Path.GetTempPath(),
    "Engo.WinUI.SmokeTests",
    Guid.NewGuid().ToString("N"));

Directory.CreateDirectory(root);

try
{
    var firstPdf = Path.Combine(root, "first.pdf");
    var secondPdf = Path.Combine(root, "second.pdf");
    var imageFile = Path.Combine(root, "scan.png");
    var wordFile = Path.Combine(root, "sample.docx");
    var powerpointFile = Path.Combine(root, "sample.pptx");
    var annotationSource = Path.Combine(root, "annotation-source.pdf");
    var annotationOutput = Path.Combine(root, "annotation-output.pdf");
    var mergeFirst = Path.Combine(root, "merge-first.pdf");
    var mergeSecond = Path.Combine(root, "merge-second.pdf");
    var mergeOutput = Path.Combine(root, "merged-output.pdf");
    var textFile = Path.Combine(root, "not-supported.txt");
    var missingPdf = Path.Combine(root, "missing.pdf");

    await File.WriteAllTextAsync(firstPdf, "%PDF-1.7\n");
    await File.WriteAllTextAsync(secondPdf, "%PDF-1.7\n");
    CreateSinglePagePdf(annotationSource);
    CreatePdfWithPages(mergeFirst, 2);
    CreatePdfWithPages(mergeSecond, 3);
    await File.WriteAllBytesAsync(imageFile, [0x89, 0x50, 0x4E, 0x47]);
    await File.WriteAllTextAsync(textFile, "This is not a supported document.");
    CreateDocxFixture(wordFile);
    CreatePptxFixture(powerpointFile);

    await VerifyRecentDocumentsAsync(root, firstPdf, imageFile, wordFile, powerpointFile, textFile);
    await VerifyDocumentSessionAsync(
        root,
        firstPdf,
        secondPdf,
        imageFile,
        textFile,
        missingPdf,
        wordFile,
        powerpointFile);
    await VerifyOfficeDocumentReadingAsync(wordFile, powerpointFile);
    await VerifyTagLibraryAsync(root);
    await VerifyPdfAnnotationRoundTripAsync(annotationSource, annotationOutput);
    await VerifyPdfMergeRoundTripAsync(mergeFirst, mergeSecond, mergeOutput);
    VerifyAnnotationEraserHitTesting();
    VerifyImageViewportMath();
    VerifyNoTemporaryFilesRemain(root);

    Console.WriteLine("PASS: recent PDF, image and Office persistence");
    Console.WriteLine("PASS: PDF/image/Office session persistence and path filtering");
    Console.WriteLine("PASS: DOCX text/table/image preview and PPTX slide-order/image preview");
    Console.WriteLine("PASS: shared tag library create/rename/recolor/delete and alias tombstones");
    Console.WriteLine("PASS: PDF region tags persist as named, colored annotations");
    Console.WriteLine("PASS: PDF annotations save as a separate round-trip-readable copy");
    Console.WriteLine("PASS: PDF merge preserves input order and page count");
    Console.WriteLine("PASS: annotation eraser hit testing respects stroke geometry and draw order");
    Console.WriteLine("PASS: image zoom remains anchored at the pointer and drag-pan follows pointer movement");
    Console.WriteLine("PASS: atomic JSON writes leave no temporary files");
    Console.WriteLine("All Engo smoke checks passed.");
    return 0;
}
catch (Exception exception)
{
    Console.Error.WriteLine(exception);
    return 1;
}
finally
{
    try
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }
    catch
    {
        // Do not hide the actual smoke-test result because temporary cleanup failed.
    }
}

static async Task VerifyRecentDocumentsAsync(
    string root,
    string firstPdf,
    string imageFile,
    string wordFile,
    string powerpointFile,
    string textFile)
{
    var repository = new JsonRecentDocumentsRepository(
        Path.Combine(root, "recent-documents.json"));
    var service = new RecentDocumentsService(repository);

    await service.RecordOpenedAsync(firstPdf);
    await service.RecordOpenedAsync(firstPdf);
    var image = await service.RecordOpenedAsync(imageFile);
    var word = await service.RecordOpenedAsync(wordFile);
    var powerpoint = await service.RecordOpenedAsync(powerpointFile);

    var recent = await service.GetRecentAsync();
    Require(
        recent.Count == 4 &&
        recent.Count(document => document.Kind == DocumentKind.Pdf) == 1 &&
        recent.Any(document => document.Kind == DocumentKind.Image &&
            string.Equals(document.FullPath, imageFile, StringComparison.OrdinalIgnoreCase)) &&
        recent.Any(document => document.Kind == DocumentKind.Word &&
            string.Equals(document.FullPath, wordFile, StringComparison.OrdinalIgnoreCase)) &&
        recent.Any(document => document.Kind == DocumentKind.PowerPoint &&
            string.Equals(document.FullPath, powerpointFile, StringComparison.OrdinalIgnoreCase)),
        "Recent documents must deduplicate PDFs and retain supported images and Office documents.");

    Require(image.Kind == DocumentKind.Image, "PNG files must be classified as images.");
    Require(word.Kind == DocumentKind.Word, "DOCX files must be classified as Word documents.");
    Require(powerpoint.Kind == DocumentKind.PowerPoint, "PPTX files must be classified as PowerPoint documents.");

    await AssertThrowsAsync<NotSupportedException>(
        () => service.RecordOpenedAsync(textFile),
        "The recent-document service must reject unsupported file types.");
}

static async Task VerifyDocumentSessionAsync(
    string root,
    string firstPdf,
    string secondPdf,
    string imageFile,
    string textFile,
    string missingPdf,
    string wordFile,
    string powerpointFile)
{
    var repository = new JsonDocumentSessionRepository(
        Path.Combine(root, "document-session.json"));
    var service = new DocumentSessionService(repository);

    await service.SaveAsync(
        new[] { firstPdf, imageFile, wordFile, textFile, missingPdf, powerpointFile, secondPdf },
        imageFile);

    var restored = await service.LoadAsync();

    Require(restored is not null, "A saved document session must be loadable.");
    Require(
        restored!.OpenFilePaths.SequenceEqual(
            new[] { firstPdf, imageFile, wordFile, powerpointFile, secondPdf },
            StringComparer.OrdinalIgnoreCase),
        "A session must retain existing PDFs, images, Word and PowerPoint files, filter unsupported/missing files, and preserve tab order.");
    Require(
        string.Equals(restored.ActiveFilePath, imageFile, StringComparison.OrdinalIgnoreCase),
        "A session must preserve an active image document.");

    await service.SaveAsync(new[] { firstPdf, imageFile, secondPdf, wordFile, powerpointFile }, textFile);
    var withoutActiveDocument = await service.LoadAsync();

    Require(
        withoutActiveDocument is not null && withoutActiveDocument.ActiveFilePath is null,
        "An unsupported active path must not be persisted as the selected document.");
}


static void CreateDocxFixture(string outputPath)
{
    using var archive = ZipFile.Open(outputPath, ZipArchiveMode.Create);
    WriteZipText(
        archive,
        "word/document.xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                    xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <w:body>
            <w:p>
              <w:pPr><w:pStyle w:val="Title"/></w:pPr>
              <w:r><w:t>Title from Word</w:t></w:r>
            </w:p>
            <w:p><w:r><w:t>&lt;script&gt;alert(1)&lt;/script&gt;</w:t></w:r></w:p>
            <w:p><w:pPr><w:bidi/></w:pPr><w:r><w:t>مرحبا بالعالم</w:t></w:r></w:p>
            <w:p><w:hyperlink r:id="rIdExternal"><w:r><w:t>External link text</w:t></w:r></w:hyperlink></w:p>
            <w:p>
              <w:r>
                <w:drawing><a:blip r:embed="rIdImage"/></w:drawing>
              </w:r>
            </w:p>
            <w:tbl>
              <w:tr><w:tc><w:p><w:r><w:t>Header cell</w:t></w:r></w:p></w:tc></w:tr>
              <w:tr><w:tc><w:p><w:r><w:t>Word table value</w:t></w:r></w:p></w:tc></w:tr>
            </w:tbl>
            <w:sectPr/>
          </w:body>
        </w:document>
        """);
    WriteZipText(
        archive,
        "word/_rels/document.xml.rels",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdImage"
                        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
                        Target="media/pixel.png"/>
          <Relationship Id="rIdExternal"
                        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
                        Target="https://example.invalid/"
                        TargetMode="External"/>
        </Relationships>
        """);
    WriteZipBytes(
        archive,
        "word/media/pixel.png",
        Convert.FromBase64String(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jXioAAAAASUVORK5CYII="));
}

static void CreatePptxFixture(string outputPath)
{
    using var archive = ZipFile.Open(outputPath, ZipArchiveMode.Create);
    WriteZipText(
        archive,
        "ppt/presentation.xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                        xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:sldIdLst>
            <p:sldId id="7" r:id="rIdSecond"/>
            <p:sldId id="8" r:id="rIdFirst"/>
          </p:sldIdLst>
          <p:sldSz cx="9144000" cy="5143500"/>
        </p:presentation>
        """);
    WriteZipText(
        archive,
        "ppt/_rels/presentation.xml.rels",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdSecond" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slideB.xml"/>
          <Relationship Id="rIdFirst" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slideA.xml"/>
        </Relationships>
        """);
    WriteZipText(
        archive,
        "ppt/slides/slideB.xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
               xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
               xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <p:cSld><p:spTree>
            <p:sp>
              <p:spPr><a:xfrm><a:off x="100000" y="100000"/><a:ext cx="3000000" cy="900000"/></a:xfrm></p:spPr>
              <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr b="1"/><a:t>Second slide text</a:t></a:r></a:p></p:txBody>
            </p:sp>
            <p:pic>
              <p:blipFill><a:blip r:embed="rIdSlideImage"/></p:blipFill>
              <p:spPr><a:xfrm><a:off x="1000000" y="1800000"/><a:ext cx="1500000" cy="1200000"/></a:xfrm></p:spPr>
            </p:pic>
          </p:spTree></p:cSld>
        </p:sld>
        """);
    WriteZipText(
        archive,
        "ppt/slides/_rels/slideB.xml.rels",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rIdSlideImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/pixel.png"/>
        </Relationships>
        """);
    WriteZipText(
        archive,
        "ppt/slides/slideA.xml",
        """
        <?xml version="1.0" encoding="UTF-8"?>
        <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
               xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <p:cSld><p:spTree>
            <p:sp>
              <p:spPr><a:xfrm><a:off x="100000" y="100000"/><a:ext cx="3000000" cy="900000"/></a:xfrm></p:spPr>
              <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>First slide text</a:t></a:r></a:p></p:txBody>
            </p:sp>
          </p:spTree></p:cSld>
        </p:sld>
        """);
    WriteZipBytes(
        archive,
        "ppt/media/pixel.png",
        Convert.FromBase64String(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jXioAAAAASUVORK5CYII="));
}

static void WriteZipText(ZipArchive archive, string path, string content)
{
    var entry = archive.CreateEntry(path, CompressionLevel.Optimal);
    using var stream = entry.Open();
    using var writer = new StreamWriter(stream, new UTF8Encoding(false));
    writer.Write(content);
}

static void WriteZipBytes(ZipArchive archive, string path, byte[] content)
{
    var entry = archive.CreateEntry(path, CompressionLevel.Optimal);
    using var stream = entry.Open();
    stream.Write(content, 0, content.Length);
}

static async Task VerifyOfficeDocumentReadingAsync(
    string wordFile,
    string powerpointFile)
{
    var service = new OpenXmlOfficeDocumentReader();
    OfficeDocumentPreview? wordPreview = null;
    OfficeDocumentPreview? powerpointPreview = null;

    try
    {
        wordPreview = await service.CreatePreviewAsync(wordFile);
        Require(
            wordPreview.Kind == DocumentKind.Word && wordPreview.Pages.Count == 1,
            "A DOCX must produce one Word reading page.");

        var wordHtml = await File.ReadAllTextAsync(wordPreview.Pages[0].HtmlFilePath);
        Require(
            wordHtml.Contains("<h1", StringComparison.Ordinal) &&
            wordHtml.Contains("Title from Word", StringComparison.Ordinal) &&
            wordHtml.Contains("<table>", StringComparison.Ordinal) &&
            wordHtml.Contains("Word table value", StringComparison.Ordinal),
            "The DOCX preview must retain title text and table content.");
        Require(
            wordHtml.Contains("&lt;script&gt;alert(1)&lt;/script&gt;", StringComparison.Ordinal) &&
            !wordHtml.Contains("<script>", StringComparison.Ordinal),
            "Word text must be HTML-encoded and must not become executable markup.");
        Require(
            wordHtml.Contains("مرحبا بالعالم", StringComparison.Ordinal) &&
            wordHtml.Contains("direction:rtl", StringComparison.Ordinal),
            "Arabic Word paragraphs must be rendered with right-to-left text direction.");
        Require(
            wordHtml.Contains("External link text", StringComparison.Ordinal) &&
            !wordHtml.Contains("https://example.invalid/", StringComparison.Ordinal),
            "External Office hyperlinks must remain inert and never become WebView navigation targets.");
        Require(
            File.Exists(Path.Combine(wordPreview.PreviewDirectory, "media", "media-0001.png")) &&
            wordHtml.Contains("media/media-0001.png", StringComparison.Ordinal),
            "Embedded Word pictures must be copied to the preview media folder and referenced.");

        powerpointPreview = await service.CreatePreviewAsync(powerpointFile);
        Require(
            powerpointPreview.Kind == DocumentKind.PowerPoint &&
            powerpointPreview.Pages.Count == 2 &&
            powerpointPreview.Pages[0].Label == "الشريحة 1 / 2",
            "A PPTX must create separate slide pages in presentation order.");

        var firstSlideHtml = await File.ReadAllTextAsync(powerpointPreview.Pages[0].HtmlFilePath);
        var secondSlideHtml = await File.ReadAllTextAsync(powerpointPreview.Pages[1].HtmlFilePath);
        Require(
            firstSlideHtml.Contains("Second slide text", StringComparison.Ordinal) &&
            !firstSlideHtml.Contains("First slide text", StringComparison.Ordinal) &&
            secondSlideHtml.Contains("First slide text", StringComparison.Ordinal),
            "PowerPoint previews must follow the slide relationship order, not ZIP filename order.");
        Require(
            firstSlideHtml.Contains("media/media-0001.png", StringComparison.Ordinal) &&
            File.Exists(Path.Combine(powerpointPreview.PreviewDirectory, "media", "media-0001.png")),
            "Embedded PowerPoint pictures must be extracted into the preview media folder.");
    }
    finally
    {
        if (wordPreview is not null && Directory.Exists(wordPreview.PreviewDirectory))
        {
            Directory.Delete(wordPreview.PreviewDirectory, recursive: true);
        }

        if (powerpointPreview is not null && Directory.Exists(powerpointPreview.PreviewDirectory))
        {
            Directory.Delete(powerpointPreview.PreviewDirectory, recursive: true);
        }
    }
}

static void CreateSinglePagePdf(string outputPath)
{
    using var document = Aspose.Pdf.Document.Create();
    var page = document.Pages.Add();

    // Exercise a non-zero CropBox origin and clockwise rotation so the
    // annotation adapter has to map screen coordinates back to PDF space.
    page.CropBox = new Rectangle(40, 60, 572, 732);
    page.RotateDegrees = 90;

    document.Save(outputPath);
}


static async Task VerifyTagLibraryAsync(string root)
{
    var path = Path.Combine(root, "tag-library.json");
    var service = new TagLibraryService(new JsonTagLibraryRepository(path));

    var created = await service.CreateAsync("Lecture", "#123456");
    Require(
        created.Name == "Lecture" && created.ColorHex == "#123456",
        "Creating a tag must preserve its validated name and color.");

    await AssertThrowsAsync<InvalidOperationException>(
        () => service.CreateAsync("lecture", "#ABCDEF"),
        "Tag names must be unique without regard to letter casing.");

    await AssertThrowsAsync<ArgumentException>(
        () => service.CreateAsync("Invalid Color", "#GGGGGG"),
        "Tag colors must use a valid #RRGGBB value.");

    var renamed = await service.RenameAsync("Lecture", "Important");
    Require(
        renamed.Name == "Important" && renamed.ColorHex == "#123456",
        "Renaming a tag must preserve its color.");

    var renamedSnapshot = await service.GetSnapshotAsync();
    Require(
        TagLibraryService.ResolveName(renamedSnapshot, "Lecture") == "Important",
        "A renamed tag must resolve through its alias for existing PDF annotations.");

    var recolored = await service.RecolorAsync("Important", "#AA22BB");
    Require(
        recolored.ColorHex == "#AA22BB",
        "Recoloring a tag must update the shared catalogue.");

    await service.DeleteAsync("Important");
    var deletedSnapshot = await service.GetSnapshotAsync();
    Require(
        TagLibraryService.ResolveName(deletedSnapshot, "Important") is null &&
        TagLibraryService.ResolveName(deletedSnapshot, "Lecture") is null,
        "Deleting a tag must leave tombstones for its old name and aliases.");

    await service.CreateAsync("Important", "#00AACC");
    var recreatedSnapshot = await service.GetSnapshotAsync();
    Require(
        TagLibraryService.ResolveName(recreatedSnapshot, "Important") == "Important" &&
        TagLibraryService.ResolveName(recreatedSnapshot, "Lecture") is null,
        "Recreating a deleted tag must not resurrect stale aliases from older PDFs.");

    Require(
        !Directory.GetFiles(root, "*.tmp", SearchOption.TopDirectoryOnly).Any(),
        "The tag library must use atomic writes and clean up temporary files.");
}

static async Task VerifyPdfAnnotationRoundTripAsync(
    string sourcePath,
    string outputPath)
{
    var service = new AsposePdfAnnotationService();
    var annotations = new[]
    {
        new PdfAnnotationDraft(
            1,
            PdfAnnotationKind.Highlight,
            0.10, 0.12, 0.62, 0.18,
            [],
            null,
            PdfAnnotationColor.Yellow,
            2),
        new PdfAnnotationDraft(
            1,
            PdfAnnotationKind.Rectangle,
            0.12, 0.25, 0.52, 0.45,
            [],
            null,
            PdfAnnotationColor.Red,
            1.5),
        new PdfAnnotationDraft(
            1,
            PdfAnnotationKind.Freehand,
            0.10, 0.55, 0.45, 0.75,
            new[]
            {
                new PdfAnnotationPoint(0.10, 0.70),
                new PdfAnnotationPoint(0.24, 0.55),
                new PdfAnnotationPoint(0.45, 0.72)
            },
            null,
            PdfAnnotationColor.Blue,
            1.5),
        new PdfAnnotationDraft(
            1,
            PdfAnnotationKind.TagRegion,
            0.18, 0.78, 0.52, 0.94,
            [],
            "Vocabulary",
            new PdfAnnotationColor(0.25, 0.65, 0.85),
            2)
    };

    await service.SaveAnnotatedCopyAsync(sourcePath, outputPath, annotations);

    Require(File.Exists(outputPath), "The annotated output PDF must be created.");

    using var original = Aspose.Pdf.Document.Open(sourcePath);
    using var annotated = Aspose.Pdf.Document.Open(outputPath);

    Require(
        original.Pages[1].Annotations.Count == 0,
        "Saving annotations must not modify the source PDF.");

    var savedPage = annotated.Pages[1];
    Require(
        savedPage.Annotations.Count == annotations.Length,
        "Highlight, rectangle, ink, and region-tag annotations must survive save and reopen.");

    var highlight = savedPage.Annotations
        .OfType<HighlightAnnotation>()
        .SingleOrDefault();

    Require(
        highlight is not null && highlight.QuadPoints.Length == 4,
        "A saved highlight must contain four PDF QuadPoints for interoperable rendering.");

    var tag = savedPage.Annotations
        .OfType<SquareAnnotation>()
        .SingleOrDefault(annotation =>
            string.Equals(annotation.Title, "Engo Region Tag", StringComparison.Ordinal));
    Require(
        tag is not null && tag.Contents == "Vocabulary",
        "A region tag must survive save/reopen with its Engo identifier and tag name.");

    var cropBox = savedPage.CropBox;
    foreach (var annotation in savedPage.Annotations)
    {
        var bounds = annotation.Rect;
        Require(bounds is not null, "Every saved annotation must contain a PDF rectangle.");
        Require(
            bounds!.LLX >= cropBox.LLX - 0.5 &&
            bounds.LLY >= cropBox.LLY - 0.5 &&
            bounds.URX <= cropBox.URX + 0.5 &&
            bounds.URY <= cropBox.URY + 0.5,
            "Annotation rectangles must stay inside the page CropBox after rotation mapping.");
    }

    await AssertThrowsAsync<InvalidOperationException>(
        () => service.SaveAnnotatedCopyAsync(sourcePath, sourcePath, annotations),
        "The annotation service must never overwrite the original source PDF.");
}

static void CreatePdfWithPages(string outputPath, int pageCount)
{
    using var document = Aspose.Pdf.Document.Create();
    for (var index = 0; index < pageCount; index++)
    {
        document.Pages.Add();
    }

    document.Save(outputPath);
}

static async Task VerifyPdfMergeRoundTripAsync(
    string firstPdf,
    string secondPdf,
    string outputPdf)
{
    var service = new AsposePdfMergeService();
    var mergedPageCount = await service.MergeAsync(
        new[] { firstPdf, secondPdf },
        outputPdf);

    Require(
        mergedPageCount == 5,
        "Merging two PDFs must report the total page count in input order.");

    using var first = Aspose.Pdf.Document.Open(firstPdf);
    using var second = Aspose.Pdf.Document.Open(secondPdf);
    using var merged = Aspose.Pdf.Document.Open(outputPdf);

    Require(first.PageCount == 2, "The first source PDF must remain unchanged.");
    Require(second.PageCount == 3, "The second source PDF must remain unchanged.");
    Require(merged.PageCount == 5, "The merged PDF must contain all pages from both sources.");

    await AssertThrowsAsync<ArgumentException>(
        () => service.MergeAsync(new[] { firstPdf }, Path.Combine(Path.GetDirectoryName(outputPdf)!, "single.pdf")),
        "The merge service must require at least two input PDFs.");

    await AssertThrowsAsync<ArgumentException>(
        () => service.MergeAsync(new[] { firstPdf, firstPdf }, outputPdf),
        "The merge service must reject duplicate input paths.");

    await AssertThrowsAsync<InvalidOperationException>(
        () => service.MergeAsync(new[] { firstPdf, secondPdf }, firstPdf),
        "The merge service must never overwrite an input source PDF.");
}

static void VerifyAnnotationEraserHitTesting()
{
    var rectangle = new PdfAnnotationDraft(
        1,
        PdfAnnotationKind.Rectangle,
        0.10, 0.10, 0.30, 0.30,
        [],
        null,
        PdfAnnotationColor.Red,
        1.5);

    var highlight = new PdfAnnotationDraft(
        1,
        PdfAnnotationKind.Highlight,
        0.20, 0.20, 0.40, 0.40,
        [],
        null,
        PdfAnnotationColor.Yellow,
        1);

    var ink = new PdfAnnotationDraft(
        1,
        PdfAnnotationKind.Freehand,
        0.10, 0.60, 0.40, 0.90,
        new[]
        {
            new PdfAnnotationPoint(0.10, 0.60),
            new PdfAnnotationPoint(0.25, 0.75),
            new PdfAnnotationPoint(0.40, 0.90)
        },
        null,
        PdfAnnotationColor.Blue,
        1.5);

    var overlapping = new[] { rectangle, highlight };
    Require(
        PdfAnnotationHitTester.FindTopmostHitIndex(
            overlapping,
            new PdfAnnotationPoint(0.25, 0.25)) == 1,
        "The eraser must select the most recently drawn overlapping annotation.");

    Require(
        PdfAnnotationHitTester.FindTopmostHitIndex(
            overlapping,
            new PdfAnnotationPoint(0.15, 0.15)) == 0,
        "The eraser must find the earlier rectangle outside the newer highlight.");

    Require(
        PdfAnnotationHitTester.FindTopmostHitIndex(
            new[] { ink },
            new PdfAnnotationPoint(0.25, 0.75)) == 0,
        "The eraser must hit a point close to a freehand segment.");

    Require(
        PdfAnnotationHitTester.FindTopmostHitIndex(
            new[] { ink },
            new PdfAnnotationPoint(0.10, 0.90)) == -1,
        "The eraser must not treat the entire freehand bounding rectangle as ink.");

    Require(
        PdfAnnotationHitTester.FindTopmostHitIndex(
            overlapping,
            new PdfAnnotationPoint(0.85, 0.85)) == -1,
        "The eraser must return no hit when the pointer is outside all drafts.");
}

static void VerifyImageViewportMath()
{
    var zoomOffsets = ImageViewportMath.CalculateZoomAnchoredOffsets(
        horizontalOffset: 200,
        verticalOffset: 100,
        pointerX: 100,
        pointerY: 50,
        currentZoomFactor: 2,
        nextZoomFactor: 3);

    Require(
        Math.Abs(zoomOffsets.Horizontal - 350) < 0.001 &&
        Math.Abs(zoomOffsets.Vertical - 175) < 0.001,
        "Zooming must keep the same image point beneath the mouse pointer.");

    var panOffsets = ImageViewportMath.CalculatePanOffsets(
        horizontalOffset: 120,
        verticalOffset: 70,
        pointerDeltaX: 25,
        pointerDeltaY: -10);

    Require(
        Math.Abs(panOffsets.Horizontal - 95) < 0.001 &&
        Math.Abs(panOffsets.Vertical - 80) < 0.001,
        "Dragging right/down must move the displayed image in the same direction.");

    var clampedOffsets = ImageViewportMath.CalculatePanOffsets(
        horizontalOffset: 5,
        verticalOffset: 3,
        pointerDeltaX: 20,
        pointerDeltaY: 20);

    Require(
        clampedOffsets.Horizontal == 0 &&
        clampedOffsets.Vertical == 0,
        "Panning must not produce negative scroll offsets.");
}

static void VerifyNoTemporaryFilesRemain(string root)
{
    var temporaryFiles = Directory.GetFiles(
        root,
        "*.tmp",
        SearchOption.AllDirectories);

    Require(
        temporaryFiles.Length == 0,
        "Atomic repository writes must clean up temporary files.");
}

static async Task AssertThrowsAsync<TException>(
    Func<Task> action,
    string failureMessage)
    where TException : Exception
{
    try
    {
        await action();
    }
    catch (TException)
    {
        return;
    }

    throw new InvalidOperationException(failureMessage);
}

static void Require(bool condition, string failureMessage)
{
    if (!condition)
    {
        throw new InvalidOperationException(failureMessage);
    }
}
