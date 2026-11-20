using Engo.Application.Documents;

namespace Engo.Application.Documents;

public static class PdfAnnotationHitTester
{
    public static int FindTopmostHitIndex(
        IReadOnlyList<PdfAnnotationDraft> annotations,
        PdfAnnotationPoint target,
        double edgeTolerance = 0.008,
        double strokeTolerance = 0.014)
    {
        ArgumentNullException.ThrowIfNull(annotations);
        ArgumentNullException.ThrowIfNull(target);

        ValidateRatio(target.XRatio, nameof(target.XRatio));
        ValidateRatio(target.YRatio, nameof(target.YRatio));

        if (!double.IsFinite(edgeTolerance) || edgeTolerance < 0 ||
            !double.IsFinite(strokeTolerance) || strokeTolerance < 0)
        {
            throw new ArgumentOutOfRangeException(
                nameof(edgeTolerance),
                "Hit-test tolerances must be finite non-negative values.");
        }

        // Newer drafts are drawn later and visually sit on top of earlier ones.
        for (var index = annotations.Count - 1; index >= 0; index--)
        {
            var annotation = annotations[index];
            var hit = annotation.Kind == PdfAnnotationKind.Freehand
                ? IsNearStroke(target, annotation.StrokePoints, strokeTolerance)
                : IsInsideExpandedBounds(target, annotation, edgeTolerance);

            if (hit)
            {
                return index;
            }
        }

        return -1;
    }

    private static bool IsInsideExpandedBounds(
        PdfAnnotationPoint target,
        PdfAnnotationDraft annotation,
        double tolerance) =>
        target.XRatio >= annotation.LeftRatio - tolerance &&
        target.XRatio <= annotation.RightRatio + tolerance &&
        target.YRatio >= annotation.TopRatio - tolerance &&
        target.YRatio <= annotation.BottomRatio + tolerance;

    private static bool IsNearStroke(
        PdfAnnotationPoint target,
        IReadOnlyList<PdfAnnotationPoint> points,
        double tolerance)
    {
        if (points.Count == 0)
        {
            return false;
        }

        var toleranceSquared = tolerance * tolerance;

        if (points.Count == 1)
        {
            return DistanceSquared(target, points[0]) <= toleranceSquared;
        }

        for (var index = 1; index < points.Count; index++)
        {
            var start = points[index - 1];
            var end = points[index];
            var deltaX = end.XRatio - start.XRatio;
            var deltaY = end.YRatio - start.YRatio;
            var lengthSquared = (deltaX * deltaX) + (deltaY * deltaY);

            var projection = lengthSquared <= double.Epsilon
                ? 0
                : Math.Clamp(
                    ((target.XRatio - start.XRatio) * deltaX +
                     (target.YRatio - start.YRatio) * deltaY) / lengthSquared,
                    0,
                    1);

            var closest = new PdfAnnotationPoint(
                start.XRatio + (projection * deltaX),
                start.YRatio + (projection * deltaY));

            if (DistanceSquared(target, closest) <= toleranceSquared)
            {
                return true;
            }
        }

        return false;
    }

    private static double DistanceSquared(
        PdfAnnotationPoint first,
        PdfAnnotationPoint second)
    {
        var deltaX = first.XRatio - second.XRatio;
        var deltaY = first.YRatio - second.YRatio;
        return (deltaX * deltaX) + (deltaY * deltaY);
    }

    private static void ValidateRatio(double value, string parameterName)
    {
        if (!double.IsFinite(value) || value < 0 || value > 1)
        {
            throw new ArgumentOutOfRangeException(
                parameterName,
                "Annotation hit-test coordinates must be ratios between 0 and 1.");
        }
    }
}
