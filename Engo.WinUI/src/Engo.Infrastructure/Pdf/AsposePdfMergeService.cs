using Aspose.Pdf;
using Engo.Application.Documents;
using PdfDocument = Aspose.Pdf.Document;

namespace Engo.Infrastructure.Pdf;

public sealed class AsposePdfMergeService : IPdfMergeService
{
    public Task<int> MergeAsync(
        IReadOnlyList<string> sourcePdfPaths,
        string destinationPdfPath,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(sourcePdfPaths);
        ArgumentException.ThrowIfNullOrWhiteSpace(destinationPdfPath);

        if (sourcePdfPaths.Count < 2)
        {
            throw new ArgumentException(
                "Select at least two PDF files to merge.",
                nameof(sourcePdfPaths));
        }

        var sources = sourcePdfPaths
            .Select(Path.GetFullPath)
            .ToArray();

        if (sources.Any(path => !File.Exists(path)))
        {
            var missingPath = sources.First(path => !File.Exists(path));
            throw new FileNotFoundException(
                "One of the selected PDF files no longer exists.",
                missingPath);
        }

        var duplicatePath = sources
            .GroupBy(path => path, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(group => group.Count() > 1);

        if (duplicatePath is not null)
        {
            throw new ArgumentException(
                "The same PDF file was selected more than once.",
                nameof(sourcePdfPaths));
        }

        var destination = Path.GetFullPath(destinationPdfPath);
        if (sources.Contains(destination, StringComparer.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "The merged output cannot overwrite one of the selected source PDFs.");
        }

        if (!string.Equals(
                Path.GetExtension(destination),
                ".pdf",
                StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                "The output file must use the .pdf extension.",
                nameof(destinationPdfPath));
        }

        return Task.Run(
            () => MergeCore(sources, destination, cancellationToken),
            cancellationToken);
    }

    private static int MergeCore(
        IReadOnlyList<string> sourcePaths,
        string destinationPath,
        CancellationToken cancellationToken)
    {
        var openedDocuments = new List<PdfDocument>(sourcePaths.Count);
        PdfDocument? mergedDocument = null;

        try
        {
            foreach (var sourcePath in sourcePaths)
            {
                cancellationToken.ThrowIfCancellationRequested();
                openedDocuments.Add(PdfDocument.Open(sourcePath));
            }

            cancellationToken.ThrowIfCancellationRequested();

            mergedDocument = PdfDocument.Create();
            mergedDocument.Merge(openedDocuments.ToArray());

            var pageCount = mergedDocument.PageCount;
            if (pageCount <= 0)
            {
                throw new InvalidDataException(
                    "The merged PDF did not contain any pages.");
            }

            cancellationToken.ThrowIfCancellationRequested();

            var directory = Path.GetDirectoryName(destinationPath);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            // Write a complete temporary PDF beside the destination, then replace
            // it atomically. If serialization fails, the previous file is retained.
            var temporaryPath = $"{destinationPath}.{Guid.NewGuid():N}.tmp";
            try
            {
                mergedDocument.Save(temporaryPath);
                cancellationToken.ThrowIfCancellationRequested();

                File.Move(temporaryPath, destinationPath, overwrite: true);
            }
            finally
            {
                if (File.Exists(temporaryPath))
                {
                    File.Delete(temporaryPath);
                }
            }

            return pageCount;
        }
        finally
        {
            mergedDocument?.Dispose();

            foreach (var document in openedDocuments)
            {
                document.Dispose();
            }
        }
    }
}
