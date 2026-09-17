<#
.SYNOPSIS
    Sign a Peaks Windows onedir directory or installer executable.

.DESCRIPTION
    This hook is intentionally fail-closed. It expects the release runner to
    provide a base64-encoded PFX and its password through protected
    environment variables. No certificate is committed to the repository and
    the temporary PFX is removed even when signtool fails.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Target
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$certificateBase64 = $env:PEAKS_SIGN_CERT_BASE64
$certificatePassword = $env:PEAKS_SIGN_CERT_PASSWORD
if ([string]::IsNullOrWhiteSpace($certificateBase64) -or
    [string]::IsNullOrWhiteSpace($certificatePassword)) {
    throw "PEAKS_SIGN_CERT_BASE64 and PEAKS_SIGN_CERT_PASSWORD are required for a release signature"
}

$signToolPath = $env:PEAKS_SIGNTOOL_PATH
if ([string]::IsNullOrWhiteSpace($signToolPath)) {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "signtool.exe was not found; set PEAKS_SIGNTOOL_PATH on the release runner"
    }
    $signToolPath = $command.Source
}
if (-not (Test-Path -LiteralPath $signToolPath -PathType Leaf)) {
    throw "signtool.exe does not exist: $signToolPath"
}
if (-not (Test-Path -LiteralPath $Target)) {
    throw "signing target does not exist: $Target"
}

$timestampUrl = $env:PEAKS_SIGN_TIMESTAMP_URL
if ([string]::IsNullOrWhiteSpace($timestampUrl)) {
    $timestampUrl = "http://timestamp.digicert.com"
}

$temporaryCertificate = Join-Path ([IO.Path]::GetTempPath()) ("peaks-signing-" + [guid]::NewGuid().ToString("N") + ".pfx")
try {
    try {
        $certificateBytes = [Convert]::FromBase64String($certificateBase64)
    }
    catch {
        throw "PEAKS_SIGN_CERT_BASE64 is not valid base64"
    }
    [IO.File]::WriteAllBytes($temporaryCertificate, $certificateBytes)

    $files = @()
    if (Test-Path -LiteralPath $Target -PathType Container) {
        $files = @(Get-ChildItem -LiteralPath $Target -Recurse -File |
            Where-Object { $_.Extension.ToLowerInvariant() -in @(".exe", ".dll", ".pyd", ".sys", ".ocx") } |
            Sort-Object FullName)
    }
    else {
        $files = @(Get-Item -LiteralPath $Target)
    }
    if ($files.Count -eq 0) {
        throw "no Windows binaries found under signing target: $Target"
    }

    foreach ($file in $files) {
        & $signToolPath sign /fd sha256 /td sha256 /tr $timestampUrl /f $temporaryCertificate /p $certificatePassword /a $file.FullName
        if ($LASTEXITCODE -ne 0) {
            throw "signtool failed for $($file.FullName) with exit code $LASTEXITCODE"
        }
        & $signToolPath verify /pa /all $file.FullName
        if ($LASTEXITCODE -ne 0) {
            throw "signtool verification failed for $($file.FullName) with exit code $LASTEXITCODE"
        }
    }
}
finally {
    if (Test-Path -LiteralPath $temporaryCertificate) {
        Remove-Item -LiteralPath $temporaryCertificate -Force
    }
}
