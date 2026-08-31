# Migration Source

- Migration date: 2026-08-31
- Source repository: `D:\test\select_stocks`
- Source worktree: `D:\test\select_stocks\.worktrees\resonance-no-atr-exit`
- Source branch: `codex/resonance-no-atr-exit`
- Strategy/test content baseline: `5e81c07`
- Approved migration-design source commit: `f4053de`
- Migration method: Git archive of the frozen content baseline plus byte-identical copy of the approved migration design.

## Verification

- Baseline file-set comparison: PASS
- Baseline SHA-256 comparison: PASS
- Migration-design SHA-256 comparison: PASS
- Python scope assertion: PASS
- Python compilation: PASS
- Pytest discovery scope: PASS
- Dedicated resonance tests: `502 passed, 3 skipped`
- Source worktree unchanged: PASS

## Reproduction Commands

Run the following commands in PowerShell. The audit ZIP path must not already exist.

```powershell
$sourceRoot = 'D:\test\select_stocks\.worktrees\resonance-no-atr-exit'
$targetRoot = 'D:\test\resonance_reversal_strategy'
$auditZip = 'C:\Users\C1-CWadmin\AppData\Local\Temp\resonance-standalone-audit-5e81c07.zip'
$designAuditZip = 'C:\Users\C1-CWadmin\AppData\Local\Temp\resonance-standalone-audit-f4053de.zip'

if (Test-Path -LiteralPath $auditZip) { throw 'baseline audit ZIP already exists' }
if (Test-Path -LiteralPath $designAuditZip) { throw 'design audit ZIP already exists' }

git -C $sourceRoot -c core.autocrlf=true archive --format=zip --output=$auditZip 5e81c07 -- `
    resonance_reversal_strategy `
    tests/test_resonance_reversal_strategy.py `
    tests/test_resonance_relative_turn_analysis.py `
    tests/test_resonance_trade_risk_analysis.py
git -C $sourceRoot -c core.autocrlf=false archive --format=zip --output=$designAuditZip f4053de -- `
    resonance_reversal_strategy/docs/superpowers/specs/2026-08-31-standalone-project-migration-design.md

# The baseline was originally exported with core.autocrlf=true.
# The design was copied byte-for-byte from an LF worktree file whose Git blob is f4053de,
# so its frozen-commit audit disables checkout conversion.

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipFile = [System.IO.Compression.ZipFile]::OpenRead($auditZip)
$designRelative = 'resonance_reversal_strategy/docs/superpowers/specs/2026-08-31-standalone-project-migration-design.md'
$allowedNew = @('.gitignore', 'AGENTS.md', 'MIGRATION_SOURCE.md', 'pytest.ini', $designRelative)
try {
    $archiveFiles = @(
        $zipFile.Entries |
            Where-Object { $_.Name -ne '' } |
            ForEach-Object { $_.FullName.Replace('\', '/') } |
            Sort-Object
    )
} finally {
    $zipFile.Dispose()
}
$targetBaselineFiles = @(
    Get-ChildItem -LiteralPath $targetRoot -Recurse -File |
        ForEach-Object {
            $_.FullName.Substring($targetRoot.Length + 1).Replace('\', '/')
        } |
        Where-Object {
            -not $_.StartsWith('.git/') `
            -and -not $_.StartsWith('.pytest_cache/') `
            -and -not $_.Contains('/__pycache__/') `
            -and $allowedNew -notcontains $_
        } |
        Sort-Object
)
if (@(Compare-Object $archiveFiles $targetBaselineFiles).Count -ne 0) {
    throw 'baseline file sets differ'
}

$zipFile = [System.IO.Compression.ZipFile]::OpenRead($auditZip)
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    foreach ($entry in @($zipFile.Entries | Where-Object { $_.Name -ne '' })) {
        $entryStream = $entry.Open()
        try {
            $sourceHash = [BitConverter]::ToString(
                $sha256.ComputeHash($entryStream)
            ).Replace('-', '').ToLowerInvariant()
        } finally {
            $entryStream.Dispose()
        }
        $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (
            Join-Path $targetRoot $entry.FullName
        )).Hash.ToLowerInvariant()
        if ($sourceHash -ne $targetHash) {
            throw "baseline hash mismatch: $($entry.FullName)"
        }
        $sha256.Initialize()
    }
} finally {
    $sha256.Dispose()
    $zipFile.Dispose()
}

$designZipFile = [System.IO.Compression.ZipFile]::OpenRead($designAuditZip)
$designSha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $designEntry = $designZipFile.GetEntry($designRelative)
    if ($null -eq $designEntry) { throw 'design entry missing from f4053de' }
    $designStream = $designEntry.Open()
    try {
        $sourceDesignHash = [BitConverter]::ToString(
            $designSha256.ComputeHash($designStream)
        ).Replace('-', '').ToLowerInvariant()
    } finally {
        $designStream.Dispose()
    }
} finally {
    $designSha256.Dispose()
    $designZipFile.Dispose()
}
$targetDesignHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (
    "$targetRoot\resonance_reversal_strategy\docs\superpowers\specs\2026-08-31-standalone-project-migration-design.md"
)).Hash.ToLowerInvariant()
if ($sourceDesignHash -ne $targetDesignHash) {
    throw 'migration design hash mismatch'
}

Push-Location $targetRoot
try {
    python -m py_compile `
        resonance_reversal_strategy/smart_trade_joinquant_resonance_reversal_etf.py `
        resonance_reversal_strategy/research/analyze_relative_turn_observations.py `
        resonance_reversal_strategy/research/analyze_resonance_trade_risk.py
    if ($LASTEXITCODE -ne 0) { throw 'compilation failed' }
    pytest --collect-only -q
    if ($LASTEXITCODE -ne 0) { throw 'pytest collection failed' }
    pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed' }
    if ((git status --short).Length -ne 0) { throw 'target worktree is dirty' }
} finally {
    Pop-Location
}
if ((git -C $sourceRoot status --short).Length -ne 0) {
    throw 'source worktree is dirty'
}

Remove-Item -LiteralPath $auditZip, $designAuditZip
```

No JoinQuant backtest was run during migration. The migrated strategy and research content remains byte-identical to the recorded sources.
