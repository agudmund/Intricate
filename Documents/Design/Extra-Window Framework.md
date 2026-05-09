# Extra-Window Framework

Intricate's spatial canvas runs on a Z-depth workflow — frameless, always-on-top, the OS's native windows visible through transparency, every node and sticker compositing over the desktop the user is already in. Popups are alien to that worldview. They obstruct the depth, they break the calm, they demand instead of invite. So Intricate has almost none of them.

But every now and then a moment genuinely needs one — naming a new session before it can be created, composing a commit message before a bulk push lands, browsing for a file when one hand isn't free for drag-and-drop. The framework documented here is what turns those rare exceptions into ceremonies that hold their ground gracefully, then leave.

## The 30-second rule

> *"There will not be any floating windows that exist for more than 30 seconds. If so that would be a case for a separate app since it's something that stays on the screen and is therefore a first-class citizen with its own ceremonies."*

Lifetime is the threshold. Anything that needs to stay open longer than the address-and-dismiss window gets promoted out of the popup category and into its own sideloaded app. The Settlers, The Majestic, Pebbles — each was a popup that grew, and the right answer was always to move it out, not to make the popup more accommodating. Drag-aside, minimise-to-corner, multi-tab — none of those affordances belong on an Intricate popup. Adding them would undermine the contract.

## The popup pattern

> *"I'm here > Address this > Thank You > Come Again > Done."*

Every Intricate popup follows this shape. It enters at screen centre, on top of every other window. The user addresses what it asks. It thanks them and leaves. Pinning is the point — the popup is the only thing that matters during its 30 seconds, and parking it out of the way would say *"never mind, do this later"*, which is exactly the wrong message for a moment that's earned its rare interruption.

## Two halves

The framework splits into two responsibilities. The split is what lets each half stay simple while their composition handles the full Windows-foreground discipline:

| Half | Concern | Lives in | Inherits as |
|---|---|---|---|
| **WHEN** | Curtain dance + HWND settle while the popup spawns | `nodes/_dialog_helper.py` | `_DialogChoreographyMixin` |
| **HOW** | Screen centring + topmost-band defence once the popup is shown | `pretty_widgets/PrettyDialog.py` | `PrettyDialog` |

The WHEN-half is Intricate-specific (it knows about curtain animations, `is_collapsed`, `toggle_curtains` — concepts that only make sense inside this app). The HOW-half is universal (any Qt-managed popup wants to land centred and assert topmost dominance) and therefore lives in the shared Pretty Widgets package so other family apps inherit it for free when they introduce their first ceremony popup.

## The choreography (`_DialogChoreographyMixin`)

Three classes inherit the mixin: `BaseNode`, `ChromelessRoot`, and `IntricateApp`. They reach the main window via a single extension point — `_get_main_window()` — which the default implementation walks via `self.scene().views()[0].window()` (correct for any QGraphicsItem on the canvas) and `IntricateApp` overrides with a one-line `return self`. The mixin is context-agnostic; subclasses tell it where the main window lives.

Inside the mixin, three settle-points are load-bearing for Windows-foreground reliability. They earn their place in the order they fire:

### Settle 1 — drain HWND-recreation aftermath

`setWindowFlags` inside `_drop_topmost()` clears `Qt.WindowStaysOnTopHint`, and on Windows that flag-flip recreates the native HWND. Without an immediate `processEvents()` drain right after the flip, the recreation events stack up behind the curtain animation and the dialog spawn — the dialog ends up parented to a not-yet-foregrounded HWND, and Windows silently refuses to surface it. The user sees the curtains roll up and then nothing happens. This was the first-run "dialog never appears" bug that triggered the framework's first extraction; the drain breaks the stack-up so the HWND is settled before any further choreography begins.

### Settle 2 — wait for the curtain animation to finish

The curtain roll is roughly 539 ms. If the dialog spawns mid-animation, Windows refuses to promote it to foreground while the parent HWND is in animated flight, and the dialog opens behind whatever else holds foreground state. The mixin blocks on `curtain_anim.finished` via a nested `QEventLoop`. Two safeties live here:

1. **Connect-before-state-check.** The slot is connected to `loop.quit` *before* the animation state is inspected, so a fast finish between the attribute access and the state read can't leave the mixin listening for a signal that already fired.
2. **Dynamic safety timeout.** A `QTimer.singleShot(max(1500, anim.duration() * 3), loop.quit)` quits the loop if `finished` is missed entirely (e.g. animation interrupted without emitting). The `* 3` ratio scales the safety with the curtain anim's actual duration; the 1500 ms floor guards against a momentarily zero-duration animation collapsing the safety to nothing.

### Settle 3 — drain after activate/raise

`activateWindow()` is a request, not an immediate effect — Windows may delay the actual activation until pending events drain. A second `processEvents()` flushes pending events so the activation has actually landed before the dialog spawns. Without this, the same race that Settle 1 closes can re-open at a slightly later point in the choreography.

