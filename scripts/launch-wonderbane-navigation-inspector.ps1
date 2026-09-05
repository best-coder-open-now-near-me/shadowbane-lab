[CmdletBinding()]
param(
    [string]$RuntimeDirectory = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$runtime = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$client = Join-Path $runtime 'client'
$executable = Join-Path $client 'sb.exe'
$python = Join-Path $runtime 'python\Scripts\python.exe'
foreach ($path in @($executable, $python, (Join-Path $client 'wonderbane-extension.dll'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Prepared inspector runtime is incomplete: $path"
    }
}
# Do not create a second instance in a runtime whose mutable files are in use.
$existing = @(Get-CimInstance Win32_Process -Filter "Name='sb.exe'" | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.Equals($executable, [StringComparison]::OrdinalIgnoreCase)
})
if ($existing.Count -gt 0) {
    throw "This prepared client is already running (PID $($existing.ProcessId -join ', ')). Connect the inspector to that process."
}
$settings = @{
    PYTHONPATH = $null
    LIBGL_ALWAYS_SOFTWARE = 'true'
    GALLIUM_DRIVER = 'llvmpipe'
    LP_NUM_THREADS = '3'
    MESA_EXTENSION_MAX_YEAR = '2001'
    MESA_GL_VERSION_OVERRIDE = $null
    MESA_GLSL_VERSION_OVERRIDE = $null
}
$previous = @{}
try {
    foreach ($name in $settings.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
    }
    & $python -m shadowbane_lab.client_extension verify-runtime-copy $client --pretty
    if ($LASTEXITCODE -ne 0) { throw 'Prepared client integrity verification failed; game was not launched.' }
    $game = Start-Process -FilePath $executable -WorkingDirectory $client -WindowStyle Normal -PassThru
    [pscustomobject]@{
        process_id = $game.Id
        process_creation_filetime = $game.StartTime.ToUniversalTime().ToFileTimeUtc()
        executable = $executable
        status = 'launched'
    }
} finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
