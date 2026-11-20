using System.Globalization;
using Engo.Application.Documents;
using Engo.Infrastructure.Pdf;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using Microsoft.UI.Xaml.Shapes;
using Windows.Data.Pdf;
using Windows.Globalization;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Windows.Storage;
using Windows.Storage.Pickers;
using Windows.Storage.Streams;
using Windows.UI;
using WinRT.Interop;
using Microsoft.UI.Xaml.Media.Imaging;

namespace Engo.App.Views;

public sealed partial class PdfViewerPage : Page
{
    private readonly IPdfTextService _textService = new PdfPigTextService();
    private readonly IPdfAnnotationService _annotationService = new AsposePdfAnnotationService();
    private readonly List<PdfAnnotationDraft> _pendingAnnotations = [];
    private PdfDocument? _document;
    private CancellationTokenSource? _searchCancellation;
    private string? _filePath;
    private uint _pageIndex;
    private bool _isDrawing;
    private Point _drawingStart;
    private List<Point>? _activeStrokePoints;
    private Polyline? _activePolyline;
    private Microsoft.UI.Xaml.Shapes.Rectangle? _activeRectangle;

    public event EventHandler<string>? AnnotatedCopySaved;

    public PdfViewerPage()
    {
        InitializeComponent();
    }

    protected override async void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);

        if (e.Parameter is string filePath && !string.IsNullOrWhiteSpace(filePath))
        {
            _filePath = filePath;
            await LoadDocumentAsync(filePath);
        }
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e)
    {
        _searchCancellation?.Cancel();
        _searchCancellation?.Dispose();
        _searchCancellation = null;

        PageImage.Source = null;
        AnnotationCanvas.Children.Clear();
        _activeStrokePoints = null;
        _activePolyline = null;
        _activeRectangle = null;
        _document?.Dispose();
        _document = null;

        base.OnNavigatedFrom(e);
    }

    private async Task LoadDocumentAsync(string filePath)
    {
        LoadingRing.IsActive = true;
        ErrorInfoBar.IsOpen = false;
        SearchResultsList.ItemsSource = null;
        SearchResultSummary.Text = "اكتب كلمة أو عبارة للبحث داخل الملف.";
        ExtractedPageText.Text = "استخدم زر استخراج نص الصفحة لعرض النص القابل للاستخراج.";

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
            PdfPageSurface.Width = page.Size.Width;
            PdfPageSurface.Height = page.Size.Height;
            AnnotationCanvas.Width = page.Size.Width;
            AnnotationCanvas.Height = page.Size.Height;
            RedrawPendingAnnotations();

            PageCounter.Text = $"الصفحة {_pageIndex + 1} من {_document.PageCount}";
            PageNumberTextBox.Text = (_pageIndex + 1).ToString(CultureInfo.InvariantCulture);
            ExtractedPageText.Text = "استخدم زر استخراج نص الصفحة لعرض النص القابل للاستخراج.";
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

    private async void GoToPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (_document is null)
        {
            ShowError("افتح ملف PDF أولًا.");
            return;
        }

        var normalizedPageNumber = NormalizeArabicDigits(PageNumberTextBox.Text.Trim());
        if (!uint.TryParse(
                normalizedPageNumber,
                NumberStyles.None,
                CultureInfo.InvariantCulture,
                out var pageNumber) ||
            pageNumber < 1 ||
            pageNumber > _document.PageCount)
        {
            ShowError($"أدخل رقم صفحة من 1 إلى {_document.PageCount}.");
            return;
        }

        _pageIndex = pageNumber - 1;
        await RenderCurrentPageAsync();
    }

    private async void SearchButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_filePath))
        {
            ShowError("افتح ملف PDF أولًا.");
            return;
        }

        var query = SearchTextBox.Text.Trim();
        if (query.Length == 0)
        {
            SearchResultSummary.Text = "اكتب كلمة أو عبارة للبحث داخل الملف.";
            SearchResultsList.ItemsSource = null;
            return;
        }

        _searchCancellation?.Cancel();
        _searchCancellation?.Dispose();
        _searchCancellation = new CancellationTokenSource();
        var cancellationToken = _searchCancellation.Token;

        LoadingRing.IsActive = true;
        ErrorInfoBar.IsOpen = false;
        SearchResultsList.ItemsSource = null;
        SearchResultSummary.Text = "جاري البحث داخل المستند...";

        try
        {
            var results = await _textService.SearchAsync(
                _filePath,
                query,
                cancellationToken);

            if (cancellationToken.IsCancellationRequested)
            {
                return;
            }

            SearchResultsList.ItemsSource = results;
            SearchResultSummary.Text = results.Count switch
            {
                0 => "لم يتم العثور على نتائج.",
                1 => "تم العثور على نتيجة واحدة.",
                _ => $"تم العثور على {results.Count} نتيجة."
            };
        }
        catch (OperationCanceledException)
        {
            // A newer search or page navigation replaced this request.
        }
        catch (Exception exception)
        {
            ShowError($"تعذّر البحث داخل المستند: {exception.Message}");
            SearchResultSummary.Text = "تعذّر إكمال البحث.";
        }
        finally
        {
            if (!cancellationToken.IsCancellationRequested)
            {
                LoadingRing.IsActive = false;
            }
        }
    }

    private async void SearchResultsList_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (SearchResultsList.SelectedItem is not PdfTextSearchHit hit ||
            _document is null)
        {
            return;
        }

        var targetPageIndex = (uint)Math.Max(0, hit.PageNumber - 1);
        if (targetPageIndex >= _document.PageCount)
        {
            return;
        }

        _pageIndex = targetPageIndex;
        await RenderCurrentPageAsync();

        ExtractedPageText.Text = hit.Snippet;
        PageTextExpander.IsExpanded = true;
    }

    private async void ExtractCurrentPageTextButton_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_filePath) || _document is null)
        {
            ShowError("افتح ملف PDF أولًا.");
            return;
        }

        LoadingRing.IsActive = true;
        ErrorInfoBar.IsOpen = false;

        try
        {
            var pageNumber = checked((int)_pageIndex + 1);
            var text = await _textService.ExtractPageTextAsync(
                _filePath,
                pageNumber);

            ExtractedPageText.Text = string.IsNullOrWhiteSpace(text)
                ? "لم يتم العثور على نص قابل للاستخراج في هذه الصفحة. قد تكون الصفحة صورة ممسوحة ضوئيًا وتحتاج إلى OCR."
                : text;

            PageTextExpander.IsExpanded = true;
        }
        catch (Exception exception)
        {
            ShowError($"تعذّر استخراج النص: {exception.Message}");
        }
        finally
        {
            LoadingRing.IsActive = false;
        }
    }


    private async void RecognizePageTextButton_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (_document is null)
        {
            ShowError("افتح ملف PDF أولًا.");
            return;
        }

        var languageCode = (OcrLanguageComboBox.SelectedItem as ComboBoxItem)?.Tag as string;
        if (string.IsNullOrWhiteSpace(languageCode))
        {
            ShowError("اختر لغة التعرف الضوئي أولًا.");
            return;
        }

        var matchingLanguage = OcrEngine.AvailableRecognizerLanguages
            .FirstOrDefault(language =>
                string.Equals(language.LanguageTag, languageCode, StringComparison.OrdinalIgnoreCase) ||
                (languageCode == "ar" &&
                 language.LanguageTag.StartsWith("ar-", StringComparison.OrdinalIgnoreCase)) ||
                (languageCode == "en-US" &&
                 language.LanguageTag.StartsWith("en-", StringComparison.OrdinalIgnoreCase)));

        if (matchingLanguage is null)
        {
            ShowError(
                $"حزمة OCR للغة {languageCode} غير مثبتة أو غير متاحة. " +
                "ثبّت ميزة التعرف الضوئي المناسبة من إعدادات اللغة في Windows ثم أعد المحاولة.");
            return;
        }

        var engine = OcrEngine.TryCreateFromLanguage(matchingLanguage);
        if (engine is null)
        {
            ShowError(
                $"تعذّر إنشاء محرك OCR للغة {matchingLanguage.LanguageTag}. " +
                "تحقق من تثبيت ميزة التعرف الضوئي في Windows.");
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

            using var decoder = await BitmapDecoder.CreateAsync(stream);
            using var softwareBitmap = await decoder.GetSoftwareBitmapAsync(
                BitmapPixelFormat.Bgra8,
                BitmapAlphaMode.Premultiplied);

            if (softwareBitmap.PixelWidth > engine.MaxImageDimension ||
                softwareBitmap.PixelHeight > engine.MaxImageDimension)
            {
                ShowError(
                    $"أبعاد الصفحة أكبر من الحد الذي يدعمه OCR ({engine.MaxImageDimension} بكسل). " +
                    "يمكن تقليل دقة العرض ثم إعادة المحاولة.");
                return;
            }

            var recognition = await engine.RecognizeAsync(softwareBitmap);
            var recognizedText = string.Join(
                Environment.NewLine,
                recognition.Lines.Select(line => line.Text));

            ExtractedPageText.Text = string.IsNullOrWhiteSpace(recognizedText)
                ? "لم يتمكن OCR من التعرف على نص واضح في هذه الصفحة."
                : recognizedText;

            PageTextExpander.IsExpanded = true;
        }
        catch (Exception exception)
        {
            ShowError($"تعذّر تنفيذ OCR: {exception.Message}");
        }
        finally
        {
            LoadingRing.IsActive = false;
        }
    }

    private void ZoomInButton_Click(object sender, RoutedEventArgs e)
    {
        var nextZoom = Math.Min(4.0, PdfScrollViewer.ZoomFactor * 1.2);
        PdfScrollViewer.ChangeView(null, null, (float)nextZoom);
    }

    private void ZoomOutButton_Click(object sender, RoutedEventArgs e)
    {
        var nextZoom = Math.Max(0.1, PdfScrollViewer.ZoomFactor / 1.2);
        PdfScrollViewer.ChangeView(null, null, (float)nextZoom);
    }

    private void ResetZoomButton_Click(object sender, RoutedEventArgs e)
    {
        PdfScrollViewer.ChangeView(null, null, 1.0f);
    }

    private void FitPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (PageImage.Source is null || PageImage.Width <= 0 || PageImage.Height <= 0)
        {
            return;
        }

        var availableWidth = Math.Max(1, PdfScrollViewer.ActualWidth - 32);
        var availableHeight = Math.Max(1, PdfScrollViewer.ActualHeight - 32);
        var fitScale = Math.Min(
            availableWidth / PageImage.Width,
            availableHeight / PageImage.Height);

        PdfScrollViewer.ChangeView(
            null,
            null,
            (float)Math.Clamp(fitScale, 0.1, 4.0));
    }

    private void FitWidthButton_Click(object sender, RoutedEventArgs e)
    {
        if (PageImage.Source is null || PageImage.Width <= 0)
        {
            return;
        }

        var availableWidth = Math.Max(1, PdfScrollViewer.ActualWidth - 32);
        var fitScale = availableWidth / PageImage.Width;

        PdfScrollViewer.ChangeView(
            null,
            null,
            (float)Math.Clamp(fitScale, 0.5, 4.0));
    }

    private void PdfScrollViewer_ViewChanged(
        object sender,
        ScrollViewerViewChangedEventArgs e)
    {
        ZoomStatusText.Text = $"{Math.Round(PdfScrollViewer.ZoomFactor * 100)}%";
    }

    private static string NormalizeArabicDigits(string value)
    {
        return value
            .Replace('٠', '0')
            .Replace('١', '1')
            .Replace('٢', '2')
            .Replace('٣', '3')
            .Replace('٤', '4')
            .Replace('٥', '5')
            .Replace('٦', '6')
            .Replace('٧', '7')
            .Replace('٨', '8')
            .Replace('٩', '9')
            .Replace('۰', '0')
            .Replace('۱', '1')
            .Replace('۲', '2')
            .Replace('۳', '3')
            .Replace('۴', '4')
            .Replace('۵', '5')
            .Replace('۶', '6')
            .Replace('۷', '7')
            .Replace('۸', '8')
            .Replace('۹', '9');
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