### `_saved_flags_stack`

The mixin pushes the original `windowFlags` onto an instance-level stack on every `_drop_topmost()` and pops on every `_restore_topmost()`. Nested choreography (a future feature that branches dialog flow off another dialog flow) restores LIFO without the inner call clobbering the outer's saved state. A flat single-attribute save would silently lose `WindowStaysOnTopHint` on the outer's exit; the stack closes that door before any nested flow ever exists.

## The ceremony popup base (`PrettyDialog`)

A `QDialog` subclass with three small, load-bearing features baked into `showEvent`:

```python
def showEvent(self, event):
    super().showEvent(event)
    self._center_on_screen()
    self._assert_topmost_if_platform()
    self.activateWindow()
    self.raise_()
```

### Explicit screen centring

Qt's default positioning for a `QDialog` with a parent is *centre on the parent*. If the parent main window is in a transient state during the choreography — most notably the *collapsed-curtain* state, where it shrinks to a thin strip at the top of the screen — Qt would centre the dialog on that thin strip and the dialog would land flat against the title bar instead of in the middle of the canvas. `_center_on_screen` overrides this by reading the screen geometry directly, preferring the parent's screen for multi-monitor honesty, falling back to the primary screen, and using `availableGeometry` so the centring excludes the OS taskbar.

### Cross-OS topmost-band defence

`Qt.WindowStaysOnTopHint` puts the dialog in the Windows topmost z-order band. Within that band, the most recent `SetWindowPos` wins — and Chrome's YouTube picture-in-picture also sits in the topmost band. Without active defence, a Chrome PiP window started before the dialog can win the band race, leaving the dialog visually present but stacked beneath PiP. `_win32_set_topmost` re-asserts `HWND_TOPMOST` via Win32 `SetWindowPos` *after* Qt finishes showing, so the dialog lands at the *top* of the band.

The defence sits behind an `_assert_topmost_if_platform` hook so macOS and Linux fall through to Qt-native behaviour by default. The hook is the expansion point if a per-OS defence ever proves needed (`NSWindow.level` on macOS, `_NET_WM_STATE_ABOVE` on X11/Wayland) without changing the consumer-facing API.

### Activate + raise

Final foreground assertion. After centring and topmost defence, an explicit `activateWindow()` + `raise_()` ensures the dialog has keyboard focus and is visually on top. Belt-and-braces — by this point the topmost defence has already done most of the work, but the explicit calls are the cheapest possible reinforcement.

## Composition

The two halves compose at the call site:

```python
with self._dialog_choreography() as mw:
    dlg = MyCeremonyDialog(parent=mw)
    result = dlg.exec()
```

The choreography handles WHEN — drops the always-on-top flag, waits for the curtain to settle, focuses the main window so the dialog parents to a real foreground HWND. `PrettyDialog`'s `showEvent` handles HOW — centres on screen, asserts topmost, activates and raises. On exit, the choreography rolls the curtain back down and restores the always-on-top flag from the LIFO stack.

A single `with` block covers the full Windows-foreground discipline. The subclass author writes only what the dialog *is* (visual chrome, layout, content, signal connections); the framework owns *when* it appears and *how* it holds its ground.

## Native vs custom — the decision

Two valid categories of Qt-managed dialog co-exist with native OS dialogs:

1. **Utility wrapping a custom QDialog where native fits** — *don't*. A custom Qt file picker that replicates Explorer or Finder is a Z-depth regression masquerading as visual consistency. The native picker harmonises with Intricate's transparency-driven workflow (Explorer windows visible *through* the canvas as a free side effect of the OS-native dialog), and switching to custom Qt would break that cross-OS harmony for nothing.
2. **Ceremony where the dialog IS the moment** — *do*. Inheriting `PrettyDialog` and giving it bespoke visual chrome is right when the dialog isn't a wrapper but a ritual. *Naming* a new session is a creative act; *composing* a commit message is a deliberate punctuation.

The test: would a native input prompt feel *cheap* here, like the moment was being papered over? If yes, custom Qt is right. If a native equivalent would do the job without losing anything, prefer native.

Native dialogs (`QFileDialog`, `QInputDialog`, `getExistingDirectory`) only need the choreography mixin; they're owned by the OS shell and defend their own positioning via the OS's rules. Wrap them in `with self._dialog_choreography() as mw:` and pass `mw` as the parent.

## Current consumers

| Dialog | Class | File | Inherits |
|---|---|---|---|
| Bulk-push commit message | `_CommitDialog` | `nodes/GitNode.py` | `PrettyDialog` |
| New-session naming ("Name your next masterpiece") | `_NewSessionDialog` | `main_window.py` | `PrettyDialog` |
| Native file pickers (CodeNode, ImageNode, VideoNode, AudioNode, SequenceNode, StickerNode) | `QFileDialog` (no subclass) | various nodes | choreography only, no PrettyDialog |

