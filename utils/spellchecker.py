#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
-Intricate nodal playground - spellchecker.py spell checking with debounce
-Windows native spellchecker via COM ISpellChecker for enjoying
-Built using a single shared braincell by Yours Truly and various Intelligences
"""

import ctypes
import queue
import threading
from ctypes import POINTER, c_wchar_p, c_ulong
from PySide6.QtCore import QRegularExpression, QTimer, QObject, Signal
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QTextCursor
from PySide6.QtWidgets import QMenu

# ─────────────────────────────────────────────────────────────────────────────
# WINDOWS COM INTERFACE DEFINITIONS
# comtypes requires proper vtable interface types — raw GUIDs passed to
# QueryInterface cause "must be a ctypes type" errors. ISpellingError must be
# defined before IEnumSpellingError so the pointer type resolves correctly.
# ─────────────────────────────────────────────────────────────────────────────

try:
    import comtypes
    import comtypes.client
    from comtypes import GUID, HRESULT, IUnknown, COMMETHOD

    class ISpellingError(IUnknown):
        _iid_ = GUID('{B7C82D61-FBE8-4B47-9B27-6C0D2E0DE0A3}')
        _methods_ = [
            COMMETHOD(['propget'], HRESULT, 'StartIndex',       (['out', 'retval'], POINTER(c_ulong),   'value')),
            COMMETHOD(['propget'], HRESULT, 'Length',           (['out', 'retval'], POINTER(c_ulong),   'value')),
            COMMETHOD(['propget'], HRESULT, 'CorrectiveAction', (['out', 'retval'], POINTER(c_ulong),   'value')),
            COMMETHOD(['propget'], HRESULT, 'Replacement',      (['out', 'retval'], POINTER(c_wchar_p), 'value')),
        ]

    class IEnumSpellingError(IUnknown):
        _iid_ = GUID('{803E3BD4-2828-4410-8290-418D1D73C762}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'Next', (['out', 'retval'], POINTER(POINTER(ISpellingError)), 'value')),
        ]

    class IEnumString(IUnknown):
        _iid_ = GUID('{00000101-0000-0000-C000-000000000046}')
        _methods_ = [
            COMMETHOD([], HRESULT, 'Next',
                (['in'],  c_ulong,          'celt'),
                (['out'], POINTER(c_wchar_p), 'rgelt'),
                (['out'], POINTER(c_ulong),   'pceltFetched')),
            COMMETHOD([], HRESULT, 'Skip',  (['in'], c_ulong, 'celt')),
            COMMETHOD([], HRESULT, 'Reset'),
        ]

    class ISpellChecker(IUnknown):
        _iid_ = GUID('{B6FD0B71-E2BC-4653-8D05-F197E412770B}')
        _methods_ = [
            COMMETHOD(['propget'], HRESULT, 'LanguageTag',
                (['out', 'retval'], POINTER(c_wchar_p), 'value')),
            COMMETHOD([], HRESULT, 'Check',
                (['in'],          c_wchar_p,                         'text'),
                (['out', 'retval'], POINTER(POINTER(IEnumSpellingError)), 'value')),
            COMMETHOD([], HRESULT, 'Suggest',
                (['in'],          c_wchar_p,                    'word'),
                (['out', 'retval'], POINTER(POINTER(IEnumString)), 'value')),
            COMMETHOD([], HRESULT, 'Add', (['in'], c_wchar_p, 'word')),
        ]

    class ISpellCheckerFactory(IUnknown):
        _iid_ = GUID('{8E018A9D-2415-4677-BF08-794EA61F94BB}')
        _methods_ = [
            COMMETHOD(['propget'], HRESULT, 'SupportedLanguages',
                (['out', 'retval'], POINTER(POINTER(IUnknown)), 'value')),
            COMMETHOD([], HRESULT, 'IsSupported',
                (['in'],          c_wchar_p,              'languageTag'),
                (['out', 'retval'], POINTER(ctypes.c_bool), 'value')),
            COMMETHOD([], HRESULT, 'CreateSpellChecker',
                (['in'],          c_wchar_p,                    'languageTag'),
                (['out', 'retval'], POINTER(POINTER(ISpellChecker)), 'value')),
        ]

    WINDOWS_SPELL_AVAILABLE = True

except ImportError:
    WINDOWS_SPELL_AVAILABLE = False

SPELL_CHECKER_TYPE = "windows" if WINDOWS_SPELL_AVAILABLE else None

_CLSID_SpellCheckerFactory = "{7AB36653-1796-484B-BDFA-E74F1DB7C1DC}"


def _create_windows_spell_checker(language: str = "en-US"):
    """
    Create a Windows ISpellChecker instance in STA COM context.
    Must be called from a thread that has called CoInitialize first.
    Returns the ISpellChecker instance or None on failure.
    """
    if not WINDOWS_SPELL_AVAILABLE:
        return None
    try:
        comtypes.CoInitialize()
        factory = comtypes.client.CreateObject(
            _CLSID_SpellCheckerFactory,
            interface=ISpellCheckerFactory,
        )
        return factory.CreateSpellChecker(language)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SPELL WORKER SIGNALS
# Defined before SpellWorker so the class can reference it cleanly.
# ─────────────────────────────────────────────────────────────────────────────

class _SpellWorkerSignals(QObject):
    """Qt signals for cross-thread result delivery."""
    results_ready     = Signal(list)       # list of (start, length) tuples for misspelled words
    suggestions_ready = Signal(str, list)  # (word, [suggestions])


# ─────────────────────────────────────────────────────────────────────────────
# SPELL WORKER
# Runs entirely off the Qt event loop in its own STA thread.
# Communicates results back via Qt signals — safe cross-thread delivery.
# ─────────────────────────────────────────────────────────────────────────────

class SpellWorker:
    """
    Off-thread spell checking worker.
    Owns its own STA COM context so it never touches Qt's event loop directly.

    Initialisation is asynchronous — the COM checker starts on a daemon thread.
    Call is_ready() to check if initialisation has completed.
    The shared instance (_shared_worker) is created eagerly at module import time
    so it has maximum time to finish before the user opens any editor.
    """

    def __init__(self, language: str = "en-US"):
        self.signals  = _SpellWorkerSignals()
        self._language = language
        self._ready   = threading.Event()
        self._queue   = queue.Queue()
        self._checker = None   # only ever accessed inside _sta_loop

        # Single persistent STA thread — owns the COM checker for its lifetime.
        # All COM calls are dispatched here via _queue to respect STA rules.
        self._sta_thread = threading.Thread(target=self._sta_loop, daemon=True)
        self._sta_thread.start()

    def _sta_loop(self):
        """
        Dedicated STA thread. Initialises COM, creates the checker, then
        processes callable work items from _queue until shutdown.
        STA COM objects must only be called from the thread that created them.
        """
        if not WINDOWS_SPELL_AVAILABLE:
            self._ready.set()
            return
        try:
            comtypes.CoInitialize()
            factory = comtypes.client.CreateObject(
                _CLSID_SpellCheckerFactory,
                interface=ISpellCheckerFactory,
            )
            self._checker = factory.CreateSpellChecker(self._language)
        except Exception:
            self._ready.set()
            return

        self._ready.set()

        while True:
            fn = self._queue.get()
            if fn is None:
                break
            try:
                fn(self._checker)
            except Exception:
                pass

    def is_ready(self) -> bool:
        """Return True once the STA thread has finished COM initialisation."""
        return self._ready.is_set() and self._checker is not None

    def _dispatch(self, fn) -> None:
        """Queue a callable(checker) to run on the STA thread."""
        if self.is_ready():
            self._queue.put(fn)

    def _dispatch_sync(self, fn, timeout: float = 1.0):
        """
        Queue a callable(checker) → value on the STA thread and block until done.
        Returns the result or None on timeout/failure.
        """
        if not self.is_ready():
            return None
        result = [None]
        evt    = threading.Event()
        def _wrap(checker):
            try:
                result[0] = fn(checker)
            finally:
                evt.set()
        self._queue.put(_wrap)
        evt.wait(timeout)
        return result[0]

    def check_text(self, text: str, blocks: list) -> None:
        """
        Spell-check all blocks off the main thread via the STA queue.
        Emits results_ready with (doc_start, length) tuples for misspelled words.
        """
        expression = QRegularExpression(r"\b[a-zA-Z']+\b")

        def _work(checker):
            results = []
            for block_text, block_offset in blocks:
                iterator = expression.globalMatch(block_text)
                while iterator.hasNext():
                    match = iterator.next()
                    word = match.captured(0)
                    try:
                        if checker.Check(word).Next():  # non-null/truthy → misspelled
                            results.append((block_offset + match.capturedStart(), match.capturedLength()))
                    except Exception:
                        pass
            self.signals.results_ready.emit(results)

        self._dispatch(_work)

    def get_suggestions(self, word: str) -> None:
        """Fetch suggestions async. Emits suggestions_ready(word, [str])."""
        def _work(checker):
            try:
                suggestions = _drain_enum_string(checker.Suggest(word))
            except Exception:
                suggestions = []
            self.signals.suggestions_ready.emit(word, suggestions)

        self._dispatch(_work)

    def add_to_dictionary(self, word: str) -> None:
        """Add a word to the Windows personal dictionary via the STA thread."""
        self._dispatch(lambda checker: checker.Add(word))

    def check_word(self, word: str) -> bool:
        """
        Synchronous single-word check for the right-click context menu.
        Blocks briefly (≤1s) but is only called on deliberate right-click.
        Returns True (correct) if the checker is unavailable.
        """
        def _work(checker):
            try:
                return not checker.Check(word).Next()  # null/falsy ptr → no error → correct
            except Exception:
                return True
        result = self._dispatch_sync(_work)
        return result if result is not None else True

    def suggest_sync(self, word: str) -> list:
        """Synchronous suggestion fetch for the right-click context menu."""
        result = self._dispatch_sync(
            lambda checker: _drain_enum_string(checker.Suggest(word))
        )
        return result or []


# ─────────────────────────────────────────────────────────────────────────────
# MODULE-LEVEL WORKER INSTANCE — EAGER INITIALISATION
#
# The worker is created here, at module import time, after SpellWorker is defined.
# This gives the COM STA thread maximum warm-up time — by the time the user has
# loaded a session and opened a note editor, the checker is ready to go.
#
# Previously this was lazy (created on first get_spell_worker() call), which meant
# the COM thread was still initialising when the user first right-clicked or typed.
# Eager init eliminates that race entirely at zero cost to startup performance,
# since the thread runs in the background and doesn't block the main event loop.
#
# get_spell_worker() remains the public accessor — callers stay unaware of this detail.
# ─────────────────────────────────────────────────────────────────────────────

_shared_worker: SpellWorker | None = SpellWorker("en-US") if WINDOWS_SPELL_AVAILABLE else None


def get_spell_worker() -> SpellWorker | None:
    """Return the shared SpellWorker instance. Always initialised at import time."""
    return _shared_worker


# ─────────────────────────────────────────────────────────────────────────────
# DEBOUNCED SPELL HIGHLIGHTER
# ─────────────────────────────────────────────────────────────────────────────

class DebouncedSpellHighlighter(QSyntaxHighlighter):
    """
    Highlights misspelled words with red wavy underline after a debounce delay.
    Uses the shared SpellWorker (Windows COM ISpellChecker) off-thread.
    Results are delivered back to Qt via signals — event loop stays clean.

    Size gate: spell checking is disabled for documents over SIZE_THRESHOLD_KB
    to prevent performance issues in large nodes.
    """

    DEBOUNCE_DELAY_MS = 800     # Wait after last keystroke before checking
    SIZE_THRESHOLD_KB = 50      # Disable spell check for documents larger than this

    def __init__(self, document):
        super().__init__(document)

        self._worker = get_spell_worker()
        self._misspelled_ranges: list[tuple[int, int]] = []

        # Debounce timer — batches rapid keystrokes into a single check
        self._check_timer = QTimer()
        self._check_timer.setSingleShot(True)
        self._check_timer.timeout.connect(self._perform_spell_check)

        # State flags
        self.spell_check_enabled = True
        self._document_too_large = False
        self._last_was_word_boundary = True
        self._should_highlight = False

        # Red wavy underline format
        self.misspelled_format = QTextCharFormat()
        self.misspelled_format.setUnderlineColor(QColor("#ff5555"))
        self.misspelled_format.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)

        # Wire worker results back to rehighlight on the Qt thread
        if self._worker:
            self._worker.signals.results_ready.connect(self._on_results_ready)

        if self._worker and not self._worker.is_ready():
            self._ready_poll = QTimer()
            self._ready_poll.setSingleShot(False)
            self._ready_poll.setInterval(200)  # check every 200ms
            self._ready_poll.timeout.connect(self._poll_worker_ready)
            self._ready_poll.start()

        self.document().contentsChanged.connect(self._on_text_changed)

    def _poll_worker_ready(self):
        """Poll until the COM worker finishes initialising, then run first check."""
        if self._worker and self._worker.is_ready():
            self._ready_poll.stop()
            self._ready_poll = None
            # Worker is now ready — check whatever is already in the document
            self._perform_spell_check()

    def _on_results_ready(self, results: list):
        """Receive misspelled word positions from the worker thread and repaint."""
        self._misspelled_ranges = results
        self._should_highlight = True
        self.rehighlight()
        self._should_highlight = False

    def _on_text_changed(self):
        """
        Called on every document change — gates the debounce timer.
        Checks sooner at word boundaries (150ms) than mid-word (800ms)
        so finished words are caught quickly without interrupting typing flow.
        """
        if not self.spell_check_enabled or not self._worker:
            return

        doc_size_kb = len(self.document().toPlainText().encode('utf-8')) / 1024
        if doc_size_kb > self.SIZE_THRESHOLD_KB:
            if not self._document_too_large:
                self._document_too_large = True
                self._check_timer.stop()
                self._misspelled_ranges = []
                self.rehighlight()
            return
        else:
            self._document_too_large = False

        text = self.document().toPlainText()
        if not text:
            return

        last_char = text[-1]
        is_word_boundary = last_char.isspace() or last_char in '.,;:!?\n'

        if is_word_boundary and not self._last_was_word_boundary:
            # Just finished a word — check soon
            self._check_timer.stop()
            self._check_timer.start(150)
            self._last_was_word_boundary = True
        elif not is_word_boundary:
            self._last_was_word_boundary = False
            if not self._check_timer.isActive():
                self._check_timer.start(self.DEBOUNCE_DELAY_MS)

    def _perform_spell_check(self):
        """
        Collect all document blocks and dispatch to the worker thread.
        Returns immediately — results arrive asynchronously via _on_results_ready.
        If the worker isn't ready yet the check silently skips —
        the next keystroke triggers another attempt via the debounce timer.
        """
        if not self.spell_check_enabled or self._document_too_large or not self._worker:
            return

        blocks = []
        block = self.document().begin()
        while block.isValid():
            blocks.append((block.text(), block.position()))
            block = block.next()
        if blocks:
            self._worker.check_text(self.document().toPlainText(), blocks)

    def highlightBlock(self, text):
        """
        Apply misspelled formatting only when results have arrived from the worker.
        _should_highlight flag ensures this never fires speculatively on keystrokes.
        """
        if not self.spell_check_enabled or self._document_too_large or not self._should_highlight:
            return

        block_start = self.currentBlock().position()
        block_end = block_start + len(text)

        for doc_start, length in self._misspelled_ranges:
            if doc_start >= block_start and doc_start < block_end:
                local_start = doc_start - block_start
                self.setFormat(local_start, length, self.misspelled_format)

    def add_to_dictionary(self, word: str):
        """Add a word to the Windows personal dictionary and immediately re-check."""
        if self._worker:
            self._worker.add_to_dictionary(word)
            self._check_timer.start(200)  # Short delay so Add() has time to persist

    def set_spell_check_enabled(self, enabled: bool):
        """Enable or disable spell checking."""
        self.spell_check_enabled = enabled
        self._check_timer.stop()
        self._misspelled_ranges = []
        self.rehighlight()

    def is_spell_check_enabled(self) -> bool:
        """Return whether spell checking is currently active."""
        return self.spell_check_enabled and not self._document_too_large

    def is_document_too_large(self) -> bool:
        """Return whether document exceeds size threshold."""
        return self._document_too_large

    def get_spell_checker_type(self) -> str:
        """Return the type of spell checker in use."""
        return SPELL_CHECKER_TYPE or "none"


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT MENU
# ─────────────────────────────────────────────────────────────────────────────

def _drain_enum_string(enum, limit: int = 10) -> list:
    """Drain an IEnumString into a Python list, up to limit items."""
    results = []
    while len(results) < limit:
        try:
            s, fetched = enum.Next(1)
            if not fetched:
                break
            results.append(s)
        except Exception:
            break
    return results


def show_spell_suggestions(
    text_edit,
    pos,
    highlighter: DebouncedSpellHighlighter = None,
    menu_style: str = "",
) -> bool:
    """
    Show right-click context menu with spell suggestions and add-to-dictionary option.
    Only appears on misspelled words — returns False for correct words so the caller
    can fall through to the standard context menu.

    Suggestions are fetched synchronously via worker._checker.Suggest() rather than
    the async get_suggestions() path. This is intentional — right-click is a deliberate
    user action not a typing interrupt, so a brief synchronous call is acceptable.
    The private _checker access is necessary here because the async path cannot return
    values synchronously. This is the only place in the codebase that does this.

    Args:
        text_edit:   The QTextEdit to attach the menu to
        pos:         Cursor position from customContextMenuRequested signal
        highlighter: Pass the active DebouncedSpellHighlighter so 'add to dictionary'
                     clears the underline immediately. If None, the underline stays
                     until the next debounce recheck.
        menu_style:  Optional QSS stylesheet applied to the menu so it matches the
                     app theme rather than the OS default.

    Returns True if a spell menu was shown, False if the word was correct.
    """
    worker = get_spell_worker()
    if not worker or not worker.is_ready():
        return False

    cursor = text_edit.cursorForPosition(pos)
    cursor.select(QTextCursor.WordUnderCursor)
    word = cursor.selectedText().strip()

    if not word:
        return False

    if worker.check_word(word):
        return False  # Correct word — caller falls through to standard menu

    suggestions = worker.suggest_sync(word)

    menu = QMenu(text_edit)
    if menu_style:
        menu.setStyleSheet(menu_style)

    if suggestions:
        for suggestion in suggestions:
            action = menu.addAction(suggestion)
            action.triggered.connect(
                lambda checked, s=suggestion, c=cursor: replace_word(c, s)
            )
    else:
        menu.addAction("(no suggestions)").setEnabled(False)

    menu.addSeparator()

    add_action = menu.addAction(f"Add '{word}' to dictionary")
    add_action.triggered.connect(
        lambda checked, w=word: _add_word(w, highlighter, worker)
    )

    menu.exec(text_edit.mapToGlobal(pos))
    return True


def _add_word(word: str, highlighter: DebouncedSpellHighlighter | None, worker: SpellWorker):
    """
    Add word to the Windows personal dictionary.
    If a highlighter is provided, triggers an immediate recheck so the
    underline clears without waiting for the next keystroke.
    """
    worker.add_to_dictionary(word)
    if highlighter:
        highlighter.add_to_dictionary(word)


def replace_word(cursor, suggestion):
    """Replace the selected word with the chosen suggestion."""
    cursor.beginEditBlock()
    cursor.removeSelectedText()
    cursor.insertText(suggestion)
    cursor.endEditBlock()