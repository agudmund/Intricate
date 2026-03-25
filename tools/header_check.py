#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - tools/header_check.py header compliance script
-Checks all Python files for compliant headers for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import sys
from pathlib import Path

# Files with known intentional header deviations — excluded from compliance checks
KNOWN_EXCEPTIONS = {
    'widgets/PrettyButton.py',
    'widgets\\PrettyButton.py',
}

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
    if str(py) in KNOWN_EXCEPTIONS:
        continue
    if not check_header(py):
        failures.append(str(py))

if failures:
    print('Non-compliant files:')
    for f in failures:
        print(' -', f)
    sys.exit(1)
else:
    print('All Python files have compliant headers.')
