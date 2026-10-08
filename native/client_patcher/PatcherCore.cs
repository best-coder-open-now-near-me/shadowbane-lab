using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

namespace ShadowbaneLocal {
public sealed class Channel {
    public int schema_version { get; set; }
    public string version { get; set; }
    public string manifest_url { get; set; }
    public string manifest_sha256 { get; set; }
}
public sealed class Bundle {
    public string name { get; set; }
    public string url { get; set; }
    public string sha256 { get; set; }
    public long size { get; set; }
}
public sealed class ClientFile {
    public string path { get; set; }
    public string sha256 { get; set; }
    public long size { get; set; }
    public string bundle { get; set; }
    public string policy { get; set; }
}
public sealed class Manifest {
    public int schema_version { get; set; }
    public int minimum_patcher { get; set; }
    public string version { get; set; }
    public string server { get; set; }
    public int port { get; set; }
    public Bundle[] bundles { get; set; }
    public ClientFile[] files { get; set; }
}
public interface ITransport {
    byte[] Metadata(string url, CancellationToken cancel);
    void Download(Bundle bundle, string target, Action<string> progress, CancellationToken cancel);
}
public sealed class HttpTransport : ITransport {
    static HttpWebResponse Open(string url) {
        Engine.RequireReleaseUrl(url);
        var request = (HttpWebRequest)WebRequest.Create(url);
        request.UserAgent = "ShadowbaneLocal-Patcher/1.0";
        request.Timeout = 60000; request.ReadWriteTimeout = 30000;
        var response = (HttpWebResponse)request.GetResponse();
        if (response.ResponseUri.Scheme != "https") { response.Dispose(); throw new IOException("Insecure download redirect."); }
        return response;
    }
    public byte[] Metadata(string url, CancellationToken cancel) {
        // The channel URL is a fixed, publisher-owned HTTPS endpoint.
        HttpWebRequest request = (HttpWebRequest)WebRequest.Create(url);
        if (url != Engine.ChannelUrl) Engine.RequireReleaseUrl(url);
        request.UserAgent = "ShadowbaneLocal-Patcher/1.0";
        request.Timeout = 30000; request.ReadWriteTimeout = 30000;
        using (var response = (HttpWebResponse)request.GetResponse())
        using (var input = response.GetResponseStream())
        using (var output = new MemoryStream()) {
            if (response.ResponseUri.Scheme != "https") throw new IOException("Insecure metadata redirect.");
            var buffer = new byte[65536]; int count;
            while ((count = input.Read(buffer, 0, buffer.Length)) != 0) {
                cancel.ThrowIfCancellationRequested();
                if (output.Length + count > 2 * 1024 * 1024) throw new IOException("Update manifest is too large.");
                output.Write(buffer, 0, count);
            }
            return output.ToArray();
        }
    }
    public void Download(Bundle bundle, string target, Action<string> progress, CancellationToken cancel) {
        using (var response = Open(bundle.url))
        using (var input = response.GetResponseStream())
        using (var output = new FileStream(target, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
            var buffer = new byte[1024 * 1024]; int count; long total = 0; long next = 0;
            while ((count = input.Read(buffer, 0, buffer.Length)) != 0) {
                cancel.ThrowIfCancellationRequested(); total += count;
                if (total > bundle.size) throw new IOException("Download exceeds its published size.");
                output.Write(buffer, 0, count);
                if (total >= next) {
                    progress("Downloading " + bundle.name + "  " + (total / 1048576) + " / " + (bundle.size / 1048576) + " MB");
                    next = total + 8 * 1048576;
                }
            }
            if (total != bundle.size) throw new IOException("Download was incomplete. Please retry.");
            output.Flush(true);
        }
    }
}
public static class Engine {
    public const string ChannelUrl = "https://raw.githubusercontent.com/best-coder-open-now-near-me/shadowbane-lab/codex/client-release-channel/channel.json";
    public const string ReleasePrefix = "https://github.com/best-coder-open-now-near-me/shadowbane-lab/releases/download/";
    public const int Protocol = 1;
    public static string Hash(byte[] data) {
        using (var digest = SHA256.Create()) return BitConverter.ToString(digest.ComputeHash(data)).Replace("-", "").ToLowerInvariant();
    }
    public static string HashFile(string path) {
        using (var stream = File.OpenRead(path))
        using (var digest = SHA256.Create()) return BitConverter.ToString(digest.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }
    static bool Digest(string value) { return value != null && Regex.IsMatch(value, "^[a-f0-9]{64}$"); }
    public static void RequireReleaseUrl(string value) {
        Uri uri;
        if (!Uri.TryCreate(value, UriKind.Absolute, out uri) || uri.Scheme != "https" ||
            !uri.AbsoluteUri.StartsWith(ReleasePrefix, StringComparison.Ordinal) ||
            uri.UserInfo.Length != 0 || uri.Query.Length != 0 || uri.Fragment.Length != 0)
            throw new IOException("Update URL is outside our release repository.");
    }
    public static T Parse<T>(byte[] data) {
        return new JavaScriptSerializer { MaxJsonLength = 2 * 1024 * 1024, RecursionLimit = 32 }
            .Deserialize<T>(Encoding.UTF8.GetString(data));
    }
    public static Manifest CheckChannel(ITransport transport, CancellationToken cancel) {
        var channel = Parse<Channel>(transport.Metadata(ChannelUrl, cancel));
        if (channel == null || channel.schema_version != 1 || !Digest(channel.manifest_sha256))
            throw new IOException("Unsupported update channel.");
        RequireReleaseUrl(channel.manifest_url);
        var bytes = transport.Metadata(channel.manifest_url, cancel);
        if (Hash(bytes) != channel.manifest_sha256) throw new IOException("Release manifest failed verification.");
        var manifest = Parse<Manifest>(bytes);
        Validate(manifest);
        if (manifest.version != channel.version) throw new IOException("Release versions do not agree.");
        return manifest;
    }
    public static void RelativePath(string relative) {
        if (String.IsNullOrEmpty(relative) || relative.Length > 180 || relative.Contains("\\"))
            throw new IOException("Invalid client file path.");
        foreach (var part in relative.Split('/')) {
            if (part == "." || part == ".." || !Regex.IsMatch(part, "^[A-Za-z0-9 _.-]+$") ||
                part.EndsWith(".") || part.EndsWith(" ") ||
                Regex.IsMatch(part, "^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])($|\\.)", RegexOptions.IgnoreCase))
                throw new IOException("Unsafe client file path.");
        }
        if (relative.StartsWith(".shadowbane-", StringComparison.OrdinalIgnoreCase) ||
            relative.Equals("ShadowbanePatcher.exe", StringComparison.OrdinalIgnoreCase) ||
            relative.Equals("Play-ShadowbaneLocal.cmd", StringComparison.OrdinalIgnoreCase) ||
            relative.Equals("ShadowbaneLocal.release.json", StringComparison.OrdinalIgnoreCase))
            throw new IOException("Release tries to replace a patcher-owned path.");
    }
    public static bool Personal(string path) {
        var p = path.ToLowerInvariant();
        return (p.StartsWith("config/") && p.EndsWith(".cfg")) ||
            p.StartsWith("doublefusion/") || p.StartsWith("screenshots/") ||
            p.StartsWith("logs/") || p.StartsWith("launcherlogs/");
    }
    public static void Validate(Manifest manifest) {
        if (manifest == null || manifest.schema_version != 1 || manifest.minimum_patcher < 1 ||
            manifest.minimum_patcher > Protocol || !Regex.IsMatch(manifest.version ?? "", "^[0-9]+[.][0-9]+[.][0-9]+$"))
            throw new IOException("This release needs a newer patcher. Download the current patcher from our releases page.");
        IPAddress address;
        if (!IPAddress.TryParse(manifest.server, out address) || address.AddressFamily != System.Net.Sockets.AddressFamily.InterNetwork ||
            address.GetAddressBytes()[0] != 100 || address.GetAddressBytes()[1] < 64 ||
            address.GetAddressBytes()[1] > 127 || manifest.port != 6000)
            throw new IOException("Invalid private server endpoint.");
        if (manifest.files == null || manifest.bundles == null || manifest.files.Length == 0 ||
            manifest.files.Length > 10000 || manifest.bundles.Length == 0 || manifest.bundles.Length > 1000)
            throw new IOException("Invalid release inventory.");
        var bundles = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var bundle in manifest.bundles) {
            if (bundle == null || !Regex.IsMatch(bundle.name ?? "", "^[A-Za-z0-9_.-]+\\.zip$") ||
                !bundles.Add(bundle.name) || !Digest(bundle.sha256) || bundle.size <= 0 || bundle.size >= 2147483648L)
                throw new IOException("Invalid release bundle.");
            RequireReleaseUrl(bundle.url);
        }
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var file in manifest.files) {
            if (file == null) throw new IOException("Invalid client file.");
            RelativePath(file.path);
            if (!paths.Add(file.path) || !Digest(file.sha256) || file.size < 0 || file.size >= 2147483648L ||
                !bundles.Contains(file.bundle ?? "") || (file.policy != "replace" && file.policy != "seed") ||
                (Personal(file.path) && file.policy != "seed"))
                throw new IOException("Invalid client file record or settings policy.");
        }
        foreach (var required in new[] { "sb.exe", "cache/CObjects.cache", "ShadowbaneLauncher.exe", "Config/ArcanePref.cfg" })
            if (!paths.Contains(required)) throw new IOException("Release is missing a required client component.");
        if (manifest.files.First(f => f.path.Equals("Config/ArcanePref.cfg", StringComparison.OrdinalIgnoreCase)).policy != "seed")
            throw new IOException("Personal display settings must be preserved.");
    }
    public static void PlainPath(string path) {
        for (var current = Path.GetFullPath(path); !String.IsNullOrEmpty(current); current = Path.GetDirectoryName(current)) {
            if ((File.Exists(current) || Directory.Exists(current)) &&
                (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("Linked client folders are not supported.");
        }
    }
    public static string Destination(string root, string relative) {
        RelativePath(relative);
        var path = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!path.StartsWith(Path.GetFullPath(root).TrimEnd('\\') + "\\", StringComparison.OrdinalIgnoreCase))
            throw new IOException("A client path escapes the selected folder.");
        PlainPath(path); return path;
    }
    public static bool Matches(string path, ClientFile file) {
        PlainPath(path);
        return File.Exists(path) && (file.policy == "seed" ||
            (new FileInfo(path).Length == file.size && HashFile(path) == file.sha256));
    }
    public static void ClosedGame() {
        foreach (var process in Process.GetProcessesByName("sb")) {
            using (process) if (!process.HasExited) throw new IOException("Close Shadowbane before installing updates.");
        }
    }
    public static void Atomic(string path, byte[] bytes) {
        PlainPath(path); Directory.CreateDirectory(Path.GetDirectoryName(path));
        string temporary = path + ".patch-" + Guid.NewGuid().ToString("N");
        try {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
                stream.Write(bytes, 0, bytes.Length); stream.Flush(true);
            }
            Promote(temporary, path);
        } finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    static void Promote(string temporary, string destination) {
        PlainPath(destination);
        if (File.Exists(destination)) File.Replace(temporary, destination, null, true);
        else File.Move(temporary, destination);
    }
    public static byte[] Endpoint(byte[] bytes, string server, int port) {
        if (bytes.Length > 1048576 || bytes.Contains((byte)0)) throw new IOException("Unsupported ArcaneIP.cfg.");
        var encoding = Encoding.GetEncoding(28591);
        string source = encoding.GetString(bytes), bom = "";
        if (source.StartsWith("\u00ef\u00bb\u00bf", StringComparison.Ordinal)) { bom = source.Substring(0,3); source = source.Substring(3); }
        string newline = source.Length == 0 || source.Contains("\r\n") ? "\r\n" : "\n";
        foreach (var pair in new[] { new[] { "SERVER", server }, new[] { "PORT", port.ToString() } }) {
            var regex = new Regex("(?m)^([ \\t]*" + pair[0] + "[ \\t]*=[ \\t]*)([^\\r\\n]*)");
            var matches = regex.Matches(source);
            if (matches.Count > 1) throw new IOException("Duplicate server configuration key: " + pair[0]);
            if (matches.Count == 0) {
                if (source.Length > 0 && !source.EndsWith("\n")) source += newline;
                source += pair[0] + "= " + pair[1] + newline;
            } else {
                var match = matches[0];
                var note = Regex.Match(match.Groups[2].Value, "[ \\t]*(?:[#;(]|//).*").Value;
                source = source.Remove(match.Index, match.Length).Insert(match.Index, match.Groups[1].Value + pair[1] + note);
            }
        }
        return encoding.GetBytes(bom + source);
    }
    public static void Apply(Manifest manifest, string root, ITransport transport, Action<string> progress,
                             CancellationToken cancel, Action requireClosed) {
        Validate(manifest); root = Path.GetFullPath(root); PlainPath(root); Directory.CreateDirectory(root);
        using (var mutex = new Mutex(false, "Local\\ShadowbanePatcher-" + Hash(Encoding.UTF8.GetBytes(root.ToUpperInvariant())))) {
            bool owned = false;
            try {
                try { owned = mutex.WaitOne(0); } catch (AbandonedMutexException) { owned = true; }
                if (!owned) throw new IOException("Another patcher is already updating this folder.");
                requireClosed();
                var endpointPath = Destination(root, "Config/ArcaneIP.cfg");
                byte[] endpoint = Endpoint(File.Exists(endpointPath) ? File.ReadAllBytes(endpointPath) : new byte[0], manifest.server, manifest.port);
                var needed = new HashSet<string>(StringComparer.OrdinalIgnoreCase); int scanned = 0;
                foreach (var file in manifest.files) {
                    cancel.ThrowIfCancellationRequested(); progress("Checking " + (++scanned) + " / " + manifest.files.Length + "  " + file.path);
                    if (!Matches(Destination(root, file.path), file)) needed.Add(file.path);
                }
                var stage = Path.Combine(root, ".shadowbane-stage"); PlainPath(stage); Directory.CreateDirectory(stage);
                try {
                    foreach (var bundle in manifest.bundles) {
                        var records = manifest.files.Where(f => f.bundle.Equals(bundle.name, StringComparison.OrdinalIgnoreCase)).ToArray();
                        if (!records.Any(f => needed.Contains(f.path))) continue;
                        cancel.ThrowIfCancellationRequested(); requireClosed();
                        string archive = Path.Combine(stage, Guid.NewGuid().ToString("N") + ".zip");
                        try {
                            transport.Download(bundle, archive, progress, cancel);
                            if (new FileInfo(archive).Length != bundle.size || HashFile(archive) != bundle.sha256)
                                throw new IOException("Downloaded bundle failed verification.");
                            using (var zip = ZipFile.OpenRead(archive)) {
                                var actual = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                                foreach (var entry in zip.Entries) {
                                    RelativePath(entry.FullName);
                                    var record = records.FirstOrDefault(f => f.path == entry.FullName);
                                    if (!actual.Add(entry.FullName) || record == null || record.size != entry.Length)
                                        throw new IOException("Bundle contents differ from the release manifest.");
                                }
                                if (actual.Count != records.Length) throw new IOException("Bundle is incomplete.");
                                foreach (var record in records.Where(f => needed.Contains(f.path))) {
                                    cancel.ThrowIfCancellationRequested(); requireClosed();
                                    progress("Installing " + record.path);
                                    string destination = Destination(root, record.path);
                                    Directory.CreateDirectory(Path.GetDirectoryName(destination));
                                    string temporary = Path.Combine(stage, Guid.NewGuid().ToString("N") + ".part");
                                    try {
                                        using (var input = zip.GetEntry(record.path).Open())
                                        using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None)) {
                                            var buffer = new byte[1024 * 1024]; int count; long length = 0;
                                            while ((count = input.Read(buffer, 0, buffer.Length)) != 0) {
                                                cancel.ThrowIfCancellationRequested(); length += count;
                                                if (length > record.size) throw new IOException("Client file exceeds its published size.");
                                                output.Write(buffer, 0, count);
                                            }
                                            if (length != record.size) throw new IOException("Incomplete client file.");
                                            output.Flush(true);
                                        }
                                        if (HashFile(temporary) != record.sha256) throw new IOException("Client file failed verification: " + record.path);
                                        requireClosed(); Promote(temporary, destination);
                                    } finally { if (File.Exists(temporary)) File.Delete(temporary); }
                                }
                            }
                        } finally { if (File.Exists(archive)) File.Delete(archive); }
                    }
                } finally { if (Directory.Exists(stage) && !Directory.EnumerateFileSystemEntries(stage).Any()) Directory.Delete(stage); }
                cancel.ThrowIfCancellationRequested(); requireClosed();
                // Only our endpoint keys are owned; other configuration stays in place.
                Atomic(endpointPath, endpoint);
                foreach (var file in manifest.files) {
                    cancel.ThrowIfCancellationRequested();
                    if (!Matches(Destination(root, file.path), file)) throw new IOException("Final verification failed: " + file.path);
                }
                progress("Client " + manifest.version + " is up to date.");
            } finally { if (owned) mutex.ReleaseMutex(); }
        }
    }
}
}
