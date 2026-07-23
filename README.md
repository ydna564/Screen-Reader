# Screen Reader

A tiny macOS **menu-bar gadget**. Press `Shift+Cmd+1`, drag a rectangle over any area of the screen, and the text inside is recognised in the language you choose from the menu-bar icon and optionally translated. While it works, three things happen.

- The **selected area stays highlighted** on screen.
- The **translated text is pinned in a panel beside the selection** as a reference.
- A **Cancel button just below the selection** dismisses it, and a **Copy button in the panel** puts the text on the clipboard. The panel text is also selectable with the mouse. **Copy Last Text** in the menu recovers the most recent result even after dismissing.

`Shift+Cmd+1` is the hotkey and works as a toggle. Press it to start a selection, press it again to cancel the selection, dismiss the pinned overlay, or stop speech. Once cleared, press it once more for the next selection. Each press-and-drag translates exactly one area.

Everything runs **locally**, using Apple's **Vision** framework for on-device OCR and `say` for speech.

## Example

Reading a PDF's table of contents in WPS Office, press `Shift+Cmd+1`, drag over the section you want (yellow frame), and the recognised text is pinned in the panel beside it, ready to copy.

![Selecting a PDF section and getting the text pinned beside it](docs/example.png)

The **Copy** button puts the text on the clipboard, and the **Cancel** button below the selection dismisses the overlay. Pressing `Shift+Cmd+1` again does the same.

## Hotkeys

| Shortcut | Action |
|----------|--------|
| `Shift+Cmd+1` (idle) | Select an area and translate it (one selection per press) |
| `Shift+Cmd+1` (again) | Cancel the selection, dismiss the pinned overlay, or stop speech |

Press `Esc` while selecting to abort. You can also trigger, dismiss, and pick the language from the eye icon in the menu bar.

The monochrome book icon in the menu bar shows the state with a small symbol beside it. Idle shows none, `+` selecting, `…` recognising, `♪` speaking, `•` overlay pinned.

## Install and run

```bash
cd ~/screen-reader
./run.sh          # first run creates a venv and installs dependencies
```

Or set it up manually.

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python screenreader.py
```

## macOS permissions (required)

Grant these to whichever app launches the tool (Terminal, iTerm, or the packaged app) in **System Settings**, then **Privacy & Security**.

- **Screen Recording**, so the region can be captured.
- **Accessibility**, so the global `Shift+Cmd+1` hotkey works.

If the hotkeys do not respond, it is almost always the Accessibility permission. After granting it, quit and relaunch the tool.

## Choosing the spoken language

Click the menu-bar icon, then **Language**. The default is **English**. Your choice is remembered in `~/.screenreader.json`.

## Project structure

```text
screen-reader/
├── screenreader.py           The whole app, with menu-bar item, region selector,
│                             Vision OCR, translation, speech, pinned overlay
├── install.sh                Builds ~/Applications/ScreenReader.app and
│                             registers the LaunchAgent for login autostart
├── uninstall.sh              Removes the app bundle and the autostart entry
├── run.sh                    Dev mode that creates the venv and runs the script
├── requirements.txt          rumps, pynput, pyobjc (Vision + Quartz)
├── assets/
│   ├── logo.png              Source artwork for the app icon
│   ├── AppIcon.icns          Generated multi-resolution app icon
│   ├── menubar_icon.png      Monochrome template icon for the menu bar
│   └── make_menubar_icon.py  Regenerates menubar_icon.png
└── docs/
    └── example.png           Screenshot used in this README
```

## Optional offline translation

Out of the box the recognised text is spoken as written, using the voice of your selected language. To actually translate the source text into your chosen language first, install two extra packages.

```bash
./.venv/bin/pip install argostranslate langdetect
```

Then download the language pairs you want, for example French to English.

```python
./.venv/bin/python - <<'PY'
import argostranslate.package as p
p.update_package_index()
avail = p.get_available_packages()
pkg = next(x for x in avail if x.from_code=="fr" and x.to_code=="en")
p.install_from_path(pkg.download())
PY
```

Restart the app. It will auto-detect the source language and translate into the language selected in the menu before speaking.

## Install as a system app (starts at login, no Terminal needed)

```bash
./install.sh
```

This builds `~/Applications/ScreenReader.app` (a real menu-bar app wrapping this project), registers a LaunchAgent so it launches at every login, and starts it immediately. Re-run it any time to refresh. `./uninstall.sh` removes the autostart and the app bundle.

One time after installing, grant **Screen Recording**, **Accessibility** (and **Input Monitoring**, if listed) to **ScreenReader** in **System Settings**, then **Privacy & Security**. Permissions given to Terminal do not carry over to the new app. Then quit and reopen it once. Logs go to `~/Library/Logs/ScreenReader.log` if anything misbehaves.

## License

Released under the MIT License. See [LICENSE](LICENSE).
