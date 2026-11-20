using System.Text.Json;
using Engo.Application.Documents;
using Engo.Domain.Documents;

namespace Engo.Infrastructure.Persistence;

public sealed class JsonRecentDocumentsRepository : IRecentDocumentsRepository
{
    private const int MaximumEntries = 100;

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true
    };

    private readonly string _filePath;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public JsonRecentDocumentsRepository(string? filePath = null)
    {
        _filePath = Path.GetFullPath(filePath ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Engo",
            "Engo.WinUI",
            "recent-documents.json"));
    }

    public async Task<IReadOnlyList<DocumentReference>> GetRecentAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var documents = await LoadUnsafeAsync(cancellationToken);
            return documents
                .OrderByDescending(document => document.LastOpenedUtc)
                .ToArray();
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task UpsertAsync(
        DocumentReference document,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(document);

        await _gate.WaitAsync(cancellationToken);
        try
        {
            var documents = await LoadUnsafeAsync(cancellationToken);
            documents.RemoveAll(existing =>
                existing.Id == document.Id ||
                string.Equals(existing.FullPath, document.FullPath, StringComparison.OrdinalIgnoreCase));

            documents.Add(document);

            var trimmed = documents
                .OrderByDescending(item => item.LastOpenedUtc)
                .Take(MaximumEntries)
                .ToList();

            await SaveUnsafeAsync(trimmed, cancellationToken);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task RemoveAsync(
        Guid documentId,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var documents = await LoadUnsafeAsync(cancellationToken);
            var removed = documents.RemoveAll(document => document.Id == documentId) > 0;

            if (removed)
            {
                await SaveUnsafeAsync(documents, cancellationToken);
            }
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task<List<DocumentReference>> LoadUnsafeAsync(
        CancellationToken cancellationToken)
    {
        if (!File.Exists(_filePath))
        {
            return [];
        }

        await using var stream = new FileStream(
            _filePath,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            bufferSize: 16 * 1024,
            options: FileOptions.Asynchronous | FileOptions.SequentialScan);

        return await JsonSerializer.DeserializeAsync<List<DocumentReference>>(
            stream,
            JsonOptions,
            cancellationToken) ?? [];
    }

    private async Task SaveUnsafeAsync(
        List<DocumentReference> documents,
        CancellationToken cancellationToken)
    {
        var directory = Path.GetDirectoryName(_filePath)
            ?? throw new InvalidOperationException("The recent-documents storage path has no parent directory.");

        Directory.CreateDirectory(directory);

        var temporaryPath = $"{_filePath}.{Guid.NewGuid():N}.tmp";
        try
        {
            await using (var stream = new FileStream(
                temporaryPath,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None,
                bufferSize: 16 * 1024,
                options: FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                await JsonSerializer.SerializeAsync(
                    stream,
                    documents,
                    JsonOptions,
                    cancellationToken);
                await stream.FlushAsync(cancellationToken);
            }

            File.Move(temporaryPath, _filePath, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporaryPath))
            {
                File.Delete(temporaryPath);
            }
        }
    }
}