`_CommitDialog` and `_NewSessionDialog` are the two ceremony popups that earned their place. Both spawn from inside the choreography (GitNode via `with self._dialog_choreography() as mw:`, `_create_new_session` via the same after the IntricateApp / mixin migration), and both inherit `PrettyDialog` for the show-time discipline.

## Adding a new ceremony popup

Recipe for the rare moment a third ceremony earns its 30 seconds:

1. **Confirm the 30-second rule.** Could this be a sideloaded app instead? A persistent state? An inline edit on the canvas? If yes to any, prefer that. Only proceed if the moment is genuinely brief and dominant.
2. **Confirm the ceremony test.** Would a native input prompt feel cheap here? If no, use a native dialog with the choreography only. If yes, build a `PrettyDialog` subclass.
3. **Subclass `PrettyDialog`** from `pretty_widgets.PrettyDialog`. The base auto-applies the shared visual chrome on `__init__` — frameless + translucent + topmost window flags, themed outer container (`Theme.windowBg` background, `Theme.primaryBorder` border, 9 px rounded corners), inner content layout with the canonical margins (16, 16, 16, 16) and spacing 12. No setup code needed unless you want a non-default value: override class constants like `_DEFAULT_FIXED_WIDTH = 480` per-dialog if the family default doesn't fit.
4. **Populate `self.content_layout`** with the dialog's content. The framework provides three helpers for the canonical shapes — `make_prompt_label(text)` for instruction text, `make_input(placeholder=, single_line=, spellcheck=)` for the text input, `make_button_row(cancel_label=, accept_label=)` for the Cancel + Accept row wired to `reject` / `accept`. A typical `__init__` is around a dozen lines:
   ```python
   class MyCeremony(PrettyDialog):
       def __init__(self, parent=None):
           super().__init__(parent)
           self.content_layout.addWidget(
               self.make_prompt_label("Name your next masterpiece:")
           )
           self._input = self.make_input(placeholder="something lovely…")
           self._input.committed.connect(lambda _t: self.accept())
           self.content_layout.addWidget(self._input)
           self.content_layout.addLayout(
               self.make_button_row(accept_label="Create")
           )
           self._input.setFocus()
   ```
5. **Spawn the dialog** from inside the choreography:
   ```python
   with self._dialog_choreography() as mw:
       dlg = MyCeremony(parent=mw)
       result = dlg.exec()
   ```
6. **Address the result** if accepted. The dialog leaves immediately on accept or cancel — the choreography restores curtains and always-on-top on exit.

## Relationship to other systems

- **Z-depth workflow** (`Documents/Design/Z-depth Workflow.md`-equivalent — captured in memory + Architecture). The framework exists *because* Intricate's spatial workflow makes popups exceptional. Native OS dialogs preserve the depth; custom Qt dialogs are reserved for ceremony moments where the dialog itself is the experience. See the saved memory `project_zdepth_workflow` for the full principle.
- **Curtain animation** (`main_window.py` toggle_curtains + curtain_anim). The choreography composes with the existing curtain mechanism — rolls up before the dialog spawns, rolls back down on exit. The 1500ms safety timeout floor + `* 3` dynamic scaling means the framework adapts if the curtain anim duration changes.
- **Pretty Widgets package** (`pretty_widgets.PrettyDialog`). The HOW-half lives in the shared widget package so Pebbles and Majestic inherit it directly when they introduce their first ceremony popup. Cross-repo: changes to `PrettyDialog` ship via Pretty Widgets version bumps.
- **Native OS dialogs**. The framework deliberately does NOT wrap native dialogs in any custom Qt chrome. Native is preferred for utility flows because it preserves the cross-OS harmony Intricate gets for free through transparency.

## Technical notes

- **The mixin is a pure-Python class**, not a `QObject` descendant. Multiple inheritance with Qt-derived parent classes (`QGraphicsRectItem`, `QMainWindow`) composes cleanly because there's no metaclass conflict — the Qt parent contributes the metaclass, the mixin contributes Python methods.
- **`_get_main_window`'s default catches `AttributeError, RuntimeError`** so a node not yet added to a scene returns `None` gracefully, and the choreography skips its scene-dependent steps without raising.
- **`_assert_topmost_if_platform` is the OS-aware boundary** — keep all platform-specific window manipulation behind it, so the rest of `PrettyDialog` stays portable.
- **Curtain anim duration is read from `mw.curtain_anim.duration()`** at the moment of safety-timeout calculation, not cached at framework init time, so a future runtime tweak to anim duration takes effect on the next dialog spawn without restart.
- **Logging**: `nodes/_dialog_helper.py` and `pretty_widgets/PrettyDialog.py` both expose a `setup_logger("dialog")` instance. The choreography's three exception-swallow paths and `_win32_set_topmost`'s failure path log at DEBUG with `exc_info=True`, so a production-relevant raise leaves a paper trail without spamming normal-flow logs.
