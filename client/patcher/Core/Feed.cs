using System.Net;
using System.Security.Cryptography;

namespace Shadowbane.Patching;

public interface IFeed : IDisposable
{
    byte[] ReadManifest(CancellationToken cancellation);
    void Download(FileSpec file, string destination, Action<long> progress, CancellationToken cancellation);
}

public sealed class ReleaseFeed : IFeed
{
    private readonly string? directory;
    private readonly Uri? uri;
    private readonly HttpClient http = new(new HttpClientHandler
    {
        AllowAutoRedirect = false, AutomaticDecompression = DecompressionMethods.None,
        UseDefaultCredentials = false
    }) { Timeout = TimeSpan.FromMinutes(10) };

    public ReleaseFeed(string location)
    {
        if (Uri.TryCreate(location, UriKind.Absolute, out var parsed) && parsed.Scheme == "https")
        {
            if (!string.IsNullOrEmpty(parsed.UserInfo) || !string.IsNullOrEmpty(parsed.Query) ||
                !string.IsNullOrEmpty(parsed.Fragment)) throw new InvalidDataException("Use a plain HTTPS feed address.");
            uri = new Uri(location.TrimEnd('/') + "/");
        }
        else if (Path.IsPathFullyQualified(location)) directory = SafePaths.Root(location);
        else throw new InvalidDataException("The update feed must be HTTPS or an offline release folder.");
    }
    private Stream Open(string relative, CancellationToken cancellation, out HttpResponseMessage? response)
    {
        response = null;
        if (directory is not null)
            return new FileStream(SafePaths.Within(directory, relative), FileMode.Open, FileAccess.Read, FileShare.Read);
        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri(uri!, relative));
        response = http.Send(request, HttpCompletionOption.ResponseHeadersRead, cancellation);
        try { response.EnsureSuccessStatusCode(); return response.Content.ReadAsStream(cancellation); }
        catch { response.Dispose(); throw; }
    }
    private static int ReadChunk(Stream source, byte[] buffer, CancellationToken cancellation)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        timeout.CancelAfter(TimeSpan.FromSeconds(30));
        return source.ReadAsync(buffer.AsMemory(), timeout.Token).AsTask().GetAwaiter().GetResult();
    }
    public byte[] ReadManifest(CancellationToken cancellation)
    {
        using var source = Open("release.json", cancellation, out var response);
        using (response)
        using (var output = new MemoryStream())
        {
            var buffer = new byte[8192];
            int count;
            while ((count = ReadChunk(source, buffer, cancellation)) != 0)
            {
                cancellation.ThrowIfCancellationRequested();
                if (output.Length + count > ReleaseCodec.MaximumManifest) throw new InvalidDataException("Feed metadata is too large.");
                output.Write(buffer, 0, count);
            }
            return output.ToArray();
        }
    }
    public void Download(FileSpec file, string destination, Action<long> progress, CancellationToken cancellation)
    {
        using var source = Open("objects/" + file.Sha256, cancellation, out var response);
        using (response)
        using (var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        using (var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256))
        {
            var buffer = new byte[65536];
            long size = 0;
            int count;
            while ((count = ReadChunk(source, buffer, cancellation)) != 0)
            {
                cancellation.ThrowIfCancellationRequested();
                size += count;
                if (size > file.Size) throw new InvalidDataException("Downloaded file exceeds its signed size.");
                hash.AppendData(buffer, 0, count); output.Write(buffer, 0, count); progress(size);
            }
            if (size != file.Size || Convert.ToHexStringLower(hash.GetHashAndReset()) != file.Sha256)
                throw new InvalidDataException("Downloaded file does not match the signed release.");
            output.Flush(true);
        }
    }
    public void Dispose() => http.Dispose();
}
