namespace Engo.Application.Documents;

/// <summary>
/// Shared tag catalogue metadata. PDF region assignments remain embedded in each PDF.
/// Aliases allow tags renamed in the app to keep resolving in older files.
/// </summary>
public sealed record TagLibrarySnapshot(
    List<StudyTag> Tags,
    Dictionary<string, string> Aliases,
    List<string> DeletedNames)
{
    public static TagLibrarySnapshot Empty() => new([], [], []);
}
