export default {
  app: { title: 'Taskproof 调度台', subtitle: '调度台' },

  nav: { matrix: '矩阵', projects: '项目', tasks: '任务', settings: '设置', collapse: '收起侧栏', expand: '展开侧栏' },

  rail: { title: '项目', all: '全选', none: '清空', tasks: '个任务' },

  /* The matrix's board-level filter and its finished-column window. */
  board: {
    range: '范围',
    project: '项目',
    ranges: { today: '今天', '7d': '最近 7 天', '30d': '最近 30 天', all: '全部' },
    capped: '仅取回最近 {n} 条 · 更早的还没取到',
    continue: '继续取回',
    expand: '还有 {n} 张 · 展开',
    collapse: '收起',
    taken: '已取回 {n} / 共 {m}',
    takeMore: '取更多'
  },

  live: { on: '实时', off: '已暂停轮询' },

  status: {
    queued: '排队',
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

  tally: { tasks: '任务', flying: '处理中', failed: '未通过' },

  card: { attempt: '尝试', files: '文件' },

  /* 控制台的四个动作 + 新增表单 + 排队列。统一放在 `task.*`（单数）下，
     卡片菜单、失败文案与弹窗都读这一个命名空间；`tasks`（复数）是任务表页。 */
  task: {
    new: '新增任务',
    menu: '操作',
    advance: '立刻发车',
    stop: '停止',
    delete: '删除',
    rerun: '再跑一次',
    busy: '处理中…',
    dismiss: '忽略',
    compose: {
      title: '新增任务',
      rerun: '再跑一次',
      project: '项目',
      brief: '任务 brief',
      briefPlaceholder: '要 agent 做什么？',
      adapter: '适配器',
      timeout: '超时',
      seconds: '秒',
      review: '查看后果摘要',
      back: '返回',
      noProjects: '还没有登记项目'
    },
    summary: {
      title: '发车前确认',
      project: '项目',
      path: '真实路径',
      adapter: '适配器',
      timeout: '最长时长',
      forbidden: '生效的保护路径',
      none: '无',
      seconds: '{n} 秒',
      dispatch: '立刻发车',
      queue: '存为待发车'
    },
    confirmStop: {
      title: '停止这个任务？',
      body: '工作区不会被动。任务会记为「已取消」。此操作不可撤销。',
      confirm: '停止'
    },
    confirmDelete: {
      title: '删除这个任务？',
      body: '会删除任务记录与事件流。此操作不可撤销。',
      confirm: '删除'
    },
    queue: {
      order: '序号',
      wave: '同波',
      waveHint: '序号相同 = 同一波'
    },
    error: {
      concurrency: '暂时被拒：{detail}',
      state: '当前状态不允许这个操作：{detail}',
      invalid: '请求被拒绝：{detail}',
      forbidden: '本地服务拒绝了写入（令牌不对）。',
      notfound: '没有这个任务：{detail}',
      network: '连不上本地服务：{detail}'
    },
    notice: {
      group: '这个项目的道被占用了 —— 卡片仍在排队，稍后重试。',
      cap: '全局并发已满 —— 卡片仍在排队，稍后重试。'
    }
  },

  tasks: {
    title: '全部任务',
    sub: '点任意一行看详情与判定。',
    col: { brief: '任务', adapter: '适配器', dur: '耗时' }
  },

  projects: {
    title: '项目总览',
    sub: '每个项目一行。数字与矩阵同源（同一个聚合查询）。',
    col: {
      id: '项目',
      group: '并发组',
      path: '路径',
      tasks: '任务',
      flying: '处理中',
      failed: '未通过',
      last: '最近活动',
      probe: '验收命令'
    }
  },

  /* 增删改文案逐字取自原型。原型用的是扁平点号键（`proj.group` 与
     `proj.group.default` 并存），vue-i18n 查找扁平键时先按整串匹配，所以
     这里原样保留这些键，不做嵌套改写。 */
  'proj.add': '新增项目',
  'proj.edit': '编辑…',
  'proj.remove': '移除',
  'proj.actions': '操作',
  'proj.register': '登记',
  'proj.detect': '探测',
  'proj.detect.run': '探测',
  'proj.detect.d': '等价于 taskproof register --dry-run：挑代码目录、猜验收命令、生成 AGENTS 草稿。',
  'proj.path': '仓库路径',
  'proj.path.d': '绝对路径。探测与验收命令都在这里跑。',
  'proj.path.locked': '登记后不可改。改路径等于换了项目，历史任务记录会挂空。',
  'proj.id.locked': '不可改 —— tasks.project 存的就是它。',
  'proj.aliases': '别名',
  'proj.group': '并发组',
  'proj.group.d': '同一组的项目同时只跑 1 个任务。留空＝落进 default 组，也就是全部串行。',
  'proj.group.default': 'default · 全部串行',
  'proj.verify': '验收命令',
  'proj.verify.d': 'agent 退出后由 taskproof 独立跑一遍。agent 自称"完成"永远不算证据。',
  'proj.verify.none': '未配置（验收记为 SKIPPED，不会记为通过）',
  'proj.verifykind': '验收方式',
  'proj.forbidden': '禁改路径',
  'proj.forbidden.d': '逗号分隔。agent 碰这些路径即判失败。',
  'proj.schema': '结构化结果',
  'proj.schema.d': '约束 agent 的最终回答为 JSON。',
  'proj.schema.default': '默认',
  'proj.schema.none': '关闭',
  'proj.probe': '探测结果',
  'proj.add.hint': '确认后会写进 ~/.taskproof/projects.toml —— 那是人可编辑的配置文件，会被一起提交进你自己的 git。',
  'proj.edit.hint': '保存前会先比对 projects.toml 是否被外部改过；冲突会提示你选，不会静默覆盖。',
  'proj.remove.q': '移除这个项目的登记？',
  'proj.remove.hint': '只从注册表里去掉，不会删除仓库里的任何文件。该项目的任务记录会失去对应项目。',
  'proj.conflict': '~/.taskproof/projects.toml 已被外部修改。',
  'proj.reload': '重新载入文件',
  'proj.keep': '保留我的改动',
  /* 原型没有、忙碌态与错误文案需要的键。 */
  'proj.writing': '写中…',
  'proj.detecting': '探测中…',
  'proj.error.conflict': '注册表已被外部修改，这次改动没有写入。',
  'proj.error.invalid': '注册表拒绝了这次改动：{detail}',
  'proj.error.forbidden': '本地服务拒绝了写入（令牌不对）。',
  'proj.error.notfound': '没有这个项目：{detail}',
  'proj.error.network': '连不上本地服务：{detail}',

  probe: { passed: '探针通过', failed: '探针失败', none: '未配置' },

  dlg: { cancel: '取消', save: '保存' },

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
    hint: '登记一个仓库，调度台就有人可看。'
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
    limitsDesc: '来自注册表全局默认，只读。',
    token: '写操作令牌',
    tokenDesc: '回环口对本机任何网页都可达；写端点必须带令牌，否则任意网页都能改你的注册表。',
    tokenValue: '会话内有效 · 不落盘',
    registry: '注册表',
    openRegistry: '用默认编辑器打开',
    workspace: 'workspace',
    workspaceDesc: '数据位置，只读展示。',
    taskproof: 'taskproof 可执行文件',
    taskproofDesc: '留空则从 PATH 找。',
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
    claim: 'worker 声称',
    claimNote: '自述，未经核实',
    evidence: '系统证据',
    close: '关闭',
    now: '现在',
    noClaim: '（worker 未给出结果）',
    noTask: '没有这个任务',
    verdict: '验收判定'
  },

  ev: {
    exit: '退出码',
    verify: '验收',
    files: '改动文件',
    adapter: '适配器',
    group: '并发组',
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
