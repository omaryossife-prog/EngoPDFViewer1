using System.Text.Json;
using Engo.Application.Documents;

namespace Engo.Infrastructure.Persistence;

public sealed class JsonTagLibraryRepository : ITagLibraryRepository
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true
    };

    private readonly string _filePath;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public JsonTagLibraryRepository(string? filePath = null)
    {
        _filePath = Path.GetFullPath(filePath ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Engo",
            "Engo.WinUI",
            "tag-library.json"));
    }

    public async Task<TagLibrarySnapshot> LoadAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            if (!File.Exists(_filePath))
            {
                return TagLibrarySnapshot.Empty();
            }

            await using var stream = new FileStream(
                _filePath,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 8 * 1024,
                options: FileOptions.Asynchronous | FileOptions.SequentialScan);

            return await JsonSerializer.DeserializeAsync<TagLibrarySnapshot>(
                       stream,
                       JsonOptions,
                       cancellationToken)
                   ?? TagLibrarySnapshot.Empty();
        }
        catch (JsonException exception)
        {
            throw new InvalidDataException(
                "The tag library file contains invalid JSON. It was not overwritten.",
                exception);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task SaveAsync(
        TagLibrarySnapshot snapshot,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(snapshot);

        await _gate.WaitAsync(cancellationToken);
        try
        {
            var directory = Path.GetDirectoryName(_filePath)
                ?? throw new InvalidOperationException("The tag-library storage path has no parent directory.");
            Directory.CreateDirectory(directory);

            var temporaryPath = $"{_filePath}.{Guid.NewGuid():N}.tmp";
            try
            {
                await using (var stream = new FileStream(
                    temporaryPath,
                    FileMode.CreateNew,
                    FileAccess.Write,
                    FileShare.None,
                    bufferSize: 8 * 1024,
                    options: FileOptions.Asynchronous | FileOptions.WriteThrough))
                {
                    await JsonSerializer.SerializeAsync(
                        stream,
                        snapshot,
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
        finally
        {
            _gate.Release();
        }
    }
}
