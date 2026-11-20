using Engo.App.Views;
using Engo.Application.Documents;
using Engo.Infrastructure.Persistence;
using Engo.Infrastructure.Pdf;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace Engo.App;

public sealed partial class MainWindow : Window
{
    private readonly RecentDocumentsService _recentDocuments;
    private readonly DocumentSessionService _documentSession;
    private readonly IPdfMergeService _pdfMergeService = new AsposePdfMergeService();
    private bool _sessionRestoreStarted;
    private bool _isRestoringSession;

    public MainWindow()
    {
        InitializeComponent();

        Title = "Engo PDF Viewer & AI Study Agent";

        _recentDocuments = new RecentDocumentsService(
            new JsonRecentDocumentsRepository());
        _documentSession = new DocumentSessionService(
            new JsonDocumentSessionRepository());

        HomeFrame.Navigated += HomeFrame_Navigated;
        HomeFrame.Navigate(typeof(HomePage));
    }

    private void HomeFrame_Navigated(
        object sender,
        Microsoft.UI.Xaml.Navigation.NavigationEventArgs e)
    {
        if (e.Content is not HomePage homePage)
        {
            return;
        }

        homePage.OpenDocumentRequested -= HomePage_OpenDocumentRequested;
        homePage.OpenDocumentRequested += HomePage_OpenDocumentRequested;
    }

    private async void DocumentTabs_Loaded(object sender, RoutedEventArgs e)
    {
        if (_sessionRestoreStarted)
        {
            return;
        }

        _sessionRestoreStarted = true;
        await RestoreDocumentSessionAsync();
    }

    private async Task RestoreDocumentSessionAsync()
    {
        _isRestoringSession = true;
        var shouldPersistRestoredSession = true;
        try
        {
            var snapshot = await _documentSession.LoadAsync();
            if (snapshot is null)
            {
                return;
            }

            foreach (var path in snapshot.OpenFilePaths)
            {
                if (!File.Exists(path))
                {
                    continue;
                }

                try
                {
                    await _recentDocuments.RecordOpenedAsync(path);
                    OpenDocumentInTab(path);
                }
                catch
                {
                    // A single unavailable or invalid document must not block
                    // the rest of the saved session from being restored.
                }
            }

            if (!string.IsNullOrWhiteSpace(snapshot.ActiveFilePath))
            {
                var activeTab = DocumentTabs.TabItems
                    .OfType<TabViewItem>()
                    .FirstOrDefault(tab =>
                        string.Equals(
                            tab.Tag as string,
                            snapshot.ActiveFilePath,
                            StringComparison.OrdinalIgnoreCase));

                if (activeTab is not null)
                {
                    DocumentTabs.SelectedItem = activeTab;
                }
            }
        }
        catch (Exception exception)
        {
            shouldPersistRestoredSession = false;
            await ShowErrorAsync(
                "تعذّرت استعادة الجلسة السابقة",
                exception.Message);
        }
        finally
        {
            _isRestoringSession = false;
            if (shouldPersistRestoredSession)
            {
                await PersistCurrentSessionAsync();
            }
        }
    }

