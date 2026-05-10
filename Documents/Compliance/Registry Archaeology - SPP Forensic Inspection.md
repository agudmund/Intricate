# Registry Archaeology — SPP Forensic Inspection

A diagnostic record of the 2026-05-10 forensic dive into `HKLM\SYSTEM\CurrentControlSet\Control\{7746D80F-97E0-4E26-9543-26B41FC22F79}` — a registry key that surfaced as a tangent during icon-pipeline work and turned out to be the **Software Protection Platform (SPP) token vault**, Windows' encrypted store of every license and activation grant on the machine. This document captures what we found, the methodology that made the inspection safe, the ACL repair side-quest that followed, and the reusable patterns worth keeping for future protected-key inspections.

The icon-pipeline finding from the same session lives in `Documents/Design/Icon Pipeline.md`. This doc is for the registry-archaeology side that grew out of it — a different thread of work, kept separate so neither narrative muddies the other.

---

## How We Got Here

While auditing what registry entries surfaced in the Personalization > Taskbar panel, the user opened regedit in admin mode and the editor auto-loaded `HKLM\SYSTEM\CurrentControlSet\Control\{7746D80F-97E0-4E26-9543-26B41FC22F79}` from a previous session — and immediately threw an "Access denied" dialog. The GUID had no label, no obvious purpose, and was unreadable even from elevated regedit.

In the "good accounting books" frame the user holds the machine to (every registry entry should have a purpose you can name), this was the equivalent of an unlabelled line item in an audit. The "don't look in there" implication made it the *first* thing worth looking in to. The same admin authority that protects it from casual access doesn't protect it from *understanding* it.

---

## Identification — What `{7746D80F-...}` Is

