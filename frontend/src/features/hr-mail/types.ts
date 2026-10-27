export type ReportType = 'week' | 'month'
export type UploadKind = ReportType | 'mapping'
export type BatchStatus = 'PREVIEW' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'INTERRUPTED'
export type ItemStatus = 'PENDING' | 'SENDING' | 'SUCCESS' | 'FAILED' | 'UNKNOWN' | 'SKIPPED'
export interface MailFile {
  name: string
  url: string
  sha256?: string
}
export interface Upload {
  id: string
  name: string
  kind: UploadKind
  sha256: string
}
export interface MailConfig {
  storageReady: boolean
  mailConfigReady: boolean
  sendEnabled: boolean
  permissions: { upload: boolean; send: boolean }
  error?: string
  mailConfigError?: string
}
export interface MailItem {
  id: string
  dept_name: string
  dept_leader: string
  to: string
  cc: string
  subject: string
  valid: boolean
  errors: string[]
  indicators: Record<string, unknown>
  persons?: Record<string, unknown>[]
  html_body?: string
  status: ItemStatus
  error: string
  attachment?: MailFile
  previewed?: boolean
}
export interface BatchSummary {
  id: string
  version: number
  reportType: ReportType
  period: string
  status: BatchStatus
  createdAt: string
  operator: string
  total: number
  success: number
  failed: number
  unknown: number
}
export interface Batch extends BatchSummary {
  items: MailItem[]
  charts: MailFile[]
  warnings: string[]
}
export interface MailPreview {
  id: string
  subject: string
  to: string
  cc: string
  html_body: string
  attachment?: MailFile
  receipt: string
}
export interface HistoryQuery {
  page: number
  pageSize: number
  search: string
  reportType: string
  status: string
}
export interface HistoryResult {
  items: BatchSummary[]
  total: number
  page: number
  pageSize: number
}
