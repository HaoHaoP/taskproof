/**
 * The projects page's write surface.
 *
 * Everything the add / edit / remove sheets do lives here so the component
 * stays declarative and the reasoning (which failure maps to which banner,
 * what a conflict leaves on screen) can be pinned by unit tests without a DOM.
 *
 * Two rules the tests protect:
 *  - a write reads the registry hash first (that is the main process's job; see
 *    `src/main/projects.ts`) and a 409 is surfaced, never retried or
 *    overwritten. After a conflict no further write leaves this store until the
 *    user picks "reload" or "keep",
 *  - the list is never stitched together locally: the caller re-reads it from
 *    the API after a successful write.
 */
import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { i18n } from '../i18n'
import type { Project } from '../api/client'
import type {
  ConflictSnapshot,
  ProbeVerdict,
  ProjectCreatePayload,
  ProjectPatch,
  RegistryResult,
  WriteError
} from '../../../preload/types'

/** The editable shape behind all three sheets; strings are comma separated. */
export interface ProjectDraft {
  id: string
  path: string
  aliases: string
  group: string
  verify: string
  verify_kind: string
  forbidden: string
  result_schema: string
  /** Set once a probe (add) or an existing row (edit) has filled the form. */
  detected: boolean
  probe: ProbeVerdict | null
  probe_exit: number | null
}

function emptyDraft(): ProjectDraft {
  return {
    id: '',
    path: '',
    aliases: '',
    group: 'default',
    verify: '',
    verify_kind: 'none',
    forbidden: '',
    result_schema: 'default',
    detected: false,
    probe: null,
    probe_exit: null
  }
}

/** One in-flight write, kept so "Keep my edits" can re-apply it verbatim. */
type WriteOp =
  | { kind: 'create'; payload: ProjectCreatePayload }
  | { kind: 'patch'; id: string; patch: ProjectPatch }
  | { kind: 'remove'; id: string }

function csv(values: string[] | null | undefined): string {
  return (values ?? []).join(', ')
}

