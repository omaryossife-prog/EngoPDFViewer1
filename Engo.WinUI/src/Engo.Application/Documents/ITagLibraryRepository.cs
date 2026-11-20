namespace Engo.Application.Documents;

public interface ITagLibraryRepository
{
    Task<TagLibrarySnapshot> LoadAsync(
        CancellationToken cancellationToken = default);

    Task SaveAsync(
        TagLibrarySnapshot snapshot,
        CancellationToken cancellationToken = default);
}
