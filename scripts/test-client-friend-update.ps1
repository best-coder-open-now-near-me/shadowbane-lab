#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'client-friend-update/Install-ShadowbaneLocal.ps1'
$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($installer, [ref]$tokens, [ref]$parseErrors)
if (@($parseErrors).Count) { throw 'Installer parse failure' }
foreach ($function in $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $false)) {
    Invoke-Expression $function.Extent.Text
}
$encoding = [Text.Encoding]::GetEncoding(28591)
$original = "# Keep my settings`r`nSERVER= old.example ; my server`r`nPORT= 1234`r`nOTHER= unchanged`r`n"
$expected = "# Keep my settings`r`nSERVER= 100.87.213.55 ; my server`r`nPORT= 6000`r`nOTHER= unchanged`r`n"
$actual = Set-ServerEndpoint ($encoding.GetBytes($original))
if ($encoding.GetString($actual) -cne $expected) { throw 'Endpoint rewrite did not preserve unrelated bytes' }
if ($encoding.GetString((Set-ServerEndpoint $actual)) -cne $expected) { throw 'Endpoint rewrite is not idempotent' }
$bom = [byte[]]@(239,187,191)
$withBom = Set-ServerEndpoint ([byte[]]($bom + $encoding.GetBytes("SERVER= old`nPORT= 5`n")))
if ($encoding.GetString($withBom) -cne $encoding.GetString($bom + $encoding.GetBytes("SERVER= 100.87.213.55`nPORT= 6000`n"))) { throw 'UTF-8 BOM or LF was changed' }
$appended = $encoding.GetString((Set-ServerEndpoint ($encoding.GetBytes('OTHER= keep'))))
if ($appended -cne "OTHER= keep`nSERVER= 100.87.213.55`nPORT= 6000`n") { throw 'Missing endpoint keys were not appended correctly' }
foreach ($bad in @("SERVER= one`nSERVER= two`n", "PORT= 1`nPORT= 2`n", "SERVER=`0")) {
    $rejected = $false
    try { [void](Set-ServerEndpoint ($encoding.GetBytes($bad))) } catch { $rejected = $true }
    if (-not $rejected) { throw 'Malformed configuration accepted' }
}
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('shadowbane-update-test-' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($temporary)
try {
    $path = Join-Path $temporary 'ArcaneIP.cfg'
    Write-Atomic $path ($encoding.GetBytes($original))
    Write-Atomic $path $actual
    if ([IO.File]::ReadAllText($path) -cne $expected) { throw 'Atomic replacement failed' }
    if (@(Get-ChildItem -LiteralPath $temporary -Force).Count -ne 1) { throw 'Temporary or rollback files were retained' }
} finally {
    # The generated absolute directory is constrained to this test before deletion.
    $resolved = (Resolve-Path -LiteralPath $temporary).Path
    $base = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($base, [StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path -Leaf $resolved) -notlike 'shadowbane-update-test-*') { throw 'Unexpected test cleanup target' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Output 'Friend installer tests passed: endpoint preservation, idempotence, BOM/LF, duplicate rejection, atomic replacement, and no retained copies.'
