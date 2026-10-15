<#
Serve OSRIP from this Windows laptop at https://osrip.project.com (or -Hostname) through
a named Cloudflare Tunnel (no open ports on the laptop or router).

Prerequisites (done by the owner of the parent domain, once):
  * the parent zone (project.com for osrip.project.com; osrip.com for project.osrip.com)
    is added to the owner's Cloudflare account and its name servers point to Cloudflare
    (the zone shows "Active" in the Cloudflare dashboard). project.com is currently served
    by GoDaddy name servers, so this needs that domain's owner;
  * backend\scripts\serve_public.py setup has been run (database osrip_public).

    powershell -ExecutionPolicy Bypass -File deploy\laptop_server.ps1 -Setup   # once
    powershell -ExecutionPolicy Bypass -File deploy\laptop_server.ps1          # start

-Setup opens a browser where the account owner approves cloudflared for the parent domain,
creates the tunnel "osrip-laptop" and adds the DNS record for $Hostname in
Cloudflare. Credentials stay in %USERPROFILE%\.cloudflared (never in the repository).
Starting runs the production-mode server (127.0.0.1:8090 only) and the tunnel; the
site is up only while this laptop is on, awake and both processes are running.
#>
param(
    [switch]$Setup,
    [string]$Hostname = "osrip.project.com",
    [string]$TunnelName = "osrip-laptop",
    [int]$Port = 8090,
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$cloudflared = Join-Path $env:LOCALAPPDATA "OSRIP-dev\tools\cloudflared.exe"
$cfDir = Join-Path $env:USERPROFILE ".cloudflared"
$config = Join-Path $cfDir "osrip-laptop.yml"
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $cloudflared)) { throw "cloudflared not found at $cloudflared" }

function Get-TunnelId {
    $json = & $cloudflared tunnel list --output json 2>$null | Out-String
    $t = ($json | ConvertFrom-Json) | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
    if ($t) { return $t.id } else { return $null }
}

if ($Setup) {
    if (-not (Test-Path (Join-Path $cfDir "cert.pem"))) {
        Write-Host "A browser window opens: sign in to Cloudflare and choose the parent domain of $Hostname to authorize this laptop."
        & $cloudflared tunnel login
        if ($LASTEXITCODE -ne 0) { throw "cloudflared login was not completed" }
    }
    $id = Get-TunnelId
    if (-not $id) {
        & $cloudflared tunnel create $TunnelName
        if ($LASTEXITCODE -ne 0) { throw "tunnel creation failed" }
        $id = Get-TunnelId
    }
    & $cloudflared tunnel route dns $TunnelName $Hostname
    if ($LASTEXITCODE -ne 0) { throw "DNS route failed: is the parent domain of $Hostname active in this Cloudflare account?" }
    @"
tunnel: $id
credentials-file: $(Join-Path $cfDir "$id.json")
protocol: http2
ingress:
  - hostname: $Hostname
    service: http://127.0.0.1:$Port
  - service: http_status:404
"@ | Set-Content -Path $config -Encoding ascii
    Write-Host "Setup complete: tunnel $TunnelName ($id) serves $Hostname. Start with: deploy\laptop_server.ps1"
    return
}

if (-not (Test-Path $config)) { throw "Run with -Setup first." }
$logs = Join-Path $env:LOCALAPPDATA "OSRIP-dev\logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$serveArgs = @((Join-Path $root "backend\scripts\serve_public.py"), "serve", "--url", "https://$Hostname", "--port", "$Port")
if ($SkipBuild) { $serveArgs += "--skip-build" }
$server = Start-Process -FilePath $python -ArgumentList $serveArgs -WorkingDirectory (Join-Path $root "backend") `
    -RedirectStandardOutput (Join-Path $logs "server.out.log") -RedirectStandardError (Join-Path $logs "server.err.log") -PassThru -WindowStyle Hidden
Write-Host "Server started (PID $($server.Id)); waiting for it to be ready..."
$ready = $false
for ($i = 0; $i -lt 90 -and -not $ready; $i++) {
    Start-Sleep -Seconds 2
    try { $ready = (Invoke-WebRequest "http://127.0.0.1:$Port/api/v1/health/ready" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { }
}
if (-not $ready) { throw "server did not become ready; see $logs" }
Write-Host "Tunnel starting: https://$Hostname (Ctrl+C stops the tunnel; stop the server with Stop-Process -Id $($server.Id))"
& $cloudflared tunnel --no-autoupdate --config $config run $TunnelName
