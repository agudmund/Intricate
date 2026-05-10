<#
.SYNOPSIS
SPP forensic read — take temporary ownership, dump key contents, restore ACL exactly.

.DESCRIPTION
Reads HKLM\SYSTEM\CurrentControlSet\Control\{7746D80F-97E0-4E26-9543-26B41FC22F79}
which is normally locked to TrustedInstaller-only ACLs.

Sequence:
  1. Snapshot original SDDL (owner + DACL + SACL + group)
  2. Enable SeTakeOwnership / SeRestore / SeBackup / SeSecurity privileges
  3. Take ownership, grant FullControl to current user
  4. Recursively enumerate subkey tree, dump values to output file
  5. ALWAYS restore the original SDDL (even on error) via try/finally
  6. Verify post-restore SDDL matches the snapshot

This is read-only forensic inspection — no key contents are modified.
#>

[CmdletBinding()]
param(
    [string]$KeyPath = "SYSTEM\CurrentControlSet\Control\{7746D80F-97E0-4E26-9543-26B41FC22F79}",
    [string]$OutputDir  = "C:\Users\thisg\Desktop\Intricate\Documents\Data",
    [string]$OutputFile = "C:\Users\thisg\Desktop\Intricate\Documents\Data\spp_forensic_dump.txt",
    [string]$BackupFile = "C:\Users\thisg\Desktop\Intricate\Documents\Data\spp_forensic_acl_backup.sddl",
    [string]$LogFile    = "C:\Users\thisg\Desktop\Intricate\Documents\Data\spp_forensic.log"
)
if (-not (Test-Path $OutputDir)) { New-Item -Path $OutputDir -ItemType Directory -Force | Out-Null }
Start-Transcript -Path $LogFile -Force | Out-Null

# ── Wait-ForEnter: strictly Enter, ignore other keys ───────────────────
function Wait-ForEnter {
    Write-Host ""
    Write-Host "Press ENTER to close (other keys ignored)..." -ForegroundColor Yellow
    try {
        while ($true) {
            $k = [System.Console]::ReadKey($true)
            if ($k.Key -eq [System.ConsoleKey]::Enter) { return }
        }
    } catch {
        # No real console — fall back to line-buffered Read-Host
        $null = Read-Host
    }
}

# Catch any unhandled error so the window stays open for screenshotting
trap {
    Write-Host ""
    Write-Host "================ UNHANDLED ERROR ================" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ("At: " + $_.InvocationInfo.PositionMessage) -ForegroundColor Yellow
    Write-Host "==================================================" -ForegroundColor Red
    Write-Host ""
    try { Stop-Transcript | Out-Null } catch {}
    Wait-ForEnter
    exit 98
}

# ── P/Invoke for token privileges ────────────────────────────────────
Add-Type -ErrorAction SilentlyContinue @'
using System;
using System.Runtime.InteropServices;
public class Privs {
    [StructLayout(LayoutKind.Sequential, Pack=1)]
    public struct TOKEN_PRIVILEGES {
        public uint PrivilegeCount;
        public long Luid;
        public uint Attributes;
    }
    [DllImport("advapi32.dll", SetLastError=true)]
    public static extern bool OpenProcessToken(IntPtr h, int access, ref IntPtr token);
    [DllImport("advapi32.dll", SetLastError=true)]
    public static extern bool LookupPrivilegeValue(string sys, string name, ref long luid);
    [DllImport("advapi32.dll", SetLastError=true)]
    public static extern bool AdjustTokenPrivileges(IntPtr token, bool disable, ref TOKEN_PRIVILEGES newState, int len, IntPtr prev, IntPtr ret);
    [DllImport("kernel32.dll")] public static extern IntPtr GetCurrentProcess();
    public static bool Enable(string privName) {
        IntPtr token = IntPtr.Zero;
        if (!OpenProcessToken(GetCurrentProcess(), 0x28, ref token)) return false;
        long luid = 0;
        if (!LookupPrivilegeValue(null, privName, ref luid)) return false;
        TOKEN_PRIVILEGES tp = new TOKEN_PRIVILEGES { PrivilegeCount = 1, Luid = luid, Attributes = 2 };
        return AdjustTokenPrivileges(token, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero);
    }
}
'@

