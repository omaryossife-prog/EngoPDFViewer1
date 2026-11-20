using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;
using Windows.Data.Pdf;
using Windows.Storage;
using Windows.Storage.Streams;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Engo.App.Views;

public sealed partial class PdfViewerPage : Page
{
    private PdfDocument? _document;
    private uint _pageIndex;

    public PdfViewerPage()
    {
        InitializeComponent();
    }

    protected override async void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);

        if (e.Parameter is string filePath && !string.IsNullOrWhiteSpace(filePath))
        {
            await LoadDocumentAsync(filePath);
        }
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e)
    {
        PageImage.Source = null;
        _document?.Dispose();
        _document = null;

        base.OnNavigatedFrom(e);
    }

    private async Task LoadDocumentAsync(string filePath)
    {
        LoadingRing.IsActive = true;
        ErrorInfoBar.IsOpen = false;

        try
        {
            var file = await StorageFile.GetFileFromPathAsync(filePath);
            var loadedDocument = await PdfDocument.LoadFromFileAsync(file);

            _document?.Dispose();
            _document = loadedDocument;
            _pageIndex = 0;

            if (_document.PageCount == 0)
            {
                ShowError("ملف PDF لا يحتوي على صفحات.");
                return;
            }

            await RenderCurrentPageAsync();
        }
        catch (Exception exception)
        {
            ShowError($"تعذّر تحميل ملف PDF: {exception.Message}");
        }
        finally
        {
            LoadingRing.IsActive = false;
            UpdateNavigationButtons();
        }
    }

    private async Task RenderCurrentPageAsync()
    {
        if (_document is null || _document.PageCount == 0)
        {
            return;
        }

        LoadingRing.IsActive = true;
        ErrorInfoBar.IsOpen = false;

        try
        {
            using var page = _document.GetPage(_pageIndex);
            using var stream = new InMemoryRandomAccessStream();

            await page.RenderToStreamAsync(stream);
            stream.Seek(0);

            var bitmap = new BitmapImage();
            await bitmap.SetSourceAsync(stream);

            PageImage.Source = bitmap;
            PageImage.Width = page.Size.Width;
            PageImage.Height = page.Size.Height;

            PageCounter.Text = $"الصفحة {_pageIndex + 1} من {_document.PageCount}";
        }
        catch (Exception exception)
        {
            ShowError($"تعذّر عرض الصفحة: {exception.Message}");
        }
        finally
        {
            LoadingRing.IsActive = false;
            UpdateNavigationButtons();
        }
    }

    private async void PreviousButton_Click(object sender, RoutedEventArgs e)
    {
        if (_document is null || _pageIndex == 0)
        {
            return;
        }

        _pageIndex--;
        await RenderCurrentPageAsync();
    }

    private async void NextButton_Click(object sender, RoutedEventArgs e)
    {
        if (_document is null || _pageIndex + 1 >= _document.PageCount)
        {
            return;
        }

        _pageIndex++;
        await RenderCurrentPageAsync();
    }

    private void UpdateNavigationButtons()
    {
        PreviousButton.IsEnabled = _document is not null && _pageIndex > 0;
        NextButton.IsEnabled = _document is not null && _pageIndex + 1 < _document.PageCount;
    }

    private void ShowError(string message)
    {
        ErrorInfoBar.Message = message;
        ErrorInfoBar.IsOpen = true;
    }
}
