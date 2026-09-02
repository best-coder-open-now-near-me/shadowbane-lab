$ErrorActionPreference = "Stop"
$macroVersion = "2026-08-31.13"

if ($env:OS -ne "Windows_NT") {
    throw "This macro requires Windows."
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class ShadowbaneMacroNative
{
    [StructLayout(LayoutKind.Sequential)]
    public struct INPUT
    {
        public uint type;
        public InputUnion data;
    }

    [StructLayout(LayoutKind.Explicit)]
    public struct InputUnion
    {
        [FieldOffset(0)]
        public MOUSEINPUT mouse;

        [FieldOffset(0)]
        public KEYBDINPUT keyboard;

        [FieldOffset(0)]
        public HARDWAREINPUT hardware;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint flags;
        public uint time;
        public UIntPtr extraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct KEYBDINPUT
    {
        public ushort virtualKey;
        public ushort scanCode;
        public uint flags;
        public uint time;
        public UIntPtr extraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct HARDWAREINPUT
    {
        public uint message;
        public ushort paramLow;
        public ushort paramHigh;
    }

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
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern uint SendInput(uint inputCount, INPUT[] inputs, int inputSize);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool RegisterHotKey(IntPtr window, int id, uint modifiers, uint virtualKey);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool UnregisterHotKey(IntPtr window, int id);

    [DllImport("user32.dll")]
    public static extern bool PeekMessage(out MSG message, IntPtr window, uint min, uint max, uint remove);

    public static void PressChord(ushort virtualKey, ushort[] modifiers)
    {
        if (modifiers == null)
            modifiers = new ushort[0];

        INPUT[] inputs = new INPUT[(modifiers.Length * 2) + 2];
        int index = 0;

        for (int modifierIndex = 0; modifierIndex < modifiers.Length; modifierIndex++)
        {
            inputs[index].type = 1;
            inputs[index].data.keyboard.virtualKey = modifiers[modifierIndex];
            index++;
        }

        uint keyFlags = IsExtendedKey(virtualKey) ? 0x0001u : 0u;
        inputs[index].type = 1;
        inputs[index].data.keyboard.virtualKey = virtualKey;
        inputs[index].data.keyboard.flags = keyFlags;
        index++;

        inputs[index].type = 1;
        inputs[index].data.keyboard.virtualKey = virtualKey;
        inputs[index].data.keyboard.flags = keyFlags | 0x0002u;
        index++;

        for (int modifierIndex = modifiers.Length - 1; modifierIndex >= 0; modifierIndex--)
        {
            inputs[index].type = 1;
            inputs[index].data.keyboard.virtualKey = modifiers[modifierIndex];
            inputs[index].data.keyboard.flags = 0x0002;
            index++;
        }

        uint sent = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf(typeof(INPUT)));
        if (sent != (uint)inputs.Length)
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "SendInput failed");
    }

    public static void Press(ushort virtualKey)
    {
        PressChord(virtualKey, new ushort[0]);
    }

    private static bool IsExtendedKey(ushort virtualKey)
    {
        switch (virtualKey)
        {
            case 0x21: // Page Up
            case 0x22: // Page Down
            case 0x23: // End
            case 0x24: // Home
            case 0x25: // Left
            case 0x26: // Up
            case 0x27: // Right
            case 0x28: // Down
            case 0x2D: // Insert
            case 0x2E: // Delete
            case 0x5B: // Left Windows
            case 0x5C: // Right Windows
            case 0x6F: // Keypad Divide
            case 0x90: // Num Lock
            case 0xA3: // Right Control
            case 0xA5: // Right Alt
                return true;
            default:
                return false;
        }
    }

    public static int GetInputSize()
    {
        return Marshal.SizeOf(typeof(INPUT));
    }
}
"@

$expectedInputSize = if ([Environment]::Is64BitProcess) { 40 } else { 28 }
$actualInputSize = [ShadowbaneMacroNative]::GetInputSize()
if ($actualInputSize -ne $expectedInputSize) {
    throw "Invalid Windows INPUT structure size: expected $expectedInputSize bytes, got $actualInputSize."
}

$virtualKeys = @{
    Control = 0x11
    Alt = 0x12
    C = 0x43
    F1 = 0x70
    F2 = 0x71
    F3 = 0x72
    F4 = 0x73
    F5 = 0x74
    F6 = 0x75
    F8 = 0x77
    F9 = 0x78
    F10 = 0x79
    End = 0x23
    Semicolon = 0xBA
}

function Test-ShadowbaneForeground {
    $window = [ShadowbaneMacroNative]::GetForegroundWindow()
    if ($window -eq [IntPtr]::Zero) {
        return $false
    }

    [uint32] $processId = 0
    [void][ShadowbaneMacroNative]::GetWindowThreadProcessId($window, [ref] $processId)
    if ($processId -eq 0) {
        return $false
    }

    try {
        $process = Get-Process -Id $processId -ErrorAction Stop
    }
    catch {
        return $false
    }

    return $process.ProcessName -ieq "sb"
}

function Send-GameKey([int] $VirtualKey) {
    if (-not (Test-ShadowbaneForeground)) {
        return $false
    }

    [ShadowbaneMacroNative]::Press([uint16] $VirtualKey)
    return $true
}

function Send-SelfTarget {
    if (-not (Test-ShadowbaneForeground)) {
        return $false
    }

    [ShadowbaneMacroNative]::Press([uint16] $virtualKeys.End)
    return $true
}

$steps = @(
    @{ Name = "target self"; SelfTarget = $true; DelayMs = 300 },
    @{ Name = "F1 Call Lightning"; Key = $virtualKeys.F1; DelayMs = 3300 },
    @{ Name = "F2 Earthquake"; Key = $virtualKeys.F2; DelayMs = 12000 }
)

$maintenanceActions = @(
    @{ Name = "F4 long-duration buff"; Key = $virtualKeys.F4; IntervalSeconds = 600; RecoveryMs = 3300; NextDue = [DateTime]::MinValue },
    @{ Name = "C enter combat mode (one time)"; Key = $virtualKeys.C; RunOnce = $true; RecoveryMs = 1000; NextDue = [DateTime]::MinValue },
    @{ Name = "F5 Defensive Stance"; Key = $virtualKeys.F5; IntervalSeconds = 600; RecoveryMs = 3300; NextDue = [DateTime]::MinValue },
    @{ Name = "F6 Concoction potion"; Key = $virtualKeys.F6; IntervalSeconds = 6000; RecoveryMs = 3300; NextDue = [DateTime]::MinValue },
    @{ Name = "F3 Hedge of Thorns"; Key = $virtualKeys.F3; IntervalSeconds = 40; RecoveryMs = 3300; NextDue = [DateTime]::MinValue }
)

$running = $false
$oneCycle = $false
$stepIndex = 0
$activeMaintenance = $null
$maintenanceTargetReady = $false
$nextAction = [DateTime]::UtcNow
$waitingForGameLogged = $false
$stopRequested = $false
$wmHotKey = 0x0312
$hotKeyIds = @{
    Toggle = 0x5308
    OneCycle = 0x5309
    Exit = 0x5310
}
$registeredHotKeyIds = @()
$stateDirectory = Join-Path $env:LOCALAPPDATA "ShadowbaneLab\macros"
[void](New-Item -ItemType Directory -Path $stateDirectory -Force)
$runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$runLogPath = Join-Path $stateDirectory "druid-aoe-run-$runStamp.log"
$transcriptStarted = $false

try {
    Start-Transcript -LiteralPath $runLogPath -Force | Out-Null
    $transcriptStarted = $true
}
catch {
    Write-Host "Warning: could not start run log: $($_.Exception.Message)" -ForegroundColor Yellow
}

try {
    $registrations = @(
        @{ Id = $hotKeyIds.Toggle; Key = $virtualKeys.F8; Name = "F8" },
        @{ Id = $hotKeyIds.OneCycle; Key = $virtualKeys.F9; Name = "F9" },
        @{ Id = $hotKeyIds.Exit; Key = $virtualKeys.F10; Name = "F10" }
    )
    foreach ($registration in $registrations) {
        $registered = [ShadowbaneMacroNative]::RegisterHotKey(
            [IntPtr]::Zero,
            $registration.Id,
            0,
            $registration.Key
        )
        if (-not $registered) {
            $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
            throw "Could not register $($registration.Name) (Win32 error $errorCode). Close any older macro window and retry."
        }
        $registeredHotKeyIds += $registration.Id
    }

    Write-Host "Shadowbane Druid PvE AoE macro v$macroVersion" -ForegroundColor Green
    Write-Host "Macro PID: $PID"
    Write-Host "Center loop: F1 Call Lightning, then F2 Earthquake (about 15.6s)"
    Write-Host "Outer timer: F3 Hedge of Thorns every 40s+"
    Write-Host "F4 buff: 600s | F5 Defensive Stance: 600s | F6 Concoction: 6000s"
    Write-Host "Startup: F4 buff, C, F5 defensive, F6 concoction, then combat powers"
    Write-Host "Combat mode: C once per macro process before the first F5"
    Write-Host "Targeting: End resets to self before maintenance and every AoE cycle"
    Write-Host "F8  toggle rotation"
    Write-Host "F9  run one rotation"
    Write-Host "F10 stop and exit"
    Write-Host "Control hotkeys registered; F8-F10 will not reach the game hotbar."
    Write-Host "SendInput ABI: $actualInputSize bytes"
    Write-Host "Run log: $runLogPath"
    Write-Host "The macro pauses whenever Shadowbane is not the foreground window."
    Write-Host "Status: PAUSED" -ForegroundColor Yellow

    while (-not $stopRequested) {
        $message = New-Object ShadowbaneMacroNative+MSG
        while ([ShadowbaneMacroNative]::PeekMessage(
            [ref] $message,
            [IntPtr]::Zero,
            0,
            0,
            1
        )) {
            if ($message.message -ne $wmHotKey) {
                continue
            }

            $messageId = [int] $message.wParam.ToUInt64()
            if ($messageId -eq $hotKeyIds.Toggle) {
                $running = -not $running
                $oneCycle = $false
                $stepIndex = 0
                $activeMaintenance = $null
                $maintenanceTargetReady = $false
                $nextAction = [DateTime]::UtcNow
                $waitingForGameLogged = $false
                if ($running) {
                    Write-Host "Status: RUNNING" -ForegroundColor Green
                }
                else {
                    Write-Host "Status: PAUSED" -ForegroundColor Yellow
                }
            }
            elseif ($messageId -eq $hotKeyIds.OneCycle) {
                $running = $true
                $oneCycle = $true
                $stepIndex = 0
                $activeMaintenance = $null
                $maintenanceTargetReady = $false
                $nextAction = [DateTime]::UtcNow
                $waitingForGameLogged = $false
                Write-Host "Status: ONE ROTATION" -ForegroundColor Cyan
            }
            elseif ($messageId -eq $hotKeyIds.Exit) {
                Write-Host "Status: STOPPED" -ForegroundColor Yellow
                $stopRequested = $true
            }
        }

        if (-not $stopRequested -and $running -and [DateTime]::UtcNow -ge $nextAction) {
            if (Test-ShadowbaneForeground) {
                $waitingForGameLogged = $false
                if ($null -eq $activeMaintenance -and $stepIndex -eq 0) {
                    $now = [DateTime]::UtcNow
                    $activeMaintenance = @(
                        $maintenanceActions | Where-Object { $now -ge $_.NextDue }
                    )[0]
                    $maintenanceTargetReady = $false
                }

                if ($null -ne $activeMaintenance) {
                    if (-not $maintenanceTargetReady) {
                        if (Send-SelfTarget) {
                            Write-Host ("{0:HH:mm:ss}  target self for {1}" -f [DateTime]::Now, $activeMaintenance.Name)
                            $maintenanceTargetReady = $true
                            $nextAction = [DateTime]::UtcNow.AddMilliseconds(300)
                        }
                    }
                    elseif (Send-GameKey $activeMaintenance.Key) {
                        Write-Host ("{0:HH:mm:ss}  {1}" -f [DateTime]::Now, $activeMaintenance.Name)
                        if ($activeMaintenance.RunOnce) {
                            $activeMaintenance.NextDue = [DateTime]::MaxValue
                        }
                        else {
                            $activeMaintenance.NextDue = [DateTime]::UtcNow.AddSeconds($activeMaintenance.IntervalSeconds)
                        }
                        $nextAction = [DateTime]::UtcNow.AddMilliseconds($activeMaintenance.RecoveryMs)
                        $activeMaintenance = $null
                        $maintenanceTargetReady = $false
                    }
                }
                else {
                    $step = $steps[$stepIndex]
                    $stepSent = if ($step.SelfTarget) {
                        Send-SelfTarget
                    }
                    else {
                        Send-GameKey $step.Key
                    }
                    if ($stepSent) {
                        Write-Host ("{0:HH:mm:ss}  {1}" -f [DateTime]::Now, $step.Name)
                        $nextAction = [DateTime]::UtcNow.AddMilliseconds($step.DelayMs)
                        $stepIndex += 1

                        if ($stepIndex -ge $steps.Count) {
                            $stepIndex = 0
                            if ($oneCycle) {
                                $running = $false
                                $oneCycle = $false
                                Write-Host "Status: PAUSED (one rotation complete)" -ForegroundColor Yellow
                            }
                        }
                    }
                }
            }
            elseif (-not $waitingForGameLogged) {
                Write-Host "Waiting: bring an sb.exe Shadowbane window to the foreground." -ForegroundColor Yellow
                $waitingForGameLogged = $true
            }
        }

        Start-Sleep -Milliseconds 40
    }
}
catch {
    $fatalText = ($_ | Out-String).Trim()
    Write-Host ""
    Write-Host "FATAL MACRO ERROR" -ForegroundColor Red
    Write-Host $fatalText -ForegroundColor Red
    Write-Host "Run log: $runLogPath" -ForegroundColor Yellow
    Write-Host "This window will remain open so the error can be read."
    [void](Read-Host "Press Enter to close")
}
finally {
    $running = $false
    foreach ($registeredHotKeyId in $registeredHotKeyIds) {
        [void][ShadowbaneMacroNative]::UnregisterHotKey([IntPtr]::Zero, $registeredHotKeyId)
    }
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
}
