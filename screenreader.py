#!/usr/bin/env python3
"""Screen Reader / Translator — a macOS menu-bar gadget.

Press ⇧⌘1, then drag a rectangle on the screen with the cursor. The text
inside is recognised (on-device OCR via Apple's Vision framework),
optionally translated, spoken aloud, and:

  * the selected area stays highlighted on screen,
  * the translated text is pinned in a panel beside the selection,
  * a "✕ Cancel" button just below the selection dismisses everything.

⇧⌘1 is a toggle and the ONLY hotkey:
  * when idle          → start selecting an area to translate (one-shot)
  * while selecting    → cancel the selection
  * overlay/speaking   → dismiss the overlay and stop speaking

Each selection/translation is one-shot; once something is active, press
⇧⌘1 to clear it, then ⇧⌘1 again for the next selection.

Everything runs locally: Vision (OCR) + `say` (speech). Translation is
optional (argostranslate); without it the recognised text is spoken and
shown as-is.
"""

import json
import os
import re
import subprocess
import tempfile
import threading
import time
import unicodedata

import objc
import rumps
from pynput import keyboard

import AppKit
import Quartz
import Vision
from Foundation import NSObject, NSURL, NSMakeRect
from PyObjCTools import AppHelper

# ---- optional offline translation ----
try:
    import argostranslate.translate as argos_translate
    _HAS_ARGOS = True
except Exception:
    _HAS_ARGOS = False

try:
    import argostranslate.package as argos_package
    _HAS_ARGOS_PKG = True
except Exception:
    _HAS_ARGOS_PKG = False

try:
    from langdetect import detect as _detect_lang
    _HAS_LANGDETECT = True
except Exception:
    _HAS_LANGDETECT = False

# The framework Python ships without a CA bundle, so package downloads fail
# with a certificate error unless certifi's bundle is pointed at explicitly.
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass


CONFIG_PATH = os.path.expanduser("~/.screenreader.json")

# display name, Vision/BCP-47 code, argos 2-letter code, preferred `say` voices
LANGUAGES = [
    ("English",            "en-US",   "en", ["Samantha", "Alex", "Daniel"]),
    ("Chinese (Mandarin)", "zh-Hans", "zh", ["Tingting", "Meijia"]),
]

# argos 2-letter code -> display name, for labelling the panel
LANG_BY_CODE = {argos: name for name, _b, argos, _v in LANGUAGES}

# Only the two supported languages are recognised, which also keeps Vision
# from misreading Chinese as a visually similar script.
#
# The order is deliberate and must not be reversed. Vision treats the first
# entry as the primary language, and listing English first makes it return
# nothing at all for a Chinese selection. Chinese first reads both scripts.
OCR_LANGS = ["zh-Hans", "en-US"]

PANEL_WIDTH = 340
PANEL_PAD = 14
GAP = 12


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.strip().lower()


_installed_voices = None


def installed_voices():
    global _installed_voices
    if _installed_voices is None:
        _installed_voices = {}
        try:
            out = subprocess.check_output(["say", "-v", "?"], text=True)
            for line in out.splitlines():
                m = re.match(r"^(.+?)\s{2,}[a-zA-Z_\-]+\s", line)
                if m:
                    name = m.group(1).strip()
                    _installed_voices[_norm(name)] = name
        except Exception:
            pass
    return _installed_voices


def pick_voice(candidates):
    inst = installed_voices()
    for c in candidates:
        real = inst.get(_norm(c))
        if real:
            return real
    return None


def ocr_image(path, languages):
    """Recognise text in an image file using Apple's Vision framework."""
    url = NSURL.fileURLWithPath_(path)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if not src:
        return ""
    cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if not cg:
        return ""
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(True)
    if languages:
        try:
            req.setRecognitionLanguages_(languages)
        except Exception:
            pass
    ok, _err = handler.performRequests_error_([req], None)
    if not ok:
        return ""
    lines = []
    for obs in (req.results() or []):
        cands = obs.topCandidates_(1)
        if cands and len(cands):
            lines.append(cands[0].string())
    return "\n".join(lines)


