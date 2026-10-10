export default {
  app: { title: 'Taskproof 调度台', subtitle: '调度台' },

  nav: { matrix: '矩阵', projects: '项目', tasks: '任务', settings: '设置', collapse: '收起侧栏', expand: '展开侧栏' },

  rail: { title: '项目', all: '全选', none: '清空', tasks: '个任务', lanes: '条道' },

  /* The matrix's board-level filter and its finished-column window. */
  board: {
    range: '范围',
    project: '项目',
    ranges: { today: '今天', '7d': '最近 7 天', '30d': '最近 30 天', all: '全部' },
    capped: '仅取回最近 {n} 条 · 更早的还没取到',
    continue: '继续取回',
    capReached: '已到取回上限',
    taken: '已取回 {n} / 共 {m}',
    takeMore: '取更多',
    hideLane: '隐藏「{name}」列',
    hiddenLanes: '已隐藏 {n} 列（其中 {m} 张卡）',
    showAllLanes: '全部显示',
    capChip: {
      empty: '显示全部',
      all: '显示全部 {total}',
      capped: '显示 {cap} / 共 {total}'
    },
    capMenu: {
      title: '显示上限',
      option: '{n} 张',
      all: '全部'
    }
  },

  live: { on: '实时', off: '已暂停轮询' },

  status: {
    running: '进行中',
    verifying: '验收中',
    done: '完成',
    failed: '失败',
    blocked: '阻塞',
    timeout: '超时',
    cancelled: '已取消',
    abnormal: '未通过',
    label: '状态'
  },

  /* 列头文案。多数列直接用状态词；`blocked` 列是例外 —— 它是「等你看一眼」的
     待办，不是状态词本身，所以另起一个键（状态词「阻塞」保持不变）。 */
  column: { blocked: '待复核' },

  tally: { tasks: '任务', flying: '处理中', failed: '未通过' },

  card: { attempt: '尝试', files: '文件', acceptancePassed: '验收已过', lane: '道' },

  tasks: {
    title: '全部任务',
    sub: '点任意一行看详情与判定。',
    col: { brief: '任务', adapter: '适配器', dur: '耗时' }
  },

  projects: {
    title: '项目总览',
    sub: '每个项目一行，展开是它的道。数字与矩阵同源（同一个聚合查询）。',
    col: {
      id: '项目',
      lane: '道',
      group: '并发组',
      path: '路径',
      lanes: '道数',
      verify: '验收命令',
      tasks: '任务',
      flying: '处理中',
      failed: '未通过',
      last: '最近活动',
      probe: '探针'
    }
  },

  /* 注册表 default 组的展示标签，只读的项目总览仍在用。其余项目键都是写面的
     文案，已一并删除。 */
  'proj.group.default': 'default · 全部串行',

  probe: { passed: '探针通过', failed: '探针失败', none: '未配置' },

  dlg: { cancel: '取消' },

  service: {
    local: '本地服务',
    offline: '未连接',
    ready: '已连接',
    starting: '启动中',
    stopped: '已停止',
    failed: '未连接',
    retry: '重试'
  },

  offline: {
    title: '未连上本地服务',
    hint: '应用启动时会自动拉起本地服务。若它没起来，也可以手动起一个，然后点重试。'
  },

  empty: {
    projects: '还没有登记项目',
    hint: '还没有项目。用 CLI 登记一个 —— taskproof register <path> —— 再用 taskproof run 派活。'
  },

  theme: { dark: '深色', light: '浅色', system: '跟随系统' },
  lang: { system: '跟随系统' },

  settings: {
    title: '设置',
    sub: '设置存在 App 本地 userData/settings.json，主进程持有；这里不写 taskproof 的注册表。',
    appearance: '外观与交互',
    service: '服务与进程',
    desktop: '桌面集成',
    about: '关于与诊断',
    theme: '主题',
    themeDesc: '浅色是深色的灰阶镜像：结构、密度、强调色都不变。',
    language: '语言',
    poll: '轮询',
    pollDesc: '关掉后不再定时读取，界面停在上一次快照。',
    pollOn: '实时',
    pollOff: '关闭',
    portmode: '端口',
    portmodeDesc: '自动会挑一个空闲端口；固定端口便于别的工具连过来，但可能被占用。',
    portmodeAuto: '自动',
    portmodeFixed: '固定',
    port: '固定端口',
    portDesc: '默认 8787。被占用时应用会报错而不是静默换端口。',
    launch: '启动行为',
    launchAuto: '开窗即拉起',
    launchManual: '手动启动',
    notifyFail: '验收未通过时通知',
    notifyDone: '任务完成时通知',
    dockBadge: 'Dock 徽标显示未通过数',
    tray: '关窗到托盘',
    trayDesc: '关窗后服务与通知继续，点托盘图标唤回。',
    autostart: '开机自启',
    autostartDesc: '仅打包后生效；开发态不会写入登录项。',
    adapters: '适配器状态',
    adaptersDesc: '来自 taskproof doctor，只读。',
    limits: '并发与超时',
    limitsDesc: '生效值及其来源，只读；改值走 CLI。',
    capLabel: '并发上限',
    capAuto: '自动探测：{detail}',
    capCli: '{detail}，仅本次',
    registry: '注册表',
    openRegistry: '用默认编辑器打开',
    workspace: 'workspace',
    workspaceDesc: '数据位置，只读展示。',
    taskproof: 'taskproof 可执行文件',
    taskproofDesc: '留空则从 PATH 找。',
    diagnostics: '诊断',
    launchSource: '生效命令',
    launchSourceDesc: '应用最终选中的启动方式，与实际拉起子进程的判定同源。',
    source: {
      setting: '自定义',
      bundled: '随包运行时（应用自带）',
      path: 'PATH 上的 taskproof',
      python3: 'python3 -m taskproof'
    },
    launchArgv: '完整 argv',
    launchArgvDesc: '可复制到终端手动运行本地服务。',
    git: 'git',
    gitMissing: '未检测到 git：闸门的作业树（worktree）与越界判断不可用，其余功能照常运行',
    version: '版本',
    contract: '契约',
    contractSynced: '与 Python 常量同步',
    contractDrift: '检测到合同漂移',
    aboutTaskproof: '关于 Taskproof',
    aboutTaskproofDesc: '版本、运行时与数据位置。'
  },

  about: {
    title: '关于 Taskproof',
    open: '查看',
    source: '源码与反馈都在 GitHub 上。',
    repo: 'GitHub 仓库',
    repoHint: '点开在浏览器里查看。',
    license: '许可证',
    appVersion: 'App 版本',
    cliVersion: 'CLI 版本',
    runtime: '运行时',
    paths: '数据位置',
    userData: 'userData',
    registry: '注册表',
    database: '状态库',
    events: '事件日志',
    copy: '复制诊断信息',
    copied: '已复制'
  },

  drift: {
    title: '出现了这份前端不认识的状态',
    hint: '它们仍被渲染在最后一列，但界面文案与颜色会退化为中性 —— 说明两语言的枚举契约漂移了。'
  },

  drawer: {
    brief: '任务全文',
    timeline: '进度时间线',
    claim: 'worker 自述',
    evidence: '系统证据',
    close: '关闭',
    now: '现在',
    noClaim: '（worker 未给出结果）',
    noTask: '没有这个任务',
    verdict: '验收判定',
    tab: { overview: '概览', log: '日志' }
  },

  /* The log panel: live tail, local search, the notices. The search scope is
     stated in loaded bytes -- never a hard-coded 64KB -- and the truncation
     notice names the line cap rather than dropping the head in silence. */
  log: {
    empty: '暂无输出',
    omitted: '已省略前 {n}',
    search: {
      placeholder: '搜索已加载内容',
      scope: '搜索范围：已加载 {n}',
      none: '无匹配',
      prev: '上一个命中',
      next: '下一个命中'
    },
    jumpBottom: '回到底部（{n} 行新）',
    copy: '复制',
    copied: '已复制',
    refresh: '刷新',
    truncated: '仅保留最后 {n} 行（更早的已丢弃）'
  },

  ev: {
    exit: '退出码',
    verify: '验收',
    files: '改动文件',
    adapter: '适配器',
    group: '并发组',
    lane: '道',
    notrun: '未跑'
  },

  verdict: { passed: '验收通过', failed: '验收未通过', by: '独立验收' },

  event: {
    queued: '排队',
    started: '已派发',
    claimed: '已认领',
    reclaimed: '重新认领',
    result_schema: '结果契约',
    adapter: '执行体',
    verify: '独立验收',
    done: '完成',
    failed: '失败',
    forbidden: '触碰保护路径',
    blocked: '被阻塞',
    timeout: '超时',
    cancelled: '已取消'
  }
}
