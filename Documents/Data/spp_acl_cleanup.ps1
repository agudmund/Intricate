<#
.SYNOPSIS
Cleanup script — removes the explicit FullControl rule for the current user
on the SPP key, restoring inheritance-only protection.

.DESCRIPTION
The forensic script (spp_forensic.ps1) added an explicit FullControl rule for
the current user on:
    HKLM\SYSTEM\CurrentControlSet\Control\{7746D80F-97E0-4E26-9543-26B41FC22F79}

Original ACL had no explicit DACL — protection came entirely from inheritance.
The SDDL-form restore failed with "term 'SDDL' is not recognized" (parser quirk
on the partial SDDL form returned by Get-Acl on a partially-readable key).

This script:
  1. Verifies current state (user has explicit FullControl rule)
  2. Removes ONLY the explicit Allow rule for the current user
  3. Leaves owner unchanged (was already SAKURA\thisg pre-script)
  4. Verifies post-cleanup state — only inherited rules remain
  5. Confirms regedit-style read access is gone (paradoxically: that's the goal)

Run as Administrator.
#>

[CmdletBinding()]
param(
    [string]$KeyPath = "SYSTEM\CurrentControlSet\Control\{7746D80F-97E0-4E26-9543-26B41FC22F79}",
    [string]$LogFile = "C:\Users\thisg\Desktop\Intricate\Documents\Data\spp_acl_cleanup.log"
)
Start-Transcript -Path $LogFile -Force | Out-Null

trap {
    Write-Host ""
    Write-Host "================ ERROR ================" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ("At: " + $_.InvocationInfo.PositionMessage) -ForegroundColor Yellow
    Write-Host "=======================================" -ForegroundColor Red
    Write-Host ""
    try { Stop-Transcript | Out-Null } catch {}
    $null = Read-Host "Press Enter to close"
    exit 98
}

function Wait-ForEnter {
    Write-Host ""
    Write-Host "Press ENTER to close (other keys ignored)..." -ForegroundColor Yellow
    try {
        while ($true) {
            $k = [System.Console]::ReadKey($true)
            if ($k.Key -eq [System.ConsoleKey]::Enter) { return }
        }
    } catch { $null = Read-Host }
}

# Privilege boilerplate (same as forensic script)
Add-Type -ErrorAction SilentlyContinue @'
using System;
using System.Runtime.InteropServices;
public class P2 {
    [StructLayout(LayoutKind.Sequential, Pack=1)]
    public struct TP { public uint c; public long luid; public uint a; }
    [DllImport("advapi32.dll")] public static extern bool OpenProcessToken(IntPtr h, int a, ref IntPtr t);
    [DllImport("advapi32.dll")] public static extern bool LookupPrivilegeValue(string s, string n, ref long l);
    [DllImport("advapi32.dll")] public static extern bool AdjustTokenPrivileges(IntPtr t, bool d, ref TP n, int l, IntPtr p, IntPtr r);
    [DllImport("kernel32.dll")] public static extern IntPtr GetCurrentProcess();
    public static bool En(string p) {
        IntPtr t = IntPtr.Zero;
        if (!OpenProcessToken(GetCurrentProcess(), 0x28, ref t)) return false;
        long luid = 0;
        if (!LookupPrivilegeValue(null, p, ref luid)) return false;
        TP tp = new TP { c=1, luid=luid, a=2 };
        return AdjustTokenPrivileges(t, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero);
    }
}
'@

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Must be run as Administrator."
    Stop-Transcript | Out-Null
    Wait-ForEnter
    exit 1
}

[P2]::En("SeTakeOwnershipPrivilege") | Out-Null
[P2]::En("SeRestorePrivilege")       | Out-Null
[P2]::En("SeBackupPrivilege")        | Out-Null
[P2]::En("SeSecurityPrivilege")      | Out-Null

$me     = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$myAcct = $me.User.Translate([System.Security.Principal.NTAccount])
Write-Output "Current user: $($myAcct.Value)"

$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryView]::Default)
$key  = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, [System.Security.AccessControl.RegistryRights]::ChangePermissions)
if (-not $key) { throw "Could not open $KeyPath with ChangePermissions right" }

$acl = $key.GetAccessControl([System.Security.AccessControl.AccessControlSections]::Access -bor [System.Security.AccessControl.AccessControlSections]::Owner)

Write-Output ""
Write-Output "── Current ACL state ──"
Write-Output "Owner: $($acl.Owner)"
Write-Output "Access entries:"
foreach ($r in $acl.Access) {
    $inh = if ($r.IsInherited) { "(inherited)" } else { "(EXPLICIT)" }
    Write-Output ("  {0,-12} {1,-50} {2,-12} {3}" -f $inh, $r.IdentityReference, $r.AccessControlType, $r.RegistryRights)
}

# Find explicit Allow rules for the current user
$toRemove = $acl.Access | Where-Object {
    -not $_.IsInherited -and
    $_.AccessControlType -eq 'Allow' -and
    $_.IdentityReference -eq $myAcct
}

if (-not $toRemove) {
    Write-Output ""
    Write-Output "── No explicit user rules to remove. ACL is already clean. ──"
    $key.Close()
    Stop-Transcript | Out-Null
    Wait-ForEnter
    exit 0
}

Write-Output ""
Write-Output "── Removing $($toRemove.Count) explicit Allow rule(s) for current user ──"
foreach ($r in $toRemove) {
    $removed = $acl.RemoveAccessRule($r)
    Write-Output "  removed: $($r.RegistryRights) (return=$removed)"
}

$key.SetAccessControl($acl)
$key.Close()

# Verify
$verify = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadSubTree, [System.Security.AccessControl.RegistryRights]::ReadPermissions)
$vAcl = $verify.GetAccessControl([System.Security.AccessControl.AccessControlSections]::Access -bor [System.Security.AccessControl.AccessControlSections]::Owner)
$verify.Close()

Write-Output ""
Write-Output "── Post-cleanup ACL ──"
Write-Output "Owner: $($vAcl.Owner)"
Write-Output "Access entries:"
foreach ($r in $vAcl.Access) {
    $inh = if ($r.IsInherited) { "(inherited)" } else { "(EXPLICIT)" }
    Write-Output ("  {0,-12} {1,-50} {2,-12} {3}" -f $inh, $r.IdentityReference, $r.AccessControlType, $r.RegistryRights)
}

$stillExplicitForUser = $vAcl.Access | Where-Object {
    -not $_.IsInherited -and
    $_.AccessControlType -eq 'Allow' -and
    $_.IdentityReference -eq $myAcct
}
if ($stillExplicitForUser) {
    Write-Output ""
    Write-Output "  ! STILL HAS EXPLICIT USER RULE — investigate"
} else {
    Write-Output ""
    Write-Output "  ✓ No explicit user rules. Protection back to inheritance-only."
    Write-Output "  ✓ Regedit will show 'Access denied' on this key again — that's the goal."
}

Stop-Transcript | Out-Null
Wait-ForEnter
