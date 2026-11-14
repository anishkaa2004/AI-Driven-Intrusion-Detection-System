# Setting up AI-IDS on a Windows laptop

Tested target: Windows 10 / 11. All commands below are for **PowerShell**
(Start menu → type *PowerShell* → open *Windows PowerShell* or *Terminal*).

> The project was developed on macOS. The Python and JavaScript code is cross-platform, and
> `start.ps1` is written for Windows, but it was not executed on a Windows machine during
> development. If a step fails, the manual steps in section 5 show exactly what the script does.

---

## 1. Install the prerequisites (one time)

| Tool | Where | Notes |
|---|---|---|
| **Python 3.12 or newer** (3.13 / 3.14 recommended) | https://www.python.org/downloads/windows/ | In the installer, tick **"Add python.exe to PATH"**. Python 3.11 and older will **not** work. |
| **Node.js LTS** (20 or newer) | https://nodejs.org/ | Default options are fine. |
| **Git** (optional) | https://git-scm.com/download/win | Only if you get the project from GitHub. |

Close and reopen PowerShell after installing, then check:

```powershell
python --version
```
```powershell
node --version
```

`python --version` must print 3.12 or higher. If it opens the Microsoft Store instead, turn off
*Settings → Apps → Advanced app settings → App execution aliases → python.exe*, or use `py` instead of `python`.

---

## 2. Copy the project to the laptop

Copy the whole `ai-ids` folder (USB drive, zip, or `git clone`). **Before or after copying, delete
these folders if they came along** — they contain macOS-specific files and will not work on Windows:

- `ai-ids\.venv`
- `ai-ids\frontend\node_modules`

You may also delete these so the Windows copy starts fresh (they are recreated automatically):

- `ai-ids\backend\aiids.db`, `aiids.db-wal`, `aiids.db-shm` (the database)
- `ai-ids\backend\.demo_credentials.json` and `ai-ids\backend\.env`

**Where to put it:** a normal folder such as `C:\Projects\ai-ids` or `Documents\ai-ids`.
Avoid a **OneDrive-synced** folder — syncing can lock the SQLite database file while the backend uses it.

---

## 3. Allow PowerShell to run the start script (one time)

Windows blocks local scripts by default. This allows scripts you created locally for your user only:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Answer `Y`. If you downloaded the project as a zip, also unblock the files:

```powershell
Get-ChildItem -Recurse C:\Projects\ai-ids | Unblock-File
```

(Replace `C:\Projects\ai-ids` with your folder.)

---

## 4. Start everything with one command

```powershell
cd C:\Projects\ai-ids
```
```powershell
.\start.ps1 -Demo
```

The **first run takes a few minutes**: it creates the Python environment, installs packages,
installs dashboard packages, creates `backend\.env` with a secret key, trains the ML model and creates the
admin account. Later runs start in a few seconds.

When you see **AI-IDS is running**, your browser opens http://localhost:5173.

- **Email:** `admin@aiids.local`
- **Password:** open `backend\.demo_credentials.json` in Notepad and copy the `"password"` value.

Press **Ctrl+C** in the PowerShell window to stop everything.

| Command | Starts |
|---|---|
| `.\start.ps1` | backend + dashboard |
| `.\start.ps1 -Demo` | + simulated attack traffic every 30 s |
| `.\start.ps1 -Agent` | + the monitoring agent for this laptop (enroll first — section 6) |

Logs are in the `logs\` folder (`backend.log`, `backend.err.log`, `frontend.log`, …).

---

## 5. Manual setup (if you prefer, or if the script fails)

Run these from the `ai-ids` folder. On Windows the virtual-environment Python is
`.venv\Scripts\python.exe` (not `.venv/bin/python` as on macOS).

**Create the environment and install packages:**

```powershell
python -m venv .venv
```
```powershell
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r agent\requirements.txt
```
```powershell
cd frontend; npm.cmd install; cd ..
```

**Create the config file** — copy `.env.example` to `backend\.env`, then generate a key:

```powershell
Copy-Item .env.example backend\.env
```
```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Open `backend\.env` in Notepad, paste the printed key after `AIIDS_SECRET_KEY=`, and change the
`AIIDS_DATABASE_URL=...` line to start with `#` (so the default database location is used). Save.

