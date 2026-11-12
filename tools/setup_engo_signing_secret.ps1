[CmdletBinding()]
param(
    [string]$ProjectRef = "milksrcwbqmkczlhjfsi",
    [switch]$RotateSigningKey
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot
$SecretName = 'ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64'
$SecretDir = Join-Path $ProjectRoot '.secrets'
$PrivatePath = Join-Path $SecretDir 'engo-license-signing-private.pkcs8.b64'
$PublicPath = Join-Path $SecretDir 'engo-license-signing-public.raw.b64'
$ConfigPath = Join-Path $ProjectRoot 'engo_license.json'
$GeneratorPath = Join-Path $ProjectRoot 'tools/generate_license_signing_keys.py'
$TempEnv = $null
$PrivateKey = $null

function Stop-WithMessage([string]$Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    throw $Message
}

Write-Host ''
Write-Host 'ENGO — Secure license-signing setup' -ForegroundColor Cyan
Write-Host "Target project: $ProjectRef" -ForegroundColor Yellow
Write-Host 'This will create one local Ed25519 keypair and upload only its private half as a Supabase Edge Function secret.'
Write-Host 'The private key will not be printed or copied into the desktop application.' -ForegroundColor Gray
Write-Host ''

if ($ProjectRef -cne 'milksrcwbqmkczlhjfsi') {
    Stop-WithMessage 'This setup package is pinned to the Engo project ref. The supplied ProjectRef did not match.'
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { Stop-WithMessage 'engo_license.json was not found.' }
if (-not (Test-Path -LiteralPath $GeneratorPath -PathType Leaf)) { Stop-WithMessage 'The Ed25519 key generator was not found.' }

$Supabase = Get-Command 'supabase' -ErrorAction SilentlyContinue
if (-not $Supabase) {
    Write-Host 'Supabase CLI is not installed.' -ForegroundColor Yellow
    Write-Host 'Official Windows installation (Scoop):' -ForegroundColor Cyan
    Write-Host '  scoop bucket add supabase https://github.com/supabase/scoop-bucket.git'
    Write-Host '  scoop install supabase'
    Write-Host 'Then close and reopen PowerShell and run this file again.'
    exit 2
}

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
    Stop-WithMessage 'Python with the cryptography package was not found. Run: python -m pip install "cryptography>=42.0" then retry.'
}

Write-Host 'Checking Supabase CLI...' -ForegroundColor Cyan
& $Supabase.Source --version
if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Supabase CLI could not run.' }

Write-Host 'Signing in to Supabase CLI. A browser window may open.' -ForegroundColor Cyan
& $Supabase.Source login
if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Supabase CLI login failed. No secret was uploaded.' }

Write-Host 'Checking local signing-key files...' -ForegroundColor Cyan
$HasPrivate = Test-Path -LiteralPath $PrivatePath -PathType Leaf
$HasPublic = Test-Path -LiteralPath $PublicPath -PathType Leaf
if (($HasPrivate -xor $HasPublic) -and -not $RotateSigningKey) {
    Stop-WithMessage 'Only one key file exists. Do not delete or overwrite it blindly; inspect the .secrets folder first.'
}
$ExistingConfig = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ConfiguredPublicKey = [string]$ExistingConfig.license_public_key_b64
if ($RotateSigningKey) {
    $GeneratorArgs = @()
    $GeneratorArgs += $PythonPrefix
    $GeneratorArgs += @($GeneratorPath, '--config', $ConfigPath, '--rotate-existing-public-key')
    & $PythonExe @GeneratorArgs
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Explicit Ed25519 key rotation failed.' }
    $HasPrivate = $true
    $HasPublic = $true
} elseif (-not $HasPrivate) {
    if (-not [string]::IsNullOrWhiteSpace($ConfiguredPublicKey)) {
        Stop-WithMessage 'A public key is already embedded in engo_license.json, but this folder has no matching private keypair. Restore the original .secrets files. Use -RotateSigningKey only for an intentional coordinated rotation.'
    }
    $GeneratorArgs = @()
    $GeneratorArgs += $PythonPrefix
    $GeneratorArgs += @($GeneratorPath, '--config', $ConfigPath)
    & $PythonExe @GeneratorArgs
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Ed25519 key generation failed.' }
}

$PrivateKey = ([System.IO.File]::ReadAllText($PrivatePath)).Trim()
$PublicKey = ([System.IO.File]::ReadAllText($PublicPath)).Trim()
if (-not $RotateSigningKey -and -not [string]::IsNullOrWhiteSpace($ConfiguredPublicKey) -and $ConfiguredPublicKey -cne $PublicKey) {
    Stop-WithMessage 'The local keypair public key differs from the app config. Refusing an implicit signing-key rotation.'
}
try {
    $PrivateBytes = [Convert]::FromBase64String($PrivateKey)
    $PublicBytes = [Convert]::FromBase64String($PublicKey)
} catch {
    Stop-WithMessage 'The local key files are not valid Base64. No secret was uploaded.'
}
if ($PrivateBytes.Length -lt 32 -or $PublicBytes.Length -ne 32) {
    Stop-WithMessage 'Unexpected Ed25519 key length. No secret was uploaded.'
}

# Verify the stored public key matches the stored private key before sending anything.
$VerifyPairCode = 'import base64,sys; from pathlib import Path; from cryptography.hazmat.primitives.serialization import load_der_private_key,Encoding,PublicFormat; priv=load_der_private_key(base64.b64decode(Path(sys.argv[1]).read_text().strip()),password=None); actual=priv.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw); expected=base64.b64decode(Path(sys.argv[2]).read_text().strip()); sys.exit(0 if actual == expected else 7)'
$VerifyArgs = @()
$VerifyArgs += $PythonPrefix
$VerifyArgs += @('-c', $VerifyPairCode, $PrivatePath, $PublicPath)
& $PythonExe @VerifyArgs *> $null
if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'The local public/private keypair does not match. No secret was uploaded.' }

