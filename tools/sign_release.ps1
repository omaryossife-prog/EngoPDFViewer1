param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,

    [Parameter(Mandatory = $true)]
    [string]$CertificateThumbprint,

    [string]$TimestampServer = "https://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$resolvedPath = (Resolve-Path -LiteralPath $FilePath).Path
$thumbprint = ($CertificateThumbprint -replace '\s', '').ToUpperInvariant()
$certificate = Get-ChildItem -Path Cert:\CurrentUser\My, Cert:\LocalMachine\My |
    Where-Object { $_.Thumbprint -eq $thumbprint -and $_.HasPrivateKey } |
    Select-Object -First 1

if (-not $certificate) {
    throw "No code-signing certificate with a private key was found for thumbprint $thumbprint."
}

$hasCodeSigningEku = $false
foreach ($usage in $certificate.EnhancedKeyUsageList) {
    if ($usage.ObjectId -eq "1.3.6.1.5.5.7.3.3") {
        $hasCodeSigningEku = $true
        break
    }
}
if (-not $hasCodeSigningEku) {
    throw "The selected certificate does not include the Code Signing EKU."
}

$result = Set-AuthenticodeSignature -FilePath $resolvedPath -Certificate $certificate `
    -HashAlgorithm SHA256 -TimestampServer $TimestampServer

if ($result.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    throw "Authenticode signing did not produce a valid signature. Status: $($result.Status)"
}

$verified = Get-AuthenticodeSignature -FilePath $resolvedPath
if ($verified.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
    $verified.SignerCertificate.Thumbprint -ne $thumbprint) {
    throw "Signature verification failed or the signer thumbprint does not match."
}

Write-Host "Signed and verified: $resolvedPath" -ForegroundColor Green
Write-Host "Signer: $($verified.SignerCertificate.Subject)"
Write-Host "Thumbprint: $($verified.SignerCertificate.Thumbprint)"
