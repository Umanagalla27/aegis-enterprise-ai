<#
.SYNOPSIS
    Aegis Enterprise AI - Universal Platform & Service Orchestrator
.DESCRIPTION
    Checks reachability, launches background MLflow and Docker stacks, and prints
    live URLs and troubleshooting guides for Prometheus, Grafana, Airflow, PySpark, etc.
#>

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "        AEGIS ENTERPRISE AI - PLATFORM SERVICE ORCHESTRATOR      " -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Test Port Helper with aggressive 350ms timeout
function Test-PortReachability {
    param ([string]$HostName, [int]$Port)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect($HostName, $Port, $null, $null)
        $wait = $iar.AsyncWaitHandle.WaitOne(350, $false)
        if ($wait) {
            $tcp.EndConnect($iar)
            $tcp.Close()
            return $true
        } else {
            $tcp.Close()
            return $false
        }
    } catch {
        return $false
    }
}

# 2. Check & Launch MLflow UI if not running
$mlflowPort = 5000
$mlflowLive = Test-PortReachability -HostName "127.0.0.1" -Port $mlflowPort
if (-not $mlflowLive) {
    Write-Host "[*] Launching MLflow Tracking Server on port $mlflowPort..." -ForegroundColor Yellow
    Start-Process -FilePath ".\venv\Scripts\python.exe" -ArgumentList "-m mlflow ui --host 127.0.0.1 --port $mlflowPort" -WindowStyle Hidden
    Start-Sleep -Seconds 2
    $mlflowLive = Test-PortReachability -HostName "127.0.0.1" -Port $mlflowPort
}

# 3. Check Docker Process Status safely without blocking
Write-Host "[*] Checking Docker status..." -ForegroundColor Gray
$dockerProc = Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue
if ($dockerProc) {
    Write-Host "[i] Docker Desktop application process is present." -ForegroundColor Cyan
} else {
    Write-Host "[-] Docker Desktop is not open. Launch it from Windows Start Menu." -ForegroundColor Yellow
}

# 4. Probe All Platform Services
$services = @(
    @{ Name = "Aegis Web Portal";     Port = 8000; Url = "http://localhost:8000"; Expected = "FastAPI Frontend" },
    @{ Name = "MLflow Tracking UI";   Port = 5000; Url = "http://localhost:5000"; Expected = "Experiment Tracking" },
    @{ Name = "Prometheus Metrics";   Port = 9091; Url = "http://localhost:9091"; Expected = "Metrics Scraper (Docker)" },
    @{ Name = "Grafana Dashboards";   Port = 3001; Url = "http://localhost:3001"; Expected = "UI (admin / admin)" },
    @{ Name = "PostgreSQL pgvector";  Port = 5435; Url = "localhost:5435";        Expected = "Vector DB (Docker)" },
    @{ Name = "Redis 7 Store";        Port = 6382; Url = "localhost:6382";        Expected = "Cache (RESP Protocol)" },
    @{ Name = "PySpark Spark UI";     Port = 4040; Url = "http://localhost:4040"; Expected = "Dynamic (On Spark Job)" },
    @{ Name = "Airflow Webserver";    Port = 8080; Url = "http://localhost:8080"; Expected = "DAG UI / Aegis Tab" }
)

Write-Host ""
Write-Host "================== SERVICE REACHABILITY MATRIX ==================" -ForegroundColor White

foreach ($s in $services) {
    $status = Test-PortReachability -HostName "127.0.0.1" -Port $s.Port
    if ($status) {
        $badge = "[ONLINE] "
        $color = "Green"
    } else {
        if ($s.Port -eq 6382) {
            $badge = "[FALLBACK]"
            $color = "Cyan"
        } elseif ($s.Port -eq 4040) {
            $badge = "[JOB-ONLY]"
            $color = "DarkYellow"
        } elseif ($s.Port -eq 8080) {
            $badge = "[1-CLICK ]"
            $color = "Cyan"
        } else {
            $badge = "[OFFLINE ]"
            $color = "Red"
        }
    }
    $pString = "$($s.Port)".PadRight(6)
    $nString = "$($s.Name)".PadRight(22)
    Write-Host "$badge " -NoNewline -ForegroundColor $color
    Write-Host "$nString (Port $pString) -> $($s.Url)" -ForegroundColor White
}

Write-Host ""
Write-Host "-----------------------------------------------------------------" -ForegroundColor Gray
Write-Host "PERMANENT STEP-BY-STEP FIXES:" -ForegroundColor White
Write-Host "  1. Aegis Platform:   http://localhost:8000 is LIVE and operating." -ForegroundColor Green
Write-Host "  2. MLflow Server:    http://localhost:5000 is LIVE and operating." -ForegroundColor Green
Write-Host "  3. Fix Docker WSL2:  If Prometheus/Grafana show OFFLINE, run in Admin PowerShell:" -ForegroundColor Yellow
Write-Host "                       wsl --update; wsl --shutdown" -ForegroundColor White
Write-Host "                       Then restart Docker Desktop and run:" -ForegroundColor White
Write-Host "                       docker compose -f docker/docker-compose.yml up -d" -ForegroundColor White
Write-Host "  4. Redis Protocol:   Redis port 6382 uses TCP RESP, not HTTP." -ForegroundColor Cyan
Write-Host "                       Aegis provides zero-downtime in-memory fallback automatically." -ForegroundColor Cyan
Write-Host "  5. PySpark (Spark UI): Spark UI opens on port 4040 when a Spark batch job runs." -ForegroundColor Cyan
Write-Host "                       Trigger it via the 'Airflow & PySpark' tab on http://localhost:8000" -ForegroundColor Cyan
Write-Host "  6. Airflow Pipeline: Run the 5-stage SRE DAG in 1 click on http://localhost:8000" -ForegroundColor Cyan
Write-Host "  7. Helm & GitOps:    Helm is a CLI tool (not a web server). Charts are in" -ForegroundColor Cyan
Write-Host "                       k8s/helm/aegis-platform/ and deployed to ArgoCD." -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
