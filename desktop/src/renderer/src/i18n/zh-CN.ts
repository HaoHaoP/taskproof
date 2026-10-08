export default {
  app: { title: 'taskproof 调度台' },

  nav: { matrix: '矩阵', projects: '项目', tasks: '任务', settings: '设置' },

  rail: { title: '项目', all: '全选', none: '清空', tasks: '个任务' },

  live: { on: '实时 · 每 2 秒', off: '已暂停轮询' },

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

  columns: {
    id: 'ID',
    path: '路径',
    group: '并发组',
    verifyKind: '验收类型',
    tasks: '任务',
    inProgress: '处理中',
    failed: '未通过',
    lastActivity: '最近活动',
    project: '项目',
    brief: '任务',
    adapter: '适配器',
    duration: '时长'
  },

  matrix: { live: '实时', window: '窗口内' },

  card: { attempt: '尝试', files: '文件' },

  tasks: { all: '全部任务', sub: '点任意一行查看详情与事件。' },

  projects: { sub: '注册表里的每个仓库，以及它的任务数。' },

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
    appearance: '外观与语言',
    service: '服务与工作区',
    about: '关于',
    theme: '主题',
    language: '语言',
    workspace: '工作区',
    taskproof: 'taskproof 路径',
    version: '版本',
    contract: '契约',
    contractSynced: '与 Python 常量同步',
    contractDrift: '检测到合同漂移'
  },

  drift: {
    title: '出现了这份前端不认识的状态',
    hint: '它们仍被渲染在最后一列，但界面文案与颜色会退化为中性 —— 说明两语言的枚举契约漂移了。'
  },

  drawer: {
    brief: '任务全文',
    timeline: '时间线',
    claim: 'worker 声称',
    evidence: '系统证据',
    claimNone: '无记录',
    exitCode: '退出码',
    verify: '验收',
    duration: '时长',
    files: '文件',
    adapter: '适配器',
    model: '模型',
    group: '分组',
    close: '关闭'
  }
}
