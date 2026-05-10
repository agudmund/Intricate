<#
.SYNOPSIS
Reset the Win11 identity-locked Personalization > Taskbar cache for Intricate.

.DESCRIPTION
Step 5 of the Brand Mark Refresh Chain documented in
Documents/Design/Icon Pipeline.md.

The memory entry project_personalization_panel_cache_is_identity_locked
warns about this cache: once Win11 Personalization > Taskbar binds a
wrong icon to an app identity, NO cache flush dislodges it. The cached
icon lives as raw PNG bytes inside the IconSnapshot registry value at
HKCU\Control Panel\NotifyIconSettings\<hash>\IconSnapshot — not a path
reference, the actual image. Even when every icon path is corrected,
Windows keeps showing the embedded snapshot until that key is deleted.

Procedure:
  1. Locate NotifyIconSettings entries whose ExecutablePath ends with
     python.exe or pythonw.exe (Intricate's launcher canonical forms;
     Windows aggregates them under one panel row)
  2. Backup the targets to a single combined .reg file
  3. Delete the target subkeys (Windows recreates them when the user
     next interacts with the panel; the recreation will pull fresh
     state from the live Shell_NotifyIcon registration)
  4. Sweep stale identity records from FeatureUsage:
     - AppSwitched\Intricate              (alt-tab counter, bare identity)
     - AppSwitched\SingleSharedBraincell.Intricate
     - ShowJumpView\Intricate
  5. Refresh the shell:
     - ie4uinit -show  (Windows's built-in shell icon refresh; returns
       exit 1 even on success — normal)
     - SHChangeNotify(SHCNE_ASSOCCHANGED)  (broadcast file-association
       change so Explorer re-reads any DefaultIcon entries)

DO NOT touch HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\
Taskband\Favorites or FavoritesResolve — those are the pinned-items
binary blob for EVERY app on the taskbar, not just Intricate. Wiping
them loses every pinned item.

If after this reset the pinned taskbar slot still shows the wrong icon,
the bulletproof fallback is manual unpin + repin of the taskbar item.

Originally extracted from inline operations performed on 2026-05-10.
#>

[CmdletBinding()]
param(
    [string]$BackupDir = "C:\Users\thisg\Desktop\Intricate\Documents\Data"
)

$ts = Get-Date -Format "yyyy-MM-dd"
$backupPath = Join-Path $BackupDir "identity_cache_backup_$ts.reg"

# ── 1. Locate target NotifyIconSettings entries ────────────────────
Write-Output "1. Locating NotifyIconSettings entries (python.exe / pythonw.exe)..."
$nis = "HKCU:\Control Panel\NotifyIconSettings"
$targets = @()
Get-ChildItem $nis -ErrorAction SilentlyContinue | ForEach-Object {
    $v = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if ($v.ExecutablePath -and (
        $v.ExecutablePath.ToLower().EndsWith("python.exe") -or
        $v.ExecutablePath.ToLower().EndsWith("pythonw.exe"))) {
        $targets += $_
    }
}
Write-Output "   found $($targets.Count) target entries"

if ($targets.Count -gt 0) {
    # ── 2. Backup ────────────────────────────────────────────────
    Write-Output "2. Backing up to $backupPath..."
    $tempFiles = @()
    foreach ($t in $targets) {
        $tmp = "$env:TEMP\nis_$($t.PSChildName).reg"
        reg export "HKCU\Control Panel\NotifyIconSettings\$($t.PSChildName)" $tmp /y 2>&1 | Out-Null
        if (Test-Path $tmp) { $tempFiles += $tmp }
    }
    if ($tempFiles) {
        Get-Content $tempFiles | Set-Content $backupPath -Encoding Unicode
        Remove-Item $tempFiles -ErrorAction SilentlyContinue
        Write-Output "   backup: $((Get-Item $backupPath).Length) bytes"
    }

    # ── 3. Delete target entries ─────────────────────────────────
    Write-Output "3. Deleting target NotifyIconSettings entries..."
    foreach ($t in $targets) {
        Remove-Item $t.PSPath -Force -Recurse
        Write-Output "   removed: $($t.PSChildName)"
    }
} else {
    Write-Output "2. (no targets to backup)"
    Write-Output "3. (no targets to delete)"
}

# ── 4. Sweep FeatureUsage identity records ─────────────────────────
Write-Output "4. Sweeping FeatureUsage identity records..."
$fu = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FeatureUsage"
Remove-ItemProperty -Path "$fu\AppSwitched" -Name "Intricate" -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "$fu\AppSwitched" -Name "SingleSharedBraincell.Intricate" -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "$fu\ShowJumpView" -Name "Intricate" -ErrorAction SilentlyContinue
Write-Output "   done"

# ── 5. ie4uinit ────────────────────────────────────────────────────
Write-Output "5. ie4uinit -show (Windows built-in shell icon refresh)..."
& "$env:SystemRoot\System32\ie4uinit.exe" -show 2>&1 | Out-Null
Write-Output "   done (exit 1 is normal — ie4uinit returns non-zero even on success)"

# ── 6. SHChangeNotify ──────────────────────────────────────────────
Write-Output "6. SHChangeNotify(SHCNE_ASSOCCHANGED)..."
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class ShellRefresh {
    [DllImport("shell32.dll")] public static extern void SHChangeNotify(int eventId, int flags, IntPtr item1, IntPtr item2);
}
'@
[ShellRefresh]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero)
Write-Output "   done"

Write-Output ""
Write-Output "Done. If the pinned-taskbar slot still shows the wrong icon after"
Write-Output "this reset, the bulletproof fallback is manual unpin + repin of"
Write-Output "the taskbar item — Windows binds fresh on repin."
