# MingMirror one-click local demo (Windows PowerShell)
# Usage:  .\scripts\start_demo.ps1
#         .\scripts\start_demo.ps1 -Docker
#         .\scripts\start_demo.ps1 -SmokeOnly

param(
    [switch]$Docker,
    [switch]$SmokeOnly,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "== MingMirror demo ==" -ForegroundColor Cyan
Write-Host "Root: $Root"

# Offline structure smoke (no server required)
Write-Host "`n[1/3] Structure smoke (demo charts + packages)..." -ForegroundColor Yellow
python scripts/demo_smoke.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($SmokeOnly) {
    Write-Host "`nSmoke-only done." -ForegroundColor Green
    exit 0
}

if ($Docker) {
    Write-Host "`n[2/3] Docker compose up --build..." -ForegroundColor Yellow
    docker compose up --build -d
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "`n[3/3] Open UI" -ForegroundColor Yellow
    $url = "http://localhost:$Port/app/"
    Write-Host "  Product UI : $url"
    Write-Host "  Health     : http://localhost:$Port/api/v1/health"
    Write-Host "  Demo charts: http://localhost:$Port/api/v1/product/demo-charts"
    Write-Host "  Pricing code: demo-pro (full plan demo)"
    Start-Process $url
    exit 0
}

# Local server: build web if dist missing
Write-Host "`n[2/3] Frontend build (if needed)..." -ForegroundColor Yellow
if (-not (Test-Path "web\dist\index.html")) {
    Push-Location web
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
    Pop-Location
} else {
    Write-Host "  web/dist present, skip build"
}

Write-Host "`n[3/3] Start server on port $Port..." -ForegroundColor Yellow
Write-Host "  Product UI : http://127.0.0.1:$Port/app/"
Write-Host "  Demo charts: http://127.0.0.1:$Port/api/v1/product/demo-charts"
Write-Host "  Pricing code: demo-pro"
Write-Host "  Ctrl+C to stop`n"

$env:MINGMIRROR_DEMO_CODE = if ($env:MINGMIRROR_DEMO_CODE) { $env:MINGMIRROR_DEMO_CODE } else { "demo-pro" }
python run.py --serve --serve-host 127.0.0.1 --serve-port $Port
