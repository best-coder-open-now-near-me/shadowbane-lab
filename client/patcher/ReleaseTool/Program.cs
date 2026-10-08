using System.Security.Cryptography;
using System.Text.Json;
using Shadowbane.Patching;

try
{
    if (args.Length == 0) throw new ArgumentException("Use init-key or publish, followed by named options.");
    var options = new Dictionary<string, string>(StringComparer.Ordinal);
    for (int i = 1; i < args.Length; i += 2)
        if (i + 1 == args.Length || !args[i].StartsWith("--") || !options.TryAdd(args[i], args[i + 1]))
            throw new ArgumentException("Invalid or duplicate release-tool option.");
    string Required(string name) => options.TryGetValue("--" + name, out var value) ? value :
        throw new ArgumentException("Missing --" + name);
    var name = Required("key");
    if (!System.Text.RegularExpressions.Regex.IsMatch(name, "^ShadowbaneClientRelease-[A-Za-z0-9_-]+$"))
        throw new ArgumentException("Use a named ShadowbaneClientRelease- key.");
    if (args[0] == "init-key")
    {
        if (!CngKey.Exists(name))
        {
            using var created = CngKey.Create(CngAlgorithm.ECDsaP256, name, new CngKeyCreationParameters
            { ExportPolicy = CngExportPolicies.None, KeyUsage = CngKeyUsages.Signing });
        }
        using var persisted = CngKey.Open(name);
        using var signer = new ECDsaCng(persisted);
        var output = Path.GetFullPath(Required("public-key"));
        var publicKey = signer.ExportSubjectPublicKeyInfoPem() + "\n";
        if (File.Exists(output) && File.ReadAllText(output) != publicKey)
            throw new IOException("Existing public key differs; refusing to replace the trust root.");
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        if (!File.Exists(output)) File.WriteAllText(output, publicKey);
        Console.WriteLine(JsonSerializer.Serialize(new { keyName = name, publicKeyPath = output,
            publicKeySha256 = ReleaseCodec.Digest(System.Text.Encoding.UTF8.GetBytes(publicKey)),
            privateKey = "Windows CNG user key store; non-exportable" }));
        return 0;
    }
    if (args[0] != "publish") throw new ArgumentException("Unknown release-tool command.");
    using var key = CngKey.Open(name);
    using var signingKey = new ECDsaCng(key);
    var publicPem = signingKey.ExportSubjectPublicKeyInfoPem();
    var input = SafePaths.Root(Required("input"));
    var outputRoot = Path.GetFullPath(Required("output"));
    if (outputRoot.Equals(input, StringComparison.OrdinalIgnoreCase) ||
        outputRoot.StartsWith(input + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        throw new IOException("Keep release input separate from the served output folder.");
    SafePaths.RejectIndirection(outputRoot); Directory.CreateDirectory(outputRoot);
    using var publicationLock = new FileStream(SafePaths.Within(outputRoot, ".publish.lock"),
        FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
    var files = Directory.EnumerateFiles(input, "*", SearchOption.AllDirectories)
        .Select(path =>
        {
            SafePaths.RejectIndirection(path);
            var relative = Path.GetRelativePath(input, path).Replace('\\', '/');
            if (!ReleaseCodec.OwnedPath(relative)) throw new InvalidDataException("Unowned release file: " + relative);
            return new FileSpec(relative, new FileInfo(path).Length, ReleaseCodec.DigestFile(path));
        }).OrderBy(f => f.Path, StringComparer.Ordinal).ToArray();
    var previousPath = SafePaths.Within(outputRoot, "release.json");
    var previous = File.Exists(previousPath) ? ReleaseCodec.ReadVerified(previousPath, publicPem) : null;
    var retired = previous?.Release.Files.Where(f => !files.Any(next => next.Path == f.Path)).ToArray() ?? [];
    var release = new Release(1, ReleaseCodec.Channel, long.Parse(Required("sequence")),
        Required("version"), ReleaseCodec.PatcherVersion, Baseline.Profile, Required("source"),
        DateTimeOffset.UtcNow, File.ReadAllLines(Required("notes")).Where(n => !string.IsNullOrWhiteSpace(n)).ToArray(),
        files, retired);
    ReleaseCodec.Validate(release);
    if (previous is not null && release.Sequence <= previous.Release.Sequence)
        throw new InvalidDataException("Publish with a new, strictly increasing sequence.");
    var objects = SafePaths.Within(outputRoot, "objects"); Directory.CreateDirectory(objects);
    foreach (var file in files)
    {
        var source = SafePaths.Within(input, file.Path);
        var target = SafePaths.Within(objects, file.Sha256);
        if (File.Exists(target))
        {
            if (!ReleaseCodec.Matches(target, file)) throw new IOException("Existing feed object differs: " + file.Sha256);
            continue;
        }
        var temporary = target + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var from = File.OpenRead(source))
            using (var to = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { from.CopyTo(to); to.Flush(true); }
            if (!ReleaseCodec.Matches(temporary, file)) throw new IOException("Release input changed during packaging.");
            File.Move(temporary, target);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
    if (previous is not null)
        SafePaths.AtomicWrite(SafePaths.Within(outputRoot, "receipts/" + previous.Release.Sequence + ".json"),
            previous.EnvelopeBytes);
    var signed = ReleaseCodec.Sign(release, signingKey);
    SafePaths.AtomicWrite(previousPath, signed);
    // Feed keeps current payloads and compact signed receipts, never old fallback builds.
    foreach (var path in Directory.EnumerateFiles(objects))
    {
        var hash = Path.GetFileName(path);
        if (System.Text.RegularExpressions.Regex.IsMatch(hash, "^[0-9a-f]{64}$") && !files.Any(f => f.Sha256 == hash))
        { SafePaths.RejectIndirection(path); File.Delete(path); }
    }
    Console.WriteLine(JsonSerializer.Serialize(new { release.Version, release.Sequence,
        manifest = previousPath, files = files.Length, manifestSha256 = ReleaseCodec.Digest(signed) }));
    return 0;
}
catch (Exception error) { Console.Error.WriteLine(error.Message); return 1; }
