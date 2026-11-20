namespace Engo.Application.Documents;

public interface IPdfMergeService
{
    Task<int> MergeAsync(
        IReadOnlyList<string> sourcePdfPaths,
        string destinationPdfPath,
        CancellationToken cancellationToken = default);
}
