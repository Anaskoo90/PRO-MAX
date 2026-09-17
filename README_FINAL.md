# ARC Auto Clicker + ARC Order Bot — Final Deliverable

## What's in this zip

* `source/` — the full Electron + Python source, with the single-instance
fix applied. `node\\\_modules/`, `out/`, `.venv/`, `\\\_\\\_pycache\\\_\\\_/`, and
`logs/` are excluded (all reproducible — see "Running from source" below).
* `build\\\_output/ARC Auto Clicker-win32-x64/` — a freshly built, ready-to-run
Windows package produced by `electron-forge package` from the exact
source in this zip (see "Build result" below for exactly how this was
produced and what wasn't possible in this environment).

## What was actually fixed

### 1\. App could open more than once (the reported bug)

`src/index.js` had no Electron single-instance lock. Double-launching the
`.exe` (double-click, shortcut, etc.) started a second, fully independent
Electron process — which spawned its **own** Python bridge, giving two ARC
engines fighting over the same Discord window/DXGI camera at once.

**Fix:** added `app.requestSingleInstanceLock()` at the top of
`src/index.js`, Electron's own standard pattern. A second launch attempt
now just focuses the existing window and exits, instead of creating a new
process tree.

### 2\. Start/Stop — already correct, verified, not changed

I checked this carefully since it's exactly the kind of thing that
silently regresses:

* **Electron → Python process:** `ensureArcProcess()` already returns the
existing process if one is alive (`if (arcProcess \\\&\\\& !arcProcess.killed) return arcProcess;`) — clicking Start/Stop repeatedly never spawns a
second Python process.
* **Python → monitor thread:** `electron\\\_bridge.py`'s `"start"` handler
already checks `if thread is None or not thread.is\\\_alive()` before
starting a new thread, and reuses the same `MonitorLoop` instance (so
`Stop` → `Start` doesn't recreate the DXGI camera, which is what caused
the "DXCamera instance already exists" warning loop in an earlier round
of this project). No restart-loop risk found. Left unchanged.

### 3\. Packaging bug found by actually running the build (not in the original bug report)

`forge.config.js` had `asar: true` with no unpack rule. That seals
`arc\\\_order\\\_bot/` — the entire Python engine — inside a read-only `asar`
virtual archive. But `index.js` spawns Python as an **external OS
process** pointed at `arc\\\_order\\\_bot/electron\\\_bridge.py` on disk — that
path doesn't exist for an external process once it's inside `app.asar`.
Running `npm run package`/`make` before this fix would have produced an
app whose Electron window opens fine, but whose entire ARC Order Bot
engine silently fails to spawn.

**Fix:** `forge.config.js` now unpacks `arc\\\_order\\\_bot/\\\*\\\*` from asar. I
rebuilt after the fix and confirmed `electron\\\_bridge.py` and the rest of
the engine are present as real files on disk in `build\\\_output/`, not
sealed in the archive.

## Test results

```
43 passed in 0.11s
```

Run against the exact `arc\\\_order\\\_bot/` in this zip's `source/` folder.

## Build result

`electron-forge package --platform=win32 --arch=x64` — **succeeded**,
including a fresh `npm install` to reconstitute the toolchain (this
environment's `node\\\_modules` was missing `electron`/`@electron-forge/cli`
entirely before that). Output is `build\\\_output/ARC Auto Clicker-win32-x64/`,
verified to contain the unpacked `arc\\\_order\\\_bot/` engine.

`electron-forge make` (the Squirrel Windows **installer**) — **could not
run here**: `electron-winstaller` requires Mono and Wine to build a
Windows installer from a non-Windows machine, and I'm running in a Linux
sandbox with neither installed. This is the same category of limitation
as the PyInstaller Windows-only build earlier in this project — I can
build the app itself, not a Windows installer, from here.

**To produce the `.exe` installer, run this on an actual Windows machine:**

```powershell
cd source
npm install
npm run make
```

Output: `out\\\\make\\\\squirrel.windows\\\\x64\\\\\\\*.exe`.

**`build\\\_output/` in this zip is already a complete, portable app** — copy
the whole `ARC Auto Clicker-win32-x64` folder anywhere on a Windows
machine and run `ARC Auto Clicker.exe` directly; no installer needed for
that.

## Running from source (development)

```powershell
cd source
npm install
cd arc\\\_order\\\_bot
python -m venv .venv
.venv\\\\Scripts\\\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cd ..
npm start
```

## What I did not touch

* The ARC Order Bot decision/vision/click logic itself (RIVO/TGBOOST/
FIVE\_STAR/FUSIONHUB workflows, card binding, inventory gate,
verification-pause behavior) — this task was scoped to packaging and
process-management, and that engine already passes its own 43 tests
unmodified.
* The shape+color human-verification challenge remains detect-and-pause
only, per the standing boundary established earlier in this project —
not something this packaging fix changes.

