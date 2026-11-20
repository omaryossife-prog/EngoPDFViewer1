using Microsoft.UI.Xaml.Media.Imaging;

namespace Engo.App.Views;

public sealed record PdfPageThumbnailItem(
    uint PageIndex,
    string PageLabel,
    BitmapImage Thumbnail);
