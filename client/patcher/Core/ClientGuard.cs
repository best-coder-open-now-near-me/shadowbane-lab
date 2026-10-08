using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Shadowbane.Patching;

public interface IClientGuard
{
    IDisposable Enter(string root);
    bool IsRunning(string root);
}

public sealed class ClientGuard : IClientGuard
{
    [StructLayout(LayoutKind.Sequential)]
    private struct FileIdentity
    {
        public uint Attributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME Created, Accessed, Written;
        public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle file, out FileIdentity identity);
    private static FileIdentity Identity(string path)
    {
        using var file = File.OpenHandle(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        if (!GetFileInformationByHandle(file, out var identity)) throw new IOException("Cannot identify the client.");
        return identity;
    }
    public bool IsRunning(string root)
    {
        var identity = Identity(SafePaths.Within(root, "sb.exe"));
        foreach (var process in Process.GetProcessesByName("sb"))
        using (process)
        {
            try
            {
                if (process.HasExited) continue;
                var path = process.MainModule?.FileName ?? throw new IOException("Cannot inspect a running game.");
                var other = Identity(path);
                if (other.Volume == identity.Volume && other.IndexHigh == identity.IndexHigh &&
                    other.IndexLow == identity.IndexLow) return true;
            }
            catch (InvalidOperationException) { /* Process exited during inspection. */ }
        }
        return false;
    }
    public IDisposable Enter(string root)
    {
        var identity = Identity(SafePaths.Within(root, "sb.exe"));
        var mutex = new Mutex(false, $"Local\\ShadowbaneDesktop-{identity.Volume}-{identity.IndexHigh}-{identity.IndexLow}");
        bool acquired;
        try { acquired = mutex.WaitOne(0); }
        catch (AbandonedMutexException) { acquired = true; }
        if (!acquired) { mutex.Dispose(); throw new IOException("Another update or game launch is in progress."); }
        var lease = new Lease(mutex);
        try
        {
            if (IsRunning(root)) throw new IOException("Close Shadowbane before updating or starting another game.");
            return lease;
        }
        catch { lease.Dispose(); throw; }
    }
    private sealed class Lease(Mutex mutex) : IDisposable
    {
        public void Dispose() { mutex.ReleaseMutex(); mutex.Dispose(); }
    }
}
