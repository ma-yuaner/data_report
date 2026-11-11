import { http, type ApiEnvelope } from '@/api/http'

export type Fields = Record<string, any>
export interface Option { code: string; name: string }
export interface Person {
  id: string
  name: string
  username?: string
  accountName?: string
  departmentName?: string
  disabled?: boolean
  selectionNote?: string
}
export function admPersonOptions(people: Person[], numeric = false) {
  return people.map((person) => ({
    value: numeric && /^\d+$/.test(person.id) ? Number(person.id) : person.id,
    label: [person.name, person.departmentName, person.username || (person.accountName !== person.name ? person.accountName : ''), person.selectionNote]
      .filter(Boolean).join(' · '),
    disabled: !!person.disabled,
  }))
}
export interface FxSnapshot extends Fields {
  sourceRecordId: string | null
  sourceCode: string | number
  actualSource: string | number
  exchangeUnit: string | number
  rateValue: string
  sourceUpdatedAt: string | null
  rateField: string
}
export interface AdmConfig extends Fields {
  caseStatuses: string[]; lineStatuses: string[]; issuerTypes: string[]
  sourceTypes: string[]
  appealTargets: Array<{ value: string; label: string }>
  appealResults: string[]; problemAttributions: string[]; attachmentCategories: string[]
  people: { handle: Person[]; leader: Person[]; coordinate: Person[]; rosterAvailable?: boolean }
  permissions: Record<string, boolean>
}
export interface AdmLine extends Fields {
  id: number; caseId: number; lineInternalNo: string; lineStatus: string; originalAmount: string
  departmentName: string; leaderId: number | null; leaderName: string | null
  operatorId: number | null; operatorName: string | null
}
export function canChangeAdmLeader(line: AdmLine) {
  return !line.acceptedAt && ['PENDING_LEADER', 'PENDING_OPERATOR', 'PENDING_ACCEPT'].includes(line.lineStatus)
}
export interface AdmCaseRow extends Fields {
  id: number; internalNo: string; admNo: string; issuerName: string; currency: string
  originalAmount: string; caseStatus: string; lineCount: number; completedLineCount: number; voidedLineCount: number
}
export interface AdmCaseDetail extends Fields {
  case: AdmCaseRow; lines: AdmLine[]; attachments: Fields[]; assignments: Fields[]
  responsibilitySegments: Fields[]; recoveries: Fields[]; appeals: Fields[]; reviews: Fields[]
  diffMatches: Fields[]; collections: Fields[]; transfers: Fields[]; operationLogs: Fields[]
  legacySource: Fields | null
}
export type AdmLedgerLine = Pick<AdmLine, 'id' | 'caseId' | 'lineInternalNo' | 'lineStatus' |
  'departmentName' | 'leaderName' | 'operatorName'> & {
  admNo: string; ticketNo: string | null; otaOrderNo: string | null; pnr: string | null
}

async function data<T>(promise: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  const response = await promise
  if (!response.data.success) throw new Error(response.data.message || '操作未成功')
  return response.data.data
}
const base = '/v1/adm'
const casePath = (caseId: number | string) => `${base}/cases/${encodeURIComponent(caseId)}`
const linePath = (caseId: number | string, lineId: number | string) => `${casePath(caseId)}/lines/${encodeURIComponent(lineId)}`

