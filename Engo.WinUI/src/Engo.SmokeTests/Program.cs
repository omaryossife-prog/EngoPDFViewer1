using Engo.Application.Documents;
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
    var textFile = Path.Combine(root, "not-a-pdf.txt");
    var missingPdf = Path.Combine(root, "missing.pdf");

    await File.WriteAllTextAsync(firstPdf, "%PDF-1.7\n");
    await File.WriteAllTextAsync(secondPdf, "%PDF-1.7\n");
    await File.WriteAllTextAsync(textFile, "This is not a PDF.");

    await VerifyRecentDocumentsAsync(root, firstPdf, textFile);
    await VerifyDocumentSessionAsync(root, firstPdf, secondPdf, textFile, missingPdf);
    VerifyNoTemporaryFilesRemain(root);

    Console.WriteLine("PASS: recent-document persistence");
    Console.WriteLine("PASS: document-session persistence and path filtering");
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
    string textFile)
{
    var repository = new JsonRecentDocumentsRepository(
        Path.Combine(root, "recent-documents.json"));
    var service = new RecentDocumentsService(repository);

    await service.RecordOpenedAsync(firstPdf);
    await service.RecordOpenedAsync(firstPdf);

    var recent = await service.GetRecentAsync();
    Require(
        recent.Count == 1 &&
        string.Equals(recent[0].FullPath, firstPdf, StringComparison.OrdinalIgnoreCase),
        "Opening the same PDF twice must not create duplicate recent-file entries.");

    await AssertThrowsAsync<NotSupportedException>(
        () => service.RecordOpenedAsync(textFile),
        "The recent-document service must reject unsupported file types.");
}

static async Task VerifyDocumentSessionAsync(
    string root,
    string firstPdf,
    string secondPdf,
    string textFile,
    string missingPdf)
{
    var repository = new JsonDocumentSessionRepository(
        Path.Combine(root, "document-session.json"));
    var service = new DocumentSessionService(repository);

    await service.SaveAsync(
        new[] { firstPdf, textFile, missingPdf, secondPdf },
        secondPdf);

    var restored = await service.LoadAsync();

    Require(restored is not null, "A saved document session must be loadable.");
    Require(
        restored!.OpenFilePaths.SequenceEqual(new[] { firstPdf, secondPdf }, StringComparer.OrdinalIgnoreCase),
        "A session must keep existing PDFs only and preserve their tab order.");
    Require(
        string.Equals(restored.ActiveFilePath, secondPdf, StringComparison.OrdinalIgnoreCase),
        "A session must preserve the active PDF path.");

    await service.SaveAsync(new[] { firstPdf, secondPdf }, textFile);
    var withoutActivePdf = await service.LoadAsync();

    Require(
        withoutActivePdf is not null && withoutActivePdf.ActiveFilePath is null,
        "A non-PDF active path must not be persisted as the selected PDF.");
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
