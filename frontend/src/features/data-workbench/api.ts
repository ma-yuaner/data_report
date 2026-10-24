import { http, ApiError, type ApiEnvelope } from '../../api/http'
import type { Catalog, Dataset, Job, Preview, Recipe, Step } from './types'
const base = '/v1/data-workbench'
async function unwrap<T>(request: Promise<{ data: ApiEnvelope<T> }>): Promise<T> {
  const { data } = await request
  if (!data.success) throw new ApiError(data.message || '操作未完成')
  return data.data
}
export const workbenchApi = {
  catalog: () => unwrap<Catalog>(http.get(`${base}/catalog`)),
  upload: (file: File, name: string, sheetName: string) => {
    const data = new FormData()
    data.append('file', file)
    if (name) data.append('name', name)
    if (sheetName) data.append('sheetName', sheetName)
    return unwrap<Dataset>(http.post(`${base}/datasets`, data, { timeout: 360_000 }))
  },
  sourcePreview: (id: string, offset = 0) =>
    unwrap<Preview>(http.get(`${base}/datasets/${encodeURIComponent(id)}/preview`, { params: { offset, limit: 100 } })),
  save: (data: { name: string; sourceId: string; steps: Step[] }, recipe?: Recipe) =>
    recipe
      ? unwrap<Recipe>(
          http.put(`${base}/recipes/${encodeURIComponent(recipe.id)}`, { ...data, revision: recipe.revision }),
        )
      : unwrap<Recipe>(http.post(`${base}/recipes`, data)),
  copy: (id: string) => unwrap<Recipe>(http.post(`${base}/recipes/${encodeURIComponent(id)}/copy`, {})),
  run: (data: {
    sourceId: string
    steps: Step[]
    kind: 'preview' | 'run'
    recipeId?: string
    recipeRevision?: number
  }) => unwrap<Job>(http.post(`${base}/jobs`, data)),
  job: (id: string) => unwrap<Job>(http.get(`${base}/jobs/${encodeURIComponent(id)}`)),
  cancel: (id: string) => unwrap<Job>(http.post(`${base}/jobs/${encodeURIComponent(id)}/cancel`, {})),
  publish: (id: string, name?: string) =>
    unwrap<Dataset>(http.post(`${base}/jobs/${encodeURIComponent(id)}/publish`, { name })),
  result: (id: string, offset = 0) =>
    unwrap<Preview>(http.get(`${base}/jobs/${encodeURIComponent(id)}/preview`, { params: { offset, limit: 100 } })),
  download: async (id: string) => {
    const response = await http.get(`${base}/jobs/${encodeURIComponent(id)}/download`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = `加工结果-${id}.csv`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
