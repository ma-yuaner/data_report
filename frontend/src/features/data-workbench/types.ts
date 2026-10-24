export interface Field {
  id: string
  name: string
  type: string
  sourceName?: string
  position?: number
}
export interface Step {
  id: string
  op: string
  [key: string]: unknown
}
export interface Dataset {
  id: string
  name: string
  rowCount: number
  fields: Field[]
  createdAt: string
  quality: Record<string, unknown>
}
export interface Recipe {
  id: string
  name: string
  sourceId: string
  steps: Step[]
  revision: number
  createdAt: string
  updatedAt: string
}
export interface Job {
  id: string
  kind: 'preview' | 'run'
  status: 'queued' | 'running' | 'cancel_requested' | 'cancelled' | 'succeeded' | 'failed'
  sourceId: string
  steps: Step[]
  createdAt: string
  updatedAt: string
  error?: string
  report?: Record<string, unknown>
  fields?: Field[]
  rowCount?: number
}
export interface Preview {
  fields: Field[]
  rows: Record<string, string | null>[]
  total: number
  offset: number
  limit: number
  scope: 'source' | 'preview' | 'full'
  report?: Record<string, unknown>
}
export interface Catalog {
  datasets: Dataset[]
  recipes: Recipe[]
  jobs: Job[]
  operators: string[]
  limits: Record<string, unknown>
}