export const admApi = {
  config: () => data<AdmConfig>(http.get(`${base}/config`)),
  options: (kind: string, search = '', limit = 100) => data<Option[]>(http.get(`${base}/reference-options/${encodeURIComponent(kind)}`, { params: { search, limit } })),
  exchangeRate: (currency: string) => data<FxSnapshot>(http.get(`${base}/exchange-rate`, { params: { currency } })),
  list: (params: Fields) => data<{ items: AdmCaseRow[]; pagination: Fields; summary?: Fields }>(http.get(`${base}/cases`, { params })),
  ledgerLines: (params: Fields) =>
    data<{ items: AdmLedgerLine[]; pagination: Fields }>(
      http.get(`${base}/ledger-lines`, { params }),
    ),
  workbenchQueue: (params: { queue: 'close' | 'transfer'; status: 'pending' | 'all'; page: number; pageSize: number }) =>
    data<{ items: Fields[]; pagination: { total: number } }>(http.get(`${base}/workbench/queue`, { params })),
  workbench: () => data<{ items: Fields[]; summary: Fields }>(http.get(`${base}/workbench`)),
  detail: (caseId: number | string) => data<AdmCaseDetail>(http.get(casePath(caseId))),
  summary: (caseId: number | string) => data<AdmCaseDetail>(http.get(`${casePath(caseId)}/summary`)),
  updateCase: (caseId: number | string, body: Fields) => data<AdmCaseDetail>(http.patch(casePath(caseId), body)),
  updateLine: (caseId: number | string, lineId: number | string, body: Fields) => data<AdmCaseDetail>(http.patch(linePath(caseId, lineId), body)),
  addLine: (caseId: number | string, body: Fields) => data<AdmCaseDetail>(http.post(`${casePath(caseId)}/lines`, body)),
  create: (body: Fields, idempotencyKey: string) => data<AdmCaseDetail>(http.post(`${base}/cases`, body, { headers: { 'Idempotency-Key': idempotencyKey } })),
  publishDraft: (caseId: number) => data<Fields>(http.post(`${casePath(caseId)}/publish`, {})),
  deleteDraft: (caseId: number, reason: string) => data<Fields>(http.post(`${casePath(caseId)}/delete-draft`, { reason })),
  template: () => http.get<Blob>(`${base}/imports/template`, { responseType: 'blob' }),
  importPreview: (file: File) => { const form = new FormData(); form.append('file', file); return data<Fields>(http.post(`${base}/imports/preview`, form)) },
  importCommit: (batchNo: string) => data<Fields>(http.post(`${base}/imports/${encodeURIComponent(batchNo)}/commit`, {})),
  assignOperator: (caseId: number, lineId: number, body: Fields) => data<Fields>(http.post(`${linePath(caseId, lineId)}/assign-operator`, body)),
  changeLeader: (caseId: number, lineId: number, body: Fields) => data<Fields>(http.post(`${linePath(caseId, lineId)}/change-leader`, body)),
  accept: (caseId: number, lineId: number) => data<Fields>(http.post(`${linePath(caseId, lineId)}/accept`, {})),
  investigationNote: (caseId: number, lineId: number, investigationNote: string) => data<Fields>(http.post(`${linePath(caseId, lineId)}/investigation-note`, { investigationNote })),
  transfer: (caseId: number, lineId: number, body: Fields) => data<Fields>(http.post(`${linePath(caseId, lineId)}/transfers`, body)),
  decideTransfer: (caseId: number, lineId: number, transferId: number, accepted: boolean, reason = '') => data<Fields>(http.post(`${linePath(caseId, lineId)}/transfers/${transferId}/${accepted ? 'accept' : 'reject'}`, { reason })),
  recoveryDecision: (caseId: number, lineId: number, body: Fields) => data<Fields>(http.post(`${linePath(caseId, lineId)}/recovery-decision`, body)),
  recoveryConfirm: (caseId: number, lineId: number) => data<Fields>(http.post(`${linePath(caseId, lineId)}/recovery-confirm`, {})),
  startAppeal: (caseId: number, lineId: number, body: Fields) => data<Fields>(http.post(`${linePath(caseId, lineId)}/appeals`, body)),
  finishAppeal: (caseId: number, lineId: number, body: Fields) => data<Fields>(http.post(`${linePath(caseId, lineId)}/appeals/result`, body)),
  noAppeal: (caseId: number, lineId: number, body: Fields) => data<Fields>(http.post(`${linePath(caseId, lineId)}/no-appeal`, body)),
  submitReview: (caseId: number, lineId: number) => data<Fields>(http.post(`${linePath(caseId, lineId)}/submit-review`, {})),
  review: (caseId: number, lineId: number, body: Fields) => data<Fields>(http.post(`${linePath(caseId, lineId)}/review`, body)),
  withdrawReview: (caseId: number, lineId: number, reason: string) => data<Fields>(http.post(`${linePath(caseId, lineId)}/withdraw-review`, { reason })),
  checkDifference: (caseId: number, lineId: number) => data<Fields>(http.post(`${linePath(caseId, lineId)}/check-difference-order`, {})),
  collection: (caseId: number, lineId: number, body: Fields) => data<Fields>(http.post(`${linePath(caseId, lineId)}/collections`, body)),
  voidCollection: (caseId: number, lineId: number, collectionId: number, reason: string) => data<Fields>(http.post(`${linePath(caseId, lineId)}/collections/${collectionId}/void`, { reason })),
  voidLine: (caseId: number, lineId: number, reason: string) => data<Fields>(http.post(`${linePath(caseId, lineId)}/void`, { reason })),
  rebalanceLines: (caseId: number, body: Fields) => data<Fields>(http.post(`${casePath(caseId)}/rebalance-lines`, body)),
  close: (caseId: number) => data<Fields>(http.post(`${casePath(caseId)}/close`, {})),
  voidCase: (caseId: number, reason: string) => data<Fields>(http.post(`${casePath(caseId)}/void`, { reason })),
  operatorImport: (file: File, dryRun: boolean) => { const form = new FormData(); form.append('file', file); form.append('dryRun', String(dryRun)); return data<Fields>(http.post(`${base}/operator-imports`, form)) },
  upload: (caseId: number, file: File, category: string, lineId?: number) => { const form = new FormData(); form.append('file', file); form.append('category', category); if (lineId) form.append('lineId', String(lineId)); return data<AdmCaseDetail & { uploadedAttachmentId: number }>(http.post(`${casePath(caseId)}/attachments`, form)) },
  file: (caseId: number, attachmentId: number, mode: 'preview') => http.get<Blob>(`${casePath(caseId)}/attachments/${attachmentId}/${mode}`, { responseType: 'blob' }),
  voidAttachment: (caseId: number, attachmentId: number, reason: string) => data<Fields>(http.post(`${casePath(caseId)}/attachments/${attachmentId}/void`, { reason })),
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob); const anchor = document.createElement('a')
  anchor.href = url; anchor.download = name; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export const statusLabel: Record<string, string> = {
  DRAFT: '草稿', ACTIVE: '处理中', CLOSED: '已结案', HISTORICAL: '历史只读', VOIDED: '已作废', DELETED: '已删除',
  PENDING_LEADER: '待分配组长', PENDING_OPERATOR: '待分配操作员', PENDING_ACCEPT: '待接单', PROCESSING: '办理中',
  PENDING_REVIEW: '待负责人审核', WAITING_DIFF: '待匹配差异单', WAITING_COLLECTION: '待回款', COMPLETED: '已完成',
  UNDECIDED: '待判断', NOT_REQUIRED: '无需恢复', WAITING: '等待中', REMINDER_DUE: '待确认', CONFIRMED: '已确认',
  IN_PROGRESS: '申诉中', SUCCEEDED: '申诉成功', FAILED: '申诉失败', NO_APPEAL: '不申诉', RETURNED: '审核退回', WITHDRAWN: '已撤回',
  SUPPLIER: '供应商', PLATFORM: '平台', AIRLINE: '航司', HUMAN: '人为问题', SYSTEM: '系统问题',
  NOT_MATCHED: '未录入', QUERY_FAILED: '查询失败', NOT_CONNECTED: '未连接',
  MATCHED: '已录入', MATCHED_OTA_ORDER: '已录入', MATCHED_LEGACY_ADM_NO: '已录入', MATCHED_LINE_INTERNAL_NO: '已录入',
  UNMATCHED: '未录入', PENDING: '待匹配', APPROVED: '审核通过', VALID: '有效', VOID: '已作废',
  TEST: '测试数据', LEGACY: '旧系统数据', MANUAL: '新系统人工数据', EXCEL: '新系统导入数据',
}
export const label = (value: unknown) => statusLabel[String(value)] || String(value ?? '—')
export const diffMatchLabel = (value: unknown) => {
  const status = String(value || 'NOT_REQUIRED')
  if (status === 'NOT_REQUIRED') return '无需匹配'
  if (status.startsWith('MATCHED_')) return '已录入'
  return statusLabel[status] || status
}
export const diffMatchTone = (value: unknown) => {
  const status = String(value || 'NOT_REQUIRED')
  return status.startsWith('MATCHED_') || status === 'MATCHED' ? 'green' : status === 'NOT_REQUIRED' ? 'blue' : 'red'
}
export const errorText = (error: unknown) => (error as { message?: string })?.message || '请求失败，请重试'
