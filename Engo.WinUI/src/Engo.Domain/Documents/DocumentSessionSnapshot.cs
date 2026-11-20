namespace Engo.Domain.Documents;

public sealed record DocumentSessionSnapshot(
    IReadOnlyList<string> OpenFilePaths,
    string? ActiveFilePath,
    DateTimeOffset SavedAtUtc);
