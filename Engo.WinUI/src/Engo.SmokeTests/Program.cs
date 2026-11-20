using Engo.Application.Documents;
using Engo.Domain.Documents;
using Aspose.Pdf;
using Engo.Infrastructure.Persistence;
using Engo.Infrastructure.Pdf;

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
    var annotationSource = Path.Combine(root, "annotation-source.pdf");
    var annotationOutput = Path.Combine(root, "annotation-output.pdf");
    var textFile = Path.Combine(root, "not-supported.txt");
    var missingPdf = Path.Combine(root, "missing.pdf");

    await File.WriteAllTextAsync(firstPdf, "%PDF-1.7\n");
    await File.WriteAllTextAsync(secondPdf, "%PDF-1.7\n");
    CreateSinglePagePdf(annotationSource);
    await File.WriteAllBytesAsync(imageFile, [0x89, 0x50, 0x4E, 0x47]);
    await File.WriteAllTextAsync(textFile, "This is not a supported document.");

    await VerifyRecentDocumentsAsync(root, firstPdf, imageFile, textFile);
    await VerifyDocumentSessionAsync(
        root,
        firstPdf,
        secondPdf,
        imageFile,
        textFile,
        missingPdf);
    await VerifyPdfAnnotationRoundTripAsync(annotationSource, annotationOutput);
    VerifyNoTemporaryFilesRemain(root);

    Console.WriteLine("PASS: recent PDF and image persistence");
    Console.WriteLine("PASS: PDF/image session persistence and path filtering");
    Console.WriteLine("PASS: PDF annotations save as a separate round-trip-readable copy");
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
    string textFile)
{
    var repository = new JsonRecentDocumentsRepository(
        Path.Combine(root, "recent-documents.json"));
    var service = new RecentDocumentsService(repository);

    await service.RecordOpenedAsync(firstPdf);
    await service.RecordOpenedAsync(firstPdf);
    var image = await service.RecordOpenedAsync(imageFile);

    var recent = await service.GetRecentAsync();
    Require(
        recent.Count == 2 &&
        recent.Count(document => document.Kind == DocumentKind.Pdf) == 1 &&
        recent.Any(document =>
            document.Kind == DocumentKind.Image &&
            string.Equals(document.FullPath, imageFile, StringComparison.OrdinalIgnoreCase)),
        "Recent documents must deduplicate PDFs and retain supported images.");

    Require(image.Kind == DocumentKind.Image, "PNG files must be classified as images.");

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
    string missingPdf)
{
    var repository = new JsonDocumentSessionRepository(
        Path.Combine(root, "document-session.json"));
    var service = new DocumentSessionService(repository);

    await service.SaveAsync(
        new[] { firstPdf, imageFile, textFile, missingPdf, secondPdf },
        imageFile);

    var restored = await service.LoadAsync();

    Require(restored is not null, "A saved document session must be loadable.");
    Require(
        restored!.OpenFilePaths.SequenceEqual(
            new[] { firstPdf, imageFile, secondPdf },
            StringComparer.OrdinalIgnoreCase),
        "A session must retain existing PDFs and images, filter unsupported/missing files, and preserve tab order.");
    Require(
        string.Equals(restored.ActiveFilePath, imageFile, StringComparison.OrdinalIgnoreCase),
        "A session must preserve an active image document.");

    await service.SaveAsync(new[] { firstPdf, imageFile, secondPdf }, textFile);
    var withoutActiveDocument = await service.LoadAsync();

    Require(
        withoutActiveDocument is not null && withoutActiveDocument.ActiveFilePath is null,
        "An unsupported active path must not be persisted as the selected document.");
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
            PdfAnnotationKind.Note,
            0.68, 0.20, 0.73, 0.25,
            [],
            "Annotation smoke test",
            PdfAnnotationColor.Yellow,
            1),
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
            1.5)
    };

    await service.SaveAnnotatedCopyAsync(sourcePath, outputPath, annotations);

    Require(File.Exists(outputPath), "The annotated output PDF must be created.");

    using var original = Aspose.Pdf.Document.Open(sourcePath);
    using var annotated = Aspose.Pdf.Document.Open(outputPath);

    Require(
        original.Pages[1].Annotations.Count == 0,
        "Saving annotations must not modify the source PDF.");

    Require(
        annotated.Pages[1].Annotations.Count == annotations.Length,
        "Highlight, rectangle, note, and ink annotations must survive save and reopen.");

    await AssertThrowsAsync<InvalidOperationException>(
        () => service.SaveAnnotatedCopyAsync(sourcePath, sourcePath, annotations),
        "The annotation service must never overwrite the original source PDF.");
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
