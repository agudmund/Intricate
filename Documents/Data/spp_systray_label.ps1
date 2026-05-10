<#
.SYNOPSIS
One-shot fix for Personalization > Taskbar panel label/icon for Intricate.

.DESCRIPTION
The Settings panel reads two fields from NotifyIconSettings\<hash>\:
  - InitialTooltip  → the display name (falls back to PE FileDescription)
  - IconSnapshot    → the icon PNG bytes (NOT a path reference; embedded image)

Neither field is populated by Qt's QSystemTrayIcon.setToolTip / setIcon at
registration — those write to Shell_NotifyIcon szTip / hIcon, which the live
systray reads, but the persistent panel store is separate.

This script:
  1. Generates 32×32 PNG bytes from icons\Stickers\Intricate.ico via
     System.Drawing
  2. Sweeps NotifyIconSettings for entries whose ExecutablePath matches
     python.exe or pythonw.exe (Intricate's launcher canonical forms)
  3. Writes InitialTooltip="Intricate" and IconSnapshot=<png bytes>
  4. Verifies and prints results

Idempotent — safe to run repeatedly. If no matching entries are found, prints
a hint to toggle the panel switch ON first to materialize them.

Does NOT need admin elevation — writes are to HKCU.
#>

[CmdletBinding()]
param(
    [string]$IconPath = "C:\Users\thisg\Desktop\Intricate\icons\Stickers\Intricate.ico",
    [string]$Label    = "Intricate",
    [int]$IconSize    = 32,
    [string]$LogFile  = "C:\Users\thisg\Desktop\Intricate\Documents\Data\spp_systray_label.log"
)
Start-Transcript -Path $LogFile -Force | Out-Null

trap {
    Write-Host ""
    Write-Host "================ ERROR ================" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ("At: " + $_.InvocationInfo.PositionMessage) -ForegroundColor Yellow
    Write-Host "=======================================" -ForegroundColor Red
    try { Stop-Transcript | Out-Null } catch {}
    $null = Read-Host "Press Enter to close"
    exit 98
}

function Wait-ForEnter {
    Write-Host ""
    Write-Host "Press ENTER to close (other keys ignored)..." -ForegroundColor Yellow
    try { while ($true) { $k = [System.Console]::ReadKey($true); if ($k.Key -eq 'Enter') { return } } }
    catch { $null = Read-Host }
}

Add-Type -AssemblyName System.Drawing

function Get-IconAsPngBytes {
    param([string]$IconPath, [int]$Size)
    if (-not (Test-Path $IconPath)) { throw "Icon file not found: $IconPath" }
    $icon = New-Object System.Drawing.Icon($IconPath, $Size, $Size)
    $bmp = $icon.ToBitmap()
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bytes = $ms.ToArray()
    $ms.Dispose(); $bmp.Dispose(); $icon.Dispose()
    return $bytes
}

Write-Output "=================================================="
Write-Output "Personalization panel label/icon fix"
Write-Output "  Icon source:  $IconPath"
Write-Output "  Target size:  ${IconSize}x${IconSize}"
Write-Output "  Label:        $Label"
Write-Output "=================================================="

$pngBytes = Get-IconAsPngBytes -IconPath $IconPath -Size $IconSize
$headerOk = ($pngBytes[0] -eq 137 -and $pngBytes[1] -eq 80 -and $pngBytes[2] -eq 78 -and $pngBytes[3] -eq 71)
Write-Output "  Generated:    $($pngBytes.Length) bytes, PNG header valid: $headerOk"

# ── Find matching NotifyIconSettings entries ───────────────────────────
$nis = "HKCU:\Control Panel\NotifyIconSettings"
$matches = @()
Get-ChildItem $nis -ErrorAction SilentlyContinue | ForEach-Object {
    $v = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if ($v.ExecutablePath -and (
        $v.ExecutablePath.ToLower().EndsWith("python.exe") -or
        $v.ExecutablePath.ToLower().EndsWith("pythonw.exe"))) {
        $matches += [PSCustomObject]@{
            Key = $_.PSChildName
            Path = $_.PSPath
            Exe = $v.ExecutablePath
            BeforeTooltip = $v.InitialTooltip
            BeforeIconSize = if ($v.IconSnapshot) { $v.IconSnapshot.Length } else { 0 }
        }
    }
}

Write-Output ""
if ($matches.Count -eq 0) {
    Write-Output "──────────────────────────────────────────────────"
    Write-Output "  No matching NotifyIconSettings entries found."
    Write-Output "──────────────────────────────────────────────────"
    Write-Output ""
    Write-Output "  To materialize the entries:"
    Write-Output "    1. Open Settings > Personalization > Taskbar"
    Write-Output "    2. Expand 'Other system tray icons'"
    Write-Output "    3. Toggle the 'Python' row ON (creates entries in registry)"
    Write-Output "    4. Re-run this script"
    Stop-Transcript | Out-Null; Wait-ForEnter; exit 0
}

Write-Output "Found $($matches.Count) matching entries:"
foreach ($m in $matches) {
    Write-Output ""
    Write-Output "  Key: $($m.Key)"
    Write-Output "    Exe:                $($m.Exe)"
    Write-Output "    BEFORE Tooltip:     '$($m.BeforeTooltip)'"
    Write-Output "    BEFORE IconSize:    $($m.BeforeIconSize) bytes"
}

# ── Patch ──────────────────────────────────────────────────────────────
Write-Output ""
Write-Output "Writing updates..."
foreach ($m in $matches) {
    try {
        Set-ItemProperty -Path $m.Path -Name "InitialTooltip" -Value $Label       -Type String -ErrorAction Stop
        Set-ItemProperty -Path $m.Path -Name "IconSnapshot"  -Value $pngBytes    -Type Binary -ErrorAction Stop
        Write-Output "  ✓ $($m.Key)"
    } catch {
        Write-Output "  ✗ $($m.Key): $($_.Exception.Message)"
    }
}

# ── Verify ─────────────────────────────────────────────────────────────
Write-Output ""
Write-Output "Verification:"
foreach ($m in $matches) {
    $v = Get-ItemProperty $m.Path
    $afterTt = $v.InitialTooltip
    $afterSz = if ($v.IconSnapshot) { $v.IconSnapshot.Length } else { 0 }
    $ok = ($afterTt -eq $Label) -and ($afterSz -eq $pngBytes.Length)
    $mark = if ($ok) { "✓" } else { "✗" }
    Write-Output "  $mark $($m.Key): Tooltip='$afterTt', IconSize=${afterSz}B"
}

Write-Output ""
Write-Output "──────────────────────────────────────────────────"
Write-Output "  Next step — see the panel update:"
Write-Output "──────────────────────────────────────────────────"
Write-Output "  1. Close Settings COMPLETELY (right-click on taskbar → Close)"
Write-Output "  2. Reopen Settings → Personalization → Taskbar"
Write-Output "  3. Expand 'Other system tray icons'"
Write-Output "  4. The entry should now read 'Intricate' with the new mark"

Stop-Transcript | Out-Null
Wait-ForEnter
