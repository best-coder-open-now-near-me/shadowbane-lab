using System.Diagnostics;

namespace Shadowbane.Patching;

public sealed record UpdatePlan(VerifiedRelease Candidate, FileSpec[] Needed, bool Interrupted, bool GameRunning);
public sealed record UpdateProgress(string Message, long Completed = 0, long Total = 0);

public sealed class Updater(string root, string publicKey, IClientGuard? guard = null,
    IReadOnlyList<FileSpec>? baseline = null, Action<string>? checkpoint = null)
{
    public string Root { get; } = SafePaths.Root(root);
    private readonly IClientGuard guard = guard ?? new ClientGuard();
    private readonly IReadOnlyList<FileSpec> markers = baseline ?? Baseline.Markers;
    private string Metadata(string file) => SafePaths.Within(Root, ".patcher/" + file);

    private List<FileStream> HoldBaseline()
    {
        var held = new List<FileStream>();
        try
        {
            foreach (var marker in markers)
            {
                var path = SafePaths.Within(Root, marker.Path);
                var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
                held.Add(stream);
                if (stream.Length != marker.Size ||
                    Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(stream)) != marker.Sha256)
                    throw new InvalidDataException("This folder does not contain our supported client. Keep other servers in separate folders.");
            }
            return held;
        }
        catch { foreach (var stream in held) stream.Dispose(); throw; }
    }
    private VerifiedRelease? Installed()
    {
        var path = Metadata("installed.json");
        return File.Exists(path) ? ReleaseCodec.ReadVerified(path, publicKey) : null;
    }
    private void RequireForward(VerifiedRelease next)
    {
        var previous = Installed();
        if (previous is not null && (next.Release.Sequence < previous.Release.Sequence ||
            (next.Release.Sequence == previous.Release.Sequence && next.PayloadHash != previous.PayloadHash)))
            throw new InvalidDataException("The feed tried to replace an installed release with older or conflicting content.");
        var pending = Metadata("pending.json");
        if (File.Exists(pending))
        {
            var interrupted = ReleaseCodec.ReadVerified(pending, publicKey);
            if (next.PayloadHash != interrupted.PayloadHash)
                throw new InvalidDataException("Finish repairing the interrupted release before changing versions.");
        }
    }
    public UpdatePlan Check(IFeed feed, CancellationToken cancellation = default)
    {
        var candidate = ReleaseCodec.Verify(feed.ReadManifest(cancellation), publicKey);
        RequireForward(candidate);
        var held = HoldBaseline();
        try
        {
            var needed = candidate.Release.Files.Where(f => !ReleaseCodec.Matches(SafePaths.Within(Root, f.Path), f)).ToArray();
            return new(candidate, needed, File.Exists(Metadata("pending.json")), guard.IsRunning(Root));
        }
        finally { foreach (var file in held) file.Dispose(); }
    }
    public VerifiedRelease VerifyInstalled()
    {
        if (File.Exists(Metadata("pending.json"))) throw new IOException("An update was interrupted. Use Update / Repair before playing.");
        var installed = Installed() ?? throw new IOException("Install the current release before playing.");
        var held = HoldBaseline();
        try
        {
            foreach (var file in installed.Release.Files)
                if (!ReleaseCodec.Matches(SafePaths.Within(Root, file.Path), file))
                    throw new InvalidDataException("A client fix is missing or changed. Use Update / Repair.");
            return installed;
        }
        finally { foreach (var file in held) file.Dispose(); }
    }
    public void Apply(IFeed feed, Action<UpdateProgress> progress, CancellationToken cancellation = default)
    {
        using var lease = guard.Enter(Root);
        var plan = Check(feed, cancellation);
        var held = HoldBaseline();
        var staged = new List<string>();
        try
        {
            var staging = Metadata("staging");
            Directory.CreateDirectory(staging);
            // Only this updater's scratch names are disposable; preserve unknown files.
            foreach (var old in Directory.EnumerateFiles(staging, "*.tmp", SearchOption.TopDirectoryOnly))
                if (Guid.TryParseExact(Path.GetFileNameWithoutExtension(old), "N", out _))
                { SafePaths.RejectIndirection(old); File.Delete(old); }
            foreach (var file in plan.Needed)
            {
                cancellation.ThrowIfCancellationRequested();
                var destination = SafePaths.Within(staging, Guid.NewGuid().ToString("N") + ".tmp");
                staged.Add(destination);
                progress(new("Downloading " + file.Path));
                feed.Download(file, destination, done => progress(new("Downloading " + file.Path, done, file.Size)), cancellation);
            }
            // All downloads are verified before the first installed file changes.
            cancellation.ThrowIfCancellationRequested();
            ValidateRetired(plan.Candidate.Release);
            SafePaths.AtomicWrite(Metadata("pending.json"), plan.Candidate.EnvelopeBytes);
            checkpoint?.Invoke("journal");
            for (var index = 0; index < plan.Needed.Length; ++index)
            {
                var file = plan.Needed[index];
                var destination = SafePaths.Within(Root, file.Path);
                progress(new("Installing " + file.Path));
                if (!ReleaseCodec.Matches(staged[index], file)) throw new IOException("Staged update changed.");
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                if (File.Exists(destination)) File.Replace(staged[index], destination, null);
                else File.Move(staged[index], destination);
                checkpoint?.Invoke("replace:" + file.Path);
            }
            foreach (var file in plan.Candidate.Release.Files)
                if (!ReleaseCodec.Matches(SafePaths.Within(Root, file.Path), file)) throw new IOException("Installed update verification failed.");
            ValidateRetired(plan.Candidate.Release);
            foreach (var file in plan.Candidate.Release.RetiredFiles)
            {
                var path = SafePaths.Within(Root, file.Path);
                if (File.Exists(path)) File.Delete(path);
            }
            SafePaths.AtomicWrite(Metadata("installed.json"), plan.Candidate.EnvelopeBytes);
            checkpoint?.Invoke("receipt");
            File.Delete(Metadata("pending.json"));
            progress(new("Ready to play"));
        }
        finally
        {
            try
            {
                foreach (var path in staged)
                {
                    SafePaths.RejectIndirection(path);
                    if (File.Exists(path)) File.Delete(path);
                }
            }
            finally { foreach (var file in held) file.Dispose(); }
        }
    }
    private void ValidateRetired(Release release)
    {
        foreach (var file in release.RetiredFiles)
        {
            var path = SafePaths.Within(Root, file.Path);
            if (File.Exists(path) && !ReleaseCodec.Matches(path, file))
                throw new IOException("A retired fix has local changes; it was preserved: " + file.Path);
        }
    }
    public int Play()
    {
        using var lease = guard.Enter(Root);
        var installed = VerifyInstalled();
        var executable = SafePaths.Within(Root, "ShadowbaneLauncher.exe");
        // The native launcher waits for this shared lease before checking the journal.
        var process = Process.Start(new ProcessStartInfo(executable)
        { WorkingDirectory = Root, UseShellExecute = false }) ?? throw new IOException("Could not start the game launcher.");
        using (process) return process.Id;
    }
}
