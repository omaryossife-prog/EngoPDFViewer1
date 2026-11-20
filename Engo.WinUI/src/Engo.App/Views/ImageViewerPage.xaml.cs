using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Navigation;
using Windows.Storage;
using Windows.Storage.Streams;

namespace Engo.App.Views;

public sealed partial class ImageViewerPage : Page
{
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
            ImageScrollViewer.ChangeView(null, null, 1.0f);
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

    private void ZoomInButton_Click(object sender, RoutedEventArgs e)
    {
        var nextZoom = Math.Min(8.0, ImageScrollViewer.ZoomFactor * 1.2);
        ImageScrollViewer.ChangeView(null, null, (float)nextZoom);
    }

    private void ZoomOutButton_Click(object sender, RoutedEventArgs e)
    {
        var nextZoom = Math.Max(0.1, ImageScrollViewer.ZoomFactor / 1.2);
        ImageScrollViewer.ChangeView(null, null, (float)nextZoom);
    }

    private void ResetZoomButton_Click(object sender, RoutedEventArgs e)
    {
        ImageScrollViewer.ChangeView(null, null, 1.0f);
    }

    private void ImageScrollViewer_ViewChanged(
        object sender,
        ScrollViewerViewChangedEventArgs e)
    {
        ZoomStatusText.Text = $"{Math.Round(ImageScrollViewer.ZoomFactor * 100)}%";
    }
}
