# Copilot Instructions

## Project Guidelines
- User prefers markdown list formatting without tabs/indentation - use simple dashes at line start (e.g., "- item") rather than tabbed bullets for cleaner, more standard markdown.
- This is a Python project (Nodal - a node-based UI application using PySide6). It does not require compilation. Do not ask about or suggest running build commands, compilation steps, or language-specific build tools. Python syntax can be verified with `python -m py_compile` if needed, but this is a runtime language, not a compiled one.
- For all new Python files in the Nodal project, use the following file header format in docstring style:
  ```
  #!/usr/bin/env python3
  # -*- coding: utf-8 -*-
  """
  -Intricate nodal playground - [filename] [primary utility]
  -[Extended description of what the module does] for enjoying
  -Built using a single shared braincell by Yours Truly and various Intelligences
  """
  ```
  The three lines in the docstring are: file/purpose, extended description, and static credit line (with "Intelligences" capitalized, no comma before "and").
- All Python file headers must comply with the three-line docstring format as specified above, with the second line ending in "for enjoying".
- A compliance check script (e.g., tools/header_check.py) must be run in CI/CD before any push to the remote repository.
- Copilot and all contributors must ensure header compliance before every commit and push.
- Before any git push, always run the compliance check script (tools/header_check.py) to ensure all Python file headers are compliant. The push should only proceed if the script passes with no errors. This check is required even if pre-commit hooks are present, to ensure platform-agnostic and reproducible compliance.
- When refactoring Nodal's node system, align with the existing BaseNode implementation in the Cozy Times project: use `QGraphicsRectItem`, implement resize handles in the bottom-right corner, add smooth port toggle animations, include hover scale pulse effects, and use `paint_content()` for type-specific rendering instead of overriding `_paint_text()`.
- User prefers camelCase for Python attribute/constant names (e.g., windowBorderWidth, accentSelected) but prefers "Capitalised Names With Spaces" (title case with spaces) in text documents, markdown files, and documentation (e.g., "Window Border Width", "Accent Selected"). This naming convention distinction should be applied to all future refactoring, documentation, and code style guidance.

## Documentation Standards
- All external documentation (reports, audits, summaries, analysis documents) must be stored in the `./Documents/` folder at the project root.
- Exception: README.md must remain in the project root as a default GitHub repository file.
- Documentation files should use "Title Case With Spaces" naming convention (e.g., "Final Theme Refactoring Report.md", "Docstring Compliance Report.md").
- Documentation is generated for significant refactoring work, audits, and verification processes.
- Each document should include a brief summary at the top explaining its purpose and scope.
- Documentation serves as historical reference and verification records for major code changes.

## Git Integration
- User has GitHub repository set up and linked to their Visual Studio project with Git integration working. For future sessions, remember that Git is already configured and working - no need to ask about initialization or remote setup. Just proceed with git commands via terminal.
- Git workflow: Commit changes locally automatically after implementation, but ONLY push to remote GitHub when user explicitly asks. This preserves GitHub as a stable revert point. Do not auto-push - wait for user approval.

## Terminal Commands
- Always use PowerShell commands exclusively. Do not use Unix/bash commands. The development environment is Windows-based with PowerShell as the shell.

## Logging
- Use COZYLOG as the default global log location across the solution; fall back to relative ./logs only when COZYLOG is not set.