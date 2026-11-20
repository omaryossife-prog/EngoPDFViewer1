[CmdletBinding()]
param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Debug",

    [ValidateSet("x64", "ARM64")]
    [string]$Architecture = "x64"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$AppProject = Join-Path $ProjectRoot "src\Engo.App\Engo.App.csproj"

Write-Host ""
Write-Host "Engo WinUI 3 — Development Runner" -ForegroundColor Cyan
Write-Host "Configuration : $Configuration"
Write-Host "Architecture  : $Architecture"
Write-Host ""

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw ".NET SDK was not found. Install the .NET 11 SDK, then reopen PowerShell."
}

$SdkVersion = (& dotnet --version).Trim()
if ($LASTEXITCODE -ne 0 -or -not $SdkVersion.StartsWith("11.")) {
    throw "Engo targets .NET 11. The selected SDK is '$SdkVersion'. Install .NET SDK 11.0.100 or later in the 11.x feature band."
}

if (-not (Test-Path $AppProject)) {
    throw "The Engo.App project was not found at '$AppProject'."
}

if (-not (Get-Command winapp -ErrorAction SilentlyContinue)) {
    Write-Host "Installing the Microsoft WinApp CLI..." -ForegroundColor Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "WinApp CLI is missing and winget is unavailable. Install WinApp CLI from https://learn.microsoft.com/windows/apps/dev-tools/winapp-cli, then rerun this script."
    }

    & winget install Microsoft.winappcli --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "WinApp CLI installation failed. Install it manually and rerun this script."
    }

    Write-Host "WinApp CLI was installed. Close this PowerShell window, open a new one, and run .\run-dev.ps1 again." -ForegroundColor Yellow
    exit 0
}

Push-Location $ProjectRoot
try {
    Write-Host "Restoring the app and its dependencies..." -ForegroundColor Cyan
    & dotnet restore $AppProject "-p:Platform=$Architecture"
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency restore failed."
    }

    Write-Host ""
    Write-Host "Building and launching the unpackaged app..." -ForegroundColor Cyan
    Write-Host "This is a development run; no installer or release package is created." -ForegroundColor DarkGray
    & winapp run $AppProject --configuration $Configuration --arch $Architecture

    if ($LASTEXITCODE -ne 0) {
        throw "The development run failed. Read the build/launch error above."
    }
}
finally {
    Pop-Location
}
