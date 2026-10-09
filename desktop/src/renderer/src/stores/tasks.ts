/**
 * The console's write surface: new / stop / delete / run-again + queue order.
 *
 * Everything the card menu and the dialogs do lives here, so the components
 * stay declarative and the reasoning -- which failure is a "retry later" and
 * which is a real error, what the confirmation step renders, what a "run again"
 * prefill contains -- is testable without a DOM.
 *
 * Two rules the tests protect:
 *  - a refusal (429) is NOT a failure: the card is still in the queue, so it is
 *    reported as a transient notice and the row is left alone; it must never be
 *    shown as failed or made to disappear,
 *  - a dangerous action always goes through a confirmation, and a successful
 *    write ends by asking the caller to re-read the board -- nothing is stitched
 *    together locally.
 *
 * The write token and the HTTP verbs live only in the main process; this store
 * only ever calls the named `window.tp.tasks` methods and switches on the typed
 * result.
 */
import { computed, reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { i18n } from '../i18n'
import type { Project, Task } from '../api/client'
import { consequenceSummary, draftFromTask, draftValid, emptyDraft, type TaskDraft } from '../compose'
import { useBoardStore } from './board'
import type { TaskCreatePayload, TaskWriteError } from '../../../preload/types'

function unavailable(): TaskWriteError {
  return { kind: 'network', status: 0, message: 'the desktop bridge is unavailable' }
}

export const useTasksStore = defineStore('tasks', () => {
  const board = useBoardStore()

  const composeOpen = ref(false)
  const summaryOpen = ref(false)
  const stopOpen = ref(false)
  const deleteOpen = ref(false)
  const busy = ref(false)
  /** A hard failure, shown inline in whichever sheet is open. */
  const error = ref<string | null>(null)
  /** A transient, non-error notice (a refused spawn: "retry later"). */
  const notice = ref<string | null>(null)
  /** The id this draft was seeded from, for the "run again" header only. It is
   *  never sent -- v1 keeps the ledger flat. */
  const rerunOf = ref<string | null>(null)
  /** The task the stop / delete confirmation is about. */
  const target = ref<Task | null>(null)
  const draft = reactive<TaskDraft>(emptyDraft())

  /** The selected project's registry record, or undefined when it is gone. */
  const selectedProject = computed<Project | undefined>(() =>
    board.projects.find((project) => project.id === draft.project)
  )

  /** The confirmation step's assembled values, recomputed as the draft edits. */
  const summary = computed(() => consequenceSummary(draft, selectedProject.value))

  function copyFor(failure: TaskWriteError): string {
    return String(
      i18n.global.t(`task.error.${failure.kind}`, {
        detail: failure.detail || failure.message
      })
    )
  }

  /** The "retry later" copy a refused spawn earns, chosen by the limit bit. */
  function noticeFor(failure: TaskWriteError): string {
    const key = failure.reason === 'cap' ? 'task.notice.cap' : 'task.notice.group'
    return String(i18n.global.t(key, { detail: failure.detail || failure.message }))
  }

  function requireApi(): NonNullable<Window['tp']>['tasks'] | null {
    return window.tp?.tasks ?? null
  }

  function resetTransient(): void {
    error.value = null
    notice.value = null
  }

  function closeAll(): void {
    composeOpen.value = false
    summaryOpen.value = false
    stopOpen.value = false
    deleteOpen.value = false
    target.value = null
    rerunOf.value = null
  }

  function dismissNotice(): void {
    notice.value = null
  }

  /** Open the blank form. `project` seeds the dropdown so the first dispatch is
   *  one click away; the field stays editable. */
  function openCompose(): void {
    const first = board.projects[0]?.id ?? ''
    Object.assign(draft, emptyDraft(first))
    resetTransient()
    rerunOf.value = null
    composeOpen.value = true
  }

  /** Open the form pre-seeded from a finished task: the "run again" entry. The
   *  timeout is recovered from the task's events (it is not a row column). */
  async function openRerun(task: Task): Promise<boolean> {
    resetTransient()
    const detail = await board.fetchDetail(task.id)
    if (!detail) {
      error.value = copyFor({
        kind: 'notfound',
        status: 0,
        message: `no such task: ${task.id}`
      })
      return false
    }
    Object.assign(draft, draftFromTask(detail.task, detail.events))
    rerunOf.value = task.id
    composeOpen.value = true
    return true
  }

  function closeCompose(): void {
    composeOpen.value = false
    summaryOpen.value = false
    rerunOf.value = null
  }

  /** Stamp the draft into the form's `v-model`. */
  function setDraft(patch: Partial<TaskDraft>): void {
    Object.assign(draft, patch)
  }

  /** Step one -> step two. Blocked until the minimum four fields are filled. */
  function toSummary(): boolean {
    if (!draftValid(draft)) return false
    error.value = null
    composeOpen.value = false
    summaryOpen.value = true
    return true
  }

  function backToCompose(): void {
    summaryOpen.value = false
    composeOpen.value = true
  }

  /** Dispatch. `start` is the two exits: true fires now, false parks queued. */
  async function submit(start: boolean): Promise<boolean> {
    const api = requireApi()
    busy.value = true
    error.value = null
    try {
      if (!api) {
        error.value = copyFor(unavailable())
        return false
      }
      const payload: TaskCreatePayload = {
        project: draft.project,
        brief: draft.brief,
        adapter: draft.adapter,
        timeout: draft.timeout,
        start
      }
      const result = await api.create(payload)
      if (!result.ok) {
        // A refused immediate spawn created nothing, so there is no row to keep
        // in the queue -- this is a real error, and the copy carries the reason
        // (the concurrency one says "retry later").
        error.value = copyFor(result.error)
        return false
      }
      closeAll()
      return true
    } finally {
      busy.value = false
    }
  }

  /** Fire one queued card now (`POST …/advance`). A 429 stays a notice: the row
   *  keeps its place and its seq. */
  async function advance(task: Task): Promise<boolean> {
    const api = requireApi()
    busy.value = true
    resetTransient()
    try {
      if (!api) {
        error.value = copyFor(unavailable())
        return false
      }
      const result = await api.advance(task.id)
      if (result.ok) return true
      if (result.error.kind === 'concurrency') {
        notice.value = noticeFor(result.error)
        return false
      }
      error.value = copyFor(result.error)
      return false
    } finally {
      busy.value = false
    }
  }

  function openStop(task: Task): void {
    resetTransient()
    target.value = task
    stopOpen.value = true
  }

  function closeStop(): void {
    stopOpen.value = false
    target.value = null
  }

  /** Confirm the stop: `POST …/cancel`. The workspace is never touched. */
  async function confirmStop(): Promise<boolean> {
    const api = requireApi()
    const task = target.value
    if (!task) return false
    busy.value = true
    error.value = null
    try {
      if (!api) {
        error.value = copyFor(unavailable())
        return false
      }
      const result = await api.cancel(task.id)
      if (!result.ok) {
        error.value = copyFor(result.error)
        return false
      }
      closeStop()
      return true
    } finally {
      busy.value = false
    }
  }

  function openDelete(task: Task): void {
    // Belt and braces: the menu already greys this for a non-terminal card, but
    // the gate lives here too so no future caller can slip a live row through.
    if (!isDeletable(task)) return
    resetTransient()
    target.value = task
    deleteOpen.value = true
  }

  function closeDelete(): void {
    deleteOpen.value = false
    target.value = null
  }

  /** Confirm the delete: `DELETE …`. Terminal rows only. */
  async function confirmDelete(): Promise<boolean> {
    const api = requireApi()
    const task = target.value
    if (!task) return false
    if (!isDeletable(task)) {
      closeDelete()
      return false
    }
    busy.value = true
    error.value = null
    try {
      if (!api) {
        error.value = copyFor(unavailable())
        return false
      }
      const result = await api.remove(task.id)
      if (!result.ok) {
        error.value = copyFor(result.error)
        return false
      }
      closeDelete()
      return true
    } finally {
      busy.value = false
    }
  }

  /** Edit a queued card's order: `PATCH …` with `{queue_seq}` only. */
  async function patchQueueSeq(task: Task, queueSeq: number | null): Promise<boolean> {
    const api = requireApi()
    resetTransient()
    try {
      if (!api) {
        error.value = copyFor(unavailable())
        return false
      }
      const result = await api.patchQueueSeq(task.id, queueSeq)
      if (!result.ok) {
        error.value = copyFor(result.error)
        return false
      }
      return true
    } finally {
      // no busy flag: the number input should not lock the whole board
    }
  }

  return {
    composeOpen,
    summaryOpen,
    stopOpen,
    deleteOpen,
    busy,
    error,
    notice,
    rerunOf,
    target,
    draft,
    selectedProject,
    summary,
    openCompose,
    openRerun,
    closeCompose,
    setDraft,
    toSummary,
    backToCompose,
    submit,
    advance,
    openStop,
    closeStop,
    confirmStop,
    openDelete,
    closeDelete,
    confirmDelete,
    patchQueueSeq,
    dismissNotice,
    copyFor
  }
})

/** Delete is terminal-only. Exported so the gate is testable in one place. */
export function isDeletable(task: Pick<Task, 'status'>): boolean {
  return ['done', 'failed', 'blocked', 'timeout', 'cancelled'].includes(task.status)
}
