# Screen Reader

A tiny macOS **menu-bar gadget**. Press **⇧⌘1**, drag a rectangle over any
area of the screen, the text inside is recognised in the language you choose from the menu-bar icon and optionally translated, while:

- the **selected area stays highlighted** on screen,
- the **translated text is pinned in a panel beside the selection** as a
  reference,
- a **“✕ Cancel translation” button just below the selection** dismisses it,
- a **“⧉ Copy” button in the panel** puts the text on the clipboard (the
  panel text is also selectable with the mouse). **Copy Last Text** in the
  menu-bar menu recovers the most recent result even after dismissing.

**⇧⌘1 is the hotkey and works as a toggle**: press it to start a
selection, press it again to cancel the selection, dismiss the pinned
overlay, or stop speech. Once cleared, press it once more for the next
selection. Each press-and-drag translates exactly one area.

Everything runs **locally**: Apple's **Vision** framework for on-device OCR
and `say` for speech.

## Example

Reading a PDF's table of contents in WPS Office — press ⇧⌘1, drag over the
section you want (yellow frame), and the recognised text is pinned in the
panel beside it, ready to copy:

![Selecting a PDF section and getting the text pinned beside it](docs/example.png)

The **⧉ Copy** button puts the text on the clipboard; **✕ Cancel translation**
below the selection dismisses the overlay (or just press ⇧⌘1 again).

## Hotkeys

| Shortcut | Action |
|----------|--------|
| **⇧⌘1** (idle) | Select an area and translate it (one selection per press) |
| **⇧⌘1** (again) | Cancel the selection / dismiss the pinned overlay / stop speech |

Press **Esc** while selecting to abort. You can also trigger/dismiss and pick
the language from the 👁 icon in the menu bar.

The monochrome book icon in the menu bar shows the state with a small symbol
beside it: idle (none) · `+` selecting · `…` recognising · `♪` speaking ·
`•` overlay pinned.

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

## macOS permissions (required)

Grant these to whichever app launches the tool (Terminal, iTerm, or the packaged
app) in **System Settings → Privacy & Security**:

- **Screen Recording** — so the region can be captured.
- **Accessibility** — so the global ⇧⌘1 hotkey works.

If the hotkeys don't respond, it's almost always the Accessibility permission.
After granting it, quit and relaunch the tool.

## Choosing the spoken language

Click the menu-bar icon → **Language**. The default is **English**. Your
choice is remembered in `~/.screenreader.json`.

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

## Install as a system app (starts at login, no Terminal needed)

```bash
./install.sh
```

This builds `~/Applications/ScreenReader.app` (a real menu-bar app wrapping
this project), registers a LaunchAgent so it launches at every login, and
starts it immediately. Re-run it any time to refresh; `./uninstall.sh`
removes the autostart and the app bundle.

**One-time after installing:** grant **Screen Recording**, **Accessibility**
(and **Input Monitoring**, if listed) to **ScreenReader** in System Settings →
Privacy & Security — permissions given to Terminal don't carry over to the new
app. Then quit and reopen it once. Logs go to
`~/Library/Logs/ScreenReader.log` if anything misbehaves.
