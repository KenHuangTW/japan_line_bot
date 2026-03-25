param(
    [string]$CondaEnvName = "",
    [string]$BindHost = "",
    [int]$Port = 0,
    [string]$Reload = ""
)

$ErrorActionPreference = "Stop"

$RootDir = $PSScriptRoot
if (-not $RootDir) {
    $RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if (-not $CondaEnvName) {
    $CondaEnvName = if ($env:CONDA_ENV_NAME) { $env:CONDA_ENV_NAME } else { "nihon-line-bot" }
}

if (-not $BindHost) {
    $BindHost = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
}

if ($Port -eq 0) {
    $Port = if ($env:PORT) { [int]$env:PORT } else { 8000 }
}

if (-not $Reload) {
    $Reload = if ($env:RELOAD) { $env:RELOAD } else { "true" }
}

Set-Location $RootDir

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Error "conda is required but was not found in PATH."
}

if (-not (Test-Path (Join-Path $RootDir ".env"))) {
    Write-Error "Missing .env. Copy .env.example to .env and fill in LINE settings first."
}

$Command = @(
    "run",
    "--no-capture-output",
    "-n", $CondaEnvName,
    "python",
    "-m", "uvicorn",
    "app.main:app",
    "--host", $BindHost,
    "--port", $Port.ToString()
)

if ($Reload.ToLowerInvariant() -eq "true") {
    $Command += "--reload"
}

Write-Host "Starting Nihon LINE Bot on http://$BindHost`:$Port using conda env '$CondaEnvName'"
& conda @Command
exit $LASTEXITCODE
