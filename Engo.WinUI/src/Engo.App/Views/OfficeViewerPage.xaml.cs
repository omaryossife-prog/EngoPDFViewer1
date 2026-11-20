using Engo.Application.Documents;
using Engo.Infrastructure.Office;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace Engo.App.Views;

public sealed partial class OfficeViewerPage : Page
{
    private readonly IOfficeDocumentReader _reader = new OpenXmlOfficeDocumentReader();
    private CancellationTokenSource? _loadCancellation;
    private OfficeDocumentPreview? _preview;
    private int _activePageIndex;
    private bool _webViewInitialized;

    public OfficeViewerPage()
    {
        InitializeComponent();
    }

    protected override async void OnNavigatedTo(NavigationEventArgs e)
    {
        base.OnNavigatedTo(e);

        if (e.Parameter is string filePath && !string.IsNullOrWhiteSpace(filePath))
        {
            _loadCancellation?.Cancel();
            _loadCancellation?.Dispose();
            _loadCancellation = new CancellationTokenSource();
            await LoadDocumentAsync(filePath, _loadCancellation.Token);
        }
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e)
    {
        _loadCancellation?.Cancel();
        _loadCancellation?.Dispose();
        _loadCancellation = null;
        CleanupPreview();
        base.OnNavigatedFrom(e);
    }

    private async Task LoadDocumentAsync(
        string filePath,
        CancellationToken cancellationToken)
    {
        LoadingRing.IsActive = true;
        ErrorInfoBar.IsOpen = false;
        DocumentNameText.Text = Path.GetFileName(filePath);

        try
        {
            var preview = await _reader.CreatePreviewAsync(filePath, cancellationToken);
            _preview = preview;
            cancellationToken.ThrowIfCancellationRequested();

            if (!_webViewInitialized)
            {
                await OfficeWebView.EnsureCoreWebView2Async();
                cancellationToken.ThrowIfCancellationRequested();

                OfficeWebView.CoreWebView2.Settings.IsScriptEnabled = false;
                OfficeWebView.CoreWebView2.Settings.AreDevToolsEnabled = false;
                OfficeWebView.CoreWebView2.Settings.IsStatusBarEnabled = false;
                _webViewInitialized = true;
            }

            _activePageIndex = 0;
            UpdatePageNavigation();
            NavigateToCurrentPage();
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Closing the tab cancels document parsing and WebView initialization.
        }
        catch (Exception exception)
        {
            CleanupPreview();
            ErrorInfoBar.Message = exception.GetType().Name.Contains(
                "WebView2RuntimeNotFoundException",
                StringComparison.Ordinal)
                ? "مكوّن Microsoft Edge WebView2 Runtime غير مثبت. ثبّته ثم أعد فتح مستند Office."
                : exception.Message;
            ErrorInfoBar.IsOpen = true;
        }
        finally
        {
            LoadingRing.IsActive = false;
        }
    }

    private void NavigateToCurrentPage()
    {
        if (_preview is null ||
            _activePageIndex < 0 ||
            _activePageIndex >= _preview.Pages.Count)
        {
            return;
        }

        var page = _preview.Pages[_activePageIndex];
        PageLabelText.Text = page.Label;
        OfficeWebView.CoreWebView2?.Navigate(new Uri(page.HtmlFilePath).AbsoluteUri);
        UpdatePageNavigation();
    }

    private void UpdatePageNavigation()
    {
        var pageCount = _preview?.Pages.Count ?? 0;
        var isPresentation = _preview?.Kind == Engo.Domain.Documents.DocumentKind.PowerPoint &&
                            pageCount > 1;

        PreviousPageButton.Visibility = isPresentation
            ? Visibility.Visible
            : Visibility.Collapsed;
        NextPageButton.Visibility = isPresentation
            ? Visibility.Visible
            : Visibility.Collapsed;
        PreviousPageButton.IsEnabled = isPresentation && _activePageIndex > 0;
        NextPageButton.IsEnabled = isPresentation && _activePageIndex < pageCount - 1;

        if (!isPresentation && _preview?.Pages.Count == 1)
        {
            PageLabelText.Text = _preview.Pages[0].Label;
        }
    }

    private void PreviousPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (_preview is null || _activePageIndex <= 0)
        {
            return;
        }

        _activePageIndex--;
        NavigateToCurrentPage();
    }

    private void NextPageButton_Click(object sender, RoutedEventArgs e)
    {
        if (_preview is null || _activePageIndex >= _preview.Pages.Count - 1)
        {
            return;
        }

        _activePageIndex++;
        NavigateToCurrentPage();
    }

    private void OfficeWebView_NavigationStarting(
        WebView2 sender,
        Microsoft.Web.WebView2.Core.CoreWebView2NavigationStartingEventArgs args)
    {
        if (string.Equals(args.Uri, "about:blank", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        if (_preview is null ||
            !Uri.TryCreate(args.Uri, UriKind.Absolute, out var targetUri) ||
            !targetUri.IsFile ||
            !IsPathWithinDirectory(targetUri.LocalPath, _preview.PreviewDirectory))
        {
            // The reader emits local, script-free previews only. Do not let a
            // document hyperlink or malformed package navigate to the network.
            args.Cancel = true;
        }
    }

    private static bool IsPathWithinDirectory(string path, string directory)
    {
        var fullPath = Path.GetFullPath(path);
        var fullDirectory = Path.GetFullPath(directory)
            .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            + Path.DirectorySeparatorChar;

        return fullPath.StartsWith(
            fullDirectory,
            StringComparison.OrdinalIgnoreCase);
    }

    private void CleanupPreview()
    {
        var preview = _preview;
        _preview = null;

        try
        {
            if (OfficeWebView.CoreWebView2 is not null)
            {
                OfficeWebView.CoreWebView2.Navigate("about:blank");
            }
        }
        catch
        {
            // Ignore cleanup errors during tab close.
        }

        if (preview is not null)
        {
            try
            {
                if (Directory.Exists(preview.PreviewDirectory))
                {
                    Directory.Delete(preview.PreviewDirectory, recursive: true);
                }
            }
            catch
            {
                // A WebView2 file handle may still be closing. Orphaned preview
                // directories can be removed on a subsequent application launch.
            }
        }
    }
}
