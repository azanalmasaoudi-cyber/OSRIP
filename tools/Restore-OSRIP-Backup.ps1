<#
.SYNOPSIS
Restore an OSRIP backup into a NEW local database and prove it matches the original.

.DESCRIPTION
For moving OSRIP to another Windows computer, or a restore drill on this one. The development
PostgreSQL must be running (start OSRIP once, or backend\.venv\Scripts\python.exe
backend\scripts\devdb.py start).

  powershell -ExecutionPolicy Bypass -File .\tools\Restore-OSRIP-Backup.ps1 -Backup <file.backup> -Database osrip_restored
  ... -Migrate     also apply this checkout's migrations to the restored copy afterwards

Never destructive:
  * the target database must NOT exist: an existing database (osrip_dev included) is never
    overwritten, cleaned or dropped; choose a new name;
  * the archive's SHA-256 must match its .backup.json manifest (written by
    Backup-OSRIP-Local.ps1) before anything is restored;
  * after the restore, the exact row count of every table is compared with the manifest;
    any difference is reported and the script exits with an error.

To run OSRIP on the restored copy, name it in this checkout's .osrip-local.json
({"database": "osrip_restored"}) or, once it is verified and only with the owner's decision,
use it in place of osrip_dev. On a server, restore into the server's own empty database with
the same pg_restore options (see docs/CENTRAL_HOSTING_EN.md).
#>
param(
    [Parameter(Mandatory = $true)][string]$Backup,
    [Parameter(Mandatory = $true)][string]$Database,
    [switch]$Migrate
)
$ErrorActionPreference = 'Stop'

function Find-DevHome {
    if ($env:OSRIP_DEV_HOME) { return $env:OSRIP_DEV_HOME }
    if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is not available.' }
    $default = Join-Path $env:LOCALAPPDATA 'OSRIP-dev'
    if (Test-Path (Join-Path $default 'pgdata')) { return $default }
    $found = @(Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Packages') -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'LocalCache\Local\OSRIP-dev' } |
        Where-Object { Test-Path (Join-Path $_ 'pgdata') })
    if ($found.Count -eq 1) { return $found[0] }
    if ($found.Count -gt 1) { throw 'Several development clusters found. Set OSRIP_DEV_HOME.' }
    throw 'No OSRIP development PostgreSQL cluster found. Start OSRIP once on this computer first (it creates one).'
}

if ($Database -notmatch '^[a-z_][a-z0-9_]{0,62}$') { throw 'Database name: lower-case letters, digits and _ only.' }
$Backup = (Resolve-Path $Backup).Path
$manifestPath = "$Backup.json"
if (-not (Test-Path $manifestPath)) { throw "No manifest $($manifestPath). Restore only a backup made by Backup-OSRIP-Local.ps1, or check it by hand." }
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$hash = (Get-FileHash $Backup -Algorithm SHA256).Hash.ToLowerInvariant()
if ($hash -ne $manifest.sha256) { throw 'The backup does not match its manifest (SHA-256 differs): it is damaged or not the same file. Nothing was restored.' }
Write-Host "Backup checked: SHA-256 matches the manifest ($($manifest.tables) tables, migration $($manifest.migration))."

$devHome = Find-DevHome
$pgbin = if ($env:OSRIP_PG_BIN) { $env:OSRIP_PG_BIN } else { Join-Path $devHome 'pgsql\bin' }
$restore = Join-Path $pgbin 'pg_restore.exe'
$psql = Join-Path $pgbin 'psql.exe'
$pwfile = Join-Path $devHome 'superuser-password.txt'
$port = if ($env:OSRIP_DEV_PG_PORT) { $env:OSRIP_DEV_PG_PORT } else { '55432' }
foreach ($tool in @($restore, $psql)) { if (-not (Test-Path $tool)) { throw "$tool not found (set OSRIP_PG_BIN)." } }
if (-not (Test-Path $pwfile)) { throw 'The local PostgreSQL password file was not found.' }

$countSql = @"
SELECT table_name || '|' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text
FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name
"@

$priorPgPassword = [Environment]::GetEnvironmentVariable('PGPASSWORD', 'Process')
try {
    $env:PGPASSWORD = (Get-Content $pwfile -Raw).Trim()
    $common = @('-h', '127.0.0.1', '-p', $port, '-U', 'postgres')
    $exists = & $psql @common -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$Database'"
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL is not reachable. Start the development database first.' }
    if ("$exists".Trim() -eq '1') { throw "A database named $Database already exists. It is never overwritten: choose a new name." }

    Write-Host "Creating the new database $Database ..."
    & $psql @common -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $Database" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the database.' }
    Write-Host 'Restoring (no owners, no privileges; never --clean) ...'
    & $restore @common -d $Database --no-owner --no-acl --exit-on-error $Backup
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed. The new database $Database is incomplete: inspect it, then drop it yourself if it is not wanted." }

    $differences = @()
    $restored = [ordered]@{}
    foreach ($line in @(& $psql @common -d $Database -tAc $countSql)) {
        if ($line -match '^([^|]+)\|(\d+)$') { $restored[$Matches[1]] = [int64]$Matches[2] }
    }
    foreach ($p in $manifest.rows.PSObject.Properties) {
        $got = if ($restored.Contains($p.Name)) { $restored[$p.Name] } else { $null }
        if ($got -ne [int64]$p.Value) { $differences += "$($p.Name): backup $($p.Value), restored $got" }
    }
    foreach ($name in $restored.Keys) { if (-not $manifest.rows.PSObject.Properties[$name]) { $differences += "$($name): not in the backup" } }
    $migration = "$(& $psql @common -d $Database -tAc 'SELECT version_num FROM alembic_version')".Trim()
    if ($migration -ne $manifest.migration) { $differences += "migration: backup $($manifest.migration), restored $migration" }
    if ($differences.Count) {
        $differences | ForEach-Object { Write-Host "  DIFFERENT $_" }
        throw "The restored copy does not match the backup ($($differences.Count) differences)."
    }
    $total = ($restored.Values | Measure-Object -Sum).Sum
    Write-Host "Restore verified: $Database has the same $($restored.Count) tables and $total rows as the backup (migration $migration)."

    if ($Migrate) {
        $root = Split-Path -Parent $PSScriptRoot
        $python = Join-Path $root 'backend\.venv\Scripts\python.exe'
        if (-not (Test-Path $python)) { throw "No backend environment at $python; migrate later with the launcher." }
        $url = "$(& $python (Join-Path $root 'backend\scripts\devdb.py') url $Database)".Trim()
        Write-Host "Applying this checkout's migrations to $Database (forward only) ..."
        $priorUrl = $env:OSRIP_DATABASE_URL
        try {
            $env:OSRIP_DATABASE_URL = $url
            Push-Location (Join-Path $root 'backend')
            & $python -m alembic upgrade head
            if ($LASTEXITCODE -ne 0) { throw 'The migrations failed on the restored copy.' }
        } finally {
            Pop-Location
            if ($null -ne $priorUrl) { $env:OSRIP_DATABASE_URL = $priorUrl } else { Remove-Item Env:\OSRIP_DATABASE_URL -ErrorAction SilentlyContinue }
        }
        $after = "$(& $psql @common -d $Database -tAc 'SELECT version_num FROM alembic_version')".Trim()
        Write-Host "Migrated: $migration -> $after"
    }
    Write-Host "To run OSRIP on it, put {""database"": ""$Database""} in this checkout's .osrip-local.json."
} finally {
    if ($null -ne $priorPgPassword) { $env:PGPASSWORD = $priorPgPassword }
    else { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue }
}