# Keep the verification key in the public app config; never place the private key there.
try {
    $Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $Config.license_public_key_b64 = $PublicKey
    $ConfigJson = $Config | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($ConfigPath, $ConfigJson + "`r`n", [System.Text.UTF8Encoding]::new($false))
} catch {
    Stop-WithMessage 'Could not update engo_license.json with the public key. No secret was uploaded.'
}

$confirmation = Read-Host "Type $ProjectRef exactly to upload the signing secret to this Supabase project"
if ($confirmation -cne $ProjectRef) { Stop-WithMessage 'Project confirmation did not match. No secret was uploaded.' }

try {
    # The temporary .env is created inside the ACL-protected .secrets directory and deleted after upload.
    New-Item -ItemType Directory -Force -Path $SecretDir | Out-Null
    $TempEnv = Join-Path $SecretDir ('.supabase-signing-' + [guid]::NewGuid().ToString('N') + '.env')
    [System.IO.File]::WriteAllText(
        $TempEnv,
        "$SecretName=$PrivateKey`r`n",
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Host 'Uploading the private signing key as a Supabase Edge Function secret...' -ForegroundColor Cyan
    & $Supabase.Source secrets set --env-file $TempEnv --project-ref $ProjectRef
    if ($LASTEXITCODE -ne 0) { throw 'Supabase did not accept the secret. The private key was not printed.' }

    Write-Host 'Verifying that the secret name exists (the secret value is never read or displayed)...' -ForegroundColor Cyan
    $SecretList = & $Supabase.Source secrets list --project-ref $ProjectRef 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or $SecretList -notmatch [regex]::Escape($SecretName)) {
        throw 'The CLI could not confirm the signing-secret name in the target project.'
    }

    Write-Host ''
    Write-Host 'SUCCESS: The signing secret is present in the Engo Supabase project.' -ForegroundColor Green
    Write-Host 'The public key has been written to engo_license.json.' -ForegroundColor Green
    Write-Host 'No database migrations or Edge Functions were redeployed; the live functions read the secret at runtime.' -ForegroundColor Gray
    Write-Host 'Keep .secrets/ private and never include it in a ZIP, EXE, Git commit, or support message.' -ForegroundColor Yellow
    Write-Host 'Next: run Engo from this project folder, test Google sign-in, then verify the signed Free license.' -ForegroundColor Cyan
} catch {
    Stop-WithMessage $_.Exception.Message
} finally {
    if ($TempEnv -and (Test-Path -LiteralPath $TempEnv)) {
        Remove-Item -LiteralPath $TempEnv -Force -ErrorAction SilentlyContinue
    }
    $PrivateKey = $null
    $PrivateBytes = $null
    $PublicBytes = $null
    $SecretList = $null
}
