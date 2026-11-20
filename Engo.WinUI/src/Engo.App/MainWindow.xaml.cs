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

    public MainWindow()
    {
        InitializeComponent();

        Title = "Engo PDF Viewer & AI Study Agent";

        _recentDocuments = new RecentDocumentsService(
            new JsonRecentDocumentsRepository());

        HomeFrame.Navigated += HomeFrame_Navigated;
        HomeFrame.Navigate(typeof(HomePage));
        DocumentTabs.SelectedIndex = 0;
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

    private void HomeButton_Click(object sender, RoutedEventArgs e)
    {
        DocumentTabs.SelectedIndex = 0;
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

    private void DocumentTabs_TabCloseRequested(
        TabView sender,
        TabViewTabCloseRequestedEventArgs e)
    {
        if (e.Item is not TabViewItem tab || !tab.IsClosable)
        {
            return;
        }

        if (tab.Content is Frame frame)
        {
            // Navigate away so the PDF page releases its native document handle.
            frame.Navigate(typeof(HomePage));
        }

        DocumentTabs.TabItems.Remove(tab);
        DocumentTabs.SelectedIndex = 0;
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
