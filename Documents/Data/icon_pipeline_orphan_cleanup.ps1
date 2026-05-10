<#
.SYNOPSIS
Clean up orphaned NotifyIconSettings entries (apps that no longer exist on disk).

.DESCRIPTION
The Personalization > Taskbar "Other system tray icons" panel filters out
entries whose ExecutablePath doesn't exist on disk anymore, but Windows
doesn't auto-prune them from the registry. They accumulate over time as
apps update (changing install paths), get uninstalled, or arrive then
get removed (UUS preview packages, retired Microsoft Store app versions).

This script:
  1. Enumerates HKCU\Control Panel\NotifyIconSettings\
  2. Resolves KNOWNFOLDERID GUID prefixes (e.g. {F38BF404-...} = Windows
     directory; {7C5A40EF-...} = Program Files (x86)) to actual paths
  3. Identifies entries whose ExecutablePath no longer exists on disk
  4. In PREVIEW mode (default): lists what would be removed
  5. With -Apply: backs them up to a combined .reg file, then deletes

Run without arguments first to see what would be touched. Pass -Apply
to actually delete.

Idempotent. No admin elevation needed (HKCU only).

Originally extracted from inline operations performed on 2026-05-10,
which removed 4 orphans: an old UUS Notification preview package, two
retired Copilot Microsoft Store versions, and an uninstalled-McAfee
leftover from the OS-default install.
#>

[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$BackupDir = "C:\Users\thisg\Desktop\Intricate\Documents\Data"
)

$nis = "HKCU:\Control Panel\NotifyIconSettings"
$orphans = @()

# KNOWNFOLDERID GUID resolution table — the most common prefixes that appear
# in NotifyIconSettings ExecutablePath values
$kfidMap = @{
    "F38BF404-1D43-42F2-9305-67DE0B28FC23" = $env:windir                    # FOLDERID_Windows
    "6D809377-6AF0-444B-8957-A3773F02200E" = $env:ProgramFiles              # FOLDERID_ProgramFilesX64
    "7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E" = ${env:ProgramFiles(x86)}       # FOLDERID_ProgramFilesX86
    "1AC14E77-02E7-4E5D-B744-2EB1AE5198B7" = "$env:windir\System32"         # FOLDERID_System
}

Write-Output "Scanning NotifyIconSettings for orphaned entries..."
Get-ChildItem $nis -ErrorAction SilentlyContinue | ForEach-Object {
    $v = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if (-not $v.ExecutablePath) { return }

    $exe = $v.ExecutablePath
    $resolved = $exe
    if ($exe -match '^\{([0-9A-F-]+)\}\\(.+)$') {
        $kfid = $matches[1]
        $rest = $matches[2]
        if ($kfidMap.ContainsKey($kfid)) {
            $resolved = Join-Path $kfidMap[$kfid] $rest
        }
    }

    if (-not (Test-Path $resolved -ErrorAction SilentlyContinue)) {
        $orphans += $_
        $short = if ($exe.Length -gt 80) { "..." + $exe.Substring($exe.Length - 80) } else { $exe }
        Write-Output "  ORPHAN: $($_.PSChildName)  $short"
    }
}

Write-Output ""
Write-Output "Found $($orphans.Count) orphaned entries"

if ($orphans.Count -eq 0) {
    Write-Output "Nothing to do."
    return
}

if (-not $Apply) {
    Write-Output ""
    Write-Output "PREVIEW mode. Re-run with -Apply to delete."
    return
}

# ── Backup ─────────────────────────────────────────────────────────
$ts = Get-Date -Format "yyyy-MM-dd"
$backupPath = Join-Path $BackupDir "notifyicon_orphans_backup_$ts.reg"
Write-Output ""
Write-Output "Backing up to $backupPath..."
$tempFiles = @()
foreach ($t in $orphans) {
    $tmp = "$env:TEMP\orphan_$($t.PSChildName).reg"
    reg export "HKCU\Control Panel\NotifyIconSettings\$($t.PSChildName)" $tmp /y 2>&1 | Out-Null
    if (Test-Path $tmp) { $tempFiles += $tmp }
}
if ($tempFiles) {
    Get-Content $tempFiles | Set-Content $backupPath -Encoding Unicode
    Remove-Item $tempFiles -ErrorAction SilentlyContinue
    Write-Output "  backup: $((Get-Item $backupPath).Length) bytes"
}

# ── Delete ────────────────────────────────────────────────────────
Write-Output ""
Write-Output "Deleting orphans..."
foreach ($t in $orphans) {
    Remove-Item $t.PSPath -Force -Recurse
    Write-Output "  removed: $($t.PSChildName)"
}
