using Engo.Application.Documents;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Navigation;
using Microsoft.UI.Input;
using Windows.Foundation;
using Windows.Storage;

namespace Engo.App.Views;

public sealed partial class ImageViewerPage : Page
{
    private const float MinimumZoomFactor = 0.1f;
    private const float MaximumZoomFactor = 8.0f;
    private const double WheelZoomStep = 1.15;

    private uint? _activePanPointerId;
    private Point _lastPanPosition;
    private bool _fitToViewport = true;

    public ImageViewerPage()
    {
        InitializeComponent();
    }

    protected override async void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);

        if (e.Parameter is string filePath && !string.IsNullOrWhiteSpace(filePath))
        {
            await LoadImageAsync(filePath);
        }
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e)
    {
        _activePanPointerId = null;
        DocumentImage.Source = null;
        base.OnNavigatedFrom(e);
    }

    private async Task LoadImageAsync(string filePath)
    {
        LoadingRing.IsActive = true;
        ErrorInfoBar.IsOpen = false;

        try
        {
            var file = await StorageFile.GetFileFromPathAsync(filePath);
            using var stream = await file.OpenReadAsync();

            var bitmap = new BitmapImage();
            await bitmap.SetSourceAsync(stream);

            DocumentImage.Source = bitmap;
            DocumentImage.Width = bitmap.PixelWidth;
            DocumentImage.Height = bitmap.PixelHeight;

            ImageDimensionsText.Text = $"{bitmap.PixelWidth} × {bitmap.PixelHeight}";
            _fitToViewport = true;

            // Let the page finish its current layout pass before calculating the
            // initial fit scale. SizeChanged will retry if the viewport is not ready yet.
            await Task.Yield();
            ImageScrollViewer.UpdateLayout();
            FitImage();
        }
        catch (Exception exception)
        {
            ErrorInfoBar.Message = exception.Message;
            ErrorInfoBar.IsOpen = true;
        }
        finally
        {
            LoadingRing.IsActive = false;
        }
    }

    private void FitImageButton_Click(object sender, RoutedEventArgs e)
    {
        FitImage();
    }

    private void FitImage()
    {
        if (DocumentImage.Source is null ||
            DocumentImage.Width <= 0 ||
            DocumentImage.Height <= 0 ||
            ImageScrollViewer.ActualWidth <= 0 ||
            ImageScrollViewer.ActualHeight <= 0)
        {
            return;
        }

        var availableWidth = Math.Max(1, ImageScrollViewer.ActualWidth - 32);
        var availableHeight = Math.Max(1, ImageScrollViewer.ActualHeight - 32);
        var fitScale = Math.Min(
            availableWidth / DocumentImage.Width,
            availableHeight / DocumentImage.Height);

        _fitToViewport = true;
        ImageScrollViewer.ChangeView(
            0,
            0,
            (float)Math.Clamp(
                fitScale,
                MinimumZoomFactor,
                MaximumZoomFactor),
            true);
    }

    private void ZoomInButton_Click(object sender, RoutedEventArgs e)
    {
        ZoomAroundViewportCenter(WheelZoomStep);
    }

    private void ZoomOutButton_Click(object sender, RoutedEventArgs e)
    {
        ZoomAroundViewportCenter(1.0 / WheelZoomStep);
    }

    private void ResetZoomButton_Click(object sender, RoutedEventArgs e)
    {
        ZoomAroundViewportCenter(1.0 / ImageScrollViewer.ZoomFactor);
    }

    private void ZoomAroundViewportCenter(double scaleMultiplier)
    {
        if (DocumentImage.Source is null)
        {
            return;
        }

        var currentZoom = ImageScrollViewer.ZoomFactor;
        var nextZoom = (float)Math.Clamp(
            currentZoom * scaleMultiplier,
            MinimumZoomFactor,
            MaximumZoomFactor);

        ApplyZoomAtPoint(
            nextZoom,
            new Point(
                ImageScrollViewer.ActualWidth / 2,
                ImageScrollViewer.ActualHeight / 2));
    }

    private void ApplyZoomAtPoint(float nextZoom, Point anchor)
    {
        var currentZoom = ImageScrollViewer.ZoomFactor;
        if (Math.Abs(nextZoom - currentZoom) < 0.0001)
        {
            return;
        }

        var offsets = ImageViewportMath.CalculateZoomAnchoredOffsets(
            ImageScrollViewer.HorizontalOffset,
            ImageScrollViewer.VerticalOffset,
            anchor.X,
            anchor.Y,
            currentZoom,
            nextZoom);

        _fitToViewport = false;
        ImageScrollViewer.ChangeView(
            offsets.Horizontal,
            offsets.Vertical,
            nextZoom,
            true);
    }

    private void ImageScrollViewer_PointerWheelChanged(
        object sender,
        Microsoft.UI.Xaml.Input.PointerRoutedEventArgs e)
    {
        if (DocumentImage.Source is null)
        {
            return;
        }

        var point = e.GetCurrentPoint(ImageScrollViewer);
        var wheelDelta = point.Properties.MouseWheelDelta;
        if (wheelDelta == 0)
        {
            return;
        }

        var scaleMultiplier = Math.Pow(
            WheelZoomStep,
            wheelDelta / 120.0);
        var nextZoom = (float)Math.Clamp(
            ImageScrollViewer.ZoomFactor * scaleMultiplier,
            MinimumZoomFactor,
            MaximumZoomFactor);

        ApplyZoomAtPoint(nextZoom, point.Position);
        e.Handled = true;
    }

    private void ImageScrollViewer_PointerPressed(
        object sender,
        Microsoft.UI.Xaml.Input.PointerRoutedEventArgs e)
    {
        if (e.Pointer.PointerDeviceType != PointerDeviceType.Mouse)
        {
            return;
        }

        var point = e.GetCurrentPoint(ImageScrollViewer);
        if (!point.Properties.IsLeftButtonPressed)
        {
            return;
        }

        if (!ImageScrollViewer.CapturePointer(e.Pointer))
        {
            return;
        }

        _activePanPointerId = e.Pointer.PointerId;
        _lastPanPosition = point.Position;
        e.Handled = true;
    }

    private void ImageScrollViewer_PointerMoved(
        object sender,
        Microsoft.UI.Xaml.Input.PointerRoutedEventArgs e)
    {
        if (_activePanPointerId != e.Pointer.PointerId)
        {
            return;
        }

        var currentPosition = e.GetCurrentPoint(ImageScrollViewer).Position;
        var pointerDeltaX = currentPosition.X - _lastPanPosition.X;
        var pointerDeltaY = currentPosition.Y - _lastPanPosition.Y;

        if (Math.Abs(pointerDeltaX) < 0.01 &&
            Math.Abs(pointerDeltaY) < 0.01)
        {
            return;
        }

        var offsets = ImageViewportMath.CalculatePanOffsets(
            ImageScrollViewer.HorizontalOffset,
            ImageScrollViewer.VerticalOffset,
            pointerDeltaX,
            pointerDeltaY);

        _fitToViewport = false;
        ImageScrollViewer.ChangeView(
            offsets.Horizontal,
            offsets.Vertical,
            null,
            true);

        _lastPanPosition = currentPosition;
        e.Handled = true;
    }

    private void ImageScrollViewer_PointerReleased(
        object sender,
        Microsoft.UI.Xaml.Input.PointerRoutedEventArgs e)
    {
        EndPan(e, releaseCapture: true);
    }

    private void ImageScrollViewer_PointerCanceled(
        object sender,
        Microsoft.UI.Xaml.Input.PointerRoutedEventArgs e)
    {
        EndPan(e, releaseCapture: true);
    }

    private void ImageScrollViewer_PointerCaptureLost(
        object sender,
        Microsoft.UI.Xaml.Input.PointerRoutedEventArgs e)
    {
        EndPan(e, releaseCapture: false);
    }

    private void EndPan(
        Microsoft.UI.Xaml.Input.PointerRoutedEventArgs e,
        bool releaseCapture)
    {
        if (_activePanPointerId != e.Pointer.PointerId)
        {
            return;
        }

        _activePanPointerId = null;
        if (releaseCapture)
        {
            ImageScrollViewer.ReleasePointerCapture(e.Pointer);
        }

        e.Handled = true;
    }

    private void ImageScrollViewer_SizeChanged(
        object sender,
        SizeChangedEventArgs e)
    {
        if (_fitToViewport)
        {
            FitImage();
        }
    }

    private void ImageScrollViewer_ViewChanged(
        object sender,
        ScrollViewerViewChangedEventArgs e)
    {
        ZoomStatusText.Text =
            $"{Math.Round(ImageScrollViewer.ZoomFactor * 100)}%";
    }
}
