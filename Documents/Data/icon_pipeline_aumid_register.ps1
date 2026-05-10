<#
.SYNOPSIS
Register Intricate's AUMID display-name and icon metadata in HKCU.

.DESCRIPTION
Writes the canonical AUMID metadata to:
    HKCU\Software\Classes\AppUserModelId\SingleSharedBraincell.Intricate\
        DisplayName = "Intricate"
        IconUri     = <absolute path to icons\Stickers\Intricate.ico>

This is the Win11 canonical surface for app-identity metadata, read by
toast notifications, jump-list headers, and some shell surfaces. The
Personalization > Taskbar panel does NOT read from here for the label
(it uses the PE FileDescription of ExecutablePath — see Icon Pipeline.md
for the full data-source map), but other surfaces do.

Already done automatically by _heal_systray_panel_metadata() in
main_window.py on every Intricate launch. Standalone script provided for:
  - Setup-time before Intricate has launched for the first time
  - Forensic recovery if the AUMID key was deleted
  - Verification / manual re-write outside the Intricate runtime

Idempotent. No admin elevation needed (HKCU only).

Originally extracted from inline operations performed on 2026-05-10.
#>

[CmdletBinding()]
param(
    [string]$AUMID       = "SingleSharedBraincell.Intricate",
    [string]$DisplayName = "Intricate",
    [string]$IconPath    = "C:\Users\thisg\Desktop\Intricate\icons\Stickers\Intricate.ico"
)

$key = "HKCU:\Software\Classes\AppUserModelId\$AUMID"
if (-not (Test-Path $key)) {
    New-Item -Path $key -Force | Out-Null
    Write-Output "Created: $key"
}

Set-ItemProperty -Path $key -Name "DisplayName" -Value $DisplayName -Type String
Set-ItemProperty -Path $key -Name "IconUri"     -Value $IconPath    -Type String

Write-Output ""
Write-Output "AUMID: $AUMID"
$vals = Get-ItemProperty $key
Write-Output "  DisplayName = $($vals.DisplayName)"
Write-Output "  IconUri     = $($vals.IconUri)"
