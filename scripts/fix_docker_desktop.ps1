<#
.SYNOPSIS
    Aegis Enterprise AI - Docker Desktop Reset & Relaunch Script
.DESCRIPTION
    Kills deadlocked elevated Docker Desktop backend processes, restarts WSL2,
    launches a fresh Docker Desktop instance, and brings up the compose stack.
    MUST BE RUN AS ADMINISTRATOR.
#>

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "==========================================================" -ForegroundColor Red
    Write-Host "[!] ELEVATION REQUIRED: Please run this script as Admin." -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Red
    Write-Host "Steps to run as Administrator:" -ForegroundColor White
    Write-Host "  1. Right-click Windows Start Menu -> select 'Terminal (Admin)' or 'PowerShell (Admin)'" -ForegroundColor Cyan
    Write-Host "  2. Run the command:" -ForegroundColor Cyan
    Write-Host "     cd c:\Users\nagal\aegis-enterprise-ai" -ForegroundColor White
    Write-Host "     powershell -ExecutionPolicy Bypass -File scripts\fix_docker_desktop.ps1" -ForegroundColor White
    Write-Host "==========================================================" -ForegroundColor Red
    return
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       AEGIS - DOCKER DESKTOP RESET & RELAUNCH SCRIPT     " -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan

Write-Host "[1/4] Force-terminating deadlocked Docker backend processes..." -ForegroundColor Yellow
taskkill /F /IM "Docker Desktop.exe" /IM "com.docker.backend.exe" /IM "com.docker.build.exe" /IM "docker-agent.exe" /IM "docker-sandbox.exe" /IM "docker.exe" 2>$null

Write-Host "[2/4] Resetting WSL2 subsystem cleanly..." -ForegroundColor Yellow
wsl --shutdown

Start-Sleep -Seconds 2

Write-Host "[3/4] Launching clean Docker Desktop instance..." -ForegroundColor Yellow
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

Write-Host "[4/4] Waiting 25 seconds for Docker engine daemon to initialize..." -ForegroundColor Cyan
for ($i = 25; $i -gt 0; $i--) {
    Write-Progress -Activity "Initializing Docker Engine Daemon" -Status "Seconds remaining: $i" -PercentComplete ((25 - $i) / 25 * 100)
    Start-Sleep -Seconds 1
}
Write-Progress -Activity "Initializing Docker Engine Daemon" -Completed

Write-Host "[*] Testing Docker Engine connectivity..." -ForegroundColor Gray
$dockerCheck = docker info 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "[+] SUCCESS: Docker Engine is ONLINE and healthy!" -ForegroundColor Green
    Write-Host "[*] Starting Aegis containers (Prometheus, Grafana, Redis, Postgres)..." -ForegroundColor Cyan
    docker compose -f docker/docker-compose.yml up -d
    Write-Host ""
    Write-Host "[+] All containers are up! Open http://localhost:8000 to view your portal." -ForegroundColor Green
} else {
    Write-Host "[!] Docker Desktop is still booting up in the background." -ForegroundColor Yellow
    Write-Host "    Please wait another 15-20 seconds for the engine whale icon to turn green," -ForegroundColor Yellow
    Write-Host "    then run in project root:" -ForegroundColor Yellow
    Write-Host "    docker compose -f docker/docker-compose.yml up -d" -ForegroundColor White
}

Write-Host "==========================================================" -ForegroundColor Cyan
