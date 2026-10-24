import { http, ApiError, type ApiEnvelope } from '@/api/http'
import type {
  Batch,
  HistoryQuery,
  HistoryResult,
  MailConfig,
  MailFile,
  MailPreview,
  ReportType,
  Upload,
  UploadKind,
} from './types'

const base = '/v1/hr-mail'
async function unwrap<T>(request: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  const { data } = await request
  if (!data.success) throw new ApiError(data.message || '操作未完成')
  return data.data
}
const batchPath = (id: string) => `${base}/batches/${encodeURIComponent(id)}`
// Only permit private files from this feature, never an arbitrary URL supplied in HTML.
export function privateFileUrl(url: string): string {
  const parsed = new URL(url, window.location.origin)
  if (
    parsed.origin !== window.location.origin ||
    !/^\/api\/v1\/hr-mail\/batches\/[^/]+\/files\/[^/]+$/.test(parsed.pathname) ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error('附件地址无效，请刷新批次后重试')
  }
  return parsed.pathname
}
export const hrMailApi = {
  config: () => unwrap<MailConfig>(http.get(`${base}/config`)),
  upload: (file: File, kind: UploadKind) => {
    const form = new FormData()
    form.append('file', file)
    form.append('kind', kind)
    return unwrap<Upload>(http.post(`${base}/uploads`, form))
  },
  create: (reportType: ReportType, reportId: string, mappingId: string) =>
    unwrap<Batch>(http.post(`${base}/batches`, { reportType, reportId, mappingId })),
  history: (params: HistoryQuery) => unwrap<HistoryResult>(http.get(`${base}/batches`, { params })),
  batch: (id: string) => unwrap<Batch>(http.get(batchPath(id))),
  preview: (batchId: string, itemId: string) =>
    unwrap<MailPreview>(http.get(`${batchPath(batchId)}/items/${encodeURIComponent(itemId)}/preview`)),
  send: (id: string, version: number, selectedIds: string[], previewReceipts: Record<string, string>) =>
    unwrap<Batch>(http.post(`${batchPath(id)}/send`, { version, selectedIds, previewReceipts, confirmed: true })),
  download: async (file: MailFile, stillAllowed: () => boolean) => {
    // http already has /api as its baseURL.
    const url = privateFileUrl(file.url).slice(4)
    const response = await http.get<Blob>(url, { responseType: 'blob' })
    if (!stillAllowed()) return
    const objectUrl = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = file.name
    link.click()
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
  },
}
