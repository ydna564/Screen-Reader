<div align="center">

<img src="assets/logo.png" alt="Screen Reader logo" width="128" height="128" />

# Screen Reader

**A tiny macOS menu-bar gadget that reads any pixel on your screen.**

Press&nbsp;**⇧⌘1**, drag a box over anything — text, a PDF, an image — and it is
recognised on-device, pinned beside your selection, and spoken aloud.

<br />

[![Platform](https://img.shields.io/badge/platform-macOS-1E4A5F?logo=apple&logoColor=white&style=flat-square)](https://www.apple.com/macos/)
[![Python](https://img.shields.io/badge/Python-3-1E4A5F?logo=python&logoColor=white&style=flat-square)](https://www.python.org/)
[![Apple Vision](https://img.shields.io/badge/OCR-Apple%20Vision-1E4A5F?logo=apple&logoColor=white&style=flat-square)](https://developer.apple.com/documentation/vision)
[![100% Local](https://img.shields.io/badge/privacy-100%25%20on--device-1E4A5F?style=flat-square)](#-macos-permissions-required)
[![Menu bar](https://img.shields.io/badge/lives%20in-the%20menu%20bar-1E4A5F?style=flat-square)](#hotkeys)
[![License: MIT](https://img.shields.io/badge/license-MIT-1E4A5F?style=flat-square)](LICENSE)

</div>

---

Everything runs **locally** — Apple's **Vision** framework for on-device OCR and
the built-in `say` command for speech. Nothing leaves your Mac.

While a selection is active:

- the **selected area stays highlighted** on screen,
- the **recognised text is pinned in a panel beside the selection** as a reference,
- a **“✕ Cancel translation” button just below the selection** dismisses it,
- a **“⧉ Copy” button in the panel** puts the text on the clipboard (the panel
  text is also selectable with the mouse). **Copy Last Text** in the menu-bar
  menu recovers the most recent result even after dismissing.

**⇧⌘1 is the hotkey and works as a toggle** — press it to start a selection,
press it again to cancel the selection, dismiss the pinned overlay, or stop
speech. Once cleared, press it once more for the next selection. Each
press-and-drag reads exactly one area.

## ✦ Example

Reading a PDF's table of contents in WPS Office — press ⇧⌘1, drag over the
section you want (yellow frame), and the recognised text is pinned in the panel
beside it, ready to copy:

<div align="center">

![Selecting a PDF section and getting the text pinned beside it](docs/example.png)

</div>

The **⧉ Copy** button puts the text on the clipboard; **✕ Cancel translation**
below the selection dismisses the overlay (or just press ⇧⌘1 again).

## Hotkeys

| Shortcut | Action |
|----------|--------|
| **⇧⌘1** *(idle)* | Select an area and read it — one selection per press |
| **⇧⌘1** *(again)* | Cancel the selection · dismiss the pinned overlay · stop speech |
| **Esc** *(while selecting)* | Abort the current selection |

You can also trigger/dismiss and pick the language from the 👁 icon in the menu bar.

The monochrome book icon in the menu bar reflects the current state with a small
symbol beside it:

| Symbol | State |
|:------:|-------|
| *(none)* | idle |
| `+` | selecting |
| `…` | recognising |
| `♪` | speaking |
| `•` | overlay pinned |

## Install & run

```bash
cd ~/screen-reader
./run.sh          # first run creates a venv and installs dependencies
```

Or manually:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python screenreader.py
```

## 🔐 macOS permissions (required)

Grant these to whichever app launches the tool (Terminal, iTerm, or the packaged
app) in **System Settings → Privacy & Security**:

| Permission | Why it's needed |
|------------|-----------------|
| **Screen Recording** | so the selected region can be captured |
| **Accessibility** | so the global ⇧⌘1 hotkey works |

> If the hotkeys don't respond, it's almost always the **Accessibility**
> permission. After granting it, quit and relaunch the tool.

## Choosing the spoken language

Click the menu-bar icon → **Language**. The default is **English**. Your choice
is remembered in `~/.screenreader.json`.

## Project structure

```text
screen-reader/
├── screenreader.py           The whole app: menu-bar item, region selector,
│                             Vision OCR, translation, speech, pinned overlay
├── install.sh                Builds ~/Applications/ScreenReader.app and
│                             registers the LaunchAgent for login autostart
├── uninstall.sh              Removes the app bundle and the autostart entry
├── run.sh                    Dev mode: creates the venv and runs the script
├── requirements.txt          rumps, pynput, pyobjc (Vision + Quartz)
├── assets/
│   ├── logo.png              Source artwork for the app icon
│   ├── AppIcon.icns          Generated multi-resolution app icon
│   ├── menubar_icon.png      Monochrome template icon for the menu bar
│   └── make_menubar_icon.py  Regenerates menubar_icon.png
└── docs/
    └── example.png           Screenshot used in this README
```

## Optional: offline translation

Out of the box the recognised text is spoken **as written**, using the voice of
your selected language. To actually *translate* the source text into your chosen
language first:

```bash
./.venv/bin/pip install argostranslate langdetect
```

Then download the language pairs you want, e.g. French → English:

```python
./.venv/bin/python - <<'PY'
import argostranslate.package as p
p.update_package_index()
avail = p.get_available_packages()
pkg = next(x for x in avail if x.from_code=="fr" and x.to_code=="en")
p.install_from_path(pkg.download())
PY
```

Restart the app. It will auto-detect the source language and translate into the
language selected in the menu before speaking.

## Install as a system app

*Starts at login, no Terminal needed.*

```bash
./install.sh
```

This builds `~/Applications/ScreenReader.app` (a real menu-bar app wrapping this
project), registers a LaunchAgent so it launches at every login, and starts it
immediately. Re-run it any time to refresh; `./uninstall.sh` removes the
autostart and the app bundle.

> **One-time after installing:** grant **Screen Recording**, **Accessibility**
> (and **Input Monitoring**, if listed) to **ScreenReader** in System Settings →
> Privacy & Security — permissions given to Terminal don't carry over to the new
> app. Then quit and reopen it once. Logs go to
> `~/Library/Logs/ScreenReader.log` if anything misbehaves.

<div align="center">
<br />
<sub>Built with Python · Apple Vision · rumps — runs entirely on your Mac.</sub>
</div>
