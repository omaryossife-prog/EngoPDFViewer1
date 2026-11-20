namespace Engo.Application.Documents;

public interface IPdfTextService
{
    Task<IReadOnlyList<PdfPageText>> ExtractAllPagesAsync(
        string filePath,
        CancellationToken cancellationToken = default);

    Task<string> ExtractPageTextAsync(
        string filePath,
        int pageNumber,
        CancellationToken cancellationToken = default);

    Task<IReadOnlyList<PdfTextSearchHit>> SearchAsync(
        string filePath,
        string query,
        CancellationToken cancellationToken = default);
}
