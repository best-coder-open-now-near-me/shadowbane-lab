param(
    [ValidateRange(1, 120)]
    [int] $DurationSeconds = 20,

    [string] $OutputDirectory = ""
)

$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class ShadowbaneMacroDiagnosticNative
{
    [StructLayout(LayoutKind.Sequential)]
    public struct POINT
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MSG
    {
        public IntPtr hwnd;
        public uint message;
        public UIntPtr wParam;
        public IntPtr lParam;
        public uint time;
        public POINT point;
    }

    [DllImport("user32.dll")]
    public static extern short GetAsyncKeyState(int virtualKey);

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr window, StringBuilder text, int capacity);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool RegisterHotKey(IntPtr window, int id, uint modifiers, uint virtualKey);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool UnregisterHotKey(IntPtr window, int id);

    [DllImport("user32.dll")]
    public static extern bool PeekMessage(out MSG message, IntPtr window, uint min, uint max, uint remove);
}
"@

$diagnosticVersion = "2026-08-31.1"
$virtualKeyF9 = 0x78
$wmHotKey = 0x0312
$hotKeyId = 0x5342
$stateDirectory = if ($OutputDirectory) {
    [IO.Path]::GetFullPath($OutputDirectory)
}
else {
    Join-Path $env:LOCALAPPDATA "ShadowbaneLab\macros"
}
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
$stamp = [DateTime]::Now.ToString("yyyyMMdd-HHmmss")
$logPath = Join-Path $stateDirectory "druid-aoe-diagnostic-$stamp.log"

function Get-ForegroundSnapshot {
    $window = [ShadowbaneMacroDiagnosticNative]::GetForegroundWindow()
    [uint32] $foregroundProcessId = 0
    if ($window -ne [IntPtr]::Zero) {
        [void][ShadowbaneMacroDiagnosticNative]::GetWindowThreadProcessId(
            $window,
            [ref] $foregroundProcessId
        )
    }

    $titleBuffer = New-Object System.Text.StringBuilder 512
    if ($window -ne [IntPtr]::Zero) {
        [void][ShadowbaneMacroDiagnosticNative]::GetWindowText($window, $titleBuffer, $titleBuffer.Capacity)
    }

    $processName = "<none>"
    if ($foregroundProcessId -ne 0) {
        try {
            $processName = (Get-Process -Id $foregroundProcessId -ErrorAction Stop).ProcessName
        }
        catch {
            $processName = "<unreadable>"
        }
    }

    return [pscustomobject]@{
        Handle = "0x{0:X}" -f $window.ToInt64()
        ProcessId = $foregroundProcessId
        ProcessName = $processName
        Title = $titleBuffer.ToString()
    }
}

Start-Transcript -LiteralPath $logPath -Force | Out-Null
$hotKeyRegistered = $false
try {
    Write-Host "Shadowbane Druid macro diagnostic v$diagnosticVersion" -ForegroundColor Cyan
    Write-Host "Diagnostic PID: $PID"
    Write-Host "User: $([Environment]::UserDomainName)\$([Environment]::UserName)"
    $bitness = if ([Environment]::Is64BitProcess) { "64-bit" } else { "32-bit" }
    Write-Host "PowerShell: $($PSVersionTable.PSVersion) ($bitness)"
    Write-Host "Log: $logPath"
    Write-Host ""
    Write-Host "Visible sb.exe processes:"
    $gameProcesses = @(Get-Process -Name sb -ErrorAction SilentlyContinue)
    if ($gameProcesses.Count -eq 0) {
        Write-Host "  NONE" -ForegroundColor Red
    }
    else {
        foreach ($gameProcess in $gameProcesses) {
            $path = "<unreadable>"
            try { $path = $gameProcess.Path } catch { }
            Write-Host (
                "  PID={0} Session={1} HWND=0x{2:X} Title={3} Path={4}" -f
                $gameProcess.Id,
                $gameProcess.SessionId,
                $gameProcess.MainWindowHandle.ToInt64(),
                $gameProcess.MainWindowTitle,
                $path
            )
        }
    }

    $hotKeyRegistered = [ShadowbaneMacroDiagnosticNative]::RegisterHotKey(
        [IntPtr]::Zero,
        $hotKeyId,
        0,
        $virtualKeyF9
    )
    if ($hotKeyRegistered) {
        Write-Host "RegisterHotKey(F9): SUCCESS" -ForegroundColor Green
    }
    else {
        Write-Host "RegisterHotKey(F9): FAILED Win32=$([Runtime.InteropServices.Marshal]::GetLastWin32Error())" -ForegroundColor Red
    }

    Write-Host ""
    Write-Host "For the next $DurationSeconds seconds: focus Shadowbane and press F9 once." -ForegroundColor Yellow
    $deadline = [DateTime]::UtcNow.AddSeconds($DurationSeconds)
    $lastForeground = ""
    $wasF9Down = $false
    $asyncDetected = $false
    $hotKeyDetected = $false

    while ([DateTime]::UtcNow -lt $deadline) {
        $foreground = Get-ForegroundSnapshot
        $foregroundKey = "$($foreground.Handle)|$($foreground.ProcessId)|$($foreground.ProcessName)|$($foreground.Title)"
        if ($foregroundKey -ne $lastForeground) {
            Write-Host (
                "Foreground: HWND={0} PID={1} Process={2} Title={3}" -f
                $foreground.Handle,
                $foreground.ProcessId,
                $foreground.ProcessName,
                $foreground.Title
            )
            $lastForeground = $foregroundKey
        }

        $isF9Down = ([ShadowbaneMacroDiagnosticNative]::GetAsyncKeyState($virtualKeyF9) -band 0x8000) -ne 0
        if ($isF9Down -and -not $wasF9Down) {
            $asyncDetected = $true
            Write-Host "F9 detected by GetAsyncKeyState." -ForegroundColor Green
        }
        $wasF9Down = $isF9Down

        $message = New-Object ShadowbaneMacroDiagnosticNative+MSG
        while ([ShadowbaneMacroDiagnosticNative]::PeekMessage(
            [ref] $message,
            [IntPtr]::Zero,
            0,
            0,
            1
        )) {
            if ($message.message -eq $wmHotKey -and $message.wParam.ToUInt64() -eq $hotKeyId) {
                $hotKeyDetected = $true
                Write-Host "F9 detected by RegisterHotKey/WM_HOTKEY." -ForegroundColor Green
            }
        }

        Start-Sleep -Milliseconds 20
    }

    Write-Host ""
    Write-Host "Summary: AsyncF9=$asyncDetected RegisteredF9=$hotKeyDetected HotKeyRegistration=$hotKeyRegistered"
    if (-not $asyncDetected -and -not $hotKeyDetected) {
        Write-Host "F9 never reached this Windows input desktop." -ForegroundColor Red
    }
}
finally {
    if ($hotKeyRegistered) {
        [void][ShadowbaneMacroDiagnosticNative]::UnregisterHotKey([IntPtr]::Zero, $hotKeyId)
    }
    Stop-Transcript | Out-Null
    Write-Host "Diagnostic log saved: $logPath"
}
