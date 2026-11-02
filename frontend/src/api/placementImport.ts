import { http, type ApiEnvelope } from './http'

export interface OpportunityImportPreview {
  total: number
  validCount: number
  submit: boolean
  token: string
  errors: { line: number; message: string }[]
  fields: { title: string; key: string }[]
  rows: ({ line: number } & Record<string, string | number | boolean>)[]
}
export interface OpportunityImportResult {
  count: number
  alreadyImported: boolean
  rows: { id: number; taskNo: string; status: string }[]
}

export async function downloadOpportunityTemplate() {
  const response = await http.get<Blob>('/v1/smart-placement/tasks/import/template', { responseType: 'blob' })
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = '分析机会导入模板.xlsx'
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function previewOpportunityImport(file: File, submit: boolean) {
  const values = new FormData()
  values.append('file', file)
  values.append('submit', String(submit))
  const response = await http.post<ApiEnvelope<OpportunityImportPreview>>('/v1/smart-placement/tasks/import/preview', values)
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}

export async function confirmOpportunityImport(token: string) {
  const response = await http.post<ApiEnvelope<OpportunityImportResult>>('/v1/smart-placement/tasks/import/confirm', { token })
  if (!response.data.success) throw new Error(response.data.message)
  return response.data.data
}
