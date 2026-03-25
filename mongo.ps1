param(
    [ValidateSet("up", "down", "restart", "logs")]
    [string]$Action = "up",
    [string]$ComposeFile = ""
)

$ErrorActionPreference = "Stop"

$RootDir = $PSScriptRoot
if (-not $RootDir) {
    $RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

if (-not $ComposeFile) {
    $ComposeFile = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { "docker-compose.yml" }
}

Set-Location $RootDir

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker is required but was not found in PATH."
}

switch ($Action) {
    "up" {
        & docker compose -f $ComposeFile up -d mongo
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "MongoDB is starting on mongodb://127.0.0.1:27017"
    }
    "down" {
        & docker compose -f $ComposeFile stop mongo
        exit $LASTEXITCODE
    }
    "restart" {
        & docker compose -f $ComposeFile restart mongo
        exit $LASTEXITCODE
    }
    "logs" {
        & docker compose -f $ComposeFile logs -f mongo
        exit $LASTEXITCODE
    }
}