_HAN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _detect_source(text):
    """Decide which of the two supported languages the text is written in.

    Testing for Han characters beats a general purpose detector here, because
    detectors routinely label a short Chinese line as Japanese or Korean and
    that would block the only translation route the app supports.
    """
    if _HAN_RE.search(text):
        return "zh"
    if _LATIN_RE.search(text):
        return "en"
    if _HAS_LANGDETECT:
        try:
            code = _detect_lang(text).split("-")[0]
            if code in ("zh", "en"):
                return code
        except Exception:
            pass
    return None


def _have_pair(from_code, to_code):
    try:
        return any(p.from_code == from_code and p.to_code == to_code
                   for p in argos_package.get_installed_packages())
    except Exception:
        return False


def _install_pair(from_code, to_code, on_status=None):
    """Download and install one language pair. Returns True when usable."""
    if _have_pair(from_code, to_code):
        return True
    if not _HAS_ARGOS_PKG:
        return False
    try:
        argos_package.update_package_index()
        pkg = next((x for x in argos_package.get_available_packages()
                    if x.from_code == from_code and x.to_code == to_code), None)
        if pkg is None:
            return False
        if on_status:
            on_status("Downloading %s to %s language pack, first time only"
                      % (from_code, to_code))
        argos_package.install_from_path(pkg.download())
        return True
    except Exception:
        return False


def ensure_route(from_code, to_code, on_status=None):
    """Make a translation route available, directly or pivoting via English."""
    if _install_pair(from_code, to_code, on_status):
        return True
    if "en" in (from_code, to_code):
        return False
    return (_install_pair(from_code, "en", on_status)
            and _install_pair("en", to_code, on_status))


def translate(text, to_code, on_status=None):
    """Translate text into to_code.

    Returns (output_text, source_code, translated) so the caller can tell the
    user what actually happened instead of silently passing text through.
    """
    if not _HAS_ARGOS:
        return text, None, False
    from_code = _detect_source(text)
    if not from_code:
        return text, None, False
    if from_code == to_code:
        return text, from_code, False
    if not ensure_route(from_code, to_code, on_status):
        return text, from_code, False
    try:
        out = argos_translate.translate(text, from_code, to_code)
    except Exception:
        return text, from_code, False
    if not out or not out.strip():
        return text, from_code, False
    return out, from_code, True


def notify(title, message):
    try:
        rumps.notification("Screen Reader", title, message)
    except Exception:
        pass


def copy_to_clipboard(text):
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)


def cocoa_rect_to_capture(rect):
    """Convert a global Cocoa rect (origin bottom-left) into the top-left
    coordinates `screencapture -R` expects."""
    main = AppKit.NSScreen.screens()[0].frame()
    x = rect.origin.x
    y = main.size.height - (rect.origin.y + rect.size.height)
    return (int(round(x)), int(round(y)),
            int(round(rect.size.width)), int(round(rect.size.height)))


def screen_for_rect(rect):
    for s in AppKit.NSScreen.screens():
        if AppKit.NSIntersectsRect(s.frame(), rect):
            return s
    return AppKit.NSScreen.screens()[0]


def _make_overlay_window(frame, level):
    win = _KeyWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame, AppKit.NSWindowStyleMaskBorderless,
        AppKit.NSBackingStoreBuffered, False)
    win.setReleasedWhenClosed_(False)
    win.setOpaque_(False)
    win.setBackgroundColor_(AppKit.NSColor.clearColor())
    win.setHasShadow_(False)
    win.setLevel_(level)
    win.setHidesOnDeactivate_(False)
    # CanJoinAllSpaces + FullScreenAuxiliary let the overlay appear on every
    # Space, including over full-screen apps — not just the plain desktop.
    win.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        | AppKit.NSWindowCollectionBehaviorStationary
        | AppKit.NSWindowCollectionBehaviorIgnoresCycle)
    return win


