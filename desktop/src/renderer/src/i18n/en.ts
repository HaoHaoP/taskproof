export default {
  app: { title: 'taskproof console' },

  nav: { matrix: 'Matrix', projects: 'Projects', tasks: 'Tasks', settings: 'Settings' },

  rail: { title: 'Project' },

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

  columns: {
    id: 'ID',
    path: 'Path',
    group: 'Group',
    verifyKind: 'Verify type',
    tasks: 'Tasks',
    inProgress: 'In progress',
    failed: 'Failed',
    lastActivity: 'Last activity',
    project: 'Project',
    brief: 'Brief',
    adapter: 'Adapter',
    duration: 'Duration'
  },

  matrix: { live: 'live', window: 'in window' },

  card: { attempt: 'try', files: 'files' },

  tasks: { all: 'All tasks', sub: 'Pick a row to see the brief, the claim and the evidence.' },

  projects: { sub: 'Every repository in the registry, with its task count.' },

  service: {
    local: 'local service',
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

  theme: { dark: 'Dark', light: 'Light', system: 'System' },
  lang: { system: 'System' },

  settings: {
    title: 'Settings',
    appearance: 'Appearance and language',
    service: 'Service and workspace',
    about: 'About',
    theme: 'Theme',
    language: 'Language',
    workspace: 'Workspace',
    taskproof: 'taskproof path',
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
    brief: 'Brief',
    timeline: 'Timeline',
    claim: 'worker claims',
    evidence: 'system evidence',
    claimNone: 'no record',
    exitCode: 'exit',
    verify: 'verify',
    duration: 'duration',
    files: 'files',
    adapter: 'adapter',
    model: 'model',
    group: 'group',
    close: 'Close'
  }
}
