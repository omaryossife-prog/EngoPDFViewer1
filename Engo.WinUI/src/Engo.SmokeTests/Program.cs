using Engo.Application.Documents;
using Engo.Domain.Documents;
using Engo.Infrastructure.Persistence;

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
    var textFile = Path.Combine(root, "not-supported.txt");
    var missingPdf = Path.Combine(root, "missing.pdf");

    await File.WriteAllTextAsync(firstPdf, "%PDF-1.7\n");
    await File.WriteAllTextAsync(secondPdf, "%PDF-1.7\n");
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
    VerifyNoTemporaryFilesRemain(root);

    Console.WriteLine("PASS: recent PDF and image persistence");
    Console.WriteLine("PASS: PDF/image session persistence and path filtering");
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