# --------------------------------------------------------------------------
# Cocoa view/window subclasses
# --------------------------------------------------------------------------
class _KeyWindow(AppKit.NSWindow):
    def canBecomeKeyWindow(self):
        return True


class _SelectionView(AppKit.NSView):
    """Full-screen dimmed view; drag to rubber-band a selection."""

    def initWithFrame_controller_(self, frame, controller):
        self = objc.super(_SelectionView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._controller = controller
        self._start = None
        self._current = None
        return self

    def acceptsFirstResponder(self):
        return True

    def acceptsFirstMouse_(self, event):
        return True

    def resetCursorRects(self):
        self.addCursorRect_cursor_(
            self.bounds(), AppKit.NSCursor.crosshairCursor())

    def keyDown_(self, event):
        if event.keyCode() == 53:  # Esc
            self._controller.cancel()

    def mouseDown_(self, event):
        self._start = self.convertPoint_fromView_(
            event.locationInWindow(), None)
        self._current = self._start
        self.setNeedsDisplay_(True)

    def mouseDragged_(self, event):
        self._current = self.convertPoint_fromView_(
            event.locationInWindow(), None)
        self.setNeedsDisplay_(True)

    def mouseUp_(self, event):
        if self._start is None:
            return
        rect = self._sel_rect()
        self._start = self._current = None
        self._controller.finished(self, rect)

    def _sel_rect(self):
        x = min(self._start.x, self._current.x)
        y = min(self._start.y, self._current.y)
        w = abs(self._current.x - self._start.x)
        h = abs(self._current.y - self._start.y)
        return NSMakeRect(x, y, w, h)

    def drawRect_(self, dirty):
        AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.25).setFill()
        AppKit.NSRectFill(self.bounds())
        if self._start is not None and self._current is not None:
            r = self._sel_rect()
            AppKit.NSColor.clearColor().setFill()
            AppKit.NSRectFillUsingOperation(
                r, AppKit.NSCompositingOperationCopy)
            AppKit.NSColor.whiteColor().setStroke()
            path = AppKit.NSBezierPath.bezierPathWithRect_(r)
            path.setLineWidth_(2.0)
            path.stroke()


class _BorderView(AppKit.NSView):
    """Highlight frame drawn around the pinned selection."""

    def drawRect_(self, dirty):
        AppKit.NSColor.systemYellowColor().setStroke()
        path = AppKit.NSBezierPath.bezierPathWithRect_(
            AppKit.NSInsetRect(self.bounds(), 1.5, 1.5))
        path.setLineWidth_(3.0)
        path.stroke()


class _CloseTarget(NSObject):
    def initWithCallback_(self, cb):
        self = objc.super(_CloseTarget, self).init()
        if self is None:
            return None
        self._cb = cb
        return self

    def clicked_(self, sender):
        if self._cb:
            self._cb()


# --------------------------------------------------------------------------
# selection controller (one-shot rubber-band selection)
# --------------------------------------------------------------------------
class SelectionController(object):
    def __init__(self, on_done):
        self.on_done = on_done
        self.windows = []
        self._finished = False

    def begin(self):
        for screen in AppKit.NSScreen.screens():
            win = _make_overlay_window(
                screen.frame(), AppKit.NSScreenSaverWindowLevel)
            win.setSharingType_(AppKit.NSWindowSharingNone)  # keep out of captures
            view = _SelectionView.alloc().initWithFrame_controller_(
                NSMakeRect(0, 0, screen.frame().size.width,
                           screen.frame().size.height), self)
            win.setContentView_(view)
            win.makeFirstResponder_(view)
            win.makeKeyAndOrderFront_(None)
            win.orderFrontRegardless()
            self.windows.append(win)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def finished(self, view, view_rect):
        if self._finished:
            return
        self._finished = True
        win = view.window()
        rect = win.convertRectToScreen_(
            view.convertRect_toView_(view_rect, None))
        self._close()
        if rect.size.width < 8 or rect.size.height < 8:
            self.on_done(None)
        else:
            self.on_done(rect)

    def cancel(self):
        if self._finished:
            return
        self._finished = True
        self._close()
        self.on_done(None)

    def _close(self):
        for w in self.windows:
            w.orderOut_(None)
        self.windows = []


