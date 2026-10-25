import { http, type ApiEnvelope } from '@/api/http'

export type Fields = Record<string, any>
export interface AdmPerson {
  id: string
  name: string
}
export interface WorkflowTask extends Fields {
  id: string
  caseId: string
  lineId?: string | null
  admNo: string
  kind: string
  label: string
  ownerId: string | null
  ownerName: string | null
  status: string
  dueAt: string | null
  overdue: boolean
  paused: boolean
  version: number
  url: string | null
  coordinationOnly?: boolean
  needsAssignee?: boolean
}
export interface WorkflowOverview {
  generatedAt: string
  businessDate: string
  scope: string
  summary: { tasks: number; overdue: number; unassigned: number; missingDeadline: number; waiting: number }
  people: {
    ownerId: string | null
    ownerName: string | null
    tasks: number
    overdue: number
    missingDeadline: number
  }[]
  items: WorkflowTask[]
  pagination: { page: number; pageSize: number; total: number }
  limitations: string[]
}
export interface AdmAttachment extends Fields {
  id: string
  name: string
  category: string
  lineId?: string
  mime: string
  size: number
  createdAt: string
}
export interface AdmLine extends Fields {
  id: string
  businessType: string
  platform: string
  orderNo: string
  ticketNo: string
  pnr: string
  currency: string
  amount: string | null
  status: string
  analysis: Fields
  appeals: Fields[]
  recoveries: Fields[]
  difference: Fields
  finance: Fields
  allowedActions?: string[] | Fields
}
export interface AdmCase extends Fields {
  id: string
  admNo: string
  supplierName: string
  currency: string
  originalAmount: string | null
  status: string
  version: number
  partial: boolean
  lines: AdmLine[]
  attachments: AdmAttachment[]
  allowedActions: string[] | Fields
}
export interface AdmConfig extends Fields {
  available: boolean
  storageMode: string
  capabilities: Record<string, boolean | Fields>
  caseStatuses: any[]
  lineStatuses: any[]
  businessTypes: any[]
  attachmentCategories: any[]
  people?: { handle: AdmPerson[]; review: AdmPerson[]; finance: AdmPerson[]; coordinate: AdmPerson[] }
  assignees?: AdmPerson[]
}
export interface ClosureCheck {
  canClose: boolean
  checks: { code: string; label: string; passed: boolean; lineId?: string }[]
  blockers: string[]
  amounts: { currency: string; originalAmount: string | null; allocatedAmount: string | null; gap: string | null }
}
async function data<T>(promise: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  const { data: result } = await promise
  if (!result.success) throw new Error(result.message || '操作未成功')
  return result.data
}
const base = '/v1/adm'
const casePath = (id: string) => `${base}/cases/${encodeURIComponent(id)}`
export const admApi = {
  config: () => data<AdmConfig>(http.get(`${base}/config`)),
  workflow: (params: Fields) => data<WorkflowOverview>(http.get(`${base}/workflow/overview`, { params })),
  list: (params: Fields) =>
    data<{ items: AdmCase[]; pagination: { page: number; pageSize: number; total: number }; summary: Fields }>(
      http.get(`${base}/cases`, { params }),
    ),
  detail: (id: string) => data<AdmCase>(http.get(casePath(id))),
  create: (body: Fields) => data<AdmCase>(http.post(`${base}/cases`, body)),
  update: (id: string, body: Fields) => data<AdmCase>(http.patch(casePath(id), body)),
  copy: (id: string, body: Fields) => data<AdmCase>(http.post(`${casePath(id)}/copy`, body)),
  addLine: (id: string, body: Fields) => data<AdmCase>(http.post(`${casePath(id)}/lines`, body)),
  bulkAssign: (id: string, body: Fields) => data<Fields>(http.post(`${casePath(id)}/lines/bulk-assign`, body)),
  updateLine: (id: string, lineId: string, body: Fields) =>
    data<AdmCase>(http.patch(`${casePath(id)}/lines/${encodeURIComponent(lineId)}`, body)),
  action: (id: string, body: Fields) => data<AdmCase>(http.post(`${casePath(id)}/actions`, body)),
  lineAction: (id: string, lineId: string, body: Fields) =>
    data<AdmCase>(http.post(`${casePath(id)}/lines/${encodeURIComponent(lineId)}/actions`, body)),
  closure: (id: string) => data<ClosureCheck>(http.get(`${casePath(id)}/closure-check`)),
  timeline: (id: string) => data<Fields[]>(http.get(`${casePath(id)}/timeline`)),
  attachments: (id: string) => data<AdmAttachment[]>(http.get(`${casePath(id)}/attachments`)),
  upload: (id: string, file: File, version: number, category: string, lineId = '') => {
    const form = new FormData()
    form.append('file', file)
    form.append('version', String(version))
    form.append('category', category)
    if (lineId) form.append('lineId', lineId)
    return data<Fields>(http.post(`${casePath(id)}/attachments`, form))
  },
  file: (id: string, attachmentId: string, mode: 'preview' | 'download', page = 1) =>
    http.get<Blob>(`${casePath(id)}/attachments/${encodeURIComponent(attachmentId)}/${mode}`, {
      responseType: 'blob',
      params: { page, pageSize: 50 },
    }),
  template: (format: string) => http.get<Blob>(`${base}/templates`, { responseType: 'blob', params: { format } }),
  importPreview: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return data<Fields>(http.post(`${base}/imports/preview`, form))
  },
  importCommit: (previewId: string, idempotencyKey: string) =>
    data<Fields>(http.post(`${base}/imports/${encodeURIComponent(previewId)}/commit`, { idempotencyKey })),
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = name
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const statusLabels: Record<string, string> = {
  DRAFT: '草稿',
  PENDING_ASSIGN: '待分配',
  PENDING_ACCEPT: '待接单',
  PROCESSING: '处理中',
  PENDING_REVIEW: '待审核',
  WAITING_FINANCE: '待财务确认',
  CLOSED: '已结案',
  HISTORICAL: '历史只读档案',
  HISTORICAL_UNVERIFIED: '历史财务未核验',
  COMPLETED: '已完成',
  ISSUE: '出票',
  REFUND: '退票',
  CHANGE: '改签',
  UNKNOWN: '待核实',
  UNVERIFIED: '待核实',
  OURS: '我司订单',
  NOT_OURS: '非我司订单',
}
export const label = (value: unknown) => statusLabels[String(value)] || String(value ?? '—')
export function options(values: any[] | Fields | undefined, fallback: string[] = []) {
  const source = Array.isArray(values)
    ? values
    : values && typeof values === 'object'
      ? Object.entries(values).map(([value, text]) => ({ value, label: text }))
      : fallback
  return source.map((item) =>
    typeof item === 'string'
      ? { value: item, label: label(item) }
      : { value: item.value ?? item.code ?? item.id, label: item.label ?? item.name ?? label(item.value ?? item.code) },
  )
}
export function allowed(entity: Fields | null, action: string): boolean {
  if (!entity) return false
  const actions = entity.allowedActions
  if (Array.isArray(actions)) return actions.includes(action)
  const entry = actions?.[action]
  return entry === true || entry?.allowed === true
}
export function errorText(error: unknown): string {
  const value = error as { status?: number; message?: string; code?: string }
  return value.code === 'ADM_VERSION_CONFLICT'
    ? '记录已被其他页面或人员更新。草稿已保留，请刷新记录并核对后再保存。'
    : value.message || '请求失败，请重试'
}
