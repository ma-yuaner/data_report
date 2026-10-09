import { http, type ApiEnvelope } from './http'

export interface TelemetrySummary {
  visits: number
  users: number
  pages: number
  averageActiveDurationMs: number
  averageLoadDurationMs: number
  queryFailureRate: number
  emptyResultRate: number
}
export interface TelemetryPageRow {
  pageCode: string
  pageTitle: string
  moduleCode: string
  visits: number
  users: number
  averageActiveDurationMs: number
  averageLoadDurationMs: number
  actions: number
  quickExits: number
  querySuccess: number
  queryFailed: number
  emptyResults: number
  queryFailureRate: number
  emptyResultRate: number
}
export interface TelemetryDashboard {
  available: boolean
  error: string
  period: { startDate: string; endDate: string }
  summary: TelemetrySummary
  trend: { date: string; visits: number; users: number; averageActiveDurationMs: number }[]
  pages: TelemetryPageRow[]
  users: { userId: number; displayName: string; role: string; visits: number; activeDurationMs: number; pageCount: number; primaryPageCode: string; primaryPageTitle: string }[]
  paths: { fromPageCode: string; toPageCode: string; toPageTitle: string; visits: number }[]
  recentEvents: { occurredAt: string; userId: number; displayName: string; pageCode: string; eventType: string; elementName: string; resultStatus: string; durationMs: number | null }[]
}
export interface TelemetryEventPayload {
  eventId: string
  visitId: string
  moduleCode: string
  pageCode: string
  routePath: string
  eventType: string
  elementCode?: string
  elementName?: string
  resultStatus?: string
  durationMs?: number
  errorCode?: string
  requestId?: string
  context?: Record<string, string | number | boolean | null | string[]>
  eventVersion: number
  occurredAt: string
  appVersion: string
}

export const telemetryApi = {
  startVisit: (payload: Record<string, unknown>) => http.post<ApiEnvelope<{ visitId: string }>>('/v1/telemetry/visits', payload).then(response => response.data.data),
  updateVisit: (visitId: string, payload: Record<string, unknown>) => http.patch<ApiEnvelope<{ updated: boolean }>>(`/v1/telemetry/visits/${visitId}`, payload).then(response => response.data.data),
  events: (events: TelemetryEventPayload[]) => http.post<ApiEnvelope<{ accepted: number }>>('/v1/telemetry/events', { events }).then(response => response.data.data),
  dashboard: (startDate: string, endDate: string) => http.get<ApiEnvelope<TelemetryDashboard>>('/v1/admin/telemetry/dashboard', { params: { startDate, endDate } }).then(response => response.data.data),
}
