<#
.SYNOPSIS
SPP key lockdown v2 — build a fresh ACL from scratch and Set-Acl it.

.DESCRIPTION
v1 hit a PS 7 quirk where the raw OpenSubKey/GetAccessControl path returned
partial descriptor data (AreAccessRulesProtected populated but Owner/SDDL/
Access empty), and then a null entry slipped through the rule-removal loop.

This version:
  1. Uses Get-Acl (PowerShell wrapper) for reading — more PS 7 friendly
  2. Builds a NEW RegistrySecurity in memory with exactly the two intended
     rules, instead of mutating the existing one
  3. Sets owner to SAKURA\thisg, DACL-protected (no parent inheritance),
     two access rules: thisg FullControl + SYSTEM FullControl
  4. Uses Set-Acl to commit
  5. Verifies via fresh Get-Acl

Run as Administrator.
#>

[CmdletBinding()]
param(
    [string]$RegPath = "Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\{7746D80F-97E0-4E26-9543-26B41FC22F79}",
    [string]$LogFile = "C:\Users\thisg\Desktop\Intricate\Documents\Data\spp_acl_lockdown_v2.log"
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

function Show-AclState {
    param([Parameter(Mandatory)]$Acl, [string]$Heading)
    Write-Output ""
    Write-Output "  --- $Heading ---"
    Write-Output "  Owner:                   $($Acl.Owner)"
    Write-Output "  Group:                   $($Acl.Group)"
    Write-Output "  AreAccessRulesProtected: $($Acl.AreAccessRulesProtected)"
    Write-Output "  SDDL:                    $($Acl.Sddl)"
    Write-Output "  Access entries:"
    $rules = @($Acl.Access)
    if (-not $rules -or $rules.Count -eq 0 -or ($rules.Count -eq 1 -and $null -eq $rules[0])) {
        Write-Output "    (none)"
    } else {
        foreach ($r in $rules) {
            if ($null -eq $r) { continue }
            $inh = if ($r.IsInherited) { "inh" } else { "EXP" }
            $idName = try { $r.IdentityReference.Translate([System.Security.Principal.NTAccount]).Value } catch { "$($r.IdentityReference.Value)" }
            Write-Output ("    [{0}] {1,-50} {2,-6} {3}" -f $inh, $idName, $r.AccessControlType, $r.RegistryRights)
        }
    }
}

Add-Type -ErrorAction SilentlyContinue @'
using System;
using System.Runtime.InteropServices;
public class P5 {
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

[P5]::En("SeTakeOwnershipPrivilege") | Out-Null
[P5]::En("SeRestorePrivilege")       | Out-Null
[P5]::En("SeBackupPrivilege")        | Out-Null
[P5]::En("SeSecurityPrivilege")      | Out-Null

$me        = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$myAcct    = $me.Translate([System.Security.Principal.NTAccount]).Value
$systemSid = New-Object System.Security.Principal.SecurityIdentifier("S-1-5-18")

Write-Output "=================================================="
Write-Output "Step 1: Reading current ACL via Get-Acl"
Write-Output "=================================================="
$current = Get-Acl -Path $RegPath -ErrorAction Stop
Show-AclState -Acl $current -Heading "current state"

# ── Step 2: Build a fresh ACL from scratch ─────────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 2: Building fresh ACL in memory"
Write-Output "=================================================="

$fresh = New-Object System.Security.AccessControl.RegistrySecurity

# Owner
$fresh.SetOwner($me)
Write-Output "  set owner to: $myAcct"

# Disable parent inheritance (DACL protection on)
$fresh.SetAccessRuleProtection($true, $false)
Write-Output "  DACL protection: ENABLED (no parent inheritance)"

# Add the human rule
$humanRule = New-Object System.Security.AccessControl.RegistryAccessRule(
    $me,
    [System.Security.AccessControl.RegistryRights]::FullControl,
    [System.Security.AccessControl.InheritanceFlags]::ContainerInherit,
    [System.Security.AccessControl.PropagationFlags]::None,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$fresh.AddAccessRule($humanRule)
Write-Output "  added rule: $myAcct  FullControl  (Allow, ContainerInherit)"

# Add the SYSTEM rule
$systemRule = New-Object System.Security.AccessControl.RegistryAccessRule(
    $systemSid,
    [System.Security.AccessControl.RegistryRights]::FullControl,
    [System.Security.AccessControl.InheritanceFlags]::ContainerInherit,
    [System.Security.AccessControl.PropagationFlags]::None,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$fresh.AddAccessRule($systemRule)
Write-Output "  added rule: NT AUTHORITY\SYSTEM  FullControl  (Allow, ContainerInherit)"

Show-AclState -Acl $fresh -Heading "fresh ACL ready to commit"

# ── Step 3: Commit via Set-Acl ─────────────────────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 3: Committing via Set-Acl"
Write-Output "=================================================="
try {
    Set-Acl -Path $RegPath -AclObject $fresh -ErrorAction Stop
    Write-Output "  Set-Acl succeeded"
} catch {
    Write-Output "  ! Set-Acl threw: $($_.Exception.Message)"
    throw
}

# ── Step 4: Verify via fresh Get-Acl ───────────────────────────────────
Write-Output ""
Write-Output "=================================================="
Write-Output "Step 4: Verification (fresh Get-Acl)"
Write-Output "=================================================="
$verify = Get-Acl -Path $RegPath -ErrorAction Stop
Show-AclState -Acl $verify -Heading "post-commit state"

# Sanity check — count the explicit rules
$explicit = @($verify.Access | Where-Object { $_ -and -not $_.IsInherited })
Write-Output ""
if ($explicit.Count -eq 2) {
    Write-Output "  ✓ Exactly 2 explicit rules — lockdown matches intent"
} elseif ($explicit.Count -eq 0) {
    Write-Output "  ⚠ No explicit rules visible — Set-Acl may have failed silently"
} else {
    Write-Output "  ⚠ $($explicit.Count) explicit rules present — review the list above"
}

Stop-Transcript | Out-Null
Wait-ForEnter
