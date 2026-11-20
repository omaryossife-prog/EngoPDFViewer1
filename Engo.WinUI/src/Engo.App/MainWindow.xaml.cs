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

        ContentFrame.Navigate(typeof(HomePage));
    }

    private async void OpenPdfButton_Click(object sender, RoutedEventArgs e)
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

        try
        {
            await _recentDocuments.RecordOpenedAsync(file.Path);
            ContentFrame.Navigate(typeof(PdfViewerPage), file.Path);
        }
        catch (Exception exception)
        {
            var dialog = new ContentDialog
            {
                Title = "تعذّر فتح الملف",
                Content = exception.Message,
                CloseButtonText = "موافق",
                XamlRoot = RootNavigation.XamlRoot
            };

            await dialog.ShowAsync();
        }
    }
}
