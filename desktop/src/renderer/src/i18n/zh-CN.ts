export default {
  app: { title: 'taskproof 调度台', subtitle: '调度台' },

  nav: { matrix: '矩阵', projects: '项目', tasks: '任务', settings: '设置', collapse: '收起侧栏', expand: '展开侧栏' },

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

  card: { attempt: '尝试', files: '文件' },

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
      last: '最近活动'
    }
  },

  proj: { group: { default: 'default · 全部串行' } },

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
    about: '关于',
    theme: '主题',
    themeDesc: '浅色是深色的灰阶镜像：结构、密度、强调色都不变。',
    language: '语言',
    poll: '轮询',
    pollDesc: '关掉后不再定时读取，界面停在上一次快照。',
    pollOn: '每 2 秒',
    pollOff: '关闭',
    workspace: '工作区',
    workspaceDesc: '数据位置，只读展示。',
    taskproof: 'taskproof 可执行文件',
    taskproofDesc: '留空则从 PATH 找。',
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
