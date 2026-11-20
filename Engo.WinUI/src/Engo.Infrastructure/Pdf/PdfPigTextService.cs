using Engo.Application.Documents;
using UglyToad.PdfPig.DocumentLayoutAnalysis.TextExtractor;
using PdfPigDocument = UglyToad.PdfPig.PdfDocument;

namespace Engo.Infrastructure.Pdf;

public sealed class PdfPigTextService : IPdfTextService
{
    private const int MaximumSearchHits = 500;
    private const int SnippetContextCharacters = 72;

    public Task<IReadOnlyList<PdfPageText>> ExtractAllPagesAsync(
        string filePath,
        CancellationToken cancellationToken = default)
    {
        ValidatePath(filePath);

        return Task.Run<IReadOnlyList<PdfPageText>>(
            () => ExtractAllPages(filePath, cancellationToken),
            cancellationToken);
    }

    public Task<string> ExtractPageTextAsync(
        string filePath,
        int pageNumber,
        CancellationToken cancellationToken = default)
    {
        ValidatePath(filePath);

        if (pageNumber < 1)
        {
            throw new ArgumentOutOfRangeException(
                nameof(pageNumber),
                "PDF page numbers start at 1.");
        }

        return Task.Run(
            () => ExtractPageText(filePath, pageNumber, cancellationToken),
            cancellationToken);
    }

    public Task<IReadOnlyList<PdfTextSearchHit>> SearchAsync(
        string filePath,
        string query,
        CancellationToken cancellationToken = default)
    {
        ValidatePath(filePath);
        ArgumentException.ThrowIfNullOrWhiteSpace(query);

        return Task.Run<IReadOnlyList<PdfTextSearchHit>>(
            () => Search(filePath, query.Trim(), cancellationToken),
            cancellationToken);
    }

    private static IReadOnlyList<PdfPageText> ExtractAllPages(
        string filePath,
        CancellationToken cancellationToken)
    {
        using var document = PdfPigDocument.Open(filePath);
        var pages = new List<PdfPageText>(document.NumberOfPages);
        var pageNumber = 0;

        foreach (var page in document.GetPages())
        {
            cancellationToken.ThrowIfCancellationRequested();
            pageNumber++;

            pages.Add(new PdfPageText(
                pageNumber,
                ContentOrderTextExtractor.GetText(page)));
        }

        return pages;
    }

    private static string ExtractPageText(
        string filePath,
        int pageNumber,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();

        using var document = PdfPigDocument.Open(filePath);
        if (pageNumber > document.NumberOfPages)
        {
            throw new ArgumentOutOfRangeException(
                nameof(pageNumber),
                $"The document contains only {document.NumberOfPages} pages.");
        }

        cancellationToken.ThrowIfCancellationRequested();

        var page = document.GetPage(pageNumber);
        return ContentOrderTextExtractor.GetText(page);
    }

    private static IReadOnlyList<PdfTextSearchHit> Search(
        string filePath,
        string query,
        CancellationToken cancellationToken)
    {
        using var document = PdfPigDocument.Open(filePath);
        var hits = new List<PdfTextSearchHit>();
        var pageNumber = 0;

        foreach (var page in document.GetPages())
        {
            cancellationToken.ThrowIfCancellationRequested();
            pageNumber++;

            var pageText = ContentOrderTextExtractor.GetText(page);
            if (string.IsNullOrWhiteSpace(pageText))
            {
                continue;
            }

            var normalizedText = NormalizeWhitespace(pageText);
            var searchOffset = 0;

            while (searchOffset < normalizedText.Length)
            {
                cancellationToken.ThrowIfCancellationRequested();

                var matchIndex = normalizedText.IndexOf(
                    query,
                    searchOffset,
                    StringComparison.OrdinalIgnoreCase);

                if (matchIndex < 0)
                {
                    break;
                }

                hits.Add(new PdfTextSearchHit(
                    pageNumber,
                    CreateSnippet(normalizedText, matchIndex, query.Length)));

                if (hits.Count >= MaximumSearchHits)
                {
                    return hits;
                }

                searchOffset = matchIndex + Math.Max(1, query.Length);
            }
        }

        return hits;
    }

    private static string CreateSnippet(
        string text,
        int matchIndex,
        int matchLength)
    {
        var start = Math.Max(0, matchIndex - SnippetContextCharacters);
        var end = Math.Min(
            text.Length,
            matchIndex + matchLength + SnippetContextCharacters);

        var snippet = text[start..end].Trim();

        if (start > 0)
        {
            snippet = $"…{snippet}";
        }

        if (end < text.Length)
        {
            snippet = $"{snippet}…";
        }

        return snippet;
    }

    private static string NormalizeWhitespace(string text) =>
        string.Join(
            ' ',
            text.Split(
                (char[]?)null,
                StringSplitOptions.RemoveEmptyEntries));

    private static void ValidatePath(string filePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(filePath);

        if (!File.Exists(filePath))
        {
            throw new FileNotFoundException(
                "The PDF file could not be found.",
                filePath);
        }
    }
}
