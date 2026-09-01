[CmdletBinding()]
param(
    [string] $RepositoryShare = "\\VBOXSVR\codexgfx",
    [string] $DiagnosticsShare = "\\VBOXSVR\codexdiag",
    [string] $PythonExecutable = "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe",
    [string] $ContentBuildId = "wb-55fbad5f-4b602995",
    [string] $ExtensionVersion = "1.5.4",
    [string] $PackageDirectory = (
        "S:\Wonderbane-graphics-wb-55fbad5f-4b602995-cel-1.5.4"
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$expectedExtensionSha256 = "83c7b83d37a7bf0382d2c234ba12049acaa9c5264fa9cde31741e87c949eaad2"
$expectedExecutableSha256 = "a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8"
$expectedTexturePatchId = "wonderbane-1.0.5-55fbad5f.restrained-cel-v1"
$expectedTexturePatchManifestSha256 = (
    "1128d1c82463805b6acfb5841d46c608362170963535b9db39be0f5e9079197c"
)
$evidenceDirectory = Join-Path `
    (Join-Path $DiagnosticsShare "graphics-packages") `
    "$ContentBuildId-cel-$ExtensionVersion"
$publicationReceipt = Join-Path $evidenceDirectory "publication.json"
$gameExecutable = Join-Path $PackageDirectory "sb.exe"
$extensionArtifact = Join-Path $PackageDirectory "wonderbane-extension.dll"

foreach ($required in @(
    @{ Path = $RepositoryShare; Description = "graphics-only repository share" },
    @{ Path = $PythonExecutable; Description = "guest Python environment" },
    @{ Path = $PackageDirectory; Description = "published graphics package" },
    @{ Path = $publicationReceipt; Description = "graphics publication receipt" },
    @{ Path = $gameExecutable; Description = "published WonderBane executable" },
    @{ Path = $extensionArtifact; Description = "published graphics extension" }
)) {
    if (-not (Test-Path -LiteralPath $required.Path)) {
        throw "$($required.Description) was not found: $($required.Path)"
    }
}

$receipt = Get-Content -LiteralPath $publicationReceipt -Raw | ConvertFrom-Json
$receiptChecks = [ordered]@{
    status = "published_and_verified"
    content_build_id = $ContentBuildId
    extension_version = $ExtensionVersion
    extension_sha256 = $expectedExtensionSha256
    texture_patch_id = $expectedTexturePatchId
    texture_patch_manifest_sha256 = $expectedTexturePatchManifestSha256
    destination = $PackageDirectory
}
foreach ($field in $receiptChecks.Keys) {
    $property = $receipt.PSObject.Properties[$field]
    if ($null -eq $property -or [string] $property.Value -cne [string] $receiptChecks[$field]) {
        throw "Graphics publication receipt does not match field '$field': $publicationReceipt"
    }
}

$actualExecutableSha256 = (
    Get-FileHash -LiteralPath $gameExecutable -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($actualExecutableSha256 -ne $expectedExecutableSha256) {
    throw "Published WonderBane executable no longer matches its reviewed identity"
}
$actualExtensionSha256 = (
    Get-FileHash -LiteralPath $extensionArtifact -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($actualExtensionSha256 -ne $expectedExtensionSha256) {
    throw "Published graphics extension no longer matches its reviewed identity"
}

$runningGame = Get-Process -Name "sb" -ErrorAction SilentlyContinue
if ($null -ne $runningGame) {
    throw "Close every running sb.exe before launching the isolated graphics client"
}

$env:PYTHONPATH = Join-Path $RepositoryShare "src"
& $PythonExecutable -m shadowbane_lab.client_extension `
    verify-copy `
    $PackageDirectory | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Published graphics package verification failed with exit code $LASTEXITCODE"
}

$graphicsEnvironment = [ordered]@{
    LIBGL_ALWAYS_SOFTWARE = "true"
    GALLIUM_DRIVER = "llvmpipe"
    LP_NUM_THREADS = "3"
    MESA_EXTENSION_MAX_YEAR = "2001"
    MESA_GL_VERSION_OVERRIDE = $null
    MESA_GLSL_VERSION_OVERRIDE = $null
}
$previousEnvironment = @{}
foreach ($name in $graphicsEnvironment.Keys) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    [Environment]::SetEnvironmentVariable($name, $graphicsEnvironment[$name], "Process")
}
try {
    $game = Start-Process `
        -FilePath $gameExecutable `
        -WorkingDirectory $PackageDirectory `
        -PassThru
}
finally {
    foreach ($name in $graphicsEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], "Process")
    }
}

Write-Output "Launched isolated WonderBane graphics client (PID $($game.Id))"
Write-Output "WonderBane content build: $ContentBuildId"
Write-Output "Graphics extension version: $ExtensionVersion"
Write-Output "Package: $PackageDirectory"
