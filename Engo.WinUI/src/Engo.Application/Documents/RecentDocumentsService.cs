using Engo.Domain.Documents;

namespace Engo.Application.Documents;

public sealed class RecentDocumentsService
{
    private readonly IRecentDocumentsRepository _repository;
    private readonly TimeProvider _timeProvider;

    public RecentDocumentsService(
        IRecentDocumentsRepository repository,
        TimeProvider? timeProvider = null)
    {
        _repository = repository ?? throw new ArgumentNullException(nameof(repository));
        _timeProvider = timeProvider ?? TimeProvider.System;
    }

    public Task<IReadOnlyList<DocumentReference>> GetRecentAsync(
        CancellationToken cancellationToken = default) =>
        _repository.GetRecentAsync(cancellationToken);

    public async Task<DocumentReference> RecordOpenedAsync(
        string filePath,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(filePath);

        var fullPath = Path.GetFullPath(filePath);
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException("The selected document no longer exists.", fullPath);
        }

        var kind = Classify(fullPath);
        if (kind == DocumentKind.Unknown)
        {
            throw new NotSupportedException($"The file type '{Path.GetExtension(fullPath)}' is not supported.");
        }

        var document = new DocumentReference(
            Guid.NewGuid(),
            fullPath,
            Path.GetFileName(fullPath),
            kind,
            _timeProvider.GetUtcNow());

        await _repository.UpsertAsync(document, cancellationToken);
        return document;
    }

    public Task RemoveAsync(
        Guid documentId,
        CancellationToken cancellationToken = default) =>
        _repository.RemoveAsync(documentId, cancellationToken);

    private static DocumentKind Classify(string fullPath) =>
        Path.GetExtension(fullPath).ToLowerInvariant() switch
        {
            ".pdf" => DocumentKind.Pdf,
            ".docx" => DocumentKind.Word,
            ".pptx" => DocumentKind.PowerPoint,
            ".png" or ".jpg" or ".jpeg" or ".bmp" or ".gif" or ".webp" or ".tif" or ".tiff"
                => DocumentKind.Image,
            _ => DocumentKind.Unknown
        };
}
