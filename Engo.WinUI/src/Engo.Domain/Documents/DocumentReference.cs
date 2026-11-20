namespace Engo.Domain.Documents;

public enum DocumentKind
{
    Pdf,
    Word,
    PowerPoint,
    Image,
    Unknown
}

public sealed record DocumentReference(
    Guid Id,
    string FullPath,
    string DisplayName,
    DocumentKind Kind,
    DateTimeOffset LastOpenedUtc);
