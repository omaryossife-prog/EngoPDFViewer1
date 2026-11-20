using Engo.Domain.Documents;

namespace Engo.Application.Documents;

public interface IRecentDocumentsRepository
{
    Task<IReadOnlyList<DocumentReference>> GetRecentAsync(
        CancellationToken cancellationToken = default);

    Task UpsertAsync(
        DocumentReference document,
        CancellationToken cancellationToken = default);

    Task RemoveAsync(
        Guid documentId,
        CancellationToken cancellationToken = default);
}
