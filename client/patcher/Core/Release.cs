using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace Shadowbane.Patching;

public sealed record FileSpec(string Path, long Size, string Sha256);
public sealed record Release(int Schema, string Channel, long Sequence, string Version,
    string MinimumPatcherVersion, string BaseProfile, string SourceCommit,
    DateTimeOffset PublishedUtc, string[] Notes, FileSpec[] Files, FileSpec[] RetiredFiles);
public sealed record Envelope(string Payload, string Signature);
public sealed record VerifiedRelease(Release Release, byte[] EnvelopeBytes, string PayloadHash);

public static partial class ReleaseCodec
{
    public const string Channel = "friends";
    public const string PatcherVersion = "1.0.0";
    public const int MaximumManifest = 262144;
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        WriteIndented = true
    };
    [GeneratedRegex("^[0-9a-f]{64}$")] private static partial Regex HashPattern();
    [GeneratedRegex("^[0-9a-f]{40}$")] private static partial Regex CommitPattern();
    [GeneratedRegex("^[A-Za-z0-9_-][A-Za-z0-9_.-]*$")] private static partial Regex PartPattern();

    public static string Digest(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));
    public static string DigestFile(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }
    public static bool Matches(string path, FileSpec file) =>
        File.Exists(path) && new FileInfo(path).Length == file.Size && DigestFile(path) == file.Sha256;

    public static T Parse<T>(byte[] bytes)
    {
        if (bytes.Length > MaximumManifest) throw new InvalidDataException("Release metadata is too large.");
        using var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
        RejectDuplicateProperties(document.RootElement);
        return JsonSerializer.Deserialize<T>(bytes, Json) ?? throw new InvalidDataException("Empty release metadata.");
    }
    private static void RejectDuplicateProperties(JsonElement item)
    {
        if (item.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in item.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new InvalidDataException("Duplicate metadata field.");
                RejectDuplicateProperties(property.Value);
            }
        }
        else if (item.ValueKind == JsonValueKind.Array)
            foreach (var child in item.EnumerateArray()) RejectDuplicateProperties(child);
    }
    public static VerifiedRelease ReadVerified(string path, string publicKey)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > MaximumManifest) throw new InvalidDataException("Release metadata is too large.");
        var bytes = new byte[checked((int)stream.Length)];
        stream.ReadExactly(bytes);
        return Verify(bytes, publicKey);
    }
    public static VerifiedRelease Verify(byte[] bytes, string publicKey)
    {
        var envelope = Parse<Envelope>(bytes);
        var payload = Convert.FromBase64String(envelope.Payload);
        var signature = Convert.FromBase64String(envelope.Signature);
        using var key = ECDsa.Create();
        key.ImportFromPem(publicKey);
        if (key.KeySize != 256 || signature.Length != 64 ||
            !key.VerifyData(payload, signature, HashAlgorithmName.SHA256,
                DSASignatureFormat.IeeeP1363FixedFieldConcatenation))
            throw new CryptographicException("This release was not signed by our release key.");
        var release = Parse<Release>(payload);
        Validate(release);
        return new(release, bytes.ToArray(), Digest(payload));
    }
    public static byte[] Sign(Release release, ECDsa key)
    {
        Validate(release);
        var payload = JsonSerializer.SerializeToUtf8Bytes(release, Json);
        return JsonSerializer.SerializeToUtf8Bytes(new Envelope(Convert.ToBase64String(payload),
            Convert.ToBase64String(key.SignData(payload, HashAlgorithmName.SHA256,
                DSASignatureFormat.IeeeP1363FixedFieldConcatenation))), Json);
    }
    public static void Validate(Release release)
    {
        if (release.Schema != 1 || release.Channel != Channel || release.Sequence < 1 ||
            !System.Version.TryParse(release.Version, out _) ||
            !System.Version.TryParse(release.MinimumPatcherVersion, out var minimum) ||
            minimum > System.Version.Parse(PatcherVersion) ||
            release.BaseProfile != Baseline.Profile ||
            release.SourceCommit is null || !CommitPattern().IsMatch(release.SourceCommit) ||
            release.PublishedUtc > DateTimeOffset.UtcNow.AddDays(1))
            throw new InvalidDataException("Unsupported release. Check the patcher version and client baseline.");
        if (release.Notes is null || release.Notes.Length is < 1 or > 32 ||
            release.Notes.Any(n => string.IsNullOrWhiteSpace(n) || n.Length > 4096) ||
            release.Files is null || release.Files.Length is < 1 or > 128 ||
            release.RetiredFiles is null || release.RetiredFiles.Length > 128)
            throw new InvalidDataException("Invalid release contents.");
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        foreach (var file in release.Files.Concat(release.RetiredFiles))
        {
            if (file is null || !OwnedPath(file.Path) || !paths.Add(file.Path) ||
                file.Size is < 1 or > 536870912 || file.Sha256 is null || !HashPattern().IsMatch(file.Sha256))
                throw new InvalidDataException("Invalid, duplicate, or protected release file.");
            total = checked(total + file.Size);
        }
        if (total > 2147483648L || !release.Files.Any(f => f.Path == "ShadowbaneLauncher.exe"))
            throw new InvalidDataException("The release must contain the launcher and fit the package limit.");
    }
    public static bool OwnedPath(string? path)
    {
        if (path == "ShadowbaneLauncher.exe") return true;
        if (path is null || !path.StartsWith("ClientFixes/", StringComparison.Ordinal) || path.Length > 180)
            return false;
        var parts = path.Split('/');
        return parts.All(p => PartPattern().IsMatch(p) && !p.EndsWith('.') &&
            !Regex.IsMatch(p.Split('.')[0], "^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])$", RegexOptions.IgnoreCase));
    }
}
