using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Shadowbane.Patching;

int passed = 0;
void Check(bool condition, string name)
{
    if (!condition) throw new Exception(name);
    Console.WriteLine("PASS " + name); ++passed;
}
void Reject(Action action, string name)
{
    bool rejected = false;
    try { action(); }
    catch (Exception e) when (e is IOException or InvalidDataException or CryptographicException or JsonException or FormatException) { rejected = true; }
    Check(rejected, name);
}
using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
var publicKey = key.ExportSubjectPublicKeyInfoPem();
var parent = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "fixtures"));
Directory.CreateDirectory(parent);
var root = Path.Combine(parent, Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
File.WriteAllText(Path.Combine(root, ".test-owned"), "patcher-tests");
try
{
    var client = Path.Combine(root, "client");
    var feedPath = Path.Combine(root, "feed");
    Directory.CreateDirectory(client); Directory.CreateDirectory(feedPath);
    Directory.CreateDirectory(Path.Combine(feedPath, "objects"));
    Directory.CreateDirectory(Path.Combine(client, "Config"));
    File.WriteAllText(Path.Combine(client, "sb.exe"), "test base");
    File.WriteAllText(Path.Combine(client, "Config", "ArcanePref.cfg"), "user settings survive");
    FileSpec Record(string relative, byte[] bytes) => new(relative, bytes.Length, ReleaseCodec.Digest(bytes));
    var baseline = new[] { Record("sb.exe", Encoding.UTF8.GetBytes("test base")) };
    var launcher = Record("ShadowbaneLauncher.exe", Encoding.UTF8.GetBytes("launcher-v1"));
    var fix = Record("ClientFixes/render.dll", Encoding.UTF8.GetBytes("fix-v1"));
    var release = new Release(1, ReleaseCodec.Channel, 1, "1.0.0", "1.0.0", Baseline.Profile,
        new string('a', 40), DateTimeOffset.UtcNow, ["Automatic desktop fullscreen."], [launcher, fix], []);
    void Publish(Release value)
    {
        File.WriteAllBytes(Path.Combine(feedPath, "release.json"), ReleaseCodec.Sign(value, key));
    }
    void Blob(FileSpec file, string bytes) => File.WriteAllText(Path.Combine(feedPath, "objects", file.Sha256), bytes);
    Blob(launcher, "launcher-v1"); Blob(fix, "fix-v1"); Publish(release);
    var valid = ReleaseCodec.Verify(File.ReadAllBytes(Path.Combine(feedPath, "release.json")), publicKey);
    Check(valid.Release.Sequence == 1, "verified signed release");
    using (var other = ECDsa.Create(ECCurve.NamedCurves.nistP256))
        Reject(() => ReleaseCodec.Verify(valid.EnvelopeBytes, other.ExportSubjectPublicKeyInfoPem()), "wrong signing key rejected");
    var envelope = ReleaseCodec.Parse<Envelope>(valid.EnvelopeBytes);
    Reject(() => ReleaseCodec.Verify(JsonSerializer.SerializeToUtf8Bytes(envelope with
        { Payload = Convert.ToBase64String(Encoding.UTF8.GetBytes("tampered")) }, ReleaseCodec.Json), publicKey), "tampered manifest rejected");
    Reject(() => ReleaseCodec.Parse<Envelope>(Encoding.UTF8.GetBytes("{\"payload\":\"a\",\"payload\":\"b\",\"signature\":\"x\"}")), "duplicate metadata rejected");
    foreach (var unsafePath in new[] { "Config/ArcanePref.cfg", "../sb.exe", "ClientFixes/../sb.exe",
        "ClientFixes/CON.dll", "ClientFixes/x.dll:ads", "ClientFixes/trailing.", "ClientFixes\\escape.dll", "sb.exe" })
        Check(!ReleaseCodec.OwnedPath(unsafePath), "protected path " + unsafePath);
    Reject(() => ReleaseCodec.Validate(release with { Files = [launcher, launcher with { Path = "shadowbanelauncher.exe" }] }), "ambiguous paths rejected");
    Reject(() => ReleaseCodec.Validate(release with { MinimumPatcherVersion = "9.0.0" }), "minimum patcher version enforced");
    Reject(() => new ReleaseFeed("http://example.com/updates"), "insecure feed rejected");
    Reject(() => new ReleaseFeed("https://user:secret@example.com/updates"), "credential-bearing feed rejected");
    using var feed = new ReleaseFeed(feedPath);
    var updater = new Updater(client, publicKey, new FakeGuard(), baseline);
    Check(updater.Check(feed).Needed.Length == 2, "initial plan identifies required fixes");
    updater.Apply(feed, _ => {});
    Check(updater.VerifyInstalled().Release.Sequence == 1 && updater.Check(feed).Needed.Length == 0, "install and verify complete release");
    Check(File.ReadAllText(Path.Combine(client, "Config", "ArcanePref.cfg")) == "user settings survive", "settings preserved");
    Check(!Directory.EnumerateFiles(client, "*.tmp", SearchOption.AllDirectories).Any(), "no staged files retained");
    Check(!Directory.EnumerateFiles(client, "*.bak", SearchOption.AllDirectories).Any(), "no rollback copies");
    File.WriteAllText(Path.Combine(client, "ShadowbaneLauncher.exe"), "damaged");
    Reject(() => updater.VerifyInstalled(), "corrupt installed fix blocks Play");
    updater.Apply(feed, _ => {});
    Check(updater.Check(feed).Needed.Length == 0, "repair restores signed bytes");
    var launcher2 = Record("ShadowbaneLauncher.exe", Encoding.UTF8.GetBytes("launcher-v2"));
    var fix2 = Record("ClientFixes/render.dll", Encoding.UTF8.GetBytes("fix-v2"));
    var release2 = release with { Sequence = 2, Version = "1.1.0", Files = [launcher2, fix2] };
    Blob(launcher2, "bad"); Blob(fix2, "fix-v2"); Publish(release2);
    Reject(() => updater.Apply(feed, _ => {}), "bad download rejected");
    Check(ReleaseCodec.Matches(Path.Combine(client, launcher.Path), launcher) &&
        updater.VerifyInstalled().Release.Sequence == 1, "bad download changes no installed bytes");
    Blob(launcher2, "launcher-v2");
    var interrupted = new Updater(client, publicKey, new FakeGuard(), baseline,
        phase => { if (phase.StartsWith("replace:")) throw new IOException("simulated power interruption"); });
    Reject(() => interrupted.Apply(feed, _ => {}), "interruption after first replacement is observable");
    Reject(() => updater.VerifyInstalled(), "incomplete installation blocks Play");
    Check(updater.Check(feed).Interrupted && updater.Check(feed).Needed.Length == 1, "resume recognizes already applied bytes");
    Publish(release2 with { Notes = ["conflicting content"] });
    Reject(() => updater.Check(feed), "interrupted release cannot silently change identity");
    Publish(release2); updater.Apply(feed, _ => {});
    Check(updater.VerifyInstalled().Release.Sequence == 2, "repair completes interrupted release");
    Publish(release);
    Reject(() => updater.Check(feed), "signed downgrade rejected");
    Publish(release2 with { Notes = ["same number, different content"] });
    Reject(() => updater.Check(feed), "same-sequence equivocation rejected");
    var release3 = release2 with { Sequence = 3, Version = "1.2.0", Files = [launcher2], RetiredFiles = [fix2] };
    Publish(release3); File.WriteAllText(Path.Combine(client, fix2.Path), "local customized data");
    Reject(() => updater.Apply(feed, _ => {}), "changed retired file is preserved");
    Check(File.ReadAllText(Path.Combine(client, fix2.Path)) == "local customized data", "retirement preserves changed file");
    File.WriteAllText(Path.Combine(client, fix2.Path), "fix-v2"); updater.Apply(feed, _ => {});
    Check(!File.Exists(Path.Combine(client, fix2.Path)), "exact retired fix removed");
    var blocking = new Updater(client, publicKey, new FakeGuard(true), baseline);
    Reject(() => blocking.Apply(feed, _ => {}), "running game prevents update");
    using (var cancellation = new CancellationTokenSource())
    {
        cancellation.Cancel();
        bool canceled = false;
        try { updater.Apply(feed, _ => {}, cancellation.Token); }
        catch (OperationCanceledException) { canceled = true; }
        Check(canceled && !File.Exists(Path.Combine(client, ".patcher/pending.json")), "cancellation before mutation is safe");
    }
    var nativeGuard = new ClientGuard();
    using (nativeGuard.Enter(client))
    {
        var blocked = Task.Run(() =>
        {
            try { using var lease = nativeGuard.Enter(client); return false; }
            catch (IOException) { return true; }
        }).GetAwaiter().GetResult();
        Check(blocked, "shared Windows startup mutex excludes another thread");
    }
    File.WriteAllText(Path.Combine(client, "sb.exe"), "wrong base");
    Reject(() => updater.Check(feed), "wrong client baseline rejected");
    Console.WriteLine($"{passed} patcher checks passed.");
}
finally
{
    if (!root.StartsWith(parent + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) ||
        !File.Exists(Path.Combine(root, ".test-owned"))) throw new Exception("Unsafe fixture cleanup");
    Directory.Delete(root, true);
}
sealed class FakeGuard(bool running = false) : IClientGuard
{
    public IDisposable Enter(string root)
    {
        if (running) throw new IOException("running");
        return new Lease();
    }
    public bool IsRunning(string root) => running;
    private sealed class Lease : IDisposable { public void Dispose() {} }
}
