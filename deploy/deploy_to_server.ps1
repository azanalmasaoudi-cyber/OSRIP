<#
Deploy OSRIP from this Windows machine to a server prepared with bootstrap_server.sh.

    powershell -ExecutionPolicy Bypass -File deploy\deploy_to_server.ps1 -Server <IPv4> [-Bootstrap]

  -Server     the server's public IPv4 address
  -Bootstrap  run bootstrap_server.sh first (fresh server only)
  -User       SSH user (default root)
  -Key        private key (default %USERPROFILE%\.ssh\osrip_deploy)

It checks deploy/.env with predeploy_check.py, confirms the DNS name in OSRIP_DOMAIN
points at the server (needed for the HTTPS certificate), copies the source without
secrets or build output, copies deploy/.env separately (mode 600), starts the stack and
finally probes the public https:// address.
#>
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [string]$User = "root",
    [string]$Key = "$env:USERPROFILE\.ssh\osrip_deploy",
    [switch]$Bootstrap
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$envFile = Join-Path $root "deploy\.env"
$ssh = @("-i", $Key, "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15")
$target = "$User@$Server"

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

Step "Checking deploy/.env"
& $python (Join-Path $root "deploy\predeploy_check.py") --env $envFile
if ($LASTEXITCODE -ne 0) { throw "predeploy_check failed; fix deploy/.env first" }
$domain = (Select-String -Path $envFile -Pattern '^OSRIP_DOMAIN=(.+)$').Matches[0].Groups[1].Value.Trim()

Step "Checking that $domain points at $Server"
$resolved = @()
try { $resolved = (Resolve-DnsName $domain -Type A -Server 1.1.1.1 -ErrorAction Stop | Where-Object { $_.IPAddress }).IPAddress } catch { }
if ($resolved -notcontains $Server) {
    throw "$domain resolves to '$($resolved -join ', ')', not $Server. Add the A record at your DNS provider, wait a few minutes, then run again."
}

if ($Bootstrap) {
    Step "Preparing the server (Docker, firewall, swap)"
    Get-Content (Join-Path $root "deploy\bootstrap_server.sh") -Raw | & ssh @ssh $target "tr -d '\r' | sh"
    if ($LASTEXITCODE -ne 0) { throw "bootstrap failed" }
}

Step "Packing the source (no secrets, no build output)"
$archive = Join-Path $env:TEMP "osrip-deploy.tgz"
if (Test-Path $archive) { Remove-Item $archive -Force -Confirm:$false }
Push-Location $root
try {
    & tar -czf $archive `
        --exclude=node_modules --exclude=.venv --exclude=dist --exclude=__pycache__ `
        --exclude=.pytest_cache --exclude=.ruff_cache --exclude=test-results --exclude=playwright-report `
        --exclude=.claude --exclude=.vs --exclude=.vscode --exclude=./OSRIP --exclude=./docs `
        --exclude=.env --exclude=".env.local" --exclude="*.log" `
        backend frontend deploy .dockerignore
    if ($LASTEXITCODE -ne 0) { throw "tar failed" }
} finally { Pop-Location }

Step "Copying to $target"
& ssh @ssh $target "mkdir -p /opt/osrip/src"
& scp @ssh $archive "${target}:/opt/osrip/osrip.tgz"
& scp @ssh $envFile "${target}:/opt/osrip/src/deploy/.env"
& ssh @ssh $target "tar -xzf /opt/osrip/osrip.tgz -C /opt/osrip/src && rm /opt/osrip/osrip.tgz && chmod 600 /opt/osrip/src/deploy/.env && find /opt/osrip/src/deploy -name '*.sh' -exec sed -i 's/\r$//' {} +"
if ($LASTEXITCODE -ne 0) { throw "copy failed" }
Remove-Item $archive -Force -Confirm:$false

Step "Building and starting (first run downloads images and can take several minutes)"
& ssh @ssh $target "sh /opt/osrip/src/deploy/remote_up.sh"
if ($LASTEXITCODE -ne 0) { throw "remote start failed (logs above)" }

Step "Probing https://$domain"
Start-Sleep -Seconds 10
& $python (Join-Path $root "deploy\predeploy_check.py") --env $envFile --url "https://$domain"
