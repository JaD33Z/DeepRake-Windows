# DeepRake V1 — Windows installer build

This is the original DeepRake browser GUI and **V1 Quantum-Dig bookmarklet**,
prepared for packaging as a single Windows installer. The V2 popup/relay flow
is not included.

## What the installed app does

1. Install `DeepRake_Setup.exe` (once the Windows build has completed).
2. Launch **DeepRake** using the desktop or Start Menu shortcut.
3. Its small control window keeps a local server running and opens the existing
   browser interface at `http://localhost:5000/dorks`.
4. Drag **Quantum-Dig** from the GUI to the browser's bookmarks bar once.
5. When done, click **Stop and Close** in the DeepRake control window.

Python, Flask, and the pivot engine are bundled inside the installed app.
Recipients do not install Python or use a terminal.

The app listens only on `127.0.0.1:5000` (the original bookmarklet address).
If something else already uses port 5000, the launcher displays an error.
The app needs a web browser and network connectivity to search the public web.
Use DeepRake only for lawful OSINT and authorized research.

## Where data goes

On Windows, writable search results, downloaded harvest data, pivot state, and
seed dorks live under:

`%LOCALAPPDATA%\DeepRake\`

This survives application updates and avoids trying to write inside the
installed application's folder. The installer does not remove these user files
when the application is uninstalled. The bundled seed dorks are copied on
first launch if they are not already present.

## One-time build (Windows)

The easiest reproducible way to produce the setup executable is the included
GitHub Actions workflow:

1. Put the contents of this folder into a **private** GitHub repository.
2. Open **Actions → Build DeepRake V1 Windows Installer → Run workflow**.
3. When the workflow succeeds, download the
   **DeepRake-Windows-Installer** artifact.
4. Unzip the downloaded workflow artifact to get `DeepRake_Setup.exe`.
5. Test the installer on a clean Windows computer before sharing it.

The workflow automatically installs Python build dependencies, creates the
bundled application with PyInstaller, and produces the single installer using
Inno Setup. The **builder** needs Windows; the **recipient** does not need
Python, a virtual environment, PyInstaller, or Inno Setup.

### Manual equivalent

On a Windows developer machine with Python 3.11 and Inno Setup installed,
install `requirements.txt` plus PyInstaller 6.22.3. Build
`deeprake_desktop.py` using PyInstaller's `--onedir --windowed` mode and
include `templates` and `data/dorks` as bundled data. Compile
`installer/DeepRake.iss` with Inno Setup's ISCC. The included GitHub workflow
is the authoritative reference for exact build steps.

## What changed compared to Jon's original source

Only the packaging copy was changed:

- Added a small launch/stop control window; the browser GUI and V1 bookmarklet
  file `templates/dorks.html` are **unchanged**.
- Adjusted the Flask template location for frozen executables.
- Moved writable data to LocalAppData when running packaged.
- Called the **same** pivot engine directly instead of launching a Python
  subprocess (which would relaunch `DeepRake.exe` in a frozen build).
- Fixed two original endpoints that used working-directory-relative paths.
- Disabled Flask debug mode in the original command-line entry point.

The included `tests/test_app.py` exercises the GUI, bookmarklet string, result
intake, pivot generation, harvest download, and clear behavior without network
access.

## Important distribution note

The setup executable is **not digitally signed**. Windows SmartScreen or
Smart App Control may warn about or block unfamiliar unsigned installers.
For distribution beyond a small trusted test group, plan to digitally sign the
installer, verify a clean test machine, and distribute it from a trusted
download location. Many email providers block executable attachments (even
inside ZIP files), so email a download link rather than the setup file.

The completed Windows `.exe` is **not** included in this source ZIP: it must
be built and verified on Windows, as described above.
