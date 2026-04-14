# Python Header Compliance Guide

This document describes the dual-layer validation system for ensuring all Python files in the Intricate nodal playground project have compliant headers, as required by project standards and Copilot instructions.

## Purpose and Scope
- Ensure every Python file has the required three-line docstring header, with the second line ending in "for enjoying".
- Prevent non-compliant files from being committed or pushed.
- Provide a reference for contributors and automation.

## Required Header Format
```
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - [filename] [primary utility]
-[Extended description of what the module does] for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""
```

## Pre-Commit Hook (Local Validation)
- File: `.git/hooks/pre-commit` (PowerShell, no extension)
- Blocks any commit if a staged Python file is missing the required header or 'for enjoying'.

```
$ErrorActionPreference = "Stop"
$files = git diff --cached --name-only --diff-filter=ACM | Where-Object { $_ -like "*.py" }
$headerPattern = '#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n"""'

foreach ($file in $files) {
    $content = Get-Content $file -Raw
    if (-not ($content -match [regex]::Escape($headerPattern)) -or -not ($content -match 'for enjoying')) {
        Write-Host "❌ $file is missing the required header or 'for enjoying'. Please fix before committing."
        exit 1
    }
}
Write-Host "✅ All Python files have the required header."
exit 0
```

## CI/CD Compliance Check (Remote/Team Validation)
- File: `tools/header_check.py`
- Run this script in your CI pipeline before any push to the remote repository.
- Fails the build if any Python file is non-compliant.

```
import sys
from pathlib import Path

REQUIRED_HEADER = [
    '#!/usr/bin/env python3',
    '# -*- coding: utf-8 -*-',
    '"""',
    '-Intricate nodal playground - ',
    '-',
    '-Built using a single shared braincell by Yours Truly and various Intelligences'
]

def check_header(path):
    with open(path, encoding='utf-8') as f:
        lines = [f.readline().rstrip() for _ in range(5)]
    if not lines[0] == REQUIRED_HEADER[0]: return False
    if not lines[1] == REQUIRED_HEADER[1]: return False
    if not lines[2] == REQUIRED_HEADER[2]: return False
    if not lines[3].startswith(REQUIRED_HEADER[3]): return False
    if not lines[4].endswith('for enjoying'): return False
    return True

failures = []
for py in Path('.').rglob('*.py'):
    if not check_header(py):
        failures.append(str(py))

if failures:
    print('Non-compliant files:')
    for f in failures:
        print(' -', f)
    sys.exit(1)
else:
    print('All Python files have compliant headers.')
```

## Best Practices
- Always use Copilot or the provided templates for new Python files.
- Never bypass the pre-commit hook.
- Review CI/CD results for compliance before merging or pushing.
- Update this guide and the compliance scripts if header standards change.
