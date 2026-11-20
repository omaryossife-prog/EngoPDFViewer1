namespace Engo.Application.Documents;

/// <summary>
/// Manages the program-wide study-tag catalogue. Names are case-insensitively unique
/// and capped at 32 characters to match the embedded PDF annotation contract.
/// </summary>
public sealed class TagLibraryService
{
    private static readonly string[] DefaultPalette =
    [
        "#F2BD55", "#66C7E8", "#9B8CFF", "#62C98B", "#F08080",
        "#E38BC8", "#7CA8FF", "#C5A65F", "#53C9B5", "#D28A55"
    ];

    private readonly ITagLibraryRepository _repository;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public TagLibraryService(ITagLibraryRepository repository)
    {
        _repository = repository ?? throw new ArgumentNullException(nameof(repository));
    }

    public async Task<TagLibrarySnapshot> GetSnapshotAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            return Normalize(await _repository.LoadAsync(cancellationToken));
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<StudyTag> CreateAsync(
        string name,
        string? colorHex = null,
        CancellationToken cancellationToken = default)
    {
        var cleanName = ValidateName(name);
        var cleanColor = NormalizeColor(colorHex ?? NextColor(await GetSnapshotAsync(cancellationToken), cleanName));

        await _gate.WaitAsync(cancellationToken);
        try
        {
            var snapshot = Normalize(await _repository.LoadAsync(cancellationToken));
            EnsureNameAvailable(snapshot, cleanName);

            var tag = new StudyTag(cleanName, cleanColor);
            snapshot.Tags.Add(tag);
            snapshot.DeletedNames.RemoveAll(value =>
                string.Equals(value, cleanName, StringComparison.OrdinalIgnoreCase));
            RemoveAlias(snapshot.Aliases, cleanName);

            await _repository.SaveAsync(snapshot, cancellationToken);
            return tag;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<StudyTag> RenameAsync(
        string oldName,
        string newName,
        CancellationToken cancellationToken = default)
    {
        var cleanOldName = ValidateName(oldName);
        var cleanNewName = ValidateName(newName);

        await _gate.WaitAsync(cancellationToken);
        try
        {
            var snapshot = Normalize(await _repository.LoadAsync(cancellationToken));
            var index = FindTagIndex(snapshot.Tags, cleanOldName);
            if (index < 0)
            {
                throw new KeyNotFoundException($"The tag '{cleanOldName}' does not exist.");
            }

            if (!string.Equals(cleanOldName, cleanNewName, StringComparison.OrdinalIgnoreCase))
            {
                EnsureNameAvailable(snapshot, cleanNewName);
            }
            else if (string.Equals(cleanOldName, cleanNewName, StringComparison.Ordinal))
            {
                return snapshot.Tags[index];
            }

            var renamed = new StudyTag(cleanNewName, snapshot.Tags[index].ColorHex);
            snapshot.Tags[index] = renamed;

            foreach (var alias in snapshot.Aliases.Keys.ToArray())
            {
                if (string.Equals(snapshot.Aliases[alias], cleanOldName, StringComparison.OrdinalIgnoreCase))
                {
                    snapshot.Aliases[alias] = cleanNewName;
                }
            }

            snapshot.Aliases[cleanOldName] = cleanNewName;
            snapshot.DeletedNames.RemoveAll(value =>
                string.Equals(value, cleanNewName, StringComparison.OrdinalIgnoreCase));

            await _repository.SaveAsync(snapshot, cancellationToken);
            return renamed;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<StudyTag> RecolorAsync(
        string name,
        string colorHex,
        CancellationToken cancellationToken = default)
    {
        var cleanName = ValidateName(name);
        var cleanColor = NormalizeColor(colorHex);

        await _gate.WaitAsync(cancellationToken);
        try
        {
            var snapshot = Normalize(await _repository.LoadAsync(cancellationToken));
            var index = FindTagIndex(snapshot.Tags, cleanName);
            if (index < 0)
            {
                throw new KeyNotFoundException($"The tag '{cleanName}' does not exist.");
            }

            var updated = snapshot.Tags[index] with { ColorHex = cleanColor };
            snapshot.Tags[index] = updated;
            await _repository.SaveAsync(snapshot, cancellationToken);
            return updated;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task DeleteAsync(
        string name,
        CancellationToken cancellationToken = default)
    {
        var cleanName = ValidateName(name);

        await _gate.WaitAsync(cancellationToken);
        try
        {
            var snapshot = Normalize(await _repository.LoadAsync(cancellationToken));
            var index = FindTagIndex(snapshot.Tags, cleanName);
            if (index < 0)
            {
                throw new KeyNotFoundException($"The tag '{cleanName}' does not exist.");
            }

            snapshot.Tags.RemoveAt(index);

            var tombstones = snapshot.Aliases
                .Where(pair => ResolvesTo(snapshot, pair.Key, cleanName))
                .Select(pair => pair.Key)
                .Append(cleanName)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

            foreach (var tombstone in tombstones)
            {
                if (!snapshot.DeletedNames.Contains(tombstone, StringComparer.OrdinalIgnoreCase))
                {
                    snapshot.DeletedNames.Add(tombstone);
                }
            }

            foreach (var alias in snapshot.Aliases.Keys.ToArray())
            {
                if (string.Equals(snapshot.Aliases[alias], cleanName, StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(alias, cleanName, StringComparison.OrdinalIgnoreCase))
                {
                    snapshot.Aliases.Remove(alias);
                }
            }

            await _repository.SaveAsync(snapshot, cancellationToken);
        }
        finally
        {
            _gate.Release();
        }
    }

    public static string? ResolveName(
        TagLibrarySnapshot snapshot,
        string? embeddedName)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        var candidate = (embeddedName ?? string.Empty).Trim();
        if (candidate.Length == 0 ||
            snapshot.DeletedNames.Contains(candidate, StringComparer.OrdinalIgnoreCase))
        {
            return null;
        }

        var visited = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        while (visited.Add(candidate))
        {
            var alias = snapshot.Aliases.FirstOrDefault(pair =>
                string.Equals(pair.Key, candidate, StringComparison.OrdinalIgnoreCase));
            if (string.IsNullOrWhiteSpace(alias.Key) ||
                string.IsNullOrWhiteSpace(alias.Value))
            {
                break;
            }

            candidate = alias.Value.Trim();
        }

        if (snapshot.DeletedNames.Contains(candidate, StringComparer.OrdinalIgnoreCase))
        {
            return null;
        }

        return snapshot.Tags.FirstOrDefault(tag =>
            string.Equals(tag.Name, candidate, StringComparison.OrdinalIgnoreCase))?.Name;
    }

    public static string? ResolveColor(
        TagLibrarySnapshot snapshot,
        string? embeddedName)
    {
        var canonical = ResolveName(snapshot, embeddedName);
        return canonical is null
            ? null
            : snapshot.Tags.First(tag =>
                string.Equals(tag.Name, canonical, StringComparison.OrdinalIgnoreCase)).ColorHex;
    }

    public static string NormalizeColor(string colorHex)
    {
        if (string.IsNullOrWhiteSpace(colorHex))
        {
            throw new ArgumentException("A tag color is required.", nameof(colorHex));
        }

        var normalized = colorHex.Trim().ToUpperInvariant();
        if (normalized.Length != 7 ||
            normalized[0] != '#' ||
            !normalized.AsSpan(1).ToArray().All(Uri.IsHexDigit))
        {
            throw new ArgumentException("Tag colors must use #RRGGBB format.", nameof(colorHex));
        }

        return normalized;
    }

    private static string ValidateName(string name)
    {
        var normalized = (name ?? string.Empty).Trim();
        if (normalized.Length == 0)
        {
            throw new ArgumentException("A tag name is required.", nameof(name));
        }

        if (normalized.Length > 32)
        {
            throw new ArgumentException("Tag names may contain at most 32 characters.", nameof(name));
        }

        if (normalized.Any(char.IsControl))
        {
            throw new ArgumentException("Tag names cannot contain control characters.", nameof(name));
        }

        return normalized;
    }

    private static void EnsureNameAvailable(TagLibrarySnapshot snapshot, string name)
    {
        if (FindTagIndex(snapshot.Tags, name) >= 0)
        {
            throw new InvalidOperationException($"A tag named '{name}' already exists.");
        }
    }

    private static int FindTagIndex(IReadOnlyList<StudyTag> tags, string name)
    {
        for (var index = 0; index < tags.Count; index++)
        {
            if (string.Equals(tags[index].Name, name, StringComparison.OrdinalIgnoreCase))
            {
                return index;
            }
        }

        return -1;
    }

    private static bool ResolvesTo(
        TagLibrarySnapshot snapshot,
        string source,
        string target)
    {
        var candidate = source;
        var visited = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        while (visited.Add(candidate))
        {
            if (string.Equals(candidate, target, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }

            var pair = snapshot.Aliases.FirstOrDefault(item =>
                string.Equals(item.Key, candidate, StringComparison.OrdinalIgnoreCase));
            if (string.IsNullOrWhiteSpace(pair.Key) || string.IsNullOrWhiteSpace(pair.Value))
            {
                return false;
            }

            candidate = pair.Value;
        }

        return false;
    }

    private static void RemoveAlias(Dictionary<string, string> aliases, string name)
    {
        foreach (var key in aliases.Keys.Where(key =>
                     string.Equals(key, name, StringComparison.OrdinalIgnoreCase)).ToArray())
        {
            aliases.Remove(key);
        }
    }

    private static TagLibrarySnapshot Normalize(TagLibrarySnapshot? source)
    {
        if (source is null)
        {
            return TagLibrarySnapshot.Empty();
        }

        var tags = new List<StudyTag>();
        foreach (var entry in source.Tags ?? [])
        {
            try
            {
                var name = ValidateName(entry.Name);
                if (FindTagIndex(tags, name) >= 0)
                {
                    continue;
                }

                tags.Add(new StudyTag(name, NormalizeColor(entry.ColorHex)));
            }
            catch (ArgumentException)
            {
                // Ignore malformed persisted entries without breaking the reader.
            }
        }

        var aliases = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var pair in source.Aliases ?? [])
        {
            var alias = pair.Key.Trim();
            var target = pair.Value.Trim();
            if (alias.Length > 0 && target.Length > 0 &&
                alias.Length <= 32 && target.Length <= 32)
            {
                aliases[alias] = target;
            }
        }

        var deleted = (source.DeletedNames ?? [])
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        return new TagLibrarySnapshot(tags, aliases, deleted);
    }

    private static string NextColor(TagLibrarySnapshot snapshot, string name)
    {
        var hash = StringComparer.OrdinalIgnoreCase.GetHashCode(name) & int.MaxValue;
        return DefaultPalette[(snapshot.Tags.Count + hash) % DefaultPalette.Length];
    }
}
