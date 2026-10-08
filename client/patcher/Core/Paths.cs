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
    private sealed record ProfileData(string Profile, FileSpec[] Markers);
    private static readonly ProfileData Data = Load();
    public static string Profile => Data.Profile;
    public static IReadOnlyList<FileSpec> Markers => Array.AsReadOnly(Data.Markers);
    private static ProfileData Load()
    {
        using var source = typeof(Baseline).Assembly.GetManifestResourceStream("baseline.json")
            ?? throw new InvalidDataException("Missing compiled client profile.");
        using var bytes = new MemoryStream(); source.CopyTo(bytes);
        return ReleaseCodec.Parse<ProfileData>(bytes.ToArray());
    }
}
