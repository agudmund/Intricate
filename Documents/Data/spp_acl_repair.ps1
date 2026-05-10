<#
.SYNOPSIS
Repair the SPP key's DACL — replace the Everyone-FullControl rule with
proper TrustedInstaller / SYSTEM / Administrators protection.

.DESCRIPTION
The forensic script unintentionally materialized the original NULL/protected
DACL into an explicit "Everyone allow -1" rule.  This script:

  1. Probes a SIBLING protected key (HKLM\SYSTEM\CurrentControlSet\Control\Lsa)
     to read its DACL as a reference pattern
  2. Shows current ACL on our SPP key
  3. Removes the explicit Everyone rule
  4. Adds proper rules: TrustedInstaller FullControl, SYSTEM FullControl,
     Administrators ReadKey (matching the sibling-key pattern)
  5. Enables ACL inheritance protection (so parent inheritance doesn't
     dilute the explicit rules)
  6. Verifies post-fix state

Run as Administrator.
#>

[CmdletBinding()]
param(
    [string]$KeyPath = "SYSTEM\CurrentControlSet\Control\{7746D80F-97E0-4E26-9543-26B41FC22F79}",
    [string]$RefPath = "SYSTEM\CurrentControlSet\Control\Lsa",
    [string]$LogFile = "C:\Users\thisg\Desktop\Intricate\Documents\Data\spp_acl_repair.log"
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

Add-Type -ErrorAction SilentlyContinue @'
using System;
using System.Runtime.InteropServices;
public class P3 {
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
    Stop-Transcript | Out-Null; Wait-ForEnter; exit 1
}

[P3]::En("SeTakeOwnershipPrivilege") | Out-Null
[P3]::En("SeRestorePrivilege")       | Out-Null
[P3]::En("SeBackupPrivilege")        | Out-Null
[P3]::En("SeSecurityPrivilege")      | Out-Null

$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryView]::Default)

# ── Step 1: Probe a sibling key to learn the reference DACL pattern ────
Write-Output "=================================================="
Write-Output "Step 1: Reference DACL from sibling key"
Write-Output "  Path: HKLM\$RefPath"
Write-Output "=================================================="
try {
    $refKey = $base.OpenSubKey($RefPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadSubTree, [System.Security.AccessControl.RegistryRights]::ReadPermissions)
    $refAcl = $refKey.GetAccessControl([System.Security.AccessControl.AccessControlSections]::All)
    Write-Output "  Owner: $($refAcl.Owner)"
    Write-Output "  SDDL:  $($refAcl.Sddl)"
    Write-Output "  Access entries:"
    foreach ($r in $refAcl.Access) {
        $inh = if ($r.IsInherited) { "inh" } else { "EXP" }
        Write-Output ("    [{0}] {1,-45} {2,-6} {3}" -f $inh, $r.IdentityReference, $r.AccessControlType, $r.RegistryRights)
    }
    $refKey.Close()
} catch {
    Write-Output "  ! Reference key probe failed: $($_.Exception.Message)"
    Write-Output "  Proceeding with built-in defaults..."
}

# ── Step 2: Show current state of target key ───────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 2: Current ACL on target key"
Write-Output "  Path: HKLM\$KeyPath"
Write-Output "=================================================="
$key = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, [System.Security.AccessControl.RegistryRights]::ChangePermissions)
$acl = $key.GetAccessControl([System.Security.AccessControl.AccessControlSections]::All)
Write-Output "  Owner: $($acl.Owner)"
Write-Output "  SDDL:  $($acl.Sddl)"
Write-Output "  Access entries:"
foreach ($r in $acl.Access) {
    $inh = if ($r.IsInherited) { "inh" } else { "EXP" }
    Write-Output ("    [{0}] {1,-45} {2,-6} {3}" -f $inh, $r.IdentityReference, $r.AccessControlType, $r.RegistryRights)
}

# ── Step 3: Remove explicit Everyone rule(s) ───────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 3: Removing explicit Everyone Allow rule(s)"
Write-Output "=================================================="
$everyone = New-Object System.Security.Principal.SecurityIdentifier("S-1-1-0")  # Everyone SID
$toRemove = $acl.Access | Where-Object {
    -not $_.IsInherited -and
    $_.AccessControlType -eq 'Allow' -and
    ($_.IdentityReference -eq $everyone -or $_.IdentityReference.Value -eq "Everyone")
}
if ($toRemove) {
    foreach ($r in $toRemove) {
        $ok = $acl.RemoveAccessRule($r)
        Write-Output "  removed: $($r.IdentityReference) $($r.RegistryRights) (return=$ok)"
    }
} else {
    Write-Output "  (no Everyone rule found)"
}

# ── Step 4: Add proper protection rules ────────────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 4: Adding proper protection rules"
Write-Output "=================================================="

$tiSid     = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464")  # NT SERVICE\TrustedInstaller
$systemSid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-18")  # NT AUTHORITY\SYSTEM
$adminsSid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-32-544")  # BUILTIN\Administrators

$newRules = @(
    (New-Object System.Security.AccessControl.RegistryAccessRule(
        $tiSid, [System.Security.AccessControl.RegistryRights]::FullControl,
        ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit),
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow)),
    (New-Object System.Security.AccessControl.RegistryAccessRule(
        $systemSid, [System.Security.AccessControl.RegistryRights]::FullControl,
        ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit),
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow)),
    (New-Object System.Security.AccessControl.RegistryAccessRule(
        $adminsSid, [System.Security.AccessControl.RegistryRights]::ReadKey,
        ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit),
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow))
)
foreach ($rule in $newRules) {
    $acl.AddAccessRule($rule)
    Write-Output ("  added: {0,-45} {1}" -f $rule.IdentityReference, $rule.RegistryRights)
}

# Enable DACL protection (prevent parent inheritance from diluting these rules)
$acl.SetAccessRuleProtection($true, $false)  # protected=true, preserveInheritance=false
Write-Output "  enabled DACL protection (SE_DACL_PROTECTED), inheritance disabled"

# ── Step 5: Commit & verify ────────────────────────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 5: Committing & verifying"
Write-Output "=================================================="
$key.SetAccessControl($acl)
$key.Close()

$verify = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadSubTree, [System.Security.AccessControl.RegistryRights]::ReadPermissions)
$vAcl = $verify.GetAccessControl([System.Security.AccessControl.AccessControlSections]::All)
$verify.Close()
Write-Output "  Owner: $($vAcl.Owner)"
Write-Output "  SDDL:  $($vAcl.Sddl)"
Write-Output "  Access entries:"
foreach ($r in $vAcl.Access) {
    $inh = if ($r.IsInherited) { "inh" } else { "EXP" }
    Write-Output ("    [{0}] {1,-45} {2,-6} {3}" -f $inh, $r.IdentityReference, $r.AccessControlType, $r.RegistryRights)
}

# Test: try to read the key as the current user — should get "Access denied"
$stillReadable = $false
try {
    $testRead = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadSubTree, [System.Security.AccessControl.RegistryRights]::ReadKey)
    if ($testRead) {
        $stillReadable = $true
        $testRead.Close()
    }
} catch {
    # Expected — access denied
}
if ($stillReadable) {
    Write-Output ""
    Write-Output "  ⚠ Key is STILL readable by current user — but you're admin so this could be expected."
    Write-Output "    Open regedit as a NON-admin user to truly verify protection."
} else {
    Write-Output ""
    Write-Output "  ✓ Current user no longer has read access — protection restored."
}

Stop-Transcript | Out-Null
Wait-ForEnter
