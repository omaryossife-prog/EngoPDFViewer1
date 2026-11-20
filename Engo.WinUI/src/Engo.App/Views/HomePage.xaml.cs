using Engo.Application.Documents;
using Engo.Domain.Documents;
using Engo.Infrastructure.Persistence;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Engo.App.Views;

public sealed partial class HomePage : Page
{
    private readonly RecentDocumentsService _recentDocuments = new(
        new JsonRecentDocumentsRepository());

    public event EventHandler<string>? OpenDocumentRequested;

    public HomePage()
    {
        InitializeComponent();
    }

    private async void HomePage_Loaded(object sender, RoutedEventArgs e)
    {
        await RefreshRecentDocumentsAsync();
    }

    private async Task RefreshRecentDocumentsAsync()
    {
        try
        {
            var recent = await _recentDocuments.GetRecentAsync();
            var availablePdfs = recent
                .Where(document =>
                    document.Kind == DocumentKind.Pdf &&
                    File.Exists(document.FullPath))
                .ToArray();

            RecentDocumentsList.ItemsSource = availablePdfs;
            RecentDocumentsEmptyText.Visibility = availablePdfs.Length == 0
                ? Visibility.Visible
                : Visibility.Collapsed;
        }
        catch (Exception exception)
        {
            RecentDocumentsEmptyText.Text = $"تعذّر تحميل الملفات الأخيرة: {exception.Message}";
            RecentDocumentsEmptyText.Visibility = Visibility.Visible;
        }
    }

    private void RecentDocumentsList_SelectionChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (RecentDocumentsList.SelectedItem is not DocumentReference document)
        {
            return;
        }

        OpenDocumentRequested?.Invoke(this, document.FullPath);
        RecentDocumentsList.SelectedItem = null;
    }
}
