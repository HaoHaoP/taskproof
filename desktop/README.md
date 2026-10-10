# taskproof desktop

The Electron console. It replaces the stage-1 static board's **rendering layer
only**; the static board stays as a frozen `file://` snapshot, and the read-only
loopback REST API is unchanged. The console is itself read-only: it polls the
local API and renders the board, but every project registration and task
dispatch lives in the CLI -- there is no write path here, and the app carries no
API token. The matrix windows every column to a cap the operator sets in that
column's own header (`- 10 +`, `All` for no fold); the defaults keep the finished
columns at ten with a fold bar revealing the rest, and the live columns unfolded.
The whole board can be filtered by project and by time range, both held in the
address bar's query string. A tray icon, a Dock badge (the not-passing count) and
launch-at-login are all switchable in settings.

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

The installed command has to be a build that prints its bound port (the `api`
change that comes with stage 2). If `taskproof api --port 0` prints nothing, the
app waits ten seconds, reports `no port reported within 10000ms` and shows the
offline banner — which looks like a frontend bug but is a stale install.
Reinstall it (`pipx reinstall taskproof`) or use the `TASKPROOF_CMD` form above.

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

- **Project CRUD and task control.** Registering, editing or removing a project
  and dispatching / stopping / accepting / deleting a task all live in the CLI
  (`taskproof register`, `taskproof run`, ...). The desktop console is a
  read-only board: it never writes `projects.toml`, never carries an API token,
  and offers no write entry point.
- **Packaging.** `npm run dist:mac` / `dist:win` / `dist:linux` build the
  installers (`electron-builder`), each carrying the Python runtime that
  `scripts/fetch-runtime.mjs` pins by version and sha256. Nothing is signed or
  notarised, and macOS is arm64 only. A local machine can only build the macOS
  package; the other two come from CI's native runners.
