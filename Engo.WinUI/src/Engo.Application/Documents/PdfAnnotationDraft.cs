namespace Engo.Application.Documents;

/// <summary>
/// A page annotation draft. All geometry is normalized to the displayed page:
/// X/Y ratios are in the inclusive range 0..1 with the origin at the top-left.
/// </summary>
public sealed record PdfAnnotationDraft(
    int PageNumber,
    PdfAnnotationKind Kind,
    double LeftRatio,
    double TopRatio,
    double RightRatio,
    double BottomRatio,
    IReadOnlyList<PdfAnnotationPoint> StrokePoints,
    string? Contents,
    PdfAnnotationColor Color,
    double LineWidth);