    private async void DocumentTabs_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (_sessionRestoreStarted && !_isRestoringSession)
        {
            await PersistCurrentSessionAsync();
        }
    }

    private async Task PersistCurrentSessionAsync()
    {
        if (!_sessionRestoreStarted || _isRestoringSession)
        {
            return;
        }

        var openPaths = DocumentTabs.TabItems
            .OfType<TabViewItem>()
            .Where(tab => tab.IsClosable && tab.Tag is string)
            .Select(tab => (string)tab.Tag!)
            .ToArray();

        var activePath = (DocumentTabs.SelectedItem as TabViewItem)?.Tag as string;

        try
        {
            await _documentSession.SaveAsync(openPaths, activePath);
        }
        catch
        {
            // Session persistence is best-effort; it must never prevent
            // a document from opening or being closed.
        }
    }

    private void HomeButton_Click(object sender, RoutedEventArgs e)
    {
        DocumentTabs.SelectedIndex = 0;
    }

    private void RootNavigation_SelectionChanged(
        NavigationView sender,
        NavigationViewSelectionChangedEventArgs e)
    {
        if (e.SelectedItemContainer?.Content?.ToString() == "الرئيسية")
        {
            DocumentTabs.SelectedIndex = 0;
        }
    }

    private async void OpenDocumentButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var picker = new FileOpenPicker();
            picker.FileTypeFilter.Add(".pdf");
            foreach (var extension in new[] { ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff" })
            {
                picker.FileTypeFilter.Add(extension);
            }

            var windowHandle = WindowNative.GetWindowHandle(this);
            InitializeWithWindow.Initialize(picker, windowHandle);

            var file = await picker.PickSingleFileAsync();
            if (file is null)
            {
                return;
            }

            await _recentDocuments.RecordOpenedAsync(file.Path);
            OpenDocumentInTab(file.Path);
        }
        catch (Exception exception)
        {
            await ShowErrorAsync("تعذّر فتح المستند", exception.Message);
        }
    }

    private async void HomePage_OpenDocumentRequested(
        object? sender,
        string filePath)
    {
        try
        {
            await _recentDocuments.RecordOpenedAsync(filePath);
            OpenDocumentInTab(filePath);
        }
        catch (Exception exception)
        {
            await ShowErrorAsync("تعذّر فتح الملف", exception.Message);
        }
    }

    private void DocumentFrame_Navigated(
        object sender,
        Microsoft.UI.Xaml.Navigation.NavigationEventArgs e)
    {
        if (e.Content is not PdfViewerPage pdfPage)
        {
            return;
        }

        pdfPage.AnnotatedCopySaved -= PdfViewerPage_AnnotatedCopySaved;
        pdfPage.AnnotatedCopySaved += PdfViewerPage_AnnotatedCopySaved;
    }

    private async void PdfViewerPage_AnnotatedCopySaved(
        object? sender,
        string savedPath)
    {
        var tab = DocumentTabs.TabItems
            .OfType<TabViewItem>()
            .FirstOrDefault(item =>
                item.Content is Frame frame &&
                ReferenceEquals(frame.Content, sender));

        if (tab is null)
        {
            return;
        }

        var fullPath = Path.GetFullPath(savedPath);
        tab.Tag = fullPath;
        tab.Header = Path.GetFileName(fullPath);

        try
        {
            await _recentDocuments.RecordOpenedAsync(fullPath);
            await PersistCurrentSessionAsync();
        }
        catch (Exception exception)
        {
            await ShowErrorAsync(
                "تم حفظ نسخة PDF، لكن تعذّر تحديث قائمة الملفات الأخيرة",
                exception.Message);
        }
    }

    private void OpenDocumentInTab(string filePath)
    {
        var fullPath = Path.GetFullPath(filePath);

        var existingTab = DocumentTabs.TabItems
            .OfType<TabViewItem>()
            .FirstOrDefault(tab =>
                string.Equals(
                    tab.Tag as string,
                    fullPath,
                    StringComparison.OrdinalIgnoreCase));

        if (existingTab is not null)
        {
            DocumentTabs.SelectedItem = existingTab;
            return;
        }

        var extension = Path.GetExtension(fullPath).ToLowerInvariant();
        var pageType = extension switch
        {
            ".pdf" => typeof(PdfViewerPage),
            ".png" or ".jpg" or ".jpeg" or ".bmp" or ".gif" or ".webp" or ".tif" or ".tiff"
                => typeof(ImageViewerPage),
            _ => throw new NotSupportedException(
                $"The file type '{extension}' is not supported by the current C# viewer.")
        };

        var documentFrame = new Frame();
        documentFrame.Navigated += DocumentFrame_Navigated;
        documentFrame.Navigate(pageType, fullPath);

        var tab = new TabViewItem
        {
            Header = Path.GetFileName(fullPath),
            Tag = fullPath,
            IsClosable = true,
            Content = documentFrame
        };

        DocumentTabs.TabItems.Add(tab);
        DocumentTabs.SelectedItem = tab;
    }

    private async void DocumentTabs_TabCloseRequested(
        TabView sender,
        TabViewTabCloseRequestedEventArgs e)
    {
        var tab = e.Tab;
        if (!tab.IsClosable)
        {
            return;
        }

        if (tab.Content is Frame existingFrame &&
            existingFrame.Content is PdfViewerPage currentPdfPage &&
            currentPdfPage.HasUnsavedAnnotations)
        {
            var confirmClose = new ContentDialog
            {
                Title = "هناك تعليقات لم يتم حفظها",
                Content = "إغلاق هذا التبويب الآن سيؤدي إلى فقدان التعليقات المضافة منذ آخر حفظ. هل تريد الإغلاق بدون حفظ؟",
                PrimaryButtonText = "إغلاق بدون حفظ",
                CloseButtonText = "العودة إلى المستند",
                DefaultButton = ContentDialogButton.Close,
                XamlRoot = RootNavigation.XamlRoot
            };

            var closeResult = await confirmClose.ShowAsync();
            if (closeResult != ContentDialogResult.Primary)
            {
                return;
            }
        }

        if (tab.Content is Frame frame)
        {
            if (frame.Content is PdfViewerPage pdfPage)
            {
                pdfPage.AnnotatedCopySaved -= PdfViewerPage_AnnotatedCopySaved;
            }

            frame.Navigated -= DocumentFrame_Navigated;

            // Navigate away so the current document page releases its native handles.
            frame.Navigate(typeof(HomePage));
        }

        DocumentTabs.TabItems.Remove(tab);
        if (DocumentTabs.SelectedItem is null && DocumentTabs.TabItems.Count > 0)
        {
            DocumentTabs.SelectedIndex = 0;
        }

        await PersistCurrentSessionAsync();
    }

    private async void MergePdfsButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var openPicker = new FileOpenPicker
            {
                ViewMode = PickerViewMode.List,
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary
            };
            openPicker.FileTypeFilter.Add(".pdf");
            InitializeWithWindow.Initialize(
                openPicker,
                WindowNative.GetWindowHandle(this));

            var selectedFiles = await openPicker.PickMultipleFilesAsync();
            if (selectedFiles.Count < 2)
            {
                await ShowMessageAsync(
                    "اختيار ملفات PDF",
                    "اختر ملفين PDF على الأقل لإتمام عملية الدمج.");
                return;
            }

            var savePicker = new FileSavePicker
            {
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
                SuggestedFileName = "Merged.pdf"
            };
            savePicker.FileTypeChoices.Add(
                "ملف PDF",
                new List<string> { ".pdf" });

            InitializeWithWindow.Initialize(
                savePicker,
                WindowNative.GetWindowHandle(this));

            var destination = await savePicker.PickSaveFileAsync();
            if (destination is null)
            {
                return;
            }

            if (File.Exists(destination.Path))
            {
                var replaceDialog = new ContentDialog
                {
                    Title = "الملف موجود بالفعل",
                    Content = $"هل تريد استبدال الملف التالي؟\n{destination.Path}",
                    PrimaryButtonText = "استبدال",
                    CloseButtonText = "إلغاء",
                    DefaultButton = ContentDialogButton.Close,
                    XamlRoot = RootNavigation.XamlRoot
                };

                if (await replaceDialog.ShowAsync() != ContentDialogResult.Primary)
                {
                    return;
                }
            }

            var sourcePaths = selectedFiles
                .Select(file => file.Path)
                .ToArray();

            var pageCount = await _pdfMergeService.MergeAsync(
                sourcePaths,
                destination.Path);

            await _recentDocuments.RecordOpenedAsync(destination.Path);
            OpenDocumentInTab(destination.Path);

            await ShowMessageAsync(
                "اكتمل دمج ملفات PDF",
                $"تم دمج {selectedFiles.Count} ملفات في مستند واحد يحتوي على {pageCount} صفحة.");
        }
        catch (Exception exception)
        {
            await ShowErrorAsync("تعذّر دمج ملفات PDF", exception.Message);
        }
    }

    private async Task ShowMessageAsync(string title, string message)
    {
        var dialog = new ContentDialog
        {
            Title = title,
            Content = message,
            CloseButtonText = "موافق",
            XamlRoot = RootNavigation.XamlRoot
        };

        await dialog.ShowAsync();
    }

    private async Task ShowErrorAsync(string title, string message)
    {
        var dialog = new ContentDialog
        {
            Title = title,
            Content = message,
            CloseButtonText = "موافق",
            XamlRoot = RootNavigation.XamlRoot
        };

        await dialog.ShowAsync();
    }
}
