using Engo.Domain.Documents;

namespace Engo.Application.Documents;

public interface IDocumentSessionRepository
{
    Task<DocumentSessionSnapshot?> LoadAsync(
        CancellationToken cancellationToken = default);

    Task SaveAsync(
        DocumentSessionSnapshot snapshot,
        CancellationToken cancellationToken = default);
}
