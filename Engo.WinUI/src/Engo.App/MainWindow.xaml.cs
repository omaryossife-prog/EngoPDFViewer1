using Engo.App.Views;
using Microsoft.UI.Xaml;

namespace Engo.App;

public sealed partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();

        Title = "Engo PDF Viewer & AI Study Agent";
        ContentFrame.Navigate(typeof(HomePage));
    }
}
