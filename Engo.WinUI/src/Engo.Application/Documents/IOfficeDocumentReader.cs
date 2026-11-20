namespace Engo.Application.Documents;

public interface IOfficeDocumentReader
{
    Task<OfficeDocumentPreview> CreatePreviewAsync(
        string filePath,
        CancellationToken cancellationToken = default);
}