# --------------------------------------------------------------------------
# pinned result overlay: border + text panel + cancel button
# --------------------------------------------------------------------------
class OverlaySession(object):
    def __init__(self, rect, text, header_text, on_cancel):
        self.windows = []
        self._text = text
        self._copy_btn = None
        self._target = _CloseTarget.alloc().initWithCallback_(on_cancel)
        self._copy_target = _CloseTarget.alloc().initWithCallback_(self._on_copy)
        screen = screen_for_rect(rect)
        level = AppKit.NSStatusWindowLevel

        # 1) highlight frame around the selected area
        border = _make_overlay_window(
            AppKit.NSInsetRect(rect, -4, -4), level)
        bview = _BorderView.alloc().initWithFrame_(
            NSMakeRect(0, 0, border.frame().size.width,
                       border.frame().size.height))
        border.setContentView_(bview)
        border.setIgnoresMouseEvents_(True)
        self.windows.append(border)

        # 2) translated-text panel beside the selection
        panel = self._build_panel(rect, text, header_text, screen, level)
        self.windows.append(panel)

        # 3) cancel button just below the selection
        button = self._build_button(rect, screen, level)
        self.windows.append(button)

        for w in self.windows:
            w.orderFrontRegardless()

    # ---- panel ----
    def _build_panel(self, rect, text, header_text, screen, level):
        inner_w = PANEL_WIDTH - 2 * PANEL_PAD

        header = AppKit.NSTextField.labelWithString_(header_text)
        header.setFont_(AppKit.NSFont.boldSystemFontOfSize_(11))
        header.setTextColor_(
            AppKit.NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.6))

        body = AppKit.NSTextField.wrappingLabelWithString_(text)
        body.setFont_(AppKit.NSFont.systemFontOfSize_(14))
        body.setTextColor_(AppKit.NSColor.whiteColor())

        body_size = body.cell().cellSizeForBounds_(
            NSMakeRect(0, 0, inner_w, 100000))
        max_body_h = screen.visibleFrame().size.height * 0.7
        body_h = min(body_size.height, max_body_h)
        header_row_h = 22
        panel_h = PANEL_PAD * 2 + header_row_h + 8 + body_h

        content = AppKit.NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PANEL_WIDTH, panel_h))
        content.setWantsLayer_(True)
        layer = content.layer()
        layer.setBackgroundColor_(
            AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.10, 0.95).CGColor())
        layer.setCornerRadius_(10.0)

        row_y = PANEL_PAD + body_h + 8
        btn_w = 74
        copy_btn = AppKit.NSButton.buttonWithTitle_target_action_(
            "⧉ Copy", self._copy_target, "clicked:")
        copy_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        copy_btn.setControlSize_(AppKit.NSControlSizeSmall)
        copy_btn.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        copy_btn.setFrame_(NSMakeRect(
            PANEL_WIDTH - PANEL_PAD - btn_w, row_y, btn_w, header_row_h))
        self._copy_btn = copy_btn

        body.setFrame_(NSMakeRect(PANEL_PAD, PANEL_PAD, inner_w, body_h))
        header.setFrame_(NSMakeRect(
            PANEL_PAD, row_y + 3, inner_w - btn_w - 8, 16))
        content.addSubview_(body)
        content.addSubview_(header)
        content.addSubview_(copy_btn)

        frame = self._panel_frame(rect, screen, PANEL_WIDTH, panel_h)
        win = _make_overlay_window(frame, level)
        win.setContentView_(content)
        return win

    def _on_copy(self):
        copy_to_clipboard(self._text)
        btn = self._copy_btn
        if btn is None:
            return
        btn.setTitle_("Copied ✓")
        try:
            AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                1.2, False, lambda _t: btn.setTitle_("⧉ Copy"))
        except Exception:
            pass

    @staticmethod
    def _panel_frame(rect, screen, w, h):
        sf = screen.visibleFrame()
        # prefer the right side of the selection, else the left, else clamp
        x = AppKit.NSMaxX(rect) + GAP
        if x + w > AppKit.NSMaxX(sf):
            x = rect.origin.x - GAP - w
        if x < sf.origin.x:
            x = max(sf.origin.x + 8, min(AppKit.NSMaxX(rect) - w,
                                         AppKit.NSMaxX(sf) - w - 8))
        # top-align with the selection, clamped to the screen
        y = AppKit.NSMaxY(rect) - h
        y = max(sf.origin.y + 8, min(y, AppKit.NSMaxY(sf) - h - 8))
        return NSMakeRect(x, y, w, h)

    # ---- cancel button ----
    def _build_button(self, rect, screen, level):
        btn_w, btn_h = 170, 30
        btn = AppKit.NSButton.buttonWithTitle_target_action_(
            "✕ Cancel translation", self._target, "clicked:")
        btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        btn.setFrame_(NSMakeRect(0, 0, btn_w, btn_h))

        sf = screen.visibleFrame()
        x = rect.origin.x + rect.size.width / 2.0 - btn_w / 2.0
        x = max(sf.origin.x + 8, min(x, AppKit.NSMaxX(sf) - btn_w - 8))
        y = rect.origin.y - btn_h - 8          # just below the selection
        y = max(sf.origin.y + 8, min(y, AppKit.NSMaxY(sf) - btn_h - 8))

        win = _make_overlay_window(NSMakeRect(x, y, btn_w, btn_h), level)
        content = AppKit.NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, btn_w, btn_h))
        content.addSubview_(btn)
        win.setContentView_(content)
        return win

    def close(self):
        for w in self.windows:
            w.orderOut_(None)
        self.windows = []


