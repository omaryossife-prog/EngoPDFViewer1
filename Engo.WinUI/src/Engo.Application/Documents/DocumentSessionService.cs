using Engo.Domain.Documents;

namespace Engo.Application.Documents;

public sealed class DocumentSessionService
{
    private readonly IDocumentSessionRepository _repository;
    private readonly TimeProvider _timeProvider;

    public DocumentSessionService(
        IDocumentSessionRepository repository,
        TimeProvider? timeProvider = null)
    {
        _repository = repository ?? throw new ArgumentNullException(nameof(repository));
        _timeProvider = timeProvider ?? TimeProvider.System;
    }

    public Task<DocumentSessionSnapshot?> LoadAsync(
        CancellationToken cancellationToken = default) =>
        _repository.LoadAsync(cancellationToken);

    public Task SaveAsync(
        IEnumerable<string> openFilePaths,
        string? activeFilePath,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(openFilePaths);

        var normalizedPaths = openFilePaths
            .Where(path => !string.IsNullOrWhiteSpace(path))
            .Select(Path.GetFullPath)
            .Where(File.Exists)
            .Where(IsSupportedSessionDocument)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        var normalizedActivePath = string.IsNullOrWhiteSpace(activeFilePath)
            ? null
            : Path.GetFullPath(activeFilePath);

        if (normalizedActivePath is not null &&
            !normalizedPaths.Contains(normalizedActivePath, StringComparer.OrdinalIgnoreCase))
        {
            normalizedActivePath = null;
        }

        var snapshot = new DocumentSessionSnapshot(
            normalizedPaths,
            normalizedActivePath,
            _timeProvider.GetUtcNow());

        return _repository.SaveAsync(snapshot, cancellationToken);
    }

    private static bool IsSupportedSessionDocument(string path) =>
        Path.GetExtension(path).ToLowerInvariant() switch
        {
            ".pdf" => true,
            ".png" or ".jpg" or ".jpeg" or ".bmp" or ".gif" or ".tif" or ".tiff"
                => true,
            _ => false
        };
}
