namespace Shadowbane.Patching;

public static class SafePaths
{
    public static string Root(string root)
    {
        var full = Path.TrimEndingDirectorySeparator(Path.GetFullPath(root));
        if (!Directory.Exists(full)) throw new DirectoryNotFoundException("Choose the folder containing sb.exe.");
        RejectIndirection(full);
        return full;
    }
    public static void RejectIndirection(string path)
    {
        for (var current = Path.GetFullPath(path); !string.IsNullOrEmpty(current); current = Path.GetDirectoryName(current))
        {
            try
            {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("Client and update paths cannot use junctions or symbolic links.");
            }
            catch (FileNotFoundException) { }
            catch (DirectoryNotFoundException) { }
        }
    }
    public static string Within(string root, string relative)
    {
        if (relative.Contains('\\') || relative.Contains(':') || Path.IsPathRooted(relative) ||
            relative.Split('/').Any(p => p.Length == 0 || p is "." or ".."))
            throw new IOException("Unsafe update path.");
        var full = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new IOException("Update path escaped the client folder.");
        RejectIndirection(full);
        return full;
    }
    public static void AtomicWrite(string path, byte[] bytes)
    {
        RejectIndirection(path);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { stream.Write(bytes); stream.Flush(true); }
            RejectIndirection(path);
            if (File.Exists(path)) File.Replace(temporary, path, null);
            else File.Move(temporary, path);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}

public static class Baseline
{
    public const string Profile = "wonderbane-1.3.38.14-objects-20261007-v1";
    public static readonly FileSpec[] Markers =
    [
        new("sb.exe", 21143613, "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e"),
        new("cache/CObjects.cache", 5433065, "08c115baeef5da811f7ee2802ccdc1002cfeba29cf1818956c452e3e594efef6")
    ];
}
