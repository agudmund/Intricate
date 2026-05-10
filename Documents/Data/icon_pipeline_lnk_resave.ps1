<#
.SYNOPSIS
Re-save Intricate.lnk shortcuts with the current canonical IconLocation.

.DESCRIPTION
Step 2 of the Brand Mark Refresh Chain documented in
Documents/Design/Icon Pipeline.md.

There are TWO live Intricate.lnk files that pin the brand-mark icon path,
not one:
  - C:\Users\thisg\Desktop\Intricate\Intricate.lnk
       (project-folder launcher — what File Explorer surfaces)
  - %AppData%\Microsoft\Internet Explorer\Quick Launch\User Pinned\
    TaskBar\Intricate.lnk
       (pinned-taskbar shortcut)

For each: load via WScript.Shell.CreateShortcut, set IconLocation to
the canonical path, call Save() to commit. Save() also bumps mtime,
which forces Explorer to re-read the IconLocation field on next shell
icon refresh — without this bump the per-file shell-icon cache keyed on
the old path persists indefinitely.

Idempotent — safe to run repeatedly. No admin elevation needed (HKCU
state only).

Originally extracted from inline operations performed on 2026-05-10
during the icons/ → icons/Stickers/ migration.
#>

[CmdletBinding()]
param(
    [string]$IconPath = "C:\Users\thisg\Desktop\Intricate\icons\Stickers\Intricate.ico",
    [int]$IconIndex   = 0,
    [string[]]$LnkPaths = @(
        "C:\Users\thisg\Desktop\Intricate\Intricate.lnk",
        "C:\Users\thisg\AppData\Roaming\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Intricate.lnk"
    )
)

$ws = New-Object -ComObject WScript.Shell
$newIcon = "$IconPath,$IconIndex"

foreach ($p in $LnkPaths) {
    if (-not (Test-Path $p)) {
        Write-Warning "  MISSING: $p — skipped"
        continue
    }
    $s = $ws.CreateShortcut($p)
    $oldIcon = $s.IconLocation
    $s.IconLocation = $newIcon
    $s.Save()
    Write-Output "UPDATED: $p"
    Write-Output "  was: $oldIcon"
    Write-Output "  now: $newIcon"
}

Write-Output ""
Write-Output "Verify (re-reading the saved values):"
foreach ($p in $LnkPaths) {
    if (-not (Test-Path $p)) { continue }
    $s = $ws.CreateShortcut($p)
    Write-Output "  $p  →  $($s.IconLocation)"
}
