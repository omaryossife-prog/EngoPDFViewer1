using Aspose.Pdf;
using Engo.Application.Documents;
using PdfDocument = Aspose.Pdf.Document;

namespace Engo.Infrastructure.Pdf;

public sealed class AsposePdfAnnotationService : IPdfAnnotationService
{
    public async Task SaveAnnotatedCopyAsync(
        string sourcePdfPath,
        string destinationPdfPath,
        IReadOnlyList<PdfAnnotationDraft> annotations,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourcePdfPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(destinationPdfPath);
        ArgumentNullException.ThrowIfNull(annotations);

        var sourcePath = Path.GetFullPath(sourcePdfPath);
        var destinationPath = Path.GetFullPath(destinationPdfPath);

        if (!File.Exists(sourcePath))
        {
            throw new FileNotFoundException("The source PDF could not be found.", sourcePath);
        }

        if (string.Equals(sourcePath, destinationPath, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "Annotations are saved to a separate copy. The source PDF is never overwritten.");
        }

        if (!string.Equals(
                Path.GetExtension(destinationPath),
                ".pdf",
                StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("The destination file must use the .pdf extension.", nameof(destinationPdfPath));
        }

        if (annotations.Count == 0)
        {
            throw new InvalidOperationException("There are no annotations to save.");
        }

        await Task.Run(() =>
        {
            cancellationToken.ThrowIfCancellationRequested();

            using var document = PdfDocument.Open(sourcePath);

            foreach (var draft in annotations)
            {
                cancellationToken.ThrowIfCancellationRequested();
                ApplyAnnotation(document, draft);
            }

            using var output = new MemoryStream();
            document.Save(output);
            cancellationToken.ThrowIfCancellationRequested();

            var directory = Path.GetDirectoryName(destinationPath);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            // Write beside the destination and replace it only after a complete
            // PDF has been serialized, so a failed write cannot leave a partial file.
            var temporaryPath = $"{destinationPath}.{Guid.NewGuid():N}.tmp";
            try
            {
                File.WriteAllBytes(temporaryPath, output.ToArray());
                File.Move(temporaryPath, destinationPath, overwrite: true);
            }
            finally
            {
                if (File.Exists(temporaryPath))
                {
                    File.Delete(temporaryPath);
                }
            }
        }, cancellationToken);
    }

    private static void ApplyAnnotation(
        PdfDocument document,
        PdfAnnotationDraft draft)
    {
        if (draft.PageNumber < 1 || draft.PageNumber > document.Pages.Count)
        {
            throw new ArgumentOutOfRangeException(
                nameof(draft.PageNumber),
                $"Page {draft.PageNumber} is outside the document.");
        }

        ValidateRatio(draft.LeftRatio, nameof(draft.LeftRatio));
        ValidateRatio(draft.TopRatio, nameof(draft.TopRatio));
        ValidateRatio(draft.RightRatio, nameof(draft.RightRatio));
        ValidateRatio(draft.BottomRatio, nameof(draft.BottomRatio));

        if (draft.RightRatio <= draft.LeftRatio ||
            draft.BottomRatio <= draft.TopRatio)
        {
            throw new ArgumentException("Annotation bounds must have positive width and height.");
        }

        var page = document.Pages[draft.PageNumber];
        // Use the visible CropBox rather than assuming that every page starts at (0, 0).
        // PDF viewers display the crop area after page rotation, while annotation
        // coordinates are stored in the page's unrotated PDF user space.
        var visibleBox = page.CropBox;
        var pageLeft = visibleBox.LLX;
        var pageBottom = visibleBox.LLY;
        var pageWidth = visibleBox.URX - visibleBox.LLX;
        var pageHeight = visibleBox.URY - visibleBox.LLY;
        var rotation = ((page.RotateDegrees % 360) + 360) % 360;

        if (rotation is not (0 or 90 or 180 or 270))
        {
            throw new NotSupportedException(
                $"Page rotation {page.RotateDegrees}° is not supported for annotations.");
        }

        if (pageWidth <= 0 || pageHeight <= 0)
        {
            throw new InvalidDataException(
                $"PDF page {draft.PageNumber} has invalid page dimensions.");
        }

        // The UI stores ratios from the displayed page's top-left origin.
        // PDF user space uses the lower-left origin and points (1/72 inch).
        var viewCorners = new[]
        {
            MapViewPointToPdf(draft.LeftRatio, draft.TopRatio, rotation),
            MapViewPointToPdf(draft.RightRatio, draft.TopRatio, rotation),
            MapViewPointToPdf(draft.LeftRatio, draft.BottomRatio, rotation),
            MapViewPointToPdf(draft.RightRatio, draft.BottomRatio, rotation)
        };

        var left = pageLeft + viewCorners.Min(point => point.X) * pageWidth;
        var right = pageLeft + viewCorners.Max(point => point.X) * pageWidth;
        var bottom = pageBottom + viewCorners.Min(point => point.Y) * pageHeight;
        var top = pageBottom + viewCorners.Max(point => point.Y) * pageHeight;

        var rectangle = new Rectangle(left, bottom, right, top);
        var color = NormalizeColor(draft.Color);
        var lineWidth = Math.Clamp(draft.LineWidth, 0.25, 12);

        switch (draft.Kind)
        {
            case PdfAnnotationKind.Highlight:
                // PDF text-markup annotations use four explicit corner points
                // (upper-left, upper-right, lower-left, lower-right). Without
                // QuadPoints some viewers show the annotation rectangle but no
                // visible highlighted region.
                var highlightQuadPoints = new[]
                {
                    left, top,
                    right, top,
                    left, bottom,
                    right, bottom
                };

                page.Annotations.AddHighlightAnnotation(
                    rectangle,
                    quadPoints: highlightQuadPoints,
                    color: color);
                break;

            case PdfAnnotationKind.Rectangle:
                page.Annotations.AddSquareAnnotation(
                    rectangle,
                    borderColor: color,
                    fillColor: null,
                    lineWidth: lineWidth);
                break;

            case PdfAnnotationKind.Freehand:
                ApplyInkAnnotation(
                    page,
                    rectangle,
                    draft,
                    pageLeft,
                    pageBottom,
                    pageWidth,
                    pageHeight,
                    rotation,
                    color,
                    lineWidth);
                break;

            default:
                throw new NotSupportedException(
                    $"Annotation kind '{draft.Kind}' is not supported.");
        }
    }

    private static void ApplyInkAnnotation(
        Page page,
        Rectangle bounds,
        PdfAnnotationDraft draft,
        double pageLeft,
        double pageBottom,
        double pageWidth,
        double pageHeight,
        int rotation,
        double[] color,
        double lineWidth)
    {
        if (draft.StrokePoints is null || draft.StrokePoints.Count < 2)
        {
            throw new ArgumentException(
                "A freehand annotation needs at least two stroke points.");
        }

        var path = new double[draft.StrokePoints.Count * 2];
        for (var index = 0; index < draft.StrokePoints.Count; index++)
        {
            var point = draft.StrokePoints[index];
            ValidateRatio(point.XRatio, nameof(point.XRatio));
            ValidateRatio(point.YRatio, nameof(point.YRatio));

            var mappedPoint = MapViewPointToPdf(
                point.XRatio,
                point.YRatio,
                rotation);

            path[index * 2] = pageLeft + mappedPoint.X * pageWidth;
            path[(index * 2) + 1] = pageBottom + mappedPoint.Y * pageHeight;
        }

        page.Annotations.AddInkAnnotation(
            bounds,
            inkPaths: new[] { path },
            color: color,
            lineWidth: lineWidth);
    }

    private static (double X, double Y) MapViewPointToPdf(
        double viewX,
        double viewYFromTop,
        int clockwiseRotation)
    {
        return clockwiseRotation switch
        {
            0 => (viewX, 1 - viewYFromTop),
            90 => (1 - viewYFromTop, 1 - viewX),
            180 => (1 - viewX, viewYFromTop),
            270 => (viewYFromTop, viewX),
            _ => throw new NotSupportedException(
                $"Page rotation {clockwiseRotation}° is not supported.")
        };
    }

    private static double[] NormalizeColor(PdfAnnotationColor color)
    {
        ArgumentNullException.ThrowIfNull(color);

        return
        [
            Math.Clamp(color.Red, 0, 1),
            Math.Clamp(color.Green, 0, 1),
            Math.Clamp(color.Blue, 0, 1)
        ];
    }

    private static void ValidateRatio(double value, string parameterName)
    {
        if (!double.IsFinite(value) || value < 0 || value > 1)
        {
            throw new ArgumentOutOfRangeException(
                parameterName,
                "Annotation coordinates must be finite ratios between 0 and 1.");
        }
    }
}
