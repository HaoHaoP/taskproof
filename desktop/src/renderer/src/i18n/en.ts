export default {
  app: { title: 'taskproof console', subtitle: 'dispatch console' },

  nav: {
    matrix: 'Matrix',
    projects: 'Projects',
    tasks: 'Tasks',
    settings: 'Settings',
    collapse: 'Hide sidebar',
    expand: 'Show sidebar'
  },

  rail: { title: 'Projects', all: 'All', none: 'None', tasks: 'tasks' },

  live: { on: 'live · every 2s', off: 'polling paused' },

  status: {
    queued: 'Queued',
    running: 'Running',
    verifying: 'Verifying',
    done: 'Done',
    failed: 'Failed',
    blocked: 'Blocked',
    timeout: 'Timed out',
    cancelled: 'Cancelled',
    abnormal: 'Not passing',
    label: 'Status'
  },

  tally: { tasks: 'tasks', flying: 'in progress', failed: 'failed' },

  card: { attempt: 'try', files: 'files' },

  tasks: {
    title: 'All tasks',
    sub: 'Click any row for detail and the verdict.',
    col: { brief: 'Task', adapter: 'Adapter', dur: 'Duration' }
  },

  projects: {
    title: 'Projects',
    sub: 'One row per project. Numbers come from the same aggregate query as the matrix.',
    col: {
      id: 'Project',
      group: 'Group',
      path: 'Path',
      tasks: 'Tasks',
      flying: 'In flight',
      failed: 'Not passing',
      last: 'Last activity',
      probe: 'Acceptance'
    }
  },

  /* The add / edit / remove copy is verbatim from the prototype. Those keys are
     flat and dotted (`proj.group` next to `proj.group.default`); vue-i18n
     matches the whole key before splitting, so they are kept as-is. */
  'proj.add': 'Add project',
  'proj.edit': 'Edit…',
  'proj.remove': 'Remove',
  'proj.actions': 'Actions',
  'proj.register': 'Register',
  'proj.detect': 'Detect',
  'proj.detect.run': 'Detect',
  'proj.detect.d': 'Same as taskproof register --dry-run: pick the code directory, guess the acceptance command, draft AGENTS.',
  'proj.path': 'Repository path',
  'proj.path.d': 'Absolute path. Detection and the acceptance command both run here.',
  'proj.path.locked': 'Immutable once registered. A different path is a different project, and past tasks would be orphaned.',
  'proj.id.locked': 'Immutable — tasks.project stores this id.',
  'proj.aliases': 'Aliases',
  'proj.group': 'Concurrency group',
  'proj.group.d': 'Only one task per group runs at a time. Empty means the default group — i.e. everything serialised.',
  'proj.group.default': 'default · all serialised',
  'proj.verify': 'Acceptance command',
  'proj.verify.d': 'Run independently by taskproof after the agent exits. The agent saying "done" is never evidence.',
  'proj.verify.none': 'not configured (verification is recorded as SKIPPED, never as passed)',
  'proj.verifykind': 'Acceptance kind',
  'proj.forbidden': 'Protected paths',
  'proj.forbidden.d': 'Comma separated. Touching these fails the task.',
  'proj.schema': 'Structured result',
  'proj.schema.d': 'Constrain the agent final answer to JSON.',
  'proj.schema.default': 'Default',
  'proj.schema.none': 'Off',
  'proj.probe': 'Probe result',
  'proj.add.hint': 'Confirms into ~/.taskproof/projects.toml — a hand-editable config file you can commit to your own git.',
  'proj.edit.hint': 'Before saving, the app compares projects.toml with the file on disk; a conflict is surfaced, never silently overwritten.',
  'proj.remove.q': 'Remove this project from the registry?',
  'proj.remove.hint': 'Removes the registry entry only — nothing in the repository is deleted. Its task history loses its project.',
  'proj.conflict': '~/.taskproof/projects.toml was changed outside the app.',
  'proj.reload': 'Reload file',
  'proj.keep': 'Keep my edits',
  /* Not in the prototype: the busy labels and error copy the buttons need. */
  'proj.writing': 'Writing…',
  'proj.detecting': 'Detecting…',
  'proj.error.conflict': 'The registry changed on disk; nothing was written.',
  'proj.error.invalid': 'The registry rejected the change: {detail}',
  'proj.error.forbidden': 'The local service refused the write (bad token).',
  'proj.error.notfound': 'No such project: {detail}',
  'proj.error.network': 'Cannot reach the local service: {detail}',

  probe: { passed: 'probe passed', failed: 'probe failed', none: 'none' },

  dlg: { cancel: 'Cancel', save: 'Save' },

  service: {
    local: 'local service',
    offline: 'disconnected',
    ready: 'connected',
    starting: 'starting',
    stopped: 'stopped',
    failed: 'disconnected',
    retry: 'Retry'
  },

  offline: {
    title: 'Not connected to the local service',
    hint: 'The app spawns the local service on launch. If it did not come up, start one and retry.'
  },

  empty: {
    projects: 'No projects registered yet',
    hint: 'Register a repository to give the console something to show.'
  },

  theme: { dark: 'Dark', light: 'Light', system: 'System' },
  lang: { system: 'System' },

  settings: {
    title: 'Settings',
    sub: 'Settings live in the app userData/settings.json, owned by the main process. Nothing here writes the taskproof registry.',
    appearance: 'Appearance',
    service: 'Service and process',
    about: 'About',
    theme: 'Theme',
    themeDesc: 'Light is a grey-scale mirror of dark: structure, density and accent are unchanged.',
    language: 'Language',
    poll: 'Polling',
    pollDesc: 'Off stops the periodic read; the screen keeps the last snapshot.',
    pollOn: 'every 2s',
    pollOff: 'off',
    workspace: 'Workspace',
    workspaceDesc: 'Where the data lives. Read-only here.',
    taskproof: 'taskproof executable',
    taskproofDesc: 'Leave empty to resolve from PATH.',
    version: 'Version',
    contract: 'Contract',
    contractSynced: 'in sync with the Python constants',
    contractDrift: 'drift detected'
  },

  drift: {
    title: 'The API reported statuses this build does not know',
    hint: 'They are still rendered, in the last column, with a neutral tone -- which means the enum contract has drifted between the two languages.'
  },

  drawer: {
    brief: 'Full brief',
    timeline: 'Timeline',
    claim: 'Worker claims',
    claimNote: 'self-reported, unverified',
    evidence: 'System evidence',
    close: 'Close',
    now: 'now',
    noClaim: '(no result from the worker)',
    noTask: 'No such task',
    verdict: 'Verdict'
  },

  ev: {
    exit: 'exit',
    verify: 'verify',
    files: 'files changed',
    adapter: 'adapter',
    group: 'group',
    notrun: 'not run'
  },

  verdict: { passed: 'Acceptance passed', failed: 'Acceptance failed', by: 'independent run' },

  event: {
    queued: 'queued',
    started: 'dispatched',
    claimed: 'claimed',
    reclaimed: 'reclaimed',
    result_schema: 'result contract',
    adapter: 'adapter run',
    verify: 'verification',
    done: 'done',
    failed: 'failed',
    forbidden: 'protected path touched',
    blocked: 'blocked',
    timeout: 'timed out',
    cancelled: 'cancelled'
  }
}
