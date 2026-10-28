<#
.SYNOPSIS
    CookHero PostgreSQL backup / restore helper.

.DESCRIPTION
    Creates a compressed custom-format dump of the CookHero database inside the
    running PostgreSQL container, stores it on the host, and prunes old files.

    The script is safe to run repeatedly and is designed for Task Scheduler.

.PARAMETER OutDir
    Destination folder on the host. Defaults to <repo>\backups.

.PARAMETER RetentionDays
    Delete dumps older than this many days. Default 14. Use 0 to keep forever.

.PARAMETER Restore
    Path to a .dump file. Restores it into the live database (DESTRUCTIVE:
    existing objects are dropped first).

.PARAMETER Install
    Registers a Windows scheduled task that runs the backup daily at 03:00.

.PARAMETER Uninstall
    Removes the scheduled task.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\backup-db.ps1
    powershell -ExecutionPolicy Bypass -File scripts\backup-db.ps1 -Install
    powershell -ExecutionPolicy Bypass -File scripts\backup-db.ps1 -Restore backups\cookhero_20261026_030000.dump
#>

param(
    [string]$OutDir,
    [int]$RetentionDays = 14,
    [string]$Restore,
    [switch]$Install,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$TaskName = 'CookHero - Database Backup'
$Container = 'cookhero_postgres'
$DbUser = 'cookhero'
$DbName = 'cookhero'

# ---- Locate repo root (app\main.py + config.yml + frontend\package.json) ----
function Find-RepoRoot([string]$startDir) {
    $dir = $startDir
    for ($i = 0; $i -lt 10; $i++) {
        if (-not $dir) { break }
        if ((Test-Path (Join-Path $dir 'app\main.py')) -and
            (Test-Path (Join-Path $dir 'config.yml')) -and
            (Test-Path (Join-Path $dir 'frontend\package.json'))) {
            return (Resolve-Path $dir).Path
        }
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    return $null
}

$Root = Find-RepoRoot (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Root) { $Root = Find-RepoRoot (Get-Location).Path }
if (-not $Root) {
    Write-Host 'ERROR: CookHero repository root not found.' -ForegroundColor Red
    exit 1
}

if (-not $OutDir) { $OutDir = Join-Path $Root 'backups' }
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
$LogFile = Join-Path $OutDir 'backup.log'

function Write-Log([string]$Message, [string]$Level = 'INFO') {
    $line = '{0} [{1}] {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Test-ContainerRunning {
    $state = (docker inspect -f '{{.State.Running}}' $Container 2>$null)
    return ($state -eq 'true')
}

# ---- Uninstall scheduled task ----
if ($Uninstall) {
    schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Scheduled task removed: $TaskName"
    } else {
        Write-Log "Scheduled task not found: $TaskName" 'WARN'
    }
    exit 0
}

# ---- Install scheduled task (daily 03:00) ----
if ($Install) {
    $scriptPath = $MyInvocation.MyCommand.Path
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -RetentionDays $RetentionDays"
    $action = "powershell.exe $args"
    schtasks /Create /SC DAILY /ST 03:00 /TN $TaskName /TR $action /F | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Log "Scheduled task installed: $TaskName (daily 03:00)"
        Write-Log "Verify with: schtasks /Query /TN `"$TaskName`""
    } else {
        Write-Log 'Failed to install scheduled task.' 'ERROR'
        exit 1
    }
    exit 0
}

# ---- Restore mode ----
if ($Restore) {
    $file = if (Test-Path $Restore) { (Resolve-Path $Restore).Path } else { Join-Path $OutDir $Restore }
    if (-not (Test-Path $file)) {
        Write-Log "Backup file not found: $Restore" 'ERROR'
        exit 1
    }
    if (-not (Test-ContainerRunning)) {
        Write-Log 'PostgreSQL container is not running. Start Docker first.' 'ERROR'
        exit 1
    }

    Write-Log "RESTORE from $file - this drops existing objects in '$DbName'."
    $remote = '/tmp/cookhero_restore.dump'
    docker cp $file "${Container}:$remote" | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Log 'docker cp failed.' 'ERROR'; exit 1 }

    docker exec $Container pg_restore -U $DbUser -d $DbName --clean --if-exists --no-owner --no-acl -j 4 $remote
    $code = $LASTEXITCODE
    docker exec $Container rm -f $remote | Out-Null

    if ($code -eq 0) {
        Write-Log 'Restore completed successfully.'
    } else {
        # pg_restore returns non-zero on benign warnings (e.g. missing extensions)
        Write-Log "Restore finished with exit code $code - review the output above." 'WARN'
    }
    exit $code
}

# ---- Backup mode ----
if (-not (Test-ContainerRunning)) {
    Write-Log 'PostgreSQL container is not running. Start Docker first.' 'ERROR'
    exit 1
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$fileName = "cookhero_$stamp.dump"
$hostPath = Join-Path $OutDir $fileName
$remotePath = "/tmp/$fileName"

Write-Log "Backup started -> $hostPath"

# Custom format is compressed already; -Z 9 squeezes it further.
docker exec $Container pg_dump -U $DbUser -d $DbName --format=custom --compress=9 --file=$remotePath
if ($LASTEXITCODE -ne 0) {
    Write-Log 'pg_dump failed.' 'ERROR'
    exit 1
}

docker cp "${Container}:$remotePath" $hostPath | Out-Null
$copyCode = $LASTEXITCODE
docker exec $Container rm -f $remotePath | Out-Null

if ($copyCode -ne 0 -or -not (Test-Path $hostPath)) {
    Write-Log 'Failed to copy dump from container to host.' 'ERROR'
    exit 1
}

$sizeMb = [math]::Round((Get-Item $hostPath).Length / 1MB, 2)
Write-Log "Backup finished: $fileName ($sizeMb MB)"

# Sanity check: the archive must be readable.
docker cp $hostPath "${Container}:/tmp/verify.dump" | Out-Null
docker exec $Container pg_restore --list /tmp/verify.dump > $null 2>&1
$verifyCode = $LASTEXITCODE
docker exec $Container rm -f /tmp/verify.dump | Out-Null
if ($verifyCode -ne 0) {
    Write-Log "Backup verification FAILED - $fileName may be corrupt." 'ERROR'
    exit 1
}
Write-Log 'Backup verified (pg_restore --list OK).'

# ---- Retention ----
if ($RetentionDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$RetentionDays)
    $stale = Get-ChildItem -Path $OutDir -Filter 'cookhero_*.dump' |
        Where-Object { $_.LastWriteTime -lt $cutoff }
    foreach ($item in $stale) {
        Remove-Item $item.FullName -Force
        Write-Log "Pruned old backup: $($item.Name)"
    }
    Write-Log "Retention applied: keep $RetentionDays day(s), removed $($stale.Count) file(s)."
}
