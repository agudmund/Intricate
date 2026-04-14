# Create New Session from project selector

## Context
Sessions currently come from scanning ~/Desktop/ folders, but there's no way to create a new one from within the app. Need a "Create New Session" entry at the bottom of the project selector combo box that prompts for a name and sets up the folder structure.

## Approach

### main_window.py changes only

1. **Add sentinel entry** — append `"+ New Session"` as the last item in `populate_sessions()` after the folder list

2. **Intercept in `on_session_changed()`** — if the selected text is the sentinel:
   - Show a simple `QInputDialog.getText()` asking for the session name
   - If confirmed and non-empty:
     - Create `~/Desktop/{name}/Documents/data/` via `ensure_dir()`
     - Block signals, repopulate the combo, select the new project, unblock
     - Let the normal session switch flow handle the rest (swap scene, load empty session)
   - If cancelled:
     - Block signals, restore the previous selection, unblock

3. **No new files needed** — `ensure_dir` + the existing autosave flow handles folder creation and first session.json write automatically

## Key details
- Disconnect combo signal before repopulating to avoid recursive triggers
- The sentinel entry should be visually distinct (the `+` prefix)
- Empty/whitespace names rejected
- Duplicate folder names rejected (folder already exists)
- After creation, `_active_project` is set to the new name

## Verification
- Click "+" entry → dialog appears
- Enter name → folder created on Desktop, clean canvas loads
- Cancel → returns to previous session
- Enter existing name → rejected
- Autosave writes session.json to new folder
