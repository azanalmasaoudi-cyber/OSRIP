<#
.SYNOPSIS
Back up OSRIP's local development database without changing it, and verify the backup.

.DESCRIPTION
Run on the computer that holds the data, with the development PostgreSQL running (start OSRIP
once, or: backend\.venv\Scripts\python.exe backend\scripts\devdb.py start).

  powershell -ExecutionPolicy Bypass -File .\tools\Backup-OSRIP-Local.ps1
  ... -Database osrip_preview -Destination D:\Private\OSRIP-Backups

It finds the development cluster (OSRIP-dev in LOCALAPPDATA, or the single copy in a packaged
app's virtualised AppData), reads the local superuser password from its file without printing
it, and runs pg_dump (custom format, no owners or privileges). The database is only read.

Verification, before it reports success:
  * pg_restore can read the archive's table of contents;
  * the SHA-256 of the file is recorded;
  * the exact row count of every table and the migration version are taken from the database,
    so a restore can be compared with them (Restore-OSRIP-Backup.ps1 does).

It writes <database>-<yyyyMMdd-HHmmss>.backup and a .backup.json manifest beside it (counts,
hash, versions; no secrets). It refuses a destination inside a git working tree, so a backup is
never committed by accident, and never overwrites a file.

A backup holds accounts, password hashes and every record: keep it private and encrypted, and
never upload it to GitHub or a chat.
#>
param(
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'OSRIP-Backups'),
    [string]$Database = 'osrip_dev'
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
    if ($found.Count -gt 1) { throw 'Several development clusters found. Set OSRIP_DEV_HOME to the one to back up.' }
    throw 'No OSRIP development PostgreSQL cluster found. Start OSRIP once on this computer first.'
}

function Test-InsideGitWorkTree([string]$Path) {
    $dir = [System.IO.DirectoryInfo]::new([System.IO.Path]::GetFullPath($Path))
    while ($null -ne $dir) {
        if (Test-Path (Join-Path $dir.FullName '.git')) { return $true }
        $dir = $dir.Parent
    }
    return $false
}

if ($env:OSRIP_DATABASE_URL) {
    throw 'OSRIP_DATABASE_URL is set: this script backs up the local development cluster only. Clear it, or back up that database with its own tools.'
}
if ($Database -notmatch '^[a-z_][a-z0-9_]{0,62}$') { throw 'Database name: lower-case letters, digits and _ only.' }
if (Test-InsideGitWorkTree $Destination) {
    throw "The destination $Destination is inside a git working tree; a backup must never be committed. Choose a private folder outside the repository."
}

$devHome = Find-DevHome
$pgbin = if ($env:OSRIP_PG_BIN) { $env:OSRIP_PG_BIN } else { Join-Path $devHome 'pgsql\bin' }
$dump = Join-Path $pgbin 'pg_dump.exe'
$restore = Join-Path $pgbin 'pg_restore.exe'
$psql = Join-Path $pgbin 'psql.exe'
$pwfile = Join-Path $devHome 'superuser-password.txt'
$port = if ($env:OSRIP_DEV_PG_PORT) { $env:OSRIP_DEV_PG_PORT } else { '55432' }
foreach ($tool in @($dump, $restore, $psql)) { if (-not (Test-Path $tool)) { throw "$tool not found (set OSRIP_PG_BIN)." } }
if (-not (Test-Path $pwfile)) { throw 'The local PostgreSQL password file was not found.' }
if ($port -notmatch '^\d+$') { throw 'Invalid PostgreSQL port.' }

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $Destination "$Database-$stamp.backup"
$manifestPath = "$target.json"
if ((Test-Path $target) -or (Test-Path $manifestPath)) { throw 'A backup with this name exists; refusing to overwrite.' }

# Exact counts of every table, read-only (one query; no table is locked beyond a normal read).
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
    if ("$exists".Trim() -ne '1') { throw "There is no database named $Database." }

    Write-Host "Counting the rows of $Database ..."
    $countLines = @(& $psql @common -d $Database -tAc $countSql)
    if ($LASTEXITCODE -ne 0) { throw 'Could not count the tables; nothing was backed up.' }
    $counts = [ordered]@{}
    foreach ($line in $countLines) { if ($line -match '^([^|]+)\|(\d+)$') { $counts[$Matches[1]] = [int64]$Matches[2] } }
    $migration = "$(& $psql @common -d $Database -tAc 'SELECT version_num FROM alembic_version')".Trim()

    Write-Host "Backing up $Database at 127.0.0.1:$port (read only) ..."
    & $dump @common -d $Database --format=custom --no-owner --no-acl --file=$target
    if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed; there is no verified backup.' }
    $info = Get-Item $target
    if ($info.Length -lt 4096) { throw 'The backup file is unexpectedly small.' }
    $toc = @(& $restore --list $target)
    if ($LASTEXITCODE -ne 0) { throw 'pg_restore could not read the archive.' }
    $tablesInArchive = @($toc | Where-Object { $_ -match ' TABLE DATA public ' }).Count
    if ($tablesInArchive -lt $counts.Count) { throw "The archive holds data for $tablesInArchive tables; the database has $($counts.Count)." }
    $hash = (Get-FileHash $target -Algorithm SHA256).Hash.ToLowerInvariant()

    $manifest = [ordered]@{
        database = $Database
        created = (Get-Date).ToString('s')
        file = $info.Name
        bytes = $info.Length
        sha256 = $hash
        migration = $migration
        pg_dump = "$(& $dump --version)".Trim()
        tables = $counts.Count
        rows = $counts
    }
    $manifest | ConvertTo-Json -Depth 4 | Out-File -FilePath $manifestPath -Encoding utf8
    $total = ($counts.Values | Measure-Object -Sum).Sum
    Write-Host "Backup verified: $target"
    Write-Host "  $($info.Length) bytes, SHA-256 $hash"
    Write-Host "  $($counts.Count) tables, $total rows, migration $migration"
    Write-Host "  Manifest: $manifestPath"
    Write-Host 'Keep it private and encrypted: it includes accounts and password hashes. Never upload it to GitHub.'
} finally {
    if ($null -ne $priorPgPassword) { $env:PGPASSWORD = $priorPgPassword }
    else { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue }
}
