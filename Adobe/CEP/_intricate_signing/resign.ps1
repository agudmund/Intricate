# ─────────────────────────────────────────────────────────────────────────────
#  Intricate Bridge -- CEP extension re-sign helper
#
#  Run after any edit to the CEP extension (index.html, script.jsx, manifest.xml,
#  etc.) so Premiere Pro 2026 accepts the modified files.  Premiere enforces
#  signature verification on panel instantiation even with PlayerDebugMode=1,
#  and the signature hashes the file contents -- any edit invalidates it.
#
#  Usage:
#    powershell -File %APPDATA%\Adobe\CEP\_intricate_signing\resign.ps1
#
#  Requires the Intricate_BridgeCertPw environment variable to be set
#  (the .p12 password). Set it once per user via:
#    setx Intricate_BridgeCertPw <password>
#  Then open a fresh terminal so the variable is in scope.
#
#  After this script completes, close the Intricate Bridge panel in Premiere
#  (if open) and re-open it from Window -> Extensions to load the new code.
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = 'Stop'

$signingDir = "$env:APPDATA\Adobe\CEP\_intricate_signing"
$extDir     = "$env:APPDATA\Adobe\CEP\extensions\com.intricate.bridge"
$exe        = "$signingDir\ZXPSignCmd.exe"
$cert       = "$signingDir\intricate_dev.p12"
$zxp        = "$signingDir\intricate_bridge.zxp"
# Cert password is read from the environment, not committed to the repo.
# A previous version of this file shipped the password in plaintext on
# this line — public/private repos both leak, so the cert password lives
# outside source control as a matter of policy.
$pw         = $env:Intricate_BridgeCertPw

if (-not $pw) {
    throw "Intricate_BridgeCertPw environment variable is not set. " +
          "Set it via 'setx Intricate_BridgeCertPw <password>' and open " +
          "a fresh terminal before re-running this script."
}
if (-not (Test-Path $exe))  { throw "ZXPSignCmd.exe missing at $exe" }
if (-not (Test-Path $cert)) { throw "cert missing at $cert -- regenerate with -selfSignedCert" }
if (-not (Test-Path $extDir)) { throw "extension folder missing at $extDir" }

Write-Host "=== removing stale META-INF + stale zxp ==="
if (Test-Path "$extDir\META-INF") { Remove-Item "$extDir\META-INF" -Recurse -Force }
if (Test-Path $zxp)                { Remove-Item $zxp -Force }

Write-Host "=== signing extension folder -> zxp ==="
& $exe -sign $extDir $zxp $cert $pw
if ($LASTEXITCODE -ne 0) { throw "sign failed (exit $LASTEXITCODE)" }

Write-Host "=== extracting zxp back over extension folder ==="
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
# PS5 / .NET Framework 4.x lacks ExtractToDirectory(overwrite); iterate entries
# manually so we can overwrite collisions on re-sign cycles.
$archive = [System.IO.Compression.ZipFile]::OpenRead($zxp)
try {
    foreach ($entry in $archive.Entries) {
        $targetPath = Join-Path $extDir $entry.FullName
        if ($entry.FullName.EndsWith('/') -or $entry.FullName.EndsWith('\')) {
            New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
            continue
        }
        $targetDir = Split-Path $targetPath -Parent
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $targetPath, $true) | Out-Null
    }
} finally {
    $archive.Dispose()
}

Write-Host "=== verifying ==="
& $exe -verify $extDir
if ($LASTEXITCODE -ne 0) { throw "verify failed (exit $LASTEXITCODE)" }

Write-Host ""
Write-Host "DONE -- close and re-open the Intricate Bridge panel in Premiere."
