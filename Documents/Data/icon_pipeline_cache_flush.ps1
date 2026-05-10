<#
.SYNOPSIS
Wipe Windows shell icon caches and restart Explorer.

.DESCRIPTION
Step 4 of the Brand Mark Refresh Chain documented in
Documents/Design/Icon Pipeline.md.

Procedure:
  1. Stop explorer.exe (releases the cache file handles so they can be
     deleted)
  2. Delete every iconcache_*.db and thumbcache_*.db under
     %LocalAppData%\Microsoft\Windows\Explorer\
  3. Delete legacy %LocalAppData%\IconCache.db if present
     (Win7/XP-era; modern Win11 does not generate it — conditional)
  4. Restart explorer.exe

The cache files hold rendered-pixel snapshots keyed by file path; they
don't refresh on icon-content change unless the .db files are deleted.
Icon paths can be updated everywhere else but the rendered cache will
keep showing old pixels until this flush runs.

Run after Step 2 (.lnk re-save) and any HKCU registry updates that
change icon paths. Explorer will be down for ~1-2 seconds and respawn
automatically; iconcache files rebuild immediately on restart, thumbcache
files repopulate lazily as folders are browsed.

Visible side effect: all open File Explorer windows close when explorer.exe
is stopped. Save unsaved Explorer state (column-width adjustments etc.)
before running.

Originally extracted from inline operations performed on 2026-05-10.
#>

$explorerCache = "$env:LOCALAPPDATA\Microsoft\Windows\Explorer"
$legacyCache   = "$env:LOCALAPPDATA\IconCache.db"

Write-Output "1. Stopping explorer.exe..."
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Output "2. Deleting iconcache_*.db..."
$iconDeleted = 0
Get-ChildItem -Path $explorerCache -Filter "iconcache_*.db" -ErrorAction SilentlyContinue | ForEach-Object {
    try { Remove-Item $_.FullName -Force -ErrorAction Stop; $iconDeleted++ }
    catch { Write-Output "   FAILED: $($_.Name) — $($_.Exception.Message)" }
}
Write-Output "   deleted $iconDeleted iconcache files"

Write-Output "3. Deleting thumbcache_*.db..."
$thumbDeleted = 0
Get-ChildItem -Path $explorerCache -Filter "thumbcache_*.db" -ErrorAction SilentlyContinue | ForEach-Object {
    try { Remove-Item $_.FullName -Force -ErrorAction Stop; $thumbDeleted++ }
    catch { Write-Output "   FAILED: $($_.Name) — $($_.Exception.Message)" }
}
Write-Output "   deleted $thumbDeleted thumbcache files"

Write-Output "4. Legacy IconCache.db (Win7/XP-era)..."
if (Test-Path $legacyCache) {
    Remove-Item $legacyCache -Force -ErrorAction SilentlyContinue
    Write-Output "   deleted $legacyCache"
} else {
    Write-Output "   not present (normal on Win11)"
}

Write-Output "5. Restarting explorer.exe..."
Start-Process explorer.exe
Start-Sleep -Seconds 2

Write-Output "6. Verify explorer is running:"
Get-Process explorer -ErrorAction SilentlyContinue | Select-Object Id, StartTime, ProcessName | Format-Table -AutoSize

Write-Output "7. Iconcache regeneration check:"
$newIconCacheCount = (Get-ChildItem -Path $explorerCache -Filter "iconcache_*.db" -ErrorAction SilentlyContinue).Count
$newThumbCacheCount = (Get-ChildItem -Path $explorerCache -Filter "thumbcache_*.db" -ErrorAction SilentlyContinue).Count
Write-Output "   iconcache files now: $newIconCacheCount  (rebuilds eagerly on explorer restart)"
Write-Output "   thumbcache files now: $newThumbCacheCount  (rebuilds lazily as folders are browsed)"
