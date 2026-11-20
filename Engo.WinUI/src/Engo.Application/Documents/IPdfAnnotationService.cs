namespace Engo.Application.Documents;

public interface IPdfAnnotationService
{
    Task SaveAnnotatedCopyAsync(
        string sourcePdfPath,
        string destinationPdfPath,
        IReadOnlyList<PdfAnnotationDraft> annotations,
        CancellationToken cancellationToken = default);
}
