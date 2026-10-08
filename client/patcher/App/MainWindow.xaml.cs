using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Microsoft.Win32;
using Shadowbane.Patching;

namespace Shadowbane.Patcher;

public partial class MainWindow : Window
{
    private readonly string feedLocation;
    private CancellationTokenSource? cancellation;
    private bool busy;
    public MainWindow(Options options)
    {
        InitializeComponent();
        feedLocation = options.Feed; RootBox.Text = options.Root;
        if (options.Preview is null) Loaded += async (_, _) => await RefreshAsync();
        Closing += (_, e) =>
        {
            if (!busy) return;
            e.Cancel = true; cancellation?.Cancel();
            Status.Text = "Finishing the current operation. You can close the patcher when it finishes.";
        };
    }
    private void SetBusy(bool value)
    {
        busy = value;
        BrowseButton.IsEnabled = CheckButton.IsEnabled = !value;
        UpdateButton.IsEnabled = PlayButton.IsEnabled = false;
        CancelButton.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
        Progress.IsIndeterminate = value; Progress.Value = 0;
        if (value) cancellation = new CancellationTokenSource();
        else { cancellation?.Dispose(); cancellation = null; }
    }
    public async Task RefreshAsync()
    {
        if (busy) return;
        SetBusy(true); Status.Text = "Checking the client and private update feed…";
        var root = RootBox.Text; var token = cancellation!.Token;
        UpdatePlan? plan = null; VerifiedRelease? installed = null; bool running = false;
        string? failure = null;
        try
        {
            await Task.Run(() =>
            {
                var updater = new Updater(root, Program.PublicKey);
                try
                {
                    using var feed = new ReleaseFeed(feedLocation);
                    plan = updater.Check(feed, token);
                }
                catch (Exception error) { failure = error.Message; }
                try { installed = updater.VerifyInstalled(); }
                catch (Exception error) { failure ??= error.Message; }
                running = new ClientGuard().IsRunning(updater.Root);
            });
            if (plan is not null)
            {
                VersionLabel.Text = "Release " + plan.Candidate.Release.Version;
                Notes.Text = string.Join("\n\n", plan.Candidate.Release.Notes);
                Subtitle.Text = plan.Interrupted ? "Let's finish your interrupted update." :
                    plan.Needed.Length > 0 || installed is null ? "Your next client update is ready." : "You're up to date.";
                Status.Text = running ? "Game is running. Close it before updating." :
                    plan.Interrupted ? "Repair will finish the interrupted release before Play is enabled." :
                    plan.Needed.Length > 0 ? $"{plan.Needed.Length} file(s) to update. Your settings are preserved." :
                    installed is null ? "Verify and register this release with Update / Repair." : "Client verified. Ready to play.";
            }
            else
            {
                VersionLabel.Text = installed is null ? "Feed unavailable" : "Installed " + installed.Release.Version;
                if (installed is not null) Notes.Text = string.Join("\n\n", installed.Release.Notes);
                Subtitle.Text = installed is null ? "Connect to Tailscale to check for updates." : "Installed release verified.";
                Status.Text = (installed is null ? "" : "You can play the verified installed release. ") + failure;
            }
        }
        catch (Exception error) { Status.Text = error.Message; Subtitle.Text = "Select your dedicated game folder."; }
        finally
        {
            SetBusy(false);
            UpdateButton.IsEnabled = plan is not null && !running;
            PlayButton.IsEnabled = installed is not null && !running;
        }
    }
    private async void CheckClicked(object sender, RoutedEventArgs e) => await RefreshAsync();
    private async void BrowseClicked(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFolderDialog { Title = "Choose the Shadowbane folder containing sb.exe", Multiselect = false };
        if (dialog.ShowDialog(this) != true) return;
        RootBox.Text = dialog.FolderName;
        try { Program.SaveRoot(SafePaths.Root(dialog.FolderName)); }
        catch (Exception error) { Status.Text = error.Message; return; }
        await RefreshAsync();
    }
    private async void UpdateClicked(object sender, RoutedEventArgs e)
    {
        if (busy) return;
        SetBusy(true); Status.Text = "Preparing the update…";
        var root = RootBox.Text; var token = cancellation!.Token;
        var progress = new Progress<UpdateProgress>(state =>
        {
            Status.Text = state.Message;
            Progress.IsIndeterminate = state.Total == 0;
            if (state.Total > 0) Progress.Value = state.Completed * 100.0 / state.Total;
        });
        string? failure = null;
        try
        {
            await Task.Run(() =>
            {
                using var feed = new ReleaseFeed(feedLocation);
                new Updater(root, Program.PublicKey).Apply(feed, state =>
                    ((IProgress<UpdateProgress>)progress).Report(state), token);
            });
        }
        catch (OperationCanceledException) { failure = "Update canceled before installation. Check again when ready."; }
        catch (Exception error) { failure = error.Message; }
        finally { SetBusy(false); }
        await RefreshAsync();
        if (failure is not null) Status.Text = failure;
    }
    private async void PlayClicked(object sender, RoutedEventArgs e)
    {
        if (busy) return;
        SetBusy(true); Status.Text = "Verifying and starting Shadowbane…";
        var root = RootBox.Text;
        try
        {
            await Task.Run(() => new Updater(root, Program.PublicKey).Play());
            Status.Text = "Game launcher started."; WindowState = WindowState.Minimized;
        }
        catch (Exception error) { Status.Text = error.Message; }
        finally { SetBusy(false); }
    }
    private void CancelClicked(object sender, RoutedEventArgs e) => cancellation?.Cancel();
    public void RenderPreview(string path)
    {
        var content = (FrameworkElement)Content;
        content.Measure(new Size(964, 611)); content.Arrange(new Rect(0, 0, 964, 611)); content.UpdateLayout();
        var bitmap = new RenderTargetBitmap(964, 611, 96, 96, PixelFormats.Pbgra32); bitmap.Render(content);
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None); encoder.Save(file);
    }
}