# ── Recursive dump helper ────────────────────────────────────────────
function Dump-Key {
    param([Microsoft.Win32.RegistryKey]$Key, [string]$Path, [int]$Depth = 0)
    $pad = "  " * $Depth
    Write-Output "$pad[$Path]"
    try {
        foreach ($name in $Key.GetValueNames()) {
            $kind = $Key.GetValueKind($name)
            $val  = $Key.GetValue($name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
            $disp = if ($name -eq "") { "(default)" } else { $name }
            switch ($kind) {
                "Binary" {
                    $bytes = [byte[]]$val
                    if ($bytes.Length -le 96) {
                        $hex = ($bytes | ForEach-Object { '{0:X2}' -f $_ }) -join ' '
                        Write-Output "$pad  $disp : REG_BINARY ($($bytes.Length)B) = $hex"
                    } else {
                        $head = ($bytes[0..47] | ForEach-Object { '{0:X2}' -f $_ }) -join ' '
                        Write-Output "$pad  $disp : REG_BINARY ($($bytes.Length)B) = $head ..."
                    }
                }
                "DWord"      { Write-Output ("$pad  $disp : REG_DWORD = 0x{0:X8} ({0})" -f $val) }
                "QWord"      { Write-Output ("$pad  $disp : REG_QWORD = 0x{0:X16} ({0})" -f $val) }
                "MultiString"{ Write-Output "$pad  $disp : REG_MULTI_SZ = [$($val -join ' | ')]" }
                "ExpandString"{ Write-Output "$pad  $disp : REG_EXPAND_SZ = '$val'" }
                default      { Write-Output "$pad  $disp : $kind = '$val'" }
            }
        }
    } catch {
        Write-Output "$pad  ! value enumeration failed: $($_.Exception.Message)"
    }
    try {
        foreach ($subName in $Key.GetSubKeyNames()) {
            try {
                $subKey = $Key.OpenSubKey($subName, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadSubTree, [System.Security.AccessControl.RegistryRights]::ReadKey)
                if ($subKey) {
                    Dump-Key -Key $subKey -Path "$Path\$subName" -Depth ($Depth + 1)
                    $subKey.Close()
                }
            } catch {
                Write-Output "$pad  ! [$Path\$subName] read failed: $($_.Exception.Message)"
            }
        }
    } catch {
        Write-Output "$pad  ! subkey enumeration failed: $($_.Exception.Message)"
    }
}

# ── Privilege check ───────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Must be run as Administrator. Right-click PowerShell → Run as Administrator."
    Stop-Transcript | Out-Null
    Write-Host ""
    Wait-ForEnter
    exit 1
}

[Privs]::Enable("SeTakeOwnershipPrivilege") | Out-Null
[Privs]::Enable("SeRestorePrivilege")       | Out-Null
[Privs]::Enable("SeBackupPrivilege")        | Out-Null
[Privs]::Enable("SeSecurityPrivilege")      | Out-Null

# ── Open key with TakeOwnership right ────────────────────────────────
$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, [Microsoft.Win32.RegistryView]::Default)
$key = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, [System.Security.AccessControl.RegistryRights]::TakeOwnership)
if (-not $key) { Write-Error "Could not open $KeyPath"; exit 2 }

# ── Snapshot original ACL ────────────────────────────────────────────
$origAcl   = $key.GetAccessControl([System.Security.AccessControl.AccessControlSections]::All)
$origOwner = $origAcl.Owner
$origSddl  = $origAcl.Sddl
$origSddl | Out-File $BackupFile -Encoding UTF8
Write-Output "── Original ACL captured ──"
Write-Output "Owner: $origOwner"
Write-Output "SDDL:  $origSddl"
Write-Output ""

