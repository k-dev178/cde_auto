# CDE Studio Status

Desktop GUI app for tracking studio room status on Windows.

The app is local-first:

- No web UI.
- No separate server process.
- No LAN sync.
- Today's reservation list is loaded from the Jeonju University CDE reservation endpoint.
- Room status is stored on the local machine.

## Quick Start

Install Python 3.11 or newer first.

On Windows, make sure `python --version` works in PowerShell. If it opens the Microsoft Store or says Python was not found, install Python from python.org and enable "Add python.exe to PATH" during setup.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Start the GUI app:

```powershell
.\start_app.bat
```

This opens the PySide6 desktop GUI.

Room names are in `config/client.json`:

```json
{
  "theme": "light",
  "rooms": [
    "1호실",
    "2호실",
    "3호실",
    "4호실"
  ]
}
```

## Notes

- Local status cache is stored in `data/room_state.json`.
- Rooms can be added, renamed, and deleted inside the app.
- `config/client.json` stores the room list and selected theme.