**Train the model and create the admin account:**

```powershell
.venv\Scripts\python.exe ml\src\train.py
```
```powershell
.venv\Scripts\python.exe scripts\seed_demo_data.py
```

**Run (two PowerShell windows):**

Window 1 — backend:

```powershell
cd backend; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Window 2 — dashboard:

```powershell
cd frontend; npm.cmd run dev
```

Optional window 3 — demo traffic:

```powershell
.venv\Scripts\python.exe scripts\replay_flows.py --scenario all --loop 30
```

**Run the tests:**

```powershell
cd backend; ..\.venv\Scripts\python.exe -m pytest -q
```

---

## 6. Monitor the Windows laptop itself

1. In the dashboard open **Devices**, type a name (e.g. *My Windows laptop*) and click
   **Create enrollment code**.
2. In PowerShell, from the `ai-ids\agent` folder (replace the code):

   ```powershell
   cd agent
   ```
   ```powershell
   ..\.venv\Scripts\python.exe -m agent register --server http://127.0.0.1:8000 --code XXXX-XXXX-XXXX
   ```

   Read the notice and type `y` to confirm you are authorized to monitor this laptop.
3. Start it — either `.\start.ps1 -Agent` next time, or now:

   ```powershell
   ..\.venv\Scripts\python.exe -m agent run
   ```

4. Open **Live monitoring** in the dashboard. Within ~15 s the device shows **Reporting**.

The agent stores its credential in `C:\Users\<you>\.aiids-agent\config.json`. On Windows it can
normally read the full connection table without Administrator rights; if the *Agent health* card
says *user-processes*, start PowerShell with **Run as administrator** for full visibility.

---

## 7. Optional: use two laptops (Mac backend + Windows agent, or the reverse)

This makes a good demo of multi-device monitoring. **Only do this on a network you control
(home Wi-Fi or a phone hotspot), never on college/public Wi-Fi**, because this prototype uses plain HTTP.

On the laptop running the backend:

1. Start the backend listening on the network instead of only localhost:
   ```powershell
   cd backend; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   (on macOS: `../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`)
2. Find its IP address: Windows `ipconfig` (IPv4 Address), macOS *System Settings → Wi-Fi → Details*.
3. If Windows Firewall asks, allow access on **Private networks only**.

On the other laptop, enroll the agent with that address:

```powershell
..\.venv\Scripts\python.exe -m agent register --server http://192.168.1.50:8000 --code XXXX-XXXX-XXXX
```

The agent warns that it is using plain HTTP to a non-local server — that is expected for this lab setup.
Stop the network-exposed backend when you are done.

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `running scripts is disabled on this system` | Do section 3. |
| `python` opens the Microsoft Store | Disable the *App execution alias* (section 1) or reinstall Python with "Add to PATH". |
| `Python 3.12 or newer is required` | Install a newer Python, delete the `.venv` folder, run again. |
| `pip` says *No matching distribution found* | Your Python is too old or too new for a pinned package; install the latest Python from python.org, delete `.venv`, retry. As a last resort remove the `==version` parts in `backend\requirements.txt`. |
| `npm.ps1 cannot be loaded` | Use `npm.cmd` instead of `npm` (the script already does). |
| `Port 8000 is already in use` | Another backend is running. Find it: `Get-NetTCPConnection -LocalPort 8000` then `Stop-Process -Id <OwningProcess>`. |
| Dashboard says *Cannot reach the AI-IDS backend* | The backend isn't running or crashed; check `logs\backend.err.log`. |
| `database is locked` | Move the project out of OneDrive, or close other programs opening `aiids.db`. |
| *ML analytics* shows *No model loaded* | Run `.venv\Scripts\python.exe ml\src\train.py`, restart the backend. |
| Logged out after restarting | Normal if `backend\.env` has no `AIIDS_SECRET_KEY`; add one (section 5). |
| Antivirus quarantines the agent | It reads the connection table, which some products flag. Add an exclusion for the project folder or run only the demo replay. |
| Want a clean start | Stop everything, delete `backend\aiids.db*` and `backend\.demo_credentials.json`, run `.\start.ps1` again. |

For how to use the system once it is running, see [docs/USER_GUIDE.md](docs/USER_GUIDE.md).
