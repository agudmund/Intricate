# CodeNode — Syntax-Highlighted Code Display Node

## Context
User wants a code-viewing node that displays text with colored syntax highlighting, similar to the screenshot showing Python code with colored keywords, strings, functions, and comments. Based on the TextNode pattern with a monospace font and a QSyntaxHighlighter applied to the editor widget.

## Approach
Clone TextNode + attach a QSyntaxHighlighter to PrettyEdit's document. The highlighter applies color rules for common syntax tokens (keywords, strings, comments, numbers, functions, decorators). Monospace font (`Consolas`) instead of Lato.

## Files to Create
1. **`data/CodeNodeData.py`** — clone of TextNodeData, `node_type="code"`
2. **`nodes/CodeNodeData.py`** — delete, wrong path
3. **`nodes/CodeNode.py`** — clone of TextNode, swaps font to monospace, attaches `CodeHighlighter(QSyntaxHighlighter)` to the editor's document
4. **`icons/make_code_icon.py`** + generated `.ico`/`.png` — code bracket icon `< />`

## Files to Modify
5. **`graphics/Scene.py`** — add `add_code_node()` factory + restore case for `"code"`
6. **`main_window.py`** — add `_spawn_code_node()` + menu entry in Text category
7. **`settings.toml`** — register `code = "code_node.ico"` icon

## CodeHighlighter Design
Inline class inside CodeNode.py (no separate file — single use). Color palette matching the screenshot:
- **Keywords** (`def`, `for`, `if`, `import`, `from`, `return`, `class`, etc.) — blue/purple
- **Strings** (single/double/triple quoted) — green/yellow
- **Comments** (`#`) — gray
- **Numbers** — orange
- **Function names** (after `def`) — yellow/gold
- **Decorators** (`@xxx`) — cyan
- **Built-in constants** (`True`, `False`, `None`, `self`) — magenta/pink

Colors will be warm-toned to match the app's dark theme aesthetic.

## Key Implementation Details
- Font: `Consolas` (monospace), falls back to system monospace
- Editor: PrettyEdit with `always_visible=True`, same as TextNode
- Highlighter attached via `CodeHighlighter(self._editor.document())`
- Read/write — user can paste code and edit it
- No language detection needed — generic multi-language highlighting covers Python, JS, C-like syntax

## Verification
1. Launch app, open Text sidebar category, click "The Code Node"
2. Paste Python code — keywords, strings, comments should be colored
3. Resize node — editor reflows
4. Save/reload session — code persists
5. Toggle depth — background changes
