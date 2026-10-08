# taskproof desktop

The Electron console. It replaces the stage-1 static board's **rendering layer
only**; the static board stays as a frozen `file://` snapshot, and the read-only
loopback REST API is unchanged.

## Run it

```bash
cd desktop
npm install
npm run dev
```

The app spawns the local service itself — `taskproof api --port 0` — reads the
bound port from the child's stdout, and kills the child on exit. It contacts
nothing else; the only remote-ish endpoint is `http://127.0.0.1:<port>`, and the
CSP in `src/renderer/index.html` allows exactly that.

### Against a source checkout

When the Python package is not installed as a command, point the app at the
checkout instead. `TASKPROOF_CMD` may contain arguments:

```bash
cd ~/Documents/Projects/GitHub/taskproof
PYTHONPATH=src TASKPROOF_CMD="python3 -m taskproof" npm --prefix desktop run dev
```

## Checks

```bash
npm run typecheck   # tsc (main + preload) and vue-tsc (renderer)
npm test            # vitest: the status/column mapping, never-hide rule,
                    # locale fallback, formatting
npm run build       # typecheck + a production build of all three targets
```

Layout is not covered by unit tests on purpose — that is verified against a real
window. What *is* covered is the reasoning the UI depends on.

## Layout

```
src/main/       spawning the service, settings, window, the named IPC handlers
src/preload/    the entire renderer-facing surface (window.tp) + shared types
src/renderer/   the Vue app
  contract/     imports the generated enum contract and adds presentation
  components/   StatusMark (the status atom), TaskCard, TaskDrawer
  stores/       board (the single poller), settings
  views/        matrix / projects / tasks / settings — the containers
```

## The enum contract

`../contract/enums.json` is generated from the Python constants:

```bash
cd .. && PYTHONPATH=src python3 tools/gen_contract.py
python3 tools/gen_contract.py --check     # CI: fails on drift
```

Neither side hand-copies the status words. A status that exists in Python but
not here is not a missing translation — it is a task that would disappear from
the board, which is why the contract is generated and checked instead of typed
out.

## Deliberately not here yet

- **Project CRUD.** Writing `projects.toml` needs a write endpoint plus the
  session-only local write token, and it must compare the file's mtime/hash
  before saving. The write path stays in the main process so the token never
  reaches the renderer.
- **Packaging.** `electron-builder` is a dependency and `npm run pack` exists,
  but v1 is dev-run only.
- **Tray, notifications, dock badge, autostart.** The settings page has no
  switch for these yet.