# --------------------------------------------------------------------------
# app
# --------------------------------------------------------------------------
class ScreenReaderApp(rumps.App):
    def __init__(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets", "menubar_icon.png")
        if os.path.exists(icon_path):
            super().__init__("", icon=icon_path, template=True,
                             quit_button=None)
            # keep retina detail but constrain height to the menu bar
            if getattr(self, "_icon_nsimage", None) is not None:
                self._icon_nsimage.setSize_((20, 20))
            self._has_icon = True
        else:
            super().__init__("📖", quit_button=None)
            self._has_icon = False
        # Accessory policy = pure menu-bar app. A "regular" app (the default
        # for a bare python process) switches Spaces when activated, which
        # yanked the user out of full-screen apps back to the desktop.
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(
            AppKit.NSApplicationActivationPolicyAccessory)

        self.selection = None       # active SelectionController
        self.session = None         # active OverlaySession
        self.busy = False
        self.downloading = False
        self.current_say = None

        # accessibility permission check (needed for the global hotkeys) —
        # prompting also auto-adds this app to the Accessibility list
        try:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt)
            if not AXIsProcessTrustedWithOptions(
                    {kAXTrustedCheckOptionPrompt: True}):
                notify("Permission needed",
                       "Enable ScreenReader under Privacy & Security → "
                       "Accessibility, then quit (👁 menu) and reopen it — "
                       "hotkeys won't work until then.")
        except Exception:
            pass

        # screen-recording permission check (needed for the actual capture)
        try:
            if not Quartz.CGPreflightScreenCaptureAccess():
                Quartz.CGRequestScreenCaptureAccess()
                notify("Permission needed",
                       "Enable ScreenReader under Privacy & Security → "
                       "Screen Recording, then quit and reopen it.")
        except Exception:
            pass

        cfg = self._load_cfg()
        self.target_index = cfg.get("target_index", 0)
        if not (0 <= self.target_index < len(LANGUAGES)):
            self.target_index = 0
        self.read_aloud = bool(cfg.get("read_aloud", True))

        self.last_text = None

        self.enter_item = rumps.MenuItem(
            "Translate / Cancel  (⇧⌘1)", callback=self.on_enter)
        self.stop_item = rumps.MenuItem(
            "Dismiss / Stop", callback=self.on_stop)
        self.copy_item = rumps.MenuItem(
            "Copy Last Text", callback=self.on_copy_last)
        self.read_item = rumps.MenuItem(
            "Read Aloud", callback=self.on_toggle_read)
        self.read_item.state = 1 if self.read_aloud else 0

        self.lang_menu = rumps.MenuItem("Language")
        self._lang_items = []
        for i, (name, _bcp, _argos, _voices) in enumerate(LANGUAGES):
            item = rumps.MenuItem(name, callback=self._make_lang_cb(i))
            self._lang_items.append(item)
            self.lang_menu.add(item)
        self._refresh_lang_marks()

        self.menu = [
            self.enter_item,
            self.stop_item,
            self.copy_item,
            None,
            self.read_item,
            self.lang_menu,
            None,
            rumps.MenuItem("About", callback=self.on_about),
            rumps.MenuItem("Quit", callback=self.on_app_quit),
        ]

        self._timer = rumps.Timer(self._tick, 0.4)
        self._timer.start()

        # global hotkeys (needs Accessibility permission)
        self.hotkeys = keyboard.GlobalHotKeys({
            "<cmd>+<shift>+1": lambda: AppHelper.callAfter(self.toggle_selection),
        })
        self.hotkeys.start()

    # ---- derived ----
    @property
    def target(self):
        return LANGUAGES[self.target_index]

    # ---- menu-bar title reflects state (monochrome, beside the book icon) ----
    def _tick(self, _timer):
        if self.selection is not None:
            state = "+"          # selecting
        elif self.downloading:
            state = "↓"          # fetching a language pack
        elif self.busy:
            state = "…"          # recognising
        elif self.current_say is not None:
            state = "♪"          # speaking
        elif self.session is not None:
            state = "•"          # overlay pinned
        else:
            state = ""           # idle
        if self._has_icon:
            self.title = (" " + state) if state else ""
        else:
            self.title = ("📖 " + state) if state else "📖"

    # ---- one-shot selection flow (main thread) ----
    def toggle_selection(self):
        """⇧⌘1: start a selection when idle; cancel/dismiss anything active
        (selection in progress, pinned overlay, or speech) otherwise."""
        if (self.selection is not None or self.session is not None
                or self.current_say is not None):
            self.dismiss_all()
            return
        self.selection = SelectionController(self._selection_done)
        self.selection.begin()

    def _selection_done(self, rect):
        self.selection = None
        if rect is None:
            return
        threading.Thread(
            target=self._process, args=(rect,), daemon=True).start()

    def dismiss_all(self):
        if self.selection is not None:
            sel, self.selection = self.selection, None
            sel.on_done = lambda _r: None   # swallow the callback
            sel.cancel()
        if self.session is not None:
            self.session.close()
            self.session = None
        self._stop_speech()

    @staticmethod
    def _panel_header(src_code, translated, target):
        """Label the panel with what actually happened to the text."""
        target_name, target_code = target[0], target[2]
        src_name = LANG_BY_CODE.get(src_code, src_code)
        if translated:
            return "%s to %s" % (src_name, target_name)
        if not _HAS_ARGOS:
            return "Recognised text, translation not installed"
        if src_code is None:
            return "Recognised text"
        if src_code == target_code:
            return "Recognised text, already %s" % target_name
        return "Recognised text, no %s to %s pack" % (src_name, target_name)

    # ---- background processing ----
    def _process(self, rect):
        self.busy = True
        try:
            time.sleep(0.25)  # let the selection overlay disappear
            path = self._capture_rect(rect)
            if not path:
                notify("Error", "Could not capture the screen. "
                       "Check the Screen Recording permission.")
                return
            try:
                target = self.target
                text = ocr_image(path, OCR_LANGS)
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if not text.strip():
                notify("", "No text found in selection.")
                return
            self.downloading = False

            def _status(msg):
                self.downloading = True
                notify("Screen Reader", msg)

            spoken, src, did = translate(
                text, target[2], on_status=_status)
            self.downloading = False
            self.last_text = spoken
            header = self._panel_header(src, did, target)
            AppHelper.callAfter(self._show_session, rect, spoken, header)
            if self.read_aloud:
                self._speak(spoken)
        except Exception as e:
            notify("Error", str(e))
        finally:
            self.busy = False

    def _capture_rect(self, rect):
        x, y, w, h = cocoa_rect_to_capture(rect)
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        subprocess.run(
            ["screencapture", "-R", f"{x},{y},{w},{h}", "-x", path],
            check=False)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        if os.path.exists(path):
            os.remove(path)
        return None

    def _show_session(self, rect, text, header_text):
        if self.session is not None:
            self.session.close()
        self.session = OverlaySession(
            rect, text, header_text, self._cancel_clicked)

    def _cancel_clicked(self):
        if self.session is not None:
            self.session.close()
            self.session = None
        self._stop_speech()

    # ---- speech ----
    def _speak(self, text):
        voice = pick_voice(self.target[3])
        args = ["say"]
        if voice:
            args += ["-v", voice]
        args += ["--", text]
        try:
            self.current_say = subprocess.Popen(args)
            self.current_say.wait()
        except Exception:
            pass
        finally:
            self.current_say = None

    def _stop_speech(self):
        p = self.current_say
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass

    # ---- language menu ----
    def _make_lang_cb(self, i):
        def cb(_item):
            self.target_index = i
            self._refresh_lang_marks()
            self._save_cfg()
        return cb

    def _refresh_lang_marks(self):
        for i, item in enumerate(self._lang_items):
            item.state = 1 if i == self.target_index else 0

    # ---- menu callbacks ----
    def on_enter(self, _):
        AppHelper.callAfter(self.toggle_selection)

    def on_stop(self, _):
        AppHelper.callAfter(self.dismiss_all)

    def on_toggle_read(self, _):
        self.read_aloud = not self.read_aloud
        self.read_item.state = 1 if self.read_aloud else 0
        if not self.read_aloud:
            self._stop_speech()      # silence any current playback
        self._save_cfg()

    def on_copy_last(self, _):
        if self.last_text:
            copy_to_clipboard(self.last_text)
        else:
            notify("", "Nothing to copy yet — make a selection first.")

    def on_about(self, _):
        rumps.alert(
            "Screen Reader / Translator",
            "Press ⇧⌘1 and drag over any area of the screen. The text is "
            "pinned beside the selection, and read aloud when Read Aloud "
            "is on.\n\n"
            "⇧⌘1  select & translate, press again to cancel or dismiss\n\n"
            "Translates between Chinese and English only.\n\n"
            "Current language: {}\n"
            "Translation: {}".format(
                self.target[0],
                "offline, language packs download on first use"
                if _HAS_ARGOS else "not installed",
            ),
        )

    def on_app_quit(self, _):
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        self.dismiss_all()
        rumps.quit_application()

    # ---- config ----
    def _load_cfg(self):
        try:
            with open(CONFIG_PATH) as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cfg(self):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump({"target_index": self.target_index,
                           "read_aloud": self.read_aloud}, f)
        except Exception:
            pass


if __name__ == "__main__":
    ScreenReaderApp().run()
