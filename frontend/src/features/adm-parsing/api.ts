import { http } from '@/api/http'
export type ParseIssue = { code: string; path: string; message: string; level: 'error' | 'warning' }
export type ParseTask = {
  id: string
  ownerId: string
  title: string
  version: number
  state: string
  saveStatus: string
  createdAt: string
  updatedAt: string
  stage?: string
  elapsedSeconds?: number
  attempts: number
  files: { id: string; name: string; size: number; sha256: string }[]
  segments?: { id: string; fileId: string; locator: string; text: string }[]
  candidate?: {
    schemaVersion: string
    adm: Record<string, string | null>
    lines: Record<string, unknown>[]
    evidence: { path: string; segmentId: string; quote: string }[]
    conflicts: unknown[]
  } | null
  issues?: ParseIssue[]
  error?: { code: string; message: string } | null
  history?: { at: string; attempt: number; state: string; candidate: unknown; issues: ParseIssue[] }[]
  classification?: { status: string; matches: { reason: string; department: string }[]; requiresReview: boolean }
  model?: string
  promptVersion?: string
  usage?: { prompt_tokens: number; completion_tokens: number } | null
}
export type ParseStatus = {
  localTesting: boolean
  ai: { ready: boolean; configured: boolean; enabled: boolean; model: string }
  schemaVersion: string
  template: unknown
  canUpload: boolean
  extensions: string[]
  maxFiles: number
  maxFileBytes: number
  notice: string
}
async function data<T>(promise: Promise<{ data: { data: T } }>): Promise<T> {
  return (await promise).data.data
}
const base = '/v1/adm/parsing'
export const parsingApi = {
  status: () => data<ParseStatus>(http.get(`${base}/status`)),
  list: (page: number, state: string) =>
    data<{ items: ParseTask[]; total: number }>(http.get(`${base}/tasks`, { params: { page, pageSize: 20, state } })),
  detail: (id: string) => data<ParseTask>(http.get(`${base}/tasks/${id}`)),
  upload: (files: File[], key: string) => {
    const body = new FormData()
    files.forEach((file) => body.append('files', file))
    return data<ParseTask>(http.post(`${base}/tasks`, body, { headers: { 'Idempotency-Key': key }, timeout: 120000 }))
  },
  parse: (task: ParseTask) => data<ParseTask>(http.post(`${base}/tasks/${task.id}/parse`, { version: task.version })),
  retrySave: (task: ParseTask) =>
    data<ParseTask>(http.post(`${base}/tasks/${task.id}/retry-save`, { version: task.version })),
  fileUrl: (task: string, file: string) => `/api${base}/tasks/${task}/files/${file}`,
}
