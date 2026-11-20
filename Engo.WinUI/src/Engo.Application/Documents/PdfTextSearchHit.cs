namespace Engo.Application.Documents;

public sealed record PdfTextSearchHit(
    int PageNumber,
    string Snippet);
