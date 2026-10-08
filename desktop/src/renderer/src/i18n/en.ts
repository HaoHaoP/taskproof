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
      last: 'Last activity'
    }
  },

  proj: { group: { default: 'default · all serialised' } },

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
