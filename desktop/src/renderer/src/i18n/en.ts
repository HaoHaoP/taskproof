export default {
  app: { title: 'Taskproof console', subtitle: 'dispatch console' },

  nav: {
    matrix: 'Matrix',
    projects: 'Projects',
    tasks: 'Tasks',
    settings: 'Settings',
    collapse: 'Hide sidebar',
    expand: 'Show sidebar'
  },

  rail: { title: 'Projects', all: 'All', none: 'None', tasks: 'tasks', lanes: 'lanes' },

  /* The matrix's board-level filter and its finished-column window. */
  board: {
    range: 'Range',
    project: 'Project',
    ranges: { today: 'Today', '7d': 'Last 7 days', '30d': 'Last 30 days', all: 'All' },
    capped: 'only the most recent {n} — older rows are not fetched yet',
    continue: 'Fetch earlier',
    capReached: 'fetch limit reached',
    expand: '{n} more · expand',
    collapse: 'collapse',
    taken: 'taken {n} of {m}',
    takeMore: 'Take more',
    hideLane: 'Hide the “{name}” column',
    hiddenLanes: '{n} column(s) hidden · {m} card(s) · show all',
    showAllLanes: 'Show all columns'
  },

  live: { on: 'live', off: 'polling paused' },

  status: {
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

  /* Column-head copy. Most columns reuse the status word; `blocked` is the one
     exception -- it names the operator's job ("needs review"), not the status
     word itself, which stays Blocked. Two purposes, two keys. */
  column: { blocked: 'Needs review' },

  tally: { tasks: 'tasks', flying: 'in progress', failed: 'failed' },

  card: { attempt: 'try', files: 'files', acceptancePassed: 'Acceptance passed', lane: 'lane' },

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

  /* The registry's default-group label, still shown in the read-only project
     overview. Every other project key was a write-surface label and is gone. */
  'proj.group.default': 'default · all serialised',

  probe: { passed: 'probe passed', failed: 'probe failed', none: 'none' },

  dlg: { cancel: 'Cancel' },

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
    hint: 'No projects yet. Register one from the CLI — taskproof register <path> — then dispatch work with taskproof run.'
  },

  theme: { dark: 'Dark', light: 'Light', system: 'System' },
  lang: { system: 'System' },

  settings: {
    title: 'Settings',
    sub: 'Settings live in the app userData/settings.json, owned by the main process. Nothing here writes the taskproof registry.',
    appearance: 'Appearance',
    service: 'Service and process',
    desktop: 'Desktop integration',
    about: 'About and diagnostics',
    theme: 'Theme',
    themeDesc: 'Light is a grey-scale mirror of dark: structure, density and accent are unchanged.',
    language: 'Language',
    poll: 'Polling',
    pollDesc: 'Off stops the periodic read; the screen keeps the last snapshot.',
    pollOn: 'Live',
    pollOff: 'Off',
    portmode: 'Port',
    portmodeDesc: 'Auto picks a free port; a fixed port is easier for other tools to reach but can be taken.',
    portmodeAuto: 'Auto',
    portmodeFixed: 'Fixed',
    port: 'Fixed port',
    portDesc: '8787 by default. If it is taken the app reports an error instead of silently switching.',
    launch: 'On launch',
    launchAuto: 'Spawn on open',
    launchManual: 'Start manually',
    notifyFail: 'Notify when acceptance fails',
    notifyDone: 'Notify when a task finishes',
    dockBadge: 'Dock badge shows the not-passing count',
    tray: 'Close window to tray',
    trayDesc: 'Service and notifications keep running; click the tray icon to bring the window back.',
    autostart: 'Launch at login',
    autostartDesc: 'Only applies to the packaged app; a dev build never registers a login item.',
    adapters: 'Adapter status',
    adaptersDesc: 'From taskproof doctor. Read-only.',
    limits: 'Concurrency and timeout',
    limitsDesc: 'The effective value and where it came from. Read-only; change it with the CLI.',
    capLabel: 'Concurrency cap',
    capAuto: 'auto-detected: {detail}',
    capCli: '{detail}, this run only',
    registry: 'Registry',
    openRegistry: 'Open in default editor',
    workspace: 'Workspace',
    workspaceDesc: 'Where the data lives. Read-only here.',
    taskproof: 'taskproof executable',
    taskproofDesc: 'Leave empty to resolve from PATH.',
    diagnostics: 'Diagnostics',
    launchSource: 'Effective command',
    launchSourceDesc: 'The launcher the app actually resolved, by the same rules it spawns with.',
    source: {
      setting: 'Custom',
      bundled: 'Bundled runtime (shipped with the app)',
      path: 'taskproof on PATH',
      python3: 'python3 -m taskproof'
    },
    launchArgv: 'Full argv',
    launchArgvDesc: 'Copy-paste it to run the local service by hand.',
    git: 'git',
    gitMissing:
      "git not detected: the gate's worktrees and out-of-scope checks are unavailable; everything else runs as usual.",
    version: 'Version',
    contract: 'Contract',
    contractSynced: 'in sync with the Python constants',
    contractDrift: 'drift detected',
    aboutTaskproof: 'About Taskproof',
    aboutTaskproofDesc: 'Versions, runtime and where the data lives.'
  },

  about: {
    title: 'About Taskproof',
    open: 'View',
    source: 'Source and feedback live on GitHub.',
    repo: 'GitHub repository',
    repoHint: 'Opens in your browser.',
    license: 'License',
    appVersion: 'App version',
    cliVersion: 'CLI version',
    runtime: 'Runtime',
    paths: 'Data locations',
    userData: 'userData',
    registry: 'Registry',
    database: 'State database',
    events: 'Event log',
    copy: 'Copy diagnostics',
    copied: 'Copied'
  },

  drift: {
    title: 'The API reported statuses this build does not know',
    hint: 'They are still rendered, in the last column, with a neutral tone -- which means the enum contract has drifted between the two languages.'
  },

  drawer: {
    brief: 'Full brief',
    timeline: 'Timeline',
    claim: 'Worker self-report',
    evidence: 'System evidence',
    close: 'Close',
    now: 'now',
    noClaim: '(no result from the worker)',
    noTask: 'No such task',
    verdict: 'Verdict',
    tab: { overview: 'Overview', log: 'Log' }
  },

  /* The log panel: live tail, local search and its notices. The scope is
     stated in loaded bytes -- never a hard-coded 64KB -- and a truncation is
     announced rather than dropping the head of the log in silence. */
  log: {
    empty: 'No output yet',
    omitted: '{n} omitted before this point',
    search: {
      placeholder: 'Search loaded content',
      scope: 'Search scope: {n} loaded',
      none: 'No matches',
      prev: 'Previous match',
      next: 'Next match'
    },
    jumpBottom: 'Back to bottom ({n} new lines)',
    copy: 'Copy',
    copied: 'Copied',
    refresh: 'Refresh',
    truncated: 'Only the last {n} lines are kept (earlier lines dropped)'
  },

  ev: {
    exit: 'exit',
    verify: 'verify',
    files: 'files changed',
    adapter: 'adapter',
    group: 'group',
    lane: 'lane',
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
