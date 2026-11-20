using Engo.App.Views;
using Engo.Application.Documents;
using Engo.Infrastructure.Persistence;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace Engo.App;

public sealed partial class MainWindow : Window
{
    private readonly RecentDocumentsService _recentDocuments;
    private readonly DocumentSessionService _documentSession;
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
                    OpenPdfInTab(path);
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

    private async void OpenPdfButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var picker = new FileOpenPicker();
            picker.FileTypeFilter.Add(".pdf");

            var windowHandle = WindowNative.GetWindowHandle(this);
            InitializeWithWindow.Initialize(picker, windowHandle);

            var file = await picker.PickSingleFileAsync();
            if (file is null)
            {
                return;
            }

            await _recentDocuments.RecordOpenedAsync(file.Path);
            OpenPdfInTab(file.Path);
        }
        catch (Exception exception)
        {
            await ShowErrorAsync("تعذّر فتح ملف PDF", exception.Message);
        }
    }

    private async void HomePage_OpenDocumentRequested(
        object? sender,
        string filePath)
    {
        try
        {
            await _recentDocuments.RecordOpenedAsync(filePath);
            OpenPdfInTab(filePath);
        }
        catch (Exception exception)
        {
            await ShowErrorAsync("تعذّر فتح الملف", exception.Message);
        }
    }

    private void OpenPdfInTab(string filePath)
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

        var documentFrame = new Frame();
        documentFrame.Navigate(typeof(PdfViewerPage), fullPath);

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

        if (tab.Content is Frame frame)
        {
            // Navigate away so the PDF page releases its native document handle.
            frame.Navigate(typeof(HomePage));
        }

        DocumentTabs.TabItems.Remove(tab);
        if (DocumentTabs.SelectedItem is null && DocumentTabs.TabItems.Count > 0)
        {
            DocumentTabs.SelectedIndex = 0;
        }

        await PersistCurrentSessionAsync();
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
