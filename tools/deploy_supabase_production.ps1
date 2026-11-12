[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]{20}$')]
    [string]$ProjectRef = "milksrcwbqmkczlhjfsi",
    [switch]$KeepExistingSigningKey
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

if (-not (Get-Command supabase -ErrorAction SilentlyContinue)) {
    throw 'Supabase CLI is not installed. Install it first, then reopen PowerShell.'
}
if (-not (Test-Path (Join-Path $ProjectRoot 'supabase/config.toml'))) {
    throw 'supabase/config.toml was not found. Run this script from the delivered Engo project.'
}

Write-Host "Target Supabase project: $ProjectRef" -ForegroundColor Yellow
$confirmation = Read-Host "Type the project ref exactly to continue"
if ($confirmation -cne $ProjectRef) { throw 'Project confirmation did not match. No deployment was performed.' }

$PrivateKeyPath = Join-Path $ProjectRoot '.secrets/engo-license-signing-private.pkcs8.b64'
$PrivateKey = ''
if (Test-Path $PrivateKeyPath) {
    $PrivateKey = (Get-Content -LiteralPath $PrivateKeyPath -Raw).Trim()
    if ($PrivateKey -notmatch '^[A-Za-z0-9+/]+={0,2}$') {
        throw 'Private signing key file does not contain a valid base64 value.'
    }
} else {
    if (-not $KeepExistingSigningKey) {
        throw 'No local Ed25519 private key found. Restore the matching owner key to .secrets, or use -KeepExistingSigningKey ONLY after verifying the same key is already configured in Supabase.'
    }
    Write-Warning 'No local Ed25519 key supplied. The Supabase signing secret will be left unchanged. Use this switch only after verifying the signing secret already exists in the target project.'
}
$GoogleSecretPath = Join-Path $ProjectRoot '.secrets/engo-google-desktop-client-secret.txt'
if (-not (Test-Path $GoogleSecretPath)) {
    throw 'Google Desktop OAuth secret is missing. Run: python tools/set_google_desktop_secret.py'
}
$GoogleClientSecret = (Get-Content -LiteralPath $GoogleSecretPath -Raw).Trim()
$RuntimeConfigPath = Join-Path $ProjectRoot 'engo_license.json'
if (-not (Test-Path $RuntimeConfigPath)) { $RuntimeConfigPath = Join-Path $ProjectRoot 'engo_license.example.json' }
$RuntimeConfig = Get-Content -LiteralPath $RuntimeConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json

if (-not [string]::IsNullOrWhiteSpace($PrivateKey)) {
    # Check the private key against the public key shipped by this exact build
    # before uploading anything. This prevents silently breaking every license.
    $PythonExe = $null
    $PythonPrefix = @()
    $PyLauncher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        & $PyLauncher.Source -3.13 -c 'import cryptography' *> $null
        if ($LASTEXITCODE -eq 0) { $PythonExe = $PyLauncher.Source; $PythonPrefix = @('-3.13') }
    }
    if (-not $PythonExe) {
        $PythonCommand = Get-Command 'python' -ErrorAction SilentlyContinue
        if ($PythonCommand) {
            & $PythonCommand.Source -c 'import cryptography' *> $null
            if ($LASTEXITCODE -eq 0) { $PythonExe = $PythonCommand.Source }
        }
    }
    if (-not $PythonExe) { throw 'Python with cryptography is required to verify the Ed25519 keypair before deployment.' }
    $VerifyScript = Join-Path $ProjectRoot 'tools/verify_signing_key_pair.py'
    if (-not (Test-Path $VerifyScript)) { throw 'Ed25519 keypair verifier is missing.' }
    $VerifyArgs = @()
    $VerifyArgs += $PythonPrefix
    $VerifyArgs += @($VerifyScript, '--project-root', $ProjectRoot)
    & $PythonExe @VerifyArgs
    if ($LASTEXITCODE -ne 0) { throw 'Ed25519 private key does not match the public key in this release. No secrets were uploaded.' }
} elseif (-not $KeepExistingSigningKey) {
    throw 'A local Ed25519 private key is required unless the existing server secret was independently verified.'
}
$GoogleClientId = [string]$RuntimeConfig.google_desktop_client_id
if (-not $GoogleClientId.EndsWith('.apps.googleusercontent.com') -or [string]::IsNullOrWhiteSpace($GoogleClientSecret)) {
    throw 'Valid Google Desktop OAuth Client ID/secret are required before deployment.'
}

# Never echo the private key. The temporary secrets file is removed in finally.
$TempEnv = Join-Path $ProjectRoot ('.supabase-secrets-' + [guid]::NewGuid().ToString('N') + '.env')
try {
    $SecretLines = @(
        "ENGO_GOOGLE_DESKTOP_CLIENT_ID=$GoogleClientId",
        "ENGO_GOOGLE_DESKTOP_CLIENT_SECRET=$GoogleClientSecret"
    )
    if (-not [string]::IsNullOrWhiteSpace($PrivateKey)) {
        $SecretLines += "ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64=$PrivateKey"
    }
    [System.IO.File]::WriteAllText(
        $TempEnv,
        (($SecretLines -join "`n") + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )

    supabase login
    if ($LASTEXITCODE -ne 0) { throw 'Supabase CLI login failed.' }

    supabase link --project-ref $ProjectRef
    if ($LASTEXITCODE -ne 0) { throw 'Could not link the requested Supabase project.' }

    supabase secrets set --env-file $TempEnv --yes
    if ($LASTEXITCODE -ne 0) { throw 'Could not upload the OAuth and optional signing secrets to Supabase.' }

    Write-Host 'Applying database migrations...' -ForegroundColor Cyan
    supabase db push --remote --yes
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed. Edge Functions were not deployed.' }

    $Functions = @('license-check','device-activate','device-transfer','device-heartbeat','usage-consume','account-overview','subscription-request','google-oauth-exchange')
    foreach ($FunctionName in $Functions) {
        Write-Host "Deploying Edge Function: $FunctionName" -ForegroundColor Cyan
        supabase functions deploy $FunctionName --remote=$ProjectRef --yes
        if ($LASTEXITCODE -ne 0) { throw "Deployment failed for function $FunctionName." }
    }

    Write-Host 'Supabase database and Edge Functions deployment completed.' -ForegroundColor Green
    Write-Host 'Next: configure Google OAuth in Supabase Dashboard, approve the release version, and place only the public key in engo_license.json.' -ForegroundColor Yellow
}
finally {
    if (Test-Path $TempEnv) { Remove-Item -LiteralPath $TempEnv -Force }
    $PrivateKey = $null
    $GoogleClientSecret = $null
    [System.GC]::Collect()
}