Cross-referenced from registry structure (replicated across both `ControlSet001\Control\` and `CurrentControlSet\Control\` — Windows' Last-Known-Good redundancy pattern for critical system state), the protection ACL pattern (TrustedInstaller-only), and a public Microsoft community-forum reference:

> **`{7746D80F-97E0-4E26-9543-26B41FC22F79}` is the Software Protection Platform (SPP) token store.**
> It holds the encrypted license tokens and activation grants that the SPP service (`sppsvc.exe`) reads/writes to verify Windows activation, app-store entitlements, and feature licenses. Protected by SYSTEM/TrustedInstaller-only ACL by design — modifying it could break activation; reading its structure is harmless but Microsoft locks it because *write* would be exploitable.

The key replicates across `ControlSet001` (the persisted snapshot used for Last-Known-Good recovery) and `CurrentControlSet` (the runtime symlink to the active control set). Both point at the same underlying hive data — modifying one modifies both.

No INF file references the GUID anywhere on disk — confirming it's an OS-resident class registered directly by the SPP service rather than via driver installation.

---

## The Forensic Methodology — Take-Own / Read / Restore

The challenge: even Administrator can't read a TrustedInstaller-owned key without first taking ownership, and modifying the ACL (even to grant ourselves temporary read access) leaves the system in a non-default state until we restore it. The risk profile: a crash mid-flight leaves the SPP key with weakened protection.

The safe pattern, used in `Documents/Data/spp_forensic.ps1`:

1. **Snapshot the original SDDL** to a backup file *before* touching anything (rollback safety)
2. **Enable token privileges**: `SeTakeOwnershipPrivilege`, `SeRestorePrivilege`, `SeBackupPrivilege`, `SeSecurityPrivilege` (via P/Invoke into `advapi32.dll` — PowerShell doesn't expose these natively)
3. **Take ownership** via `RegistryKey.OpenSubKey(..., TakeOwnership)` + `SetOwner` + `SetAccessControl`
4. **Grant FullControl** temporarily to the current user
5. **Recursively enumerate** keys and values, hex-dumping binary blobs and pretty-printing typed values
6. **Restore the original SDDL** in a `try`/`finally` block so it runs *even if the read throws*
7. **Verify** post-restore SDDL matches the snapshot byte-for-byte

The `try`/`finally` placement is what makes this read-only-safe in practice: any exception during the read still triggers the restore. The verify step is what catches a botched restore before the script exits.

```powershell
$origAcl  = $key.GetAccessControl([AccessControlSections]::All)
$origSddl = $origAcl.Sddl
$origSddl | Out-File $BackupFile -Encoding UTF8

try {
    # ... take ownership, grant read, enumerate, write dump to file ...
}
finally {
    # ALWAYS restore, even on exception
    $restore = New-Object System.Security.AccessControl.RegistrySecurity
    $restore.SetSecurityDescriptorSddlForm($origSddl, [AccessControlSections]::All)
    $key.SetAccessControl($restore)
}
```

In our actual run, the restore step *did* throw (`The term 'SDDL' is not recognized as the name of a cmdlet`) — a downstream effect of the partial-SDDL capture which we'll cover in the ACL Repair section. The dump still completed successfully because the try ran in full, but the ACL was not restored to its original shape and required follow-up work.

---

## What's Inside SPP — Structure of `{7746D80F-...}`

Dump produced via `spp_forensic.ps1`, saved to `C:\spp_forensic_dump.txt` (64 KB, 317 lines). Structure:

```
{7746D80F-97E0-4E26-9543-26B41FC22F79}     ← the SPP store root
├── (default value)                          ← (none)
├── {32499047-219B-4349-91F3-F9604B249FFA}   ← 32-byte binary (master handle/pointer)
│
├── {221601AB-48C7-4970-B0EC-96E66F578407}   ← empty bucket (reserved)
├── {59AEE675-B203-4D61-9A1F-04518A20F359}   ← empty bucket (reserved)
├── {D73E01AC-F5A0-4D80-928B-33C1920C38BA}   ← empty bucket (reserved)
│
├── {A25AE4F2-1B96-4CED-8007-AA30E9B1A218}   ← TOKEN VAULT
│   └── ~210 entries:
│       Key:   32-char hex (MD5/128-bit shape)
│       Value: 250–308 byte REG_BINARY blob
│       Header: `14 00 00 00 <length-LE> ...` (version 20, length-prefixed)
│
└── {FB9F5B62-B48B-45F5-8586-E514958C92E2}   ← INDEX / MAPPING TABLE
    └── ~90 entries:
        Key:   64-char hex (SHA-256/256-bit shape)
        Value: 19–76 byte REG_BINARY
        Structure: `10 00 <16-byte ref> 00 [10 00 <16-byte ref> 00 ...]`
        (each 16-byte ref points back to a token in {A25AE4F2-...})
```

**Translating to a banking metaphor**:

| Banking term | What SPP stores | Where |
|---|---|---|
| Vault layout | 5 vaults; 2 in use, 3 reserved | top-level GUID subkeys |
| Master handle | A single 32-byte pointer | root-level value |
| Cash bundles | Encrypted license tokens — ~210 of them | `{A25AE4F2-...}` |
| Account ledger | Hash→token-ID lookup — ~90 entries | `{FB9F5B62-...}` |
| Transaction log | NOT visible — encrypted bodies; AES key lives inside the sppsvc binary, not in the registry |  |

What's NOT in the dump: no plaintext keys, no timestamps, no machine-binding identifiers in cleartext. The protection is "modifying it could brick activation," not "reading it reveals secrets" — every blob is opaque without the SPP service's internal AES key. Reading structure tells you nothing exploitable.

---

## The ACL Repair Side-Quest

The forensic script's restore step failing left the SPP key with a non-default ACL. What followed was three attempts at restoration, each catching a different layer of the issue, before reaching the final clean state.

### Initial state captured by the forensic script

```
Owner: SAKURA\thisg
SDDL:  O:S-1-5-21-6171199-3533007890-1112070463-1001G:SY
```

Notable: the SDDL had **only `O:` and `G:` sections, no `D:` (DACL)**. Two possible interpretations:
- **NULL DACL** (SE_DACL_PRESENT clear) — semantically "allow everyone"
- **Empty DACL with SE_DACL_PROTECTED** — semantically "deny everyone"

The regedit "Access denied" behaviour indicated the latter — but our capture couldn't see the DACL because we lacked READ_CONTROL access at the moment of capture. The captured SDDL was a *partial* security descriptor, not the actual on-disk state.

### Attempt 1: `spp_acl_cleanup.ps1`

Filtered for explicit Allow rules where `IdentityReference == SAKURA\thisg`. Found none — because the rule the forensic script had added wasn't keyed on the user, it had been materialized as **`Everyone Allow -1`** (full access for the WORLD/Everyone SID). The cleanup script reported "ACL is already clean" — accurate to its filter, misleading about actual state.

### Attempt 2: `spp_acl_repair.ps1`

Probed `HKLM\SYSTEM\CurrentControlSet\Control\Lsa` as a reference for the standard protection pattern, then added three rules: `TrustedInstaller FullControl`, `SYSTEM FullControl`, `Administrators ReadKey`. SE_DACL_PROTECTED enabled. Hit a **PS 7 quirk**: opening the key with `ChangePermissions` right only (no `ReadPermissions`) caused `GetAccessControl()` to return a descriptor with `AreAccessRulesProtected=True` populated but `Owner`, `SDDL`, and `Access` all empty — the writes succeeded but the readback was blind, so we couldn't see what state we were leaving things in.

### Attempt 3: `spp_acl_lockdown_v2.ps1` — final working version

Switched from raw `[Microsoft.Win32.RegistryKey]::OpenSubKey + GetAccessControl` to PowerShell's higher-level `Get-Acl` / `Set-Acl` cmdlets. With proper read access, the actual ACL revealed itself — **five accumulated explicit rules** from the prior scripts:

```
[EXP] Everyone                   Allow  FullControl    ← forensic script
[EXP] Everyone                   Allow  -1             ← forensic script (inherit-only)
[EXP] NT AUTHORITY\SYSTEM        Allow  FullControl    ← repair script
[EXP] BUILTIN\Administrators     Allow  ReadKey        ← repair script
[EXP] NT SERVICE\TrustedInstaller Allow FullControl    ← repair script
```

Rather than mutating the existing ACL (the path that had compounded the problem), v2 built a **fresh `RegistrySecurity` from scratch** with exactly the two intended rules and `Set-Acl`'d it.

### Final state on disk

```
Owner:                   SAKURA\thisg
Group:                   NT AUTHORITY\SYSTEM
AreAccessRulesProtected: True
SDDL:                    O:S-1-5-21-6171199-3533007890-1112070463-1001G:SY
                         D:PAI(A;CI;KA;;;SY)(A;CI;KA;;;S-1-5-21-6171199-3533007890-1112070463-1001)
Access entries:
  [EXP] NT AUTHORITY\SYSTEM    Allow  FullControl
  [EXP] SAKURA\thisg           Allow  FullControl
```

**SDDL decode**:
- `O:S-1-5-21-...` — owner = SAKURA\thisg
- `G:SY` — primary group = SYSTEM
- `D:PAI` — DACL is **P**rotected (no parent inheritance) and **AI** (auto-inherited flag set by Windows after `Set-Acl`)
- `(A;CI;KA;;;SY)` — Allow, ContainerInherit, KeyAllAccess to SYSTEM
- `(A;CI;KA;;;S-1-5-21-...)` — Allow, ContainerInherit, KeyAllAccess to SAKURA\thisg

This **differs from the Windows default** for SPP keys (which is TrustedInstaller-only) by design. On a single-user machine where the user holds full responsibility for what runs on the system, "the human + the OS itself, nobody else" is a tighter and more semantically honest protection than the default group-based pattern.

**Compatibility with SPP function**: SYSTEM FullControl is preserved → `sppsvc.exe` continues to read/write tokens normally → Windows activation remains functional. TrustedInstaller can re-take ownership via `SeTakeOwnership` if Windows Update genuinely needs to update the SPP store — it just won't have ambient access between those moments.

---

## Reusable Patterns Worth Keeping

Four patterns from this exercise are reusable across future protected-key work:

### 1. Take-own / read / restore with try/finally

The shape from `spp_forensic.ps1` (snapshot SDDL → take ownership → grant FC → read → restore in `finally` → verify) is the safe template for inspecting any protected registry key. The `finally` block placement is the critical detail: even on read exceptions, the ACL gets restored.

### 2. Prefer `Get-Acl` / `Set-Acl` over raw `.NET RegistryKey` in PS 7

`OpenSubKey + GetAccessControl` requires every relevant access right to be present on the handle for the property to populate; in PS 7 missing rights silently return empty fields rather than throwing. `Get-Acl` / `Set-Acl` handle the access-rights dance internally and surface diagnostics cleanly. Use the cmdlet path for any ACL work in PS 7.

### 3. Build fresh ACLs instead of mutating existing ones

When the goal is "I want this exact set of rules and nothing else," constructing a new `RegistrySecurity` from scratch and `Set-Acl`'ing it is more reliable than reading existing rules and removing the ones you don't want. The mutation path can compound errors (especially when the read returns partial data); the fresh-construction path produces a known-state output regardless of input state.

### 4. Cross-host PowerShell pause primitives

For scripts launched via auto-elevation (`Start-Process -Verb RunAs`) that need to pause for screenshotting:
- `[System.Console]::ReadKey($true)` works in real consoles but throws `Cannot read keys when ... console input has been redirected` in non-console hosts (e.g., spawned from another script's stdout-redirected pipeline)
- `Read-Host "Press Enter to close"` is universally available — accepts any input line followed by Enter, gracefully falls back when no console exists

Wrap with `try { ConsoleReadKey } catch { Read-Host }` for the best of both: strict-Enter-only behaviour when a real console is present, line-input fallback when not.

### 5. Pause on error, not just on success

A `trap { ... pause ... }` block at the top of any elevated script catches unhandled errors and pauses *before* the window closes — without this, error output flashes and disappears, requiring a re-run just to read the diagnostic. Essential for scripts spawned from another process's `-Wait` invocation.

---

## Artifacts Inventory

All artifacts from this investigation live in `Documents/Data/` unless noted:

| File | What it is |
|---|---|
| `spp_forensic.ps1` | The dump script — take-own, read, restore (restore failed) |
| `spp_acl_cleanup.ps1` | Initial cleanup attempt — filter missed Everyone rule |
| `spp_acl_repair.ps1` | Repair attempt — added TI/SYSTEM/Admins rules, hit PS 7 quirk |
| `spp_acl_lockdown.ps1` | v1 lockdown — null-iteration bug on degenerate collection |
| `spp_acl_lockdown_v2.ps1` | **Final working lockdown** — fresh-from-scratch ACL via Get-Acl/Set-Acl |
| `spp_forensic.log` | Transcript of the forensic dump run |
| `spp_acl_cleanup.log` | Transcript of the cleanup attempt |
| `spp_acl_repair.log` | Transcript of the repair attempt |
| `spp_acl_lockdown.log` | v1 lockdown error transcript |
| `spp_acl_lockdown_v2.log` | v2 lockdown success transcript |
| `spp_forensic_acl_backup.sddl` | Captured original SDDL (partial — owner+group only, no DACL) |
| `notifyicon_*_backup_*.reg` | Per-key backups of NotifyIconSettings entries we modified during the icon pipeline pivot |
| `notifyicon_orphans_backup_2026-05-10.reg` | The 4 orphaned NotifyIconSettings entries cleaned up |
| `identity_cache_backup_2026-05-10.reg` | NotifyIconSettings + FeatureUsage records from earlier sweep |
| **`C:\spp_forensic_dump.txt`** | **The actual structure dump** (lives at C:\ root — earlier script revision used relative path, modern revisions write to `Documents/Data/`) |

The `C:\spp_forensic_dump.txt` path quirk is preserved as an artifact of the actual run — a future re-dump using the current script would land in `Documents/Data/spp_forensic_dump.txt` per the updated `$OutputFile` parameter default.

> **On the `.log` files**: every script produces a transcript log alongside its operation (`spp_forensic.log`, `spp_acl_cleanup.log`, etc.). These exist on the local machine but are excluded from the repository by the global `~/.gitignore_global` pattern `*.log` — application logs shouldn't bloat the repo, and a forensic re-run regenerates equivalent transcripts. The `.ps1` scripts and `.reg` backups are the durable artifacts; the logs are local witnesses to specific runs.

---

## Verification — Confirming SPP Still Works

Sanity checks performed after lockdown:

- `Get-Acl` of the SPP key shows exactly 2 explicit ACEs (verified — see `spp_acl_lockdown_v2.log`)
- SDDL string verifies as `D:PAI` (protected, auto-inherited flag) with two `(A;CI;KA;...)` entries
- SYSTEM FullControl preserved → `sppsvc.exe` operations remain functional
- No verification of activation status (Settings › System › Activation) was performed at the time but is the immediate test if any doubt arises

Open this in Settings if ever in doubt: **Settings → System → Activation → "Windows is activated"** should display normally. If it instead shows "not activated" or an error code referencing token retrieval, the lockdown's DACL is the first place to check — confirm SYSTEM still has FullControl and the DACL hasn't been further mutated.

---

## What This Document Doesn't Cover

The icon-pipeline work that happened in the same session lives in `Documents/Design/Icon Pipeline.md` — the brand-mark refresh chain, Personalization > Taskbar panel data sources, the `_heal_systray_panel_metadata()` self-heal in `main_window.py`. Some artifacts in `Documents/Data/` (notifyicon backups, etc.) belong to both threads; they're listed in both docs but are physically one set of files.

The decision to keep two docs rather than one: registry archaeology and icon pipeline are different problem domains that happened to share an evening. A reader auditing the SPP key's state shouldn't have to wade through panel-icon investigation to find the ACL repair history. A reader debugging the icon pipeline shouldn't get derailed by SPP token vault internals. Two docs, one clear scope each.
