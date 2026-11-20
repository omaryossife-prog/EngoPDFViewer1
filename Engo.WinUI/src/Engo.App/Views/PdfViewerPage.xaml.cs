using System.Globalization;
using Windows.Foundation;
using Path = System.IO.Path;
using Engo.Application.Documents;
using Engo.Infrastructure.Pdf;
using Engo.Infrastructure.Persistence;
using System.Collections.ObjectModel;
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
    private const uint ThumbnailBatchSize = 12;

    private readonly IPdfTextService _textService = new PdfPigTextService();
    private static readonly TagLibraryService SharedTagLibrary =
        new(new JsonTagLibraryRepository());
    private readonly IPdfAnnotationService _annotationService = new AsposePdfAnnotationService();
    private readonly List<PdfAnnotationDraft> _pendingAnnotations = [];
    private readonly ObservableCollection<StudyTag> _studyTags = [];
    private PdfDocument? _document;
    private CancellationTokenSource? _searchCancellation;
    private CancellationTokenSource? _thumbnailCancellation;
    private uint? _loadedThumbnailBatchStart;
    private uint? _loadingThumbnailBatchStart;
    private uint _thumbnailBatchStart;
    private string? _filePath;
    private uint _pageIndex;
    private bool _isDrawing;
    private bool _isFullPageMode;
    private Point _drawingStart;
    private List<Point>? _activeStrokePoints;
    private Polyline? _activePolyline;
    private Microsoft.UI.Xaml.Shapes.Rectangle? _activeRectangle;

    public event EventHandler<string>? AnnotatedCopySaved;

    public bool HasUnsavedAnnotations => _pendingAnnotations.Count > 0;

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
            await RefreshTagItemsAsync();
            await LoadDocumentAsync(filePath);
        }
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e)
    {
        _searchCancellation?.Cancel();
        _searchCancellation?.Dispose();
        _searchCancellation = null;

        _thumbnailCancellation?.Cancel();
        _thumbnailCancellation?.Dispose();
        _thumbnailCancellation = null;
        _loadingThumbnailBatchStart = null;

        PageImage.Source = null;
        AnnotationCanvas.Children.Clear();
        _activeStrokePoints = null;
        _activePolyline = null;
        _activeRectangle = null;
                _document = null;

        base.OnNavigatedFrom(e);
    }

    private async Task LoadDocumentAsync(string filePath)
    {
        LoadingRing.IsActive = true;
        ErrorInfoBar.IsOpen = false;
        SearchResultsList.ItemsSource = null;
        SearchResultSummary.Text = "اكتب كلمة أو عبارة للبحث داخل الملف.";
        PageThumbnailsList.ItemsSource = null;
        ThumbnailSummary.Text = "جاري تجهيز صور الصفحات المصغرة...";
        ThumbnailRangeText.Text = "—";
        _thumbnailCancellation?.Cancel();
        _thumbnailCancellation?.Dispose();
        _thumbnailCancellation = null;
        _loadedThumbnailBatchStart = null;
        _loadingThumbnailBatchStart = null;
        _thumbnailBatchStart = 0;
        ExtractedPageText.Text = "استخدم زر استخراج نص الصفحة لعرض النص القابل للاستخراج.";

        try
        {
            var file = await StorageFile.GetFileFromPathAsync(filePath);
            var loadedDocument = await PdfDocument.LoadFromFileAsync(file);

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

            var thumbnailBatchStart =
                (_pageIndex / ThumbnailBatchSize) * ThumbnailBatchSize;
            if (_loadedThumbnailBatchStart == thumbnailBatchStart)
            {
                PageThumbnailsList.SelectedIndex =
                    checked((int)(_pageIndex - thumbnailBatchStart));
                UpdateThumbnailRangeControls();
            }
            else
            {
                _ = LoadPageThumbnailBatchAsync(_pageIndex);
            }

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

    private async Task LoadPageThumbnailBatchAsync(uint pageIndex)
    {
        var document = _document;
        if (document is null || document.PageCount == 0 || pageIndex >= document.PageCount)
        {
            return;
        }

        var batchStart = (pageIndex / ThumbnailBatchSize) * ThumbnailBatchSize;
        if (_loadedThumbnailBatchStart == batchStart)
        {
            PageThumbnailsList.SelectedIndex = checked((int)(pageIndex - batchStart));
            UpdateThumbnailRangeControls();
            return;
        }

        if (_loadingThumbnailBatchStart == batchStart)
        {
            return;
        }

        _thumbnailCancellation?.Cancel();
        _thumbnailCancellation?.Dispose();

        var cancellation = new CancellationTokenSource();
        var cancellationToken = cancellation.Token;
        _thumbnailCancellation = cancellation;
        _loadingThumbnailBatchStart = batchStart;
        ThumbnailSummary.Text = "جاري تجهيز صور الصفحات المصغرة...";
        ThumbnailRangeText.Text = "جاري التحميل";

        try
        {
            var batchEnd = Math.Min(
                document.PageCount,
                batchStart + ThumbnailBatchSize);
            var thumbnails = new List<PdfPageThumbnailItem>(
                checked((int)(batchEnd - batchStart)));

            for (var currentPage = batchStart; currentPage < batchEnd; currentPage++)
            {
                cancellationToken.ThrowIfCancellationRequested();

                using var page = document.GetPage(currentPage);
                using var stream = new InMemoryRandomAccessStream();

                var renderOptions = new PdfPageRenderOptions
                {
                    DestinationWidth = 150
                };

                await page.RenderToStreamAsync(stream, renderOptions);
                stream.Seek(0);

                var thumbnail = new BitmapImage();
                await thumbnail.SetSourceAsync(stream);

                thumbnails.Add(new PdfPageThumbnailItem(
                    currentPage,
                    $"الصفحة {currentPage + 1}",
                    thumbnail));
            }

            cancellationToken.ThrowIfCancellationRequested();

            if (!ReferenceEquals(document, _document))
            {
                return;
            }

            _thumbnailBatchStart = batchStart;
            _loadedThumbnailBatchStart = batchStart;
            PageThumbnailsList.ItemsSource = thumbnails;
            PageThumbnailsList.SelectedIndex =
                checked((int)(_pageIndex - batchStart));

            ThumbnailSummary.Text =
                $"اختر صورة مصغرة للانتقال مباشرةً إلى الصفحة. يتم تحميل {ThumbnailBatchSize} صفحة في كل مجموعة.";
            ThumbnailRangeText.Text =
                $"{batchStart + 1}–{batchEnd} / {document.PageCount}";

            UpdateThumbnailRangeControls();
        }
        catch (OperationCanceledException)
        {
            // A newer page group or a document change replaced this request.
        }
        catch (Exception exception)
        {
            if (ReferenceEquals(document, _document) &&
                !cancellationToken.IsCancellationRequested)
            {
                ThumbnailSummary.Text =
                    $"تعذّر تجهيز الصور المصغرة: {exception.Message}";
                ThumbnailRangeText.Text = "—";
            }
        }
        finally
        {
            if (ReferenceEquals(_thumbnailCancellation, cancellation))
            {
                _loadingThumbnailBatchStart = null;
                _thumbnailCancellation.Dispose();
                _thumbnailCancellation = null;
            }
            else
            {
                cancellation.Dispose();
            }
        }
    }

    private void UpdateThumbnailRangeControls()
    {
        var pageCount = _document?.PageCount ?? 0;
        PreviousThumbnailRangeButton.IsEnabled =
            pageCount > 0 && _thumbnailBatchStart > 0;
        NextThumbnailRangeButton.IsEnabled =
            pageCount > _thumbnailBatchStart + ThumbnailBatchSize;
    }

    private async void PreviousThumbnailRangeButton_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (_document is null || _thumbnailBatchStart == 0)
        {
            return;
        }

        _pageIndex = _thumbnailBatchStart - 1;
        await RenderCurrentPageAsync();
    }

    private async void NextThumbnailRangeButton_Click(
        object sender,
        RoutedEventArgs e)
    {
        if (_document is null ||
            _thumbnailBatchStart + ThumbnailBatchSize >= _document.PageCount)
        {
            return;
        }

        _pageIndex = _thumbnailBatchStart + ThumbnailBatchSize;
        await RenderCurrentPageAsync();
    }

    private async void PageThumbnailsList_ItemClick(
        object sender,
        ItemClickEventArgs e)
    {
        if (e.ClickedItem is not PdfPageThumbnailItem thumbnail ||
            _document is null ||
            thumbnail.PageIndex >= _document.PageCount)
        {
            return;
        }

        _pageIndex = thumbnail.PageIndex;
        await RenderCurrentPageAsync();
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

            var decoder = await BitmapDecoder.CreateAsync(stream);
            using var softwareBitmap = await decoder.GetSoftwareBitmapAsync(
                BitmapPixelFormat.Bgra8,
                BitmapAlphaMode.Premultiplied);

            if (softwareBitmap.PixelWidth > OcrEngine.MaxImageDimension ||
                softwareBitmap.PixelHeight > OcrEngine.MaxImageDimension)
            {
                ShowError(
                    $"أبعاد الصفحة أكبر من الحد الذي يدعمه OCR ({OcrEngine.MaxImageDimension} بكسل). " +
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


    private string SelectedAnnotationTool =>
        (AnnotationToolComboBox.SelectedItem as ComboBoxItem)?.Tag as string ?? "Browse";

    private PdfAnnotationColor SelectedAnnotationColor =>
        ((AnnotationColorComboBox.SelectedItem as ComboBoxItem)?.Tag as string) switch
        {
            "Red" => PdfAnnotationColor.Red,
            "Blue" => PdfAnnotationColor.Blue,
            "Green" => PdfAnnotationColor.Green,
            _ => PdfAnnotationColor.Yellow
        };

    private double SelectedPdfLineWidth =>
        Math.Clamp(AnnotationLineWidthSlider.Value * 0.75, 0.5, 6.0);


    private StudyTag? SelectedStudyTag =>
        RegionTagComboBox?.SelectedItem as StudyTag;

    private PdfAnnotationColor SelectedTagColor =>
        SelectedStudyTag is { } tag
            ? ParseTagColor(tag.ColorHex)
            : PdfAnnotationColor.Yellow;

    private static PdfAnnotationColor ParseTagColor(string hex)
    {
        var normalized = TagLibraryService.NormalizeColor(hex);
        return new PdfAnnotationColor(
            Convert.ToByte(normalized.Substring(1, 2), 16) / 255.0,
            Convert.ToByte(normalized.Substring(3, 2), 16) / 255.0,
            Convert.ToByte(normalized.Substring(5, 2), 16) / 255.0);
    }

    private async Task RefreshTagItemsAsync(string? selectedName = null)
    {
        var snapshot = await SharedTagLibrary.GetSnapshotAsync();
        var wanted = selectedName ?? SelectedStudyTag?.Name;
        _studyTags.Clear();
        foreach (var tag in snapshot.Tags)
        {
            _studyTags.Add(tag);
        }

        RegionTagComboBox.ItemsSource = _studyTags;
        RegionTagComboBox.SelectedItem = _studyTags.FirstOrDefault(tag =>
            string.Equals(tag.Name, wanted, StringComparison.OrdinalIgnoreCase))
            ?? _studyTags.FirstOrDefault();
    }

    private void RegionTagComboBox_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (SelectedAnnotationTool == "TagRegion" && AnnotationStatusText is not null)
        {
            AnnotationStatusText.Text = SelectedStudyTag is null
                ? "لا توجد وسوم. افتح إدارة الوسوم لإنشاء وسم."
                : $"الوسم المحدد: {SelectedStudyTag.Name} — اسحب لتعيينه على منطقة.";
        }
    }

    private async void ManageTagsButton_Click(object sender, RoutedEventArgs e)
    {
        await ShowTagLibraryDialogAsync();
    }

    private async Task ShowTagLibraryDialogAsync()
    {
        var nameBox = new TextBox
        {
            Header = "اسم الوسم",
            PlaceholderText = "مثال: تعريفات مهمة",
            MaxLength = 32
        };
        var colorBox = new ComboBox
        {
            Header = "لون الوسم",
            Width = 220,
            HorizontalAlignment = HorizontalAlignment.Stretch
        };
        var colors = new[]
        {
            ("ذهبي", "#F2BD55"), ("أزرق سماوي", "#66C7E8"),
            ("بنفسجي", "#9B8CFF"), ("أخضر", "#62C98B"),
            ("أحمر", "#F08080"), ("وردي", "#E38BC8"),
            ("أزرق", "#7CA8FF"), ("تركوازي", "#53C9B5"),
            ("بني ذهبي", "#C5A65F"), ("برتقالي", "#D28A55")
        };
        foreach (var (label, hex) in colors)
        {
            colorBox.Items.Add(new ComboBoxItem
            {
                Content = label,
                Tag = hex
            });
        }

        var tagList = new ListView
        {
            ItemsSource = _studyTags,
            DisplayMemberPath = nameof(StudyTag.Name),
            SelectionMode = ListViewSelectionMode.Single,
            MinHeight = 150,
            MaxHeight = 260
        };
        var status = new TextBlock
        {
            Text = "أنشئ وسومًا مشتركة، أو اختر وسمًا لتغيير اسمه أو لونه.",
            TextWrapping = TextWrapping.Wrap,
            Opacity = 0.75
        };
        var newButton = new Button
        {
            Content = "وسم جديد",
            HorizontalAlignment = HorizontalAlignment.Stretch
        };
        var saveButton = new Button
        {
            Content = "إنشاء وسم",
            HorizontalAlignment = HorizontalAlignment.Stretch
        };
        var deleteButton = new Button
        {
            Content = "حذف الوسم المحدد",
            HorizontalAlignment = HorizontalAlignment.Stretch,
            IsEnabled = false
        };
        var panel = new StackPanel { Spacing = 10 };
        panel.Children.Add(new TextBlock
        {
            Text = "مكتبة وسوم مشتركة لكل ملفات PDF",
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold
        });
        panel.Children.Add(tagList);
        panel.Children.Add(nameBox);
        panel.Children.Add(colorBox);
        panel.Children.Add(newButton);
        panel.Children.Add(saveButton);
        panel.Children.Add(deleteButton);
        panel.Children.Add(status);

        var dialog = new ContentDialog
        {
            Title = "إدارة مكتبة الوسوم",
            Content = panel,
            PrimaryButtonText = "تم",
            DefaultButton = ContentDialogButton.Primary,
            XamlRoot = XamlRoot
        };

        var selectedOriginalName = string.Empty;
        var deleteConfirmationArmed = false;
        tagList.SelectionChanged += (_, _) =>
        {
            if (tagList.SelectedItem is StudyTag selected)
            {
                selectedOriginalName = selected.Name;
                nameBox.Text = selected.Name;
                deleteButton.IsEnabled = true;
                saveButton.Content = "حفظ التعديلات";
                deleteButton.Content = "حذف الوسم المحدد";
                deleteConfirmationArmed = false;
                var colorItem = colorBox.Items
                    .OfType<ComboBoxItem>()
                    .FirstOrDefault(item =>
                        string.Equals(item.Tag as string, selected.ColorHex, StringComparison.OrdinalIgnoreCase));
                colorBox.SelectedItem = colorItem;
                if (colorItem is null)
                {
                    var customColor = new ComboBoxItem
                    {
                        Content = selected.ColorHex,
                        Tag = selected.ColorHex
                    };
                    colorBox.Items.Add(customColor);
                    colorBox.SelectedItem = customColor;
                }
            }
            else
            {
                selectedOriginalName = string.Empty;
                deleteButton.IsEnabled = false;
                saveButton.Content = "إنشاء وسم";
            }
        };

        newButton.Click += (_, _) =>
        {
            selectedOriginalName = string.Empty;
            tagList.SelectedItem = null;
            nameBox.Text = string.Empty;
            colorBox.SelectedIndex = 0;
            saveButton.Content = "إنشاء وسم";
            deleteButton.IsEnabled = false;
            deleteButton.Content = "حذف الوسم المحدد";
            deleteConfirmationArmed = false;
            status.Text = "أدخل اسم الوسم الجديد واختر لونه.";
        };

        saveButton.Click += async (_, _) =>
        {
            try
            {
                var cleanName = nameBox.Text.Trim();
                var selectedColor = (colorBox.SelectedItem as ComboBoxItem)?.Tag as string
                    ?? "#F2BD55";
                StudyTag saved;
                if (string.IsNullOrWhiteSpace(selectedOriginalName))
                {
                    saved = await SharedTagLibrary.CreateAsync(cleanName, selectedColor);
                }
                else
                {
                    saved = string.Equals(
                        selectedOriginalName,
                        cleanName,
                        StringComparison.OrdinalIgnoreCase)
                        ? await SharedTagLibrary.RecolorAsync(selectedOriginalName, selectedColor)
                        : await SharedTagLibrary.RenameAsync(selectedOriginalName, cleanName);
                    if (!string.Equals(saved.ColorHex, selectedColor, StringComparison.OrdinalIgnoreCase))
                    {
                        saved = await SharedTagLibrary.RecolorAsync(saved.Name, selectedColor);
                    }
                }

                await RefreshTagItemsAsync(saved.Name);
                tagList.SelectedItem = _studyTags.FirstOrDefault(tag => tag.Name == saved.Name);
                status.Text = $"تم حفظ الوسم: {saved.Name}";
            }
            catch (Exception exception)
            {
                status.Text = exception.Message;
            }
        };

        deleteButton.Click += async (_, _) =>
        {
            if (tagList.SelectedItem is not StudyTag selected)
            {
                return;
            }

            if (!deleteConfirmationArmed)
            {
                deleteConfirmationArmed = true;
                deleteButton.Content = "تأكيد الحذف";
                status.Text = $"اضغط «تأكيد الحذف» مرة أخرى لحذف الوسم {selected.Name} من المكتبة.";
                return;
            }

            try
            {
                await SharedTagLibrary.DeleteAsync(selected.Name);
                await RefreshTagItemsAsync();
                tagList.SelectedItem = null;
                selectedOriginalName = string.Empty;
                nameBox.Text = string.Empty;
                saveButton.Content = "إنشاء وسم";
                deleteButton.Content = "حذف الوسم المحدد";
                deleteButton.IsEnabled = false;
                deleteConfirmationArmed = false;
                status.Text = $"تم حذف الوسم {selected.Name} من المكتبة.";
            }
            catch (Exception exception)
            {
                status.Text = exception.Message;
            }
        };

        await dialog.ShowAsync();
        await RefreshTagItemsAsync(SelectedStudyTag?.Name);
        UpdateAnnotationStatus();
    }

    private void AnnotationToolComboBox_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (AnnotationCanvas is null)
        {
            return;
        }

        AnnotationCanvas.IsHitTestVisible =
            SelectedAnnotationTool != "Browse";

        AnnotationStatusText.Text = SelectedAnnotationTool switch
        {
            "Highlight" => "اسحب فوق الصفحة لتحديد مساحة التظليل.",
            "Freehand" => "ارسم بالقلم داخل الصفحة.",
            "Rectangle" => "اسحب لرسم مستطيل.",
            "TagRegion" => SelectedStudyTag is null
                ? "أنشئ وسمًا من إدارة الوسوم أولًا، ثم حدده واسحب فوق المنطقة."
                : $"اسحب فوق منطقة الصفحة لإسناد الوسم: {SelectedStudyTag.Name}.",
            "Eraser" => "اضغط على تعليق غير محفوظ لإزالته.",
            _ => "وضع التصفح: اسحب للتنقل واستخدم عجلة التكبير."
        };
    }

    private void AnnotationCanvas_PointerPressed(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (_document is null || PageImage.Source is null)
        {
            return;
        }

        var tool = SelectedAnnotationTool;
        if (tool == "Browse")
        {
            return;
        }

        var position = e.GetCurrentPoint(AnnotationCanvas).Position;
        if (tool == "Eraser")
        {
            ErasePendingAnnotationAt(position);
            e.Handled = true;
            return;
        }

        if (tool == "TagRegion" && SelectedStudyTag is null)
        {
            AnnotationStatusText.Text = "أنشئ وسمًا وحدده قبل تعيينه لمنطقة.";
            e.Handled = true;
            return;
        }

        _isDrawing = true;
        _drawingStart = position;
        AnnotationCanvas.CapturePointer(e.Pointer);

        if (tool == "Freehand")
        {
            _activeStrokePoints = [position];
            _activePolyline = new Polyline
            {
                Stroke = CreateAnnotationBrush(SelectedAnnotationColor, 255),
                StrokeThickness = Math.Max(1, AnnotationLineWidthSlider.Value),
                StrokeLineJoin = PenLineJoin.Round,
                StrokeStartLineCap = PenLineCap.Round,
                StrokeEndLineCap = PenLineCap.Round,
                Points = new PointCollection { position }
            };
            AnnotationCanvas.Children.Add(_activePolyline);
        }
        else
        {
            var color = tool == "TagRegion"
                ? SelectedTagColor
                : SelectedAnnotationColor;
            var isHighlight = tool == "Highlight";
            _activeRectangle = new Microsoft.UI.Xaml.Shapes.Rectangle
            {
                Stroke = CreateAnnotationBrush(color, 255),
                StrokeThickness = Math.Max(1, AnnotationLineWidthSlider.Value),
                Fill = isHighlight
                    ? CreateAnnotationBrush(color, 78)
                    : new SolidColorBrush(Color.FromArgb(0, 0, 0, 0))
            };

            Canvas.SetLeft(_activeRectangle, position.X);
            Canvas.SetTop(_activeRectangle, position.Y);
            _activeRectangle.Width = 0;
            _activeRectangle.Height = 0;
            AnnotationCanvas.Children.Add(_activeRectangle);
        }

        e.Handled = true;
    }

    private void AnnotationCanvas_PointerMoved(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (!_isDrawing)
        {
            return;
        }

        var position = e.GetCurrentPoint(AnnotationCanvas).Position;

        if (_activePolyline is not null && _activeStrokePoints is not null)
        {
            var previous = _activeStrokePoints[^1];
            var distanceX = position.X - previous.X;
            var distanceY = position.Y - previous.Y;

            if ((distanceX * distanceX) + (distanceY * distanceY) >= 2.25)
            {
                _activeStrokePoints.Add(position);
                _activePolyline.Points.Add(position);
            }
        }
        else if (_activeRectangle is not null)
        {
            var left = Math.Min(_drawingStart.X, position.X);
            var top = Math.Min(_drawingStart.Y, position.Y);

            Canvas.SetLeft(_activeRectangle, left);
            Canvas.SetTop(_activeRectangle, top);
            _activeRectangle.Width = Math.Abs(position.X - _drawingStart.X);
            _activeRectangle.Height = Math.Abs(position.Y - _drawingStart.Y);
        }

        e.Handled = true;
    }

    private void AnnotationCanvas_PointerReleased(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (!_isDrawing)
        {
            return;
        }

        var end = e.GetCurrentPoint(AnnotationCanvas).Position;
        var tool = SelectedAnnotationTool;

        if (tool == "Freehand" && _activeStrokePoints is { Count: >= 2 })
        {
            var points = _activeStrokePoints
                .Select(ToNormalizedPoint)
                .ToArray();

            var bounds = GetNormalizedBounds(points);
            _pendingAnnotations.Add(new PdfAnnotationDraft(
                checked((int)_pageIndex + 1),
                PdfAnnotationKind.Freehand,
                bounds.Left,
                bounds.Top,
                bounds.Right,
                bounds.Bottom,
                points,
                null,
                SelectedAnnotationColor,
                SelectedPdfLineWidth));
        }
        else if (_activeRectangle is not null)
        {
            var bounds = GetNormalizedBounds(_drawingStart, end);
            if (bounds.Right - bounds.Left >= 0.003 &&
                bounds.Bottom - bounds.Top >= 0.003)
            {
                var kind = tool switch
                {
                    "Highlight" => PdfAnnotationKind.Highlight,
                    "TagRegion" => PdfAnnotationKind.TagRegion,
                    _ => PdfAnnotationKind.Rectangle
                };
                var selectedTag = tool == "TagRegion" ? SelectedStudyTag : null;
                var annotationColor = selectedTag is null
                    ? SelectedAnnotationColor
                    : ParseTagColor(selectedTag.ColorHex);

                _pendingAnnotations.Add(new PdfAnnotationDraft(
                    checked((int)_pageIndex + 1),
                    kind,
                    bounds.Left,
                    bounds.Top,
                    bounds.Right,
                    bounds.Bottom,
                    [],
                    selectedTag?.Name,
                    annotationColor,
                    SelectedPdfLineWidth));
            }
        }

        AnnotationCanvas.ReleasePointerCaptures();
        _isDrawing = false;
        _activePolyline = null;
        _activeRectangle = null;
        _activeStrokePoints = null;

        RedrawPendingAnnotations();
        UpdateAnnotationStatus();
        e.Handled = true;
    }

    private void AnnotationCanvas_PointerCaptureLost(
        object sender,
        PointerRoutedEventArgs e)
    {
        if (!_isDrawing)
        {
            return;
        }

        _isDrawing = false;
        _activeStrokePoints = null;
        _activePolyline = null;
        _activeRectangle = null;
        RedrawPendingAnnotations();
    }

    private void ErasePendingAnnotationAt(Point position)
    {
        if (PageImage.Width <= 0 || PageImage.Height <= 0 ||
            _pendingAnnotations.Count == 0)
        {
            return;
        }

        var target = ToNormalizedPoint(position);
        var index = PdfAnnotationHitTester.FindTopmostHitIndex(
            _pendingAnnotations,
            target);

        if (index < 0)
        {
            AnnotationStatusText.Text = "لم يتم العثور على تعليق عند موضع الممحاة.";
            return;
        }

        _pendingAnnotations.RemoveAt(index);
        RedrawPendingAnnotations();
        AnnotationStatusText.Text = "تمت إزالة التعليق غير المحفوظ.";
    }

    private PdfAnnotationPoint ToNormalizedPoint(Point point)
    {
        var width = Math.Max(1, PageImage.Width);
        var height = Math.Max(1, PageImage.Height);

        return new PdfAnnotationPoint(
            Math.Clamp(point.X / width, 0, 1),
            Math.Clamp(point.Y / height, 0, 1));
    }

    private (double Left, double Top, double Right, double Bottom) GetNormalizedBounds(
        Point first,
        Point second)
    {
        var a = ToNormalizedPoint(first);
        var b = ToNormalizedPoint(second);

        return (
            Math.Min(a.XRatio, b.XRatio),
            Math.Min(a.YRatio, b.YRatio),
            Math.Max(a.XRatio, b.XRatio),
            Math.Max(a.YRatio, b.YRatio));
    }

    private static (double Left, double Top, double Right, double Bottom) GetNormalizedBounds(
        IReadOnlyList<PdfAnnotationPoint> points)
    {
        var left = points.Min(point => point.XRatio);
        var right = points.Max(point => point.XRatio);
        var top = points.Min(point => point.YRatio);
        var bottom = points.Max(point => point.YRatio);

        const double minimumPadding = 0.0015;
        if (right - left < minimumPadding)
        {
            left = Math.Max(0, left - minimumPadding);
            right = Math.Min(1, right + minimumPadding);
        }

        if (bottom - top < minimumPadding)
        {
            top = Math.Max(0, top - minimumPadding);
            bottom = Math.Min(1, bottom + minimumPadding);
        }

        return (left, top, right, bottom);
    }

    private static SolidColorBrush CreateAnnotationBrush(
        PdfAnnotationColor color,
        byte alpha)
    {
        return new SolidColorBrush(Color.FromArgb(
            alpha,
            (byte)Math.Round(Math.Clamp(color.RedComponent, 0, 1) * 255),
            (byte)Math.Round(Math.Clamp(color.GreenComponent, 0, 1) * 255),
            (byte)Math.Round(Math.Clamp(color.BlueComponent, 0, 1) * 255)));
    }

    private void RedrawPendingAnnotations()
    {
        if (AnnotationCanvas is null ||
            PageImage.Width <= 0 ||
            PageImage.Height <= 0)
        {
            return;
        }

        AnnotationCanvas.Children.Clear();
        var pageNumber = checked((int)_pageIndex + 1);

        foreach (var draft in _pendingAnnotations.Where(
                     annotation => annotation.PageNumber == pageNumber))
        {
            var color = CreateAnnotationBrush(draft.Color, 255);
            var left = draft.LeftRatio * PageImage.Width;
            var top = draft.TopRatio * PageImage.Height;
            var width = (draft.RightRatio - draft.LeftRatio) * PageImage.Width;
            var height = (draft.BottomRatio - draft.TopRatio) * PageImage.Height;

            switch (draft.Kind)
            {
                case PdfAnnotationKind.Freehand:
                {
                    var polyline = new Polyline
                    {
                        Stroke = color,
                        StrokeThickness = Math.Max(1, draft.LineWidth / 0.75),
                        StrokeLineJoin = PenLineJoin.Round,
                        StrokeStartLineCap = PenLineCap.Round,
                        StrokeEndLineCap = PenLineCap.Round
                    };

                    foreach (var point in draft.StrokePoints)
                    {
                        polyline.Points.Add(new Point(
                            point.XRatio * PageImage.Width,
                            point.YRatio * PageImage.Height));
                    }

                    AnnotationCanvas.Children.Add(polyline);
                    break;
                }

                case PdfAnnotationKind.Highlight:
                case PdfAnnotationKind.Rectangle:
                case PdfAnnotationKind.TagRegion:
                {
                    var shape = new Microsoft.UI.Xaml.Shapes.Rectangle
                    {
                        Stroke = color,
                        StrokeThickness = Math.Max(1, draft.LineWidth / 0.75),
                        Fill = draft.Kind == PdfAnnotationKind.Highlight
                            ? CreateAnnotationBrush(draft.Color, 78)
                            : new SolidColorBrush(Color.FromArgb(0, 0, 0, 0)),
                        StrokeDashArray = draft.Kind == PdfAnnotationKind.TagRegion
                            ? new DoubleCollection { 3, 2 }
                            : null,
                        Width = width,
                        Height = height
                    };

                    Canvas.SetLeft(shape, left);
                    Canvas.SetTop(shape, top);
                    AnnotationCanvas.Children.Add(shape);

                    if (draft.Kind == PdfAnnotationKind.TagRegion &&
                        !string.IsNullOrWhiteSpace(draft.Contents))
                    {
                        var label = new TextBlock
                        {
                            Text = draft.Contents,
                            FontSize = 12,
                            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                            Foreground = new SolidColorBrush(Colors.Black),
                            Background = CreateAnnotationBrush(draft.Color, 220),
                            Padding = new Thickness(5, 2, 5, 2),
                            IsHitTestVisible = false
                        };
                        Canvas.SetLeft(label, left);
                        Canvas.SetTop(label, Math.Max(0, top - 22));
                        AnnotationCanvas.Children.Add(label);
                    }

                    break;
                }

            }
        }

        UpdateAnnotationStatus();
    }

    private void UpdateAnnotationStatus()
    {
        var count = _pendingAnnotations.Count;
        AnnotationStatusText.Text = count switch
        {
            0 => "لا توجد تعليقات غير محفوظة.",
            1 => "تعليق واحد غير محفوظ — احفظ نسخة PDF للاحتفاظ به.",
            _ => $"{count} تعليقات غير محفوظة — احفظ نسخة PDF للاحتفاظ بها."
        };
    }

    private void UndoLastAnnotationButton_Click(object sender, RoutedEventArgs e)
    {
        if (_pendingAnnotations.Count == 0)
        {
            return;
        }

        _pendingAnnotations.RemoveAt(_pendingAnnotations.Count - 1);
        RedrawPendingAnnotations();
    }

    private async void SaveAnnotatedCopyButton_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_filePath) || _document is null)
        {
            ShowError("افتح ملف PDF أولًا.");
            return;
        }

        if (_pendingAnnotations.Count == 0)
        {
            ShowError("لا توجد تعليقات غير محفوظة.");
            return;
        }

        if (App.MainWindowInstance is null)
        {
            ShowError("تعذّر الوصول إلى نافذة التطبيق لفتح نافذة الحفظ.");
            return;
        }

        try
        {
            var picker = new FileSavePicker();
            picker.FileTypeChoices.Add("ملف PDF", new List<string> { ".pdf" });
            picker.SuggestedFileName =
                $"{Path.GetFileNameWithoutExtension(_filePath)}_annotated";

            InitializeWithWindow.Initialize(
                picker,
                WindowNative.GetWindowHandle(App.MainWindowInstance));

            var destination = await picker.PickSaveFileAsync();
            if (destination is null)
            {
                return;
            }

            LoadingRing.IsActive = true;
            ErrorInfoBar.IsOpen = false;

            var annotations = _pendingAnnotations.ToArray();
            await _annotationService.SaveAnnotatedCopyAsync(
                _filePath,
                destination.Path,
                annotations);

            var savedPdf = await PdfDocument.LoadFromFileAsync(destination);
            if (savedPdf.PageCount == 0)
            {
                throw new InvalidDataException("النسخة الناتجة لا تحتوي على صفحات.");
            }

            var previousPageIndex = _pageIndex;
            _document = savedPdf;
            _filePath = destination.Path;
            _pageIndex = Math.Min(previousPageIndex, _document.PageCount - 1);
            _pendingAnnotations.Clear();

            await RenderCurrentPageAsync();
            AnnotationStatusText.Text = "تم حفظ نسخة PDF بالتعليقات الجديدة.";
            AnnotatedCopySaved?.Invoke(this, destination.Path);
        }
        catch (Exception exception)
        {
            ShowError($"تعذّر حفظ التعليقات داخل نسخة PDF: {exception.Message}");
        }
        finally
        {
            LoadingRing.IsActive = false;
        }
    }

    private void FullPageModeButton_Click(object sender, RoutedEventArgs e)
    {
        SetFullPageMode(!_isFullPageMode);
    }

    private void SetFullPageMode(bool enabled)
    {
        _isFullPageMode = enabled;

        PdfTopToolbar.Visibility = enabled ? Visibility.Collapsed : Visibility.Visible;
        ErrorInfoBar.Visibility = enabled ? Visibility.Collapsed : Visibility.Visible;
        AnnotationToolbarBorder.Visibility = enabled ? Visibility.Collapsed : Visibility.Visible;
        PdfSidePanelBorder.Visibility = enabled ? Visibility.Collapsed : Visibility.Visible;
        PageTextExpander.Visibility = enabled ? Visibility.Collapsed : Visibility.Visible;

        PdfSideColumn.Width = new GridLength(enabled ? 0 : 300);

        FullPageModeButton.Content = enabled ? "عرض عادي" : "عرض كامل";
        ExitFullPageModeButton.Visibility =
            enabled ? Visibility.Visible : Visibility.Collapsed;
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
            (float)Math.Clamp(fitScale, 0.1, 4.0));
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
