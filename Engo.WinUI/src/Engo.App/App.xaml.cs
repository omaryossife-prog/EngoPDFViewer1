using Microsoft.UI.Xaml;

namespace Engo.App;

public partial class App : Application
{
    private Window? _mainWindow;

    public static MainWindow? MainWindowInstance { get; private set; }

    public App()
    {
        InitializeComponent();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        MainWindowInstance = new MainWindow();
        _mainWindow = MainWindowInstance;
        _mainWindow.Activate();
    }
}