function splitCsv(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

function emptyConflict(): ConflictSnapshot {
  return { hash: '', content: '', projects: [] }
}

export const useProjectsStore = defineStore('projects', () => {
  const addOpen = ref(false)
  const editOpen = ref(false)
  const removeOpen = ref(false)
  const busy = ref(false)
  const detecting = ref(false)
  /** Human copy for the last failure; null when the last action was clean. */
  const error = ref<string | null>(null)
  /** The 409 body while the conflict banner should be on screen. */
  const conflict = ref<ConflictSnapshot | null>(null)
  const draft = reactive<ProjectDraft>(emptyDraft())

  /** The write that a conflict interrupted, replayed by "Keep my edits". */
  let pending: WriteOp | null = null

  function copyFor(failure: WriteError): string {
    return String(i18n.global.t(`proj.error.${failure.kind}`, { detail: failure.message }))
  }

  function closeAll(): void {
    addOpen.value = false
    editOpen.value = false
    removeOpen.value = false
  }

  function reset(): void {
    error.value = null
    conflict.value = null
    pending = null
  }

  function openAdd(): void {
    Object.assign(draft, emptyDraft())
    reset()
    addOpen.value = true
  }

  function closeAdd(): void {
    addOpen.value = false
  }

  function openEdit(row: Project): void {
    Object.assign(draft, {
      id: row.id,
      path: row.path,
      aliases: csv(row.aliases),
      group: row.group,
      verify: row.verify ?? '',
      verify_kind: row.verify_kind || 'none',
      forbidden: csv(row.forbidden_paths),
      result_schema: row.result_schema || 'default',
      detected: true,
      probe: row.probe ?? null,
      probe_exit: row.probe_exit ?? null
    })
    reset()
    editOpen.value = true
  }

  function closeEdit(): void {
    editOpen.value = false
  }

  function openRemove(row: Project): void {
    Object.assign(draft, { id: row.id, path: row.path })
    reset()
    removeOpen.value = true
  }

  function closeRemove(): void {
    removeOpen.value = false
  }

  /** Ask the API what it would register; the answer fills the add sheet. */
  async function detect(): Promise<boolean> {
    const api = window.tp?.projects
    detecting.value = true
    error.value = null
    try {
      if (!api) {
        error.value = copyFor({
          kind: 'network',
          status: 0,
          message: 'the desktop bridge is unavailable'
        })
        return false
      }
      const result = await api.probe(draft.path)
      if (!result.ok) {
        error.value = copyFor(result.error)
        return false
      }
      const record = result.value
      Object.assign(draft, {
        id: record.id,
        group: record.group || draft.group,
        verify: record.verify ?? '',
        verify_kind: record.verify_kind || 'none',
        forbidden: csv(record.forbidden_paths),
        probe: record.probe,
        probe_exit: record.probe_exit,
        detected: true
      })
      return true
    } finally {
      detecting.value = false
    }
  }

  async function dispatch(op: WriteOp): Promise<RegistryResult<unknown>> {
    const api = window.tp?.projects
    if (!api) {
      return {
        ok: false,
        error: {
          kind: 'network',
          status: 0,
          message: 'the desktop bridge is unavailable'
        }
      }
    }
    if (op.kind === 'create') return api.create(op.payload)
    if (op.kind === 'patch') return api.patch(op.id, op.patch)
    return api.remove(op.id)
  }

  async function run(op: WriteOp): Promise<boolean> {
    busy.value = true
    error.value = null
    const result = await dispatch(op)
    busy.value = false

    if (result.ok) {
      conflict.value = null
      pending = null
      closeAll()
      return true
    }

    error.value = copyFor(result.error)
    if (result.error.kind === 'conflict') {
      conflict.value = result.error.conflict ?? emptyConflict()
      pending = op
      // Surface the banner: close the sheet so the page-level conflict strip,
      // and its two choices, are not hidden behind the modal.
      closeAll()
    }
    return false
  }

  function buildCreate(): ProjectCreatePayload {
    return {
      path: draft.path,
      id: draft.id || undefined,
      group: draft.group || undefined,
      aliases: splitCsv(draft.aliases),
      verify: draft.verify || null,
      verify_kind: draft.verify_kind,
      forbidden_paths: splitCsv(draft.forbidden),
      probe: draft.probe,
      probe_exit: draft.probe_exit
    }
  }

  function buildPatch(): ProjectPatch {
    return {
      aliases: splitCsv(draft.aliases),
      group: draft.group,
      verify: draft.verify || null,
      verify_kind: draft.verify_kind,
      forbidden_paths: splitCsv(draft.forbidden),
      result_schema: draft.result_schema
    }
  }

  /** Register the probed draft (add sheet). */
  function register(): Promise<boolean> {
    return run({ kind: 'create', payload: buildCreate() })
  }

  /** Save the edit sheet. `id` and `path` are immutable and never sent. */
  function save(): Promise<boolean> {
    return run({ kind: 'patch', id: draft.id, patch: buildPatch() })
  }

  function remove(): Promise<boolean> {
    return run({ kind: 'remove', id: draft.id })
  }

  /** "Reload file": throw away the local edits and clear the conflict banner.
   *  The caller re-reads the list, which re-reads the file. */
  function reloadFile(): void {
    reset()
  }

  /** "Keep my edits": re-apply the interrupted write on top of the new file.
   *  The retry reads the *current* hash again, so it is not an overwrite. */
  function keepEdits(): Promise<boolean> {
    if (!pending) {
      conflict.value = null
      return Promise.resolve(false)
    }
    const op = pending
    pending = null
    conflict.value = null
    return run(op)
  }

  return {
    addOpen,
    editOpen,
    removeOpen,
    busy,
    detecting,
    error,
    conflict,
    draft,
    openAdd,
    closeAdd,
    openEdit,
    closeEdit,
    openRemove,
    closeRemove,
    detect,
    register,
    save,
    remove,
    reloadFile,
    keepEdits
  }
})
