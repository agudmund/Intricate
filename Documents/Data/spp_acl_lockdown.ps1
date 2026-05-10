<#
.SYNOPSIS
SPP key lockdown — strip all DACL rules except SAKURA\thisg FullControl + SYSTEM FullControl.

.DESCRIPTION
After the forensic+repair sequence, the target key has multiple explicit
DACL rules from incremental additions.  This script normalises the DACL to
the minimum-viable two-rule pattern for a single-user machine where the
human user is the sole intended actor:

  - SAKURA\thisg  FullControl   (the human owner)
  - NT AUTHORITY\SYSTEM  FullControl  (the OS, acting on the human's behalf)

Everything else (Administrators group, TrustedInstaller, Everyone, any
other explicit rules) is removed.  Inheritance from parent stays
disabled (SE_DACL_PROTECTED).

The script opens the key with BOTH ReadPermissions and ChangePermissions
this time so the readouts actually show what's in the security descriptor.

Run as Administrator.
#>

[CmdletBinding()]
param(
    [string]$KeyPath = "SYSTEM\CurrentControlSet\Control\{7746D80F-97E0-4E26-9543-26B41FC22F79}",
    [string]$LogFile = "C:\Users\thisg\Desktop\Intricate\Documents\Data\spp_acl_lockdown.log"
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

function Show-Acl {
    param([System.Security.AccessControl.RegistrySecurity]$Acl, [string]$Heading)
    Write-Output "  $Heading"
    Write-Output "  Owner: $($Acl.Owner)"
    Write-Output "  Group: $($Acl.Group)"
    Write-Output "  SDDL:  $($Acl.Sddl)"
    Write-Output "  AreAccessRulesProtected: $($Acl.AreAccessRulesProtected)"
    Write-Output "  Access entries:"
    if (-not $Acl.Access -or $Acl.Access.Count -eq 0) {
        Write-Output "    (none)"
    } else {
        foreach ($r in $Acl.Access) {
            $inh = if ($r.IsInherited) { "inh" } else { "EXP" }
            $idName = try { $r.IdentityReference.Translate([System.Security.Principal.NTAccount]).Value } catch { $r.IdentityReference.Value }
            Write-Output ("    [{0}] {1,-50} {2,-6} {3}" -f $inh, $idName, $r.AccessControlType, $r.RegistryRights)
        }
    }
}

Add-Type -ErrorAction SilentlyContinue @'
using System;
using System.Runtime.InteropServices;
public class P4 {
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

[P4]::En("SeTakeOwnershipPrivilege") | Out-Null
[P4]::En("SeRestorePrivilege")       | Out-Null
[P4]::En("SeBackupPrivilege")        | Out-Null
[P4]::En("SeSecurityPrivilege")      | Out-Null

$me        = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-18")

$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryView]::Default)

# Open with BOTH ReadPermissions AND ChangePermissions so reads populate
$rights = [System.Security.AccessControl.RegistryRights]::ReadPermissions -bor
          [System.Security.AccessControl.RegistryRights]::ChangePermissions
$key = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, $rights)
if (-not $key) { throw "Could not open $KeyPath" }

$acl = $key.GetAccessControl([System.Security.AccessControl.AccessControlSections]::All)

Write-Output "=================================================="
Write-Output "Step 1: Current state (before lockdown)"
Write-Output "=================================================="
Show-Acl -Acl $acl -Heading ""

# ── Step 2: Purge ALL explicit DACL rules ──────────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 2: Purging all explicit DACL rules"
Write-Output "=================================================="
$explicitRules = @($acl.Access | Where-Object { -not $_.IsInherited })
if ($explicitRules.Count -eq 0) {
    Write-Output "  (no explicit rules to remove)"
} else {
    foreach ($r in $explicitRules) {
        $idName = try { $r.IdentityReference.Translate([System.Security.Principal.NTAccount]).Value } catch { $r.IdentityReference.Value }
        $ok = $acl.RemoveAccessRule($r)
        Write-Output "  removed: $idName  $($r.AccessControlType) $($r.RegistryRights)  (return=$ok)"
    }
}

# ── Step 3: Add the two intended rules ─────────────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 3: Adding the two intended rules"
Write-Output "=================================================="
$humanRule = New-Object System.Security.AccessControl.RegistryAccessRule(
    $me, [System.Security.AccessControl.RegistryRights]::FullControl,
    ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit),
    [System.Security.AccessControl.PropagationFlags]::None,
    [System.Security.AccessControl.AccessControlType]::Allow)
$systemRule = New-Object System.Security.AccessControl.RegistryAccessRule(
    $systemSid, [System.Security.AccessControl.RegistryRights]::FullControl,
    ([System.Security.AccessControl.InheritanceFlags]::ContainerInherit),
    [System.Security.AccessControl.PropagationFlags]::None,
    [System.Security.AccessControl.AccessControlType]::Allow)
$acl.AddAccessRule($humanRule)
$acl.AddAccessRule($systemRule)
Write-Output "  added: $($me.Translate([System.Security.Principal.NTAccount]).Value)  FullControl  (the human)"
Write-Output "  added: NT AUTHORITY\SYSTEM                            FullControl  (the OS itself)"

# Make sure DACL stays protected (no parent inheritance dilutes the rules)
$acl.SetAccessRuleProtection($true, $false)
Write-Output "  DACL protection: ENABLED (no parent inheritance)"

# Make sure owner is SAKURA\thisg
$acl.SetOwner($me)
Write-Output "  owner: $($me.Translate([System.Security.Principal.NTAccount]).Value)"

# ── Step 4: Commit ─────────────────────────────────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 4: Committing"
Write-Output "=================================================="
$key.SetAccessControl($acl)
$key.Close()
Write-Output "  committed"

# ── Step 5: Verify by re-opening fresh ─────────────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 5: Verification (re-opening fresh)"
Write-Output "=================================================="
$verify = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadSubTree, [System.Security.AccessControl.RegistryRights]::ReadPermissions)
$vAcl = $verify.GetAccessControl([System.Security.AccessControl.AccessControlSections]::All)
$verify.Close()
Show-Acl -Acl $vAcl -Heading ""

Stop-Transcript | Out-Null
Wait-ForEnter