try {
    # ── Take ownership ───────────────────────────────────────────────
    $me = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $takeAcl = New-Object System.Security.AccessControl.RegistrySecurity
    $takeAcl.SetOwner($me)
    $key.SetAccessControl($takeAcl)
    $key.Close()
    Write-Output "Ownership taken: $($me.Translate([System.Security.Principal.NTAccount]).Value)"

    # ── Grant FullControl to current user ────────────────────────────
    $key2 = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, [System.Security.AccessControl.RegistryRights]::ChangePermissions)
    $rw   = $key2.GetAccessControl()
    $rw.AddAccessRule((New-Object System.Security.AccessControl.RegistryAccessRule($me, [System.Security.AccessControl.RegistryRights]::FullControl, [System.Security.AccessControl.InheritanceFlags]::ContainerInherit, [System.Security.AccessControl.PropagationFlags]::None, [System.Security.AccessControl.AccessControlType]::Allow)))
    $key2.SetAccessControl($rw)
    $key2.Close()
    Write-Output "FullControl granted, opening for read..."

    # ── Recursive dump ────────────────────────────────────────────────
    Set-Content -Path $OutputFile -Value "SPP forensic dump  ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))" -Encoding UTF8
    Add-Content -Path $OutputFile -Value "Source:    HKLM\$KeyPath" -Encoding UTF8
    Add-Content -Path $OutputFile -Value "OrigOwner: $origOwner" -Encoding UTF8
    Add-Content -Path $OutputFile -Value "OrigSDDL:  $origSddl" -Encoding UTF8
    Add-Content -Path $OutputFile -Value ("=" * 80) -Encoding UTF8

    $key3 = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadSubTree, [System.Security.AccessControl.RegistryRights]::ReadKey)
    $dump = Dump-Key -Key $key3 -Path "HKLM\$KeyPath"
    Add-Content -Path $OutputFile -Value $dump -Encoding UTF8
    $key3.Close()

    Write-Output ""
    Write-Output "Dump complete → $OutputFile"
    Write-Output ("Subkeys at root: " + (Dump-Key -Key ($base.OpenSubKey($KeyPath)) -Path "X" | Measure-Object | Select-Object -ExpandProperty Count))
}
finally {
    Write-Output ""
    Write-Output "── Restoring original ACL ──"
    try {
        $key4 = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree, [System.Security.AccessControl.RegistryRights]::TakeOwnership -bor [System.Security.AccessControl.RegistryRights]::ChangePermissions)
        $restore = New-Object System.Security.AccessControl.RegistrySecurity
        $restore.SetSecurityDescriptorSddlForm($origSddl, [System.Security.AccessControl.AccessControlSections]::All)
        $key4.SetAccessControl($restore)
        $key4.Close()

        # Verify
        $verifyKey = $base.OpenSubKey($KeyPath, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadSubTree, [System.Security.AccessControl.RegistryRights]::ReadPermissions)
        $verifyAcl = $verifyKey.GetAccessControl([System.Security.AccessControl.AccessControlSections]::All)
        $verifyKey.Close()
        if ($verifyAcl.Sddl -eq $origSddl) {
            Write-Output "  ✓ ACL restored exactly (SDDL match)"
        } else {
            Write-Output "  ! ACL mismatch — backup at $BackupFile"
            Write-Output "  Original: $origSddl"
            Write-Output "  Now:      $($verifyAcl.Sddl)"
        }
    } catch {
        Write-Output "  ! Restoration failed: $($_.Exception.Message)"
        Write-Output "  ! Manual restoration needed using $BackupFile"
    }
}

Write-Output ""
Write-Output "── File write verification ──"
foreach ($f in @($OutputFile, $BackupFile, $LogFile)) {
    if (Test-Path $f) {
        $sz = (Get-Item $f).Length
        Write-Output "  ✓ $f  ($sz bytes)"
    } else {
        Write-Output "  ✗ $f  (NOT WRITTEN)"
    }
}
Write-Output ""
Write-Output "Done. Output saved."
Stop-Transcript | Out-Null
Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "Forensic complete. Read/screenshot above output." -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Cyan
Wait-ForEnter
