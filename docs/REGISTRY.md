# Project registry

The registry is the only configuration file taskproof reads. It is TOML, it
describes *which repositories may be dispatched and how each is verified*, and
it lives in the workspace:

```
~/.taskproof/projects.toml        default; the workspace is configurable
```

`examples/projects.example.toml` is a working starting point. This document is
the reference; that file is the tour.

## Structure

```toml
[defaults]
concurrency = 3      # global cap on simultaneously running tasks
timeout     = 1800   # seconds before a running task is judged stuck and killed

[[project]]
id   = "my-app"
path = "/absolute/path/to/my-app"
group = "my-app"
verify = "npm run build"
verify_kind = "build"
```

`[defaults]` is optional; both keys take the values shown above when omitted.

## Project fields

| Field | Required | Default | Notes |
|---|---|---|---|
| `id` | yes | — | Unique. Every command refers to a project by it. Duplicate ids are a hard error. |
| `path` | yes | — | Must be **absolute**. |
| `group` | no | `"default"` | Concurrency group. See below. |
| `aliases` | no | `[]` | Alternative names accepted wherever an id is accepted. |
| `verify` | no | — | The acceptance command, run by taskproof **after** the agent exits. |
| `verify_kind` | no | `"none"` | `check` / `build` / `none`. Anything else is a hard error. |
| `forbidden_paths` | no | `[]` | Prefix-matched paths the agent must not touch. |
| `result_schema` | no | `"default"` | `"default"`, `"none"`, or an absolute path to a JSON Schema. |
| `auto_registered` | no | `false` | Written by `taskproof register`; not meant to be edited by hand. |

## Semantics worth spelling out

**`group` is a serialisation key, not a label.** One task per group runs at a
time; different groups run in parallel up to `concurrency`. A project with no
`group` lands in `default`, so *every* project that omits it shares one lane and
they all serialise. Give projects different groups when they can be built at the
same time, and the same group when they must not be (shared build output, same
monorepo, same device).

**A missing `verify` is SKIPPED, never "passed".** With no acceptance command,
`verify_kind` is forced to `none` and verification is recorded as skipped. This
is deliberate: "we did not check" and "we checked and it passed" must never look
the same in the audit trail.

**The acceptance command is not the agent's claim.** `verify` runs in the
project path after the agent process has exited. Nothing the agent says about
its own work counts as evidence.

**A missing custom schema is a hard error.** A `result_schema` path that does
not exist stops the run instead of silently falling back to the default —
falling back would change the result contract behind your back.

**Forbidden paths are checked after the run, and not only via git.** A rule
ending in `/` covers the directory and everything below it; a rule without the
trailing slash must match that exact path. A violation fails the task even when
the agent reported success.

The check deliberately does not rest on the `git status` change list alone. git
reports nothing inside `.git/`, and it omits every ignored path — which is what
build output and dependency directories are. Measured: with
`forbidden_paths = ["dist/"]` and `dist/` in `.gitignore`, an adapter wrote
`dist/app.js` and the run was recorded as `done`. So the declared paths are also
fingerprinted before and after the run, which covers `.git/`, ignored paths and
everything else. One limit worth knowing: a protected tree larger than 20000
entries is sampled, and the audit event records `snapshot_truncated: true` when
that happens.

## Hard errors

Each of these stops the run with exit code 2:

```
registry file not found
invalid TOML
[defaults] is not a table
a [[project]] entry is not a table
a project is missing id or path
path is not absolute
duplicate project id
verify_kind is not one of check / build / none
result_schema is neither "default", "none", nor an absolute path
result_schema file not found
```

## Editing it

The file is configuration: commit it to your own repository if that suits you.
`taskproof register <path>` appends an entry and is the intended way to add a
project, but hand-editing is fine — the file is read on every run.

Runtime state never lands here. Tasks, events and verdicts live in the SQLite
store; the audit stream is JSONL.

## Write protocol

The local API is **read-only by default**. The write surface exists only when
the server is started explicitly with the flag:

```
taskproof api --allow-write
```

With the flag the process generates a random token for this session and prints
one extra line to stdout, right after the port line:

```
taskproof api listening on http://127.0.0.1:<port>
taskproof api token <token>
```

The token is generated with `secrets.token_urlsafe(32)`, lives only in the
process's memory, and is never written to a file, never placed in `argv` or the
environment, never logged, and never returned in an HTTP response. The stdout
pipe is the only channel: the parent process (the desktop app) is its only
reader, whereas arguments and environment variables are visible to other
processes under the same macOS account via `ps`. Without `--allow-write` no
token is generated and every write verb keeps returning `405`.

Every write request must present the token:

```
X-Taskproof-Token: <token>
```

| Endpoint | Body | Success |
|---|---|---|
| `GET /api/registry` | — | `200` `{"path", "hash", "mtime"}`; `hash` is the lowercase SHA-256 of the raw bytes |
| `POST /api/projects/probe` | `{"path"}` | `200` a draft entry; **writes nothing** |
| `POST /api/projects` | `{"path", "expected_hash", "id"?, "group"?, "aliases"?, "verify"?, "verify_kind"?, "forbidden_paths"?}` | `201 {"project": {…}}` |
| `PATCH /api/projects/<id>` | `{"expected_hash", …fields}` | `200 {"project": {…}}` |
| `DELETE /api/projects/<id>` | `{"expected_hash"}` | `200 {"removed": "<id>"}` |

`PATCH` may change `aliases`, `group`, `verify`, `verify_kind`,
`forbidden_paths` and `result_schema`. `id` and `path` are immutable once a
project is registered — the id is the value `tasks.project` stores, and a
changed path is effectively a different project — so asking to change either is
rejected with `400`.

Status codes:

```
400  a field is invalid (this includes an attempt to change id or path)
403  the token is missing or wrong
404  no project with that id
409  the registry changed on disk since expected_hash was read (see below)
405  a write verb while writes are disabled (no --allow-write)
```

### Conflicts

The registry is human-editable, so a write never silently overwrites. Every
write first compares the request's `expected_hash` with the file's current
SHA-256. If they disagree the write is refused with `409` and the current file
is handed back so the client can choose what to do:

```json
{"error": "conflict", "hash": "<current>", "content": "<file text>", "projects": [ … ]}
```

Nothing is written on a conflict. It is the caller's decision to reload the file
or retry against the fresh hash.

### Surgical rewrite

Writes are done at the byte level, never by re-serialising the parsed TOML —
that would discard the handwritten comments and any keys `registry.load` does
not understand. Instead the whole file text is read, `[[project]]` block
boundaries are found by line, and only lines inside the target block are added,
changed or removed; every other byte is preserved. Deleting a block also removes
the comment lines directly above it (no blank line in between) and leaves
comments that are separated by a blank line, so a neighbouring project's note is
never taken along. After editing, the candidate is re-parsed with `tomllib` and
re-loaded, and only then written atomically (a temp file in the same directory
followed by `os.replace`). A candidate that fails to parse or validate never
reaches the real file.

---


<sub>Also available in [中文](REGISTRY.zh-CN.md).</sub>
