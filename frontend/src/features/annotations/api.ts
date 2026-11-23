import { http, type ApiEnvelope } from '@/api/http'

export type ProjectRole = 'manager' | 'annotator' | 'reviewer'
export type SampleStatus = 'draft' | 'submitted' | 'returned' | 'approved'
export type ProjectKind = 'adm' | 'general'

export interface Label {
  id: string
  name: string
  description: string
  scope: 'field' | 'document'
}

export interface Account {
  id: string
  name: string
}

export interface Member extends Account {
  role: Exclude<ProjectRole, 'manager'>
}

export interface Project {
  id: string
  name: string
  kind: ProjectKind
  ownerId?: string
  version: number
  labels: Label[]
  members: Member[]
  role: ProjectRole
}

export interface SourceFile {
  id: string
  name: string
  sha256: string
  size: number
  pages?: number
}

export interface Segment {
  id: string
  fileId: string
  locator: string
  text: string
  page?: number
}

export interface Region {
  x: number
  y: number
  w: number
  h: number
}

export interface Evidence {
  fileId: string
  segmentId?: string
  page?: number
  start?: number
  end?: number
  quote: string
  rects?: Region[]
  canonicalRange?: [number, number]
}

export interface Mark extends Evidence {
  id?: string
  labelId: string
}

export interface SampleSummary {
  id: string
  projectId: string
  name: string
  title: string
  platform: string
  status: SampleStatus
  version: number
  expected: number | null
  positionCount: number
  assigneeId?: string | null
  sourceTaskId?: string | null
  updatedAt: string
  files: SourceFile[]
  reviewNote?: string
  canEdit?: boolean
  canReview?: boolean
  canAssign?: boolean
  canDelete?: boolean
}

export interface SampleDraft {
  title: string
  platform: string
  fileLabels: string[]
  marks: Mark[]
  titleEvidence: Evidence | null
}

export interface Sample extends SampleSummary, SampleDraft {
  canReopen?: boolean
  labelReviewNeeded?: boolean
  nextEditableId?: string | null
  segments: Segment[]
  history: { action: string; at: string; actor: string; note?: string }[]
}

export interface Dataset {
  id: string
  name: string
  createdAt: string
  count: number
}

interface DatasetDetail extends Dataset {
  samples: unknown[]
}

export interface Comparison {
  sampleId: string
  title: string
  status: 'compared' | 'unlinked' | 'unavailable'
  fields: { label: string; expected: string; actual: string[]; status: 'match' | 'missing' | 'different' }[]
}

const root = '/v1/annotations'
const projectPath = (id: string) => root + '/projects/' + encodeURIComponent(id)
const samplePath = (id: string) => root + '/samples/' + encodeURIComponent(id)
const sourcePath = (sampleId: string, fileId: string) => samplePath(sampleId) + '/files/' + encodeURIComponent(fileId)

export const annotationApi = {
  projects: async () =>
    (await http.get<ApiEnvelope<{ items: Project[]; canCreate: boolean }>>(root + '/projects')).data.data,
  createProject: async (name: string, kind: ProjectKind) =>
    (await http.post<ApiEnvelope<Project>>(root + '/projects', { name, kind })).data.data,
  updateProject: async (
    id: string,
    payload: {
      version: number
      labels: (Omit<Label, 'id'> & { id?: string })[]
      members: Member[]
    },
  ) => (await http.patch<ApiEnvelope<Project>>(projectPath(id), payload)).data.data,
  accounts: async (projectId: string) =>
    (await http.get<ApiEnvelope<{ items: Account[] }>>(root + '/accounts', { params: { projectId } })).data.data,
  samples: async (projectId: string, params: { page: number; status: string; search: string }) =>
    (
      await http.get<
        ApiEnvelope<{
          items: SampleSummary[]
          total: number
          counts: Record<SampleStatus, number>
        }>
      >(projectPath(projectId) + '/samples', { params })
    ).data.data,
  upload: async (id: string, files: File[], group: boolean) => {
    const data = new FormData()
    for (const file of files) data.append('files', file)
    if (group) data.append('group', 'true')
    return (
      await http.post<
        ApiEnvelope<{
          items: SampleSummary[]
          errors: { name: string; message: string }[]
        }>
      >(projectPath(id) + '/samples', data)
    ).data.data
  },
  importAdm: async (id: string, taskId: string) =>
    (await http.post<ApiEnvelope<SampleSummary>>(projectPath(id) + '/import-adm', { taskId })).data.data,
  sample: async (id: string) => (await http.get<ApiEnvelope<Sample>>(samplePath(id))).data.data,
  updateSample: async (id: string, version: number, projectVersion: number, payload: SampleDraft) =>
    (await http.patch<ApiEnvelope<Sample>>(samplePath(id), { version, projectVersion, ...payload })).data.data,
  deleteSample: async (id: string, version: number) =>
    (await http.delete<ApiEnvelope<{ id: string }>>(samplePath(id), { data: { version } })).data.data,
  action: async (
    id: string,
    payload: {
      version: number
      projectVersion?: number
      action: 'submit' | 'approve' | 'return' | 'assign' | 'reopen'
      note?: string
      assigneeId?: string
    },
  ) => (await http.post<ApiEnvelope<Sample>>(samplePath(id) + '/actions', payload)).data.data,
  file: async (sampleId: string, fileId: string, signal?: AbortSignal) =>
    (await http.get<Blob>(sourcePath(sampleId, fileId), { responseType: 'blob', signal })).data,
  datasets: async (id: string) =>
    (await http.get<ApiEnvelope<{ items: Dataset[] }>>(projectPath(id) + '/datasets')).data.data,
  publish: async (id: string, name: string, sampleIds: string[]) =>
    (await http.post<ApiEnvelope<Dataset>>(projectPath(id) + '/datasets', { name, sampleIds })).data.data,
  dataset: async (id: string, datasetId: string) =>
    (await http.get<ApiEnvelope<DatasetDetail>>(projectPath(id) + '/datasets/' + encodeURIComponent(datasetId))).data
      .data,
  compareAdm: async (id: string, datasetId: string) =>
    (
      await http.get<ApiEnvelope<{ samples: Comparison[] }>>(
        projectPath(id) + '/datasets/' + encodeURIComponent(datasetId) + '/compare-adm',
      )
    ).data.data,
}
