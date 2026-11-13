import { http } from '@/api/http'
import type { Fields } from './api'
const unwrap = async (request: Promise<any>) => (await request).data.data as Fields
export const operationsApi = {
 report: (params: Fields) => http.get('/v1/adm/analysis/report', { params, responseType:'blob' }),
 analysis: (params: Fields) => unwrap(http.get('/v1/adm/analysis', { params })),
 rows: (params: Fields) => unwrap(http.get('/v1/adm/analysis/rows', { params })),
 settings: () => unwrap(http.get('/v1/adm/operations/settings')),
 saveSettings: (body: Fields) => unwrap(http.put('/v1/adm/operations/settings', body)),
 endpoints: () => unwrap(http.get('/v1/adm/operations/endpoints')),
 preview: () => unwrap(http.get('/v1/adm/operations/preview')),
 context: (caseId: number, lineId: number) => unwrap(http.get(`/v1/adm/cases/${caseId}/lines/${lineId}/context`)),
 saveContext: (caseId: number, lineId: number, body: Fields) => unwrap(http.put(`/v1/adm/cases/${caseId}/lines/${lineId}/context`, body)),
}
export const causeOptions = [
 {value:'HUMAN',label:'人为'}, {value:'SYSTEM',label:'系统'}, {value:'EXTERNAL',label:'外部规则 / 平台'},
 {value:'BUSINESS',label:'业务原因'}, {value:'FORCE_MAJEURE',label:'不可抗力'}, {value:'UNKNOWN',label:'待查明'},
]
