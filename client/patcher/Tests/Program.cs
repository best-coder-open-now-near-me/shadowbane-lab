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
    var launcher4 = Record("ShadowbaneLauncher.exe", Encoding.UTF8.GetBytes("launcher-v4"));
    var release4 = release3 with { Sequence = 4, Version = "1.3.0", Files = [launcher4, fix2], RetiredFiles = [] };
    Blob(launcher4, "launcher-v4"); Publish(release4);
    Reject(() => interrupted.Apply(feed, _ => {}), "second interrupted release remains recoverable");
    var launcher5 = Record("ShadowbaneLauncher.exe", Encoding.UTF8.GetBytes("launcher-v5"));
    var release5 = release4 with { Sequence = 5, Version = "1.4.0", Files = [launcher5], RetiredFiles = [fix2] };
    Blob(launcher5, "launcher-v5"); Publish(release5);
    File.Delete(Path.Combine(feedPath, "objects", launcher4.Sha256));
    var scratch = Path.Combine(client, ".patcher", "staging");
    var orphan = Path.Combine(scratch, Guid.NewGuid().ToString("N") + ".tmp");
    File.WriteAllText(orphan, "interrupted current download");
    File.WriteAllText(Path.Combine(scratch, "user-note.txt"), "preserve");
    updater.Apply(feed, _ => {});
    Check(updater.VerifyInstalled().Release.Sequence == 5, "new signed release repairs an interrupted older release");
    Check(!File.Exists(orphan) && File.Exists(Path.Combine(scratch, "user-note.txt")), "only owned staging remnants are removed");
    if (args.Length == 2)
    {
        (int Code, string Output) RunTool(string tool, params string[] arguments)
        {
            var info = new System.Diagnostics.ProcessStartInfo("dotnet")
            { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
            info.ArgumentList.Add(tool);
            foreach (var argument in arguments) info.ArgumentList.Add(argument);
            using var child = System.Diagnostics.Process.Start(info)!;
            var output = child.StandardOutput.ReadToEndAsync(); var errors = child.StandardError.ReadToEndAsync();
            if (!child.WaitForExit(20000)) throw new IOException("CLI test timeout");
            return (child.ExitCode, output.GetAwaiter().GetResult() + errors.GetAwaiter().GetResult());
        }
        var testKeyName = "ShadowbaneClientRelease-tests-" + Guid.NewGuid().ToString("N");
        Check(!CngKey.Exists(testKeyName), "release CLI test key is fresh");
        try
        {
            var pubPath = Path.Combine(root, "test-public.pem");
            var init = RunTool(args[0], "init-key", "--key", testKeyName, "--public-key", pubPath);
            Check(init.Code == 0 && File.Exists(pubPath), "release CLI creates protected signer and public key");
            var releaseInput = Path.Combine(root, "release-input"); Directory.CreateDirectory(releaseInput);
            File.WriteAllText(Path.Combine(releaseInput, "ShadowbaneLauncher.exe"), "published-launcher-1");
            var notes = Path.Combine(root, "notes.txt"); File.WriteAllText(notes, "Actual test release notes.");
            var published = Path.Combine(root, "published");
            var publish1 = RunTool(args[0], "publish", "--key", testKeyName, "--input", releaseInput,
                "--output", published, "--sequence", "1", "--version", "1.0.0", "--source", new string('b', 40), "--notes", notes);
            Check(publish1.Code == 0, "release CLI publishes signed content-addressed payloads: " + publish1.Output.Trim());
            var first = ReleaseCodec.ReadVerified(Path.Combine(published, "release.json"), File.ReadAllText(pubPath));
            Check(first.Release.Notes[0] == "Actual test release notes.", "published notes are signed");
            File.WriteAllText(Path.Combine(releaseInput, "ShadowbaneLauncher.exe"), "published-launcher-2");
            var publish2 = RunTool(args[0], "publish", "--key", testKeyName, "--input", releaseInput,
                "--output", published, "--sequence", "2", "--version", "1.1.0", "--source", new string('c', 40), "--notes", notes);
            Check(publish2.Code == 0 && !File.Exists(Path.Combine(published, "objects", first.Release.Files[0].Sha256)) &&
                File.Exists(Path.Combine(published, "receipts", "1.json")), "publisher retains receipts and removes obsolete payloads");
            var inspect = RunTool(args[1], "--inspect", "--client-root", client, "--feed", published);
            Check(inspect.Code == 1 && inspect.Output.Contains("not signed by our release key"), "player app rejects a foreign signed feed");
            var invalid = RunTool(args[1], "--inspect", "--unknown");
            Check(invalid.Code == 1 && invalid.Output.Contains("failed"), "headless CLI errors do not open a dialog");
        }
        finally { if (CngKey.Exists(testKeyName)) { using var testKey = CngKey.Open(testKeyName); testKey.Delete(); } }
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
