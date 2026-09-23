# Run before the prepared game launcher. This never patches or launches a client.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OfficialExecutable,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-fA-F0-9]{64}$')]
    [string]$ExpectedSourceSha256
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $OfficialExecutable -PathType Leaf)) {
    throw "The normal WonderBane client is missing at $OfficialExecutable. Restore its location before starting Vendor Test."
}
$actual = (Get-FileHash -LiteralPath $OfficialExecutable -Algorithm SHA256).Hash
if (-not $actual.Equals($ExpectedSourceSha256, [StringComparison]::OrdinalIgnoreCase)) {
    throw "The normal WonderBane client has changed. Vendor Test needs a matching extension update before login. Normal client: $OfficialExecutable. Leave the Vendor Test client intact so its settings and jobs can be preserved."
}
