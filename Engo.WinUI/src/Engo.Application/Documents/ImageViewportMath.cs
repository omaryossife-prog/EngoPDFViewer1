namespace Engo.Application.Documents;

/// <summary>
/// Represents scroll offsets in the image viewport, measured in view coordinates.
/// </summary>
public readonly record struct ImageViewportOffset(
    double Horizontal,
    double Vertical);

/// <summary>
/// Contains deterministic viewport calculations shared by the image viewer and smoke tests.
/// </summary>
public static class ImageViewportMath
{
    /// <summary>
    /// Calculates new scroll offsets that keep the image point under the pointer stationary
    /// while changing the viewport zoom factor.
    /// </summary>
    public static ImageViewportOffset CalculateZoomAnchoredOffsets(
        double horizontalOffset,
        double verticalOffset,
        double pointerX,
        double pointerY,
        double currentZoomFactor,
        double nextZoomFactor)
    {
        EnsureFinite(horizontalOffset, nameof(horizontalOffset));
        EnsureFinite(verticalOffset, nameof(verticalOffset));
        EnsureFinite(pointerX, nameof(pointerX));
        EnsureFinite(pointerY, nameof(pointerY));
        EnsurePositiveFinite(currentZoomFactor, nameof(currentZoomFactor));
        EnsurePositiveFinite(nextZoomFactor, nameof(nextZoomFactor));

        var imagePointX = (horizontalOffset + pointerX) / currentZoomFactor;
        var imagePointY = (verticalOffset + pointerY) / currentZoomFactor;

        return new ImageViewportOffset(
            Math.Max(0, imagePointX * nextZoomFactor - pointerX),
            Math.Max(0, imagePointY * nextZoomFactor - pointerY));
    }

    /// <summary>
    /// Converts pointer movement into scroll offsets. Dragging the pointer to the right
    /// moves the image to the right by reducing the horizontal scroll offset (and likewise
    /// for vertical movement).
    /// </summary>
    public static ImageViewportOffset CalculatePanOffsets(
        double horizontalOffset,
        double verticalOffset,
        double pointerDeltaX,
        double pointerDeltaY)
    {
        EnsureFinite(horizontalOffset, nameof(horizontalOffset));
        EnsureFinite(verticalOffset, nameof(verticalOffset));
        EnsureFinite(pointerDeltaX, nameof(pointerDeltaX));
        EnsureFinite(pointerDeltaY, nameof(pointerDeltaY));

        return new ImageViewportOffset(
            Math.Max(0, horizontalOffset - pointerDeltaX),
            Math.Max(0, verticalOffset - pointerDeltaY));
    }

    private static void EnsureFinite(double value, string parameterName)
    {
        if (!double.IsFinite(value))
        {
            throw new ArgumentOutOfRangeException(
                parameterName,
                "The value must be a finite number.");
        }
    }

    private static void EnsurePositiveFinite(double value, string parameterName)
    {
        if (!double.IsFinite(value) || value <= 0)
        {
            throw new ArgumentOutOfRangeException(
                parameterName,
                "The zoom factor must be a positive, finite number.");
        }
    }
}
