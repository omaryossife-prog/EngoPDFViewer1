using Engo.Domain.Documents;

namespace Engo.Application.Documents;

public sealed record OfficeDocumentPage(
    string Label,
    string HtmlFilePath);

public sealed record OfficeDocumentPreview(
    string SourcePath,
    DocumentKind Kind,
    string PreviewDirectory,
    IReadOnlyList<OfficeDocumentPage> Pages);
