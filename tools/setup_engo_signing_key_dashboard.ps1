[CmdletBinding()]
param([switch]$RotateSigningKey)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot
$SecretDir = Join-Path $ProjectRoot '.secrets'
$PrivatePath = Join-Path $SecretDir 'engo-license-signing-private.pkcs8.b64'
$PublicPath = Join-Path $SecretDir 'engo-license-signing-public.raw.b64'
$ConfigPath = Join-Path $ProjectRoot 'engo_license.json'
$GeneratorPath = Join-Path $ProjectRoot 'tools/generate_license_signing_keys.py'
$PrivateKey = $null
$PrivateBytes = $null
$PublicBytes = $null

function Stop-WithMessage([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    throw $Message
}

Write-Host ''
Write-Host 'ENGO — Ed25519 signing key setup (Dashboard method)' -ForegroundColor Cyan
Write-Host 'This script does not need Supabase CLI and does not send any key over the network.' -ForegroundColor Gray
Write-Host 'It writes the PUBLIC key to engo_license.json and copies the PRIVATE key to the clipboard.' -ForegroundColor Gray
Write-Host ''

if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { Stop-WithMessage 'engo_license.json was not found. Run this from the Engo source folder.' }
if (-not (Test-Path -LiteralPath $GeneratorPath -PathType Leaf)) { Stop-WithMessage 'The Ed25519 key generator was not found.' }

$PythonExe = $null
$PythonPrefix = @()
$PyLauncher = Get-Command 'py' -ErrorAction SilentlyContinue
if ($PyLauncher) {
    & $PyLauncher.Source -3.13 -c 'import cryptography' *> $null
    if ($LASTEXITCODE -eq 0) {
        $PythonExe = $PyLauncher.Source
        $PythonPrefix = @('-3.13')
    }
}
if (-not $PythonExe) {
    $PythonCommand = Get-Command 'python' -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        & $PythonCommand.Source -c 'import cryptography' *> $null
        if ($LASTEXITCODE -eq 0) { $PythonExe = $PythonCommand.Source }
    }
}
if (-not $PythonExe) {
    Stop-WithMessage 'Python with cryptography was not found. Install the project requirements, then run this script again.'
}

$HasPrivate = Test-Path -LiteralPath $PrivatePath -PathType Leaf
$HasPublic = Test-Path -LiteralPath $PublicPath -PathType Leaf
if (($HasPrivate -xor $HasPublic) -and -not $RotateSigningKey) {
    Stop-WithMessage 'Only one local key file exists. Do not delete or regenerate it blindly; inspect .secrets first.'
}

if ($RotateSigningKey) {
    Write-Host 'ROTATION REQUESTED: generating a new keypair and replacing the configured public key.' -ForegroundColor Red
    $GeneratorArgs = @()
    $GeneratorArgs += $PythonPrefix
    $GeneratorArgs += @($GeneratorPath, '--config', $ConfigPath, '--rotate-existing-public-key')
    & $PythonExe @GeneratorArgs
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Ed25519 key rotation failed.' }
    $HasPrivate = $true
    $HasPublic = $true
} elseif (-not $HasPrivate) {
    $ExistingConfig = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not [string]::IsNullOrWhiteSpace([string]$ExistingConfig.license_public_key_b64)) {
        Stop-WithMessage 'engo_license.json already contains a public key but this folder has no matching private key. Restore the original keypair or pass -RotateSigningKey for an intentional coordinated rotation.'
    }
    Write-Host 'Generating one initial Ed25519 keypair...' -ForegroundColor Cyan
    $GeneratorArgs = @()
    $GeneratorArgs += $PythonPrefix
    $GeneratorArgs += @($GeneratorPath, '--config', $ConfigPath)
    & $PythonExe @GeneratorArgs
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Ed25519 key generation failed.' }
} else {
    Write-Host 'Reusing the existing local keypair; no new key was generated.' -ForegroundColor Yellow
    $Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $PublicKeyExisting = ([System.IO.File]::ReadAllText($PublicPath)).Trim()
    if (-not [string]::IsNullOrWhiteSpace([string]$Config.license_public_key_b64) -and
        [string]$Config.license_public_key_b64 -cne $PublicKeyExisting -and -not $RotateSigningKey) {
        Stop-WithMessage 'The local keypair does not match the public key in engo_license.json. Refusing an implicit rotation.'
    }
    $Config.license_public_key_b64 = $PublicKeyExisting
    [System.IO.File]::WriteAllText($ConfigPath, ($Config | ConvertTo-Json -Depth 20) + "`r`n", [System.Text.UTF8Encoding]::new($false))
}

$PrivateKey = ([System.IO.File]::ReadAllText($PrivatePath)).Trim()
$PublicKey = ([System.IO.File]::ReadAllText($PublicPath)).Trim()
try {
    $PrivateBytes = [Convert]::FromBase64String($PrivateKey)
    $PublicBytes = [Convert]::FromBase64String($PublicKey)
} catch {
    Stop-WithMessage 'The generated key files are not valid Base64.'
}
if ($PrivateBytes.Length -lt 32 -or $PublicBytes.Length -ne 32) {
    Stop-WithMessage 'Unexpected Ed25519 key length.'
}

# Verify that the local public key is derived from the private PKCS#8 key.
$VerifyPairCode = 'import base64,sys; from pathlib import Path; from cryptography.hazmat.primitives.serialization import load_der_private_key,Encoding,PublicFormat; priv=load_der_private_key(base64.b64decode(Path(sys.argv[1]).read_text().strip()),password=None); actual=priv.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw); expected=base64.b64decode(Path(sys.argv[2]).read_text().strip()); sys.exit(0 if actual == expected else 7)'
$VerifyArgs = @()
$VerifyArgs += $PythonPrefix
$VerifyArgs += @('-c', $VerifyPairCode, $PrivatePath, $PublicPath)
& $PythonExe @VerifyArgs *> $null
if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'The local public/private keypair does not match.' }

if (-not (Get-Command 'Set-Clipboard' -ErrorAction SilentlyContinue)) {
    Stop-WithMessage 'Set-Clipboard is unavailable. Run this in Windows PowerShell 5.1 or PowerShell 7 on Windows.'
}
Set-Clipboard -Value $PrivateKey

Write-Host ''
Write-Host 'PUBLIC KEY: saved to engo_license.json -> license_public_key_b64' -ForegroundColor Green
Write-Host 'PRIVATE KEY: copied to clipboard only; it was not printed and was not uploaded.' -ForegroundColor Green
Write-Host ''
Write-Host 'Now open Supabase Dashboard → your Engo project → Edge Functions → Secrets.' -ForegroundColor Cyan
Write-Host 'Add this exact Key:' -ForegroundColor Yellow
Write-Host 'ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64' -ForegroundColor White
Write-Host 'Paste the clipboard into Value, then click Save.' -ForegroundColor Yellow
Write-Host ''
Write-Host 'After you have saved it in Supabase, return here and press Enter to clear the clipboard.' -ForegroundColor Cyan
try {
    [void](Read-Host 'Press Enter after saving the secret')
} finally {
    Set-Clipboard -Value ''
    $PrivateKey = $null
    $PrivateBytes = $null
    $PublicBytes = $null
}
Write-Host 'Clipboard cleared. Keep .secrets private and never include it in an EXE, ZIP, Git commit, or support message.' -ForegroundColor Green
Write-Host 'The Edge Functions read newly saved secrets without redeployment.' -ForegroundColor Gray
