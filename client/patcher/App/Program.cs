using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Windows;
using Shadowbane.Patching;

namespace Shadowbane.Patcher;

public sealed record Options(string Root, string Feed, string Mode, string? Report, string? Preview);
public sealed record FeedSettings(string FeedUrl);
public sealed record UserPreferences(string ClientRoot);

public static class Program
{
    public static string PublicKey
    {
        get
        {
            using var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("release-public.pem")
                ?? throw new InvalidDataException("The release trust key is missing.");
            using var reader = new StreamReader(resource); return reader.ReadToEnd();
        }
    }
    private static string PreferencePath => Path.Combine(Environment.GetFolderPath(
        Environment.SpecialFolder.LocalApplicationData), "ShadowbanePatcher", "preferences.json");
    public static void SaveRoot(string root) => SafePaths.AtomicWrite(PreferencePath,
        JsonSerializer.SerializeToUtf8Bytes(new UserPreferences(root), ReleaseCodec.Json));
    private static Options Parse(string[] args)
    {
        string root = AppContext.BaseDirectory, feed = "", mode = "window";
        string? report = null, preview = null;
        var settings = Path.Combine(AppContext.BaseDirectory, "PatcherFeed.json");
        if (File.Exists(settings))
            feed = ReleaseCodec.Parse<FeedSettings>(ReadBounded(settings)).FeedUrl;
        if (!File.Exists(Path.Combine(root, "sb.exe")) && File.Exists(PreferencePath))
            root = ReleaseCodec.Parse<UserPreferences>(ReadBounded(PreferencePath)).ClientRoot;
        var seen = new HashSet<string>();
        for (int i = 0; i < args.Length; ++i)
        {
            var option = args[i];
            if (!seen.Add(option)) throw new ArgumentException("An option was supplied twice.");
            if (option is "--inspect" or "--apply" or "--play")
            {
                if (mode != "window") throw new ArgumentException("Choose one patcher operation.");
                mode = option[2..]; continue;
            }
            if (option is not ("--client-root" or "--feed" or "--report" or "--preview-output") || ++i == args.Length)
                throw new ArgumentException("Use --client-root PATH, --feed URL_OR_FOLDER and one of --inspect, --apply, --play.");
            switch (option)
            {
                case "--client-root": root = args[i]; break;
                case "--feed": feed = args[i]; break;
                case "--report": report = args[i]; break;
                case "--preview-output": preview = args[i]; break;
            }
        }
        if (preview is not null && mode != "window") throw new ArgumentException("Preview requires window mode.");
        return new(root, feed, mode, report, preview);
    }
    private static byte[] ReadBounded(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > ReleaseCodec.MaximumManifest) throw new InvalidDataException("Patcher settings are too large.");
        var bytes = new byte[(int)stream.Length]; stream.ReadExactly(bytes); return bytes;
    }
    private static void Report(object value, string? path)
    {
        var json = JsonSerializer.Serialize(value, ReleaseCodec.Json);
        Console.WriteLine(json);
        if (path is null) return;
        using var file = new StreamWriter(new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None));
        file.WriteLine(json);
    }
    [STAThread]
    public static int Main(string[] args)
    {
        Options? options = null;
        bool cli = args.Any(a => a is "--inspect" or "--apply" or "--play" or "--preview-output");
        try
        {
            options = Parse(args);
            if (options.Mode != "window")
            {
                var updater = new Updater(options.Root, PublicKey);
                if (options.Mode == "play") Report(new { status = "launching", launcherPid = updater.Play() }, options.Report);
                else
                {
                    using var feed = new ReleaseFeed(options.Feed);
                    if (options.Mode == "apply")
                    {
                        updater.Apply(feed, _ => {});
                        var applied = updater.VerifyInstalled();
                        Report(new { status = "installed", version = applied.Release.Version,
                            sequence = applied.Release.Sequence }, options.Report);
                    }
                    else
                    {
                        var plan = updater.Check(feed);
                        Report(new { status = "inspected", version = plan.Candidate.Release.Version,
                            sequence = plan.Candidate.Release.Sequence, changedFiles = plan.Needed.Select(f => f.Path),
                            plan.Interrupted, plan.GameRunning }, options.Report);
                    }
                }
                return 0;
            }
            var app = new Application();
            var window = new MainWindow(options);
            if (options.Preview is not null)
            {
                app.ShutdownMode = ShutdownMode.OnExplicitShutdown;
                app.Startup += async (_, _) =>
                {
                    try { await window.RefreshAsync(); window.RenderPreview(options.Preview); app.Shutdown(0); }
                    catch (Exception error) { Console.Error.WriteLine(error.Message); app.Shutdown(1); }
                };
                return app.Run();
            }
            app.MainWindow = window;
            return app.Run(window);
        }
        catch (Exception error)
        {
            try { Report(new { status = "failed", message = error.Message }, options?.Report); } catch (IOException) { }
            if (!cli) MessageBox.Show(error.Message, "Shadowbane patcher", MessageBoxButton.OK, MessageBoxImage.Error);
            return 1;
        }
    }
}
