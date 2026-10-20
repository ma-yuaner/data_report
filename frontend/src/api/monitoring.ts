import { http, type ApiEnvelope } from './http'

export interface MonitorRun {
  id: number
  runNo: string
  jobType: string
  sourceCode?: string
  batchId?: string
  status: string
  rowsRead: number
  rowsWritten: number
  rulesChecked: number
  eventsCreated: number
  errorMessage?: string
  startedAt: string
  finishedAt?: string
  durationMs?: number
}

export type ResourceGrainDimension = 'gds_code' | 'pcc_code' | 'ota_code' | 'ota_site_code' | 'source_api_group'

export interface MonitorRule {
  id: number
  ruleCode: string
  ruleName: string
  templateCode: string
  templateName?: string
  businessType: string
  sourceParentId?: number
  ownerUserName?: string
  severity: string
  status: string
  effectiveStartAt?: string
  effectiveEndAt?: string
  currentVersionNo: number
  lastRunAt?: string
  lastHitAt?: string
  hitCount?: number
  groupDimensions?: ResourceGrainDimension[]
  updatedAt: string
}

export interface MonitorRuleTemplateField {
  id: number
  templateId: number
  fieldCode: string
  fieldName: string
  valueType: string
  allowedOperators: string
  requiredFlag: boolean | number
  optionSource?: string
  sortNo: number
  status: string
}

export interface MonitorRuleTemplate {
  id: number
  templateCode: string
  templateName: string
  category: string
  dataSourceCode: string
  entityType: string
  executionMode: string
  defaultScheduleSeconds: number
  description?: string
  status: string
  fields: MonitorRuleTemplateField[]
}

export interface MonitorCondition {
  id: number
  fieldCode: string
  operatorCode: string
  valueType: string
  valueJson: string
  conditionRole: string
}

export interface MonitorRuleDetail {
  rule: MonitorRule
  versions: Array<Record<string, unknown> & { id: number; versionNo: number; conditions: MonitorCondition[]; groupDimensions?: ResourceGrainDimension[] }>
  logs: Array<Record<string, unknown>>
}

export interface MonitorEvent {
  id: number
  eventNo: string
  ruleId: number
  ruleCode: string
  templateCode: string
  businessType: string
  entityType: string
  entityKey: string
  severity: string
  eventTitle: string
  eventDetail?: string
  eventStatus: string
  hitCount: number
  occurredAt: string
  businessRefType?: string
  businessRefId?: number
  scope?: Record<string, string>
  assigneeUserId?: number | null
  assigneeUserName?: string | null
  dueAt?: string | null
  observeUntil?: string | null
  escalationLevel?: number
  lastEscalatedAt?: string | null
  resolutionCode?: string | null
  actionOrderId?: number | null
}

export interface MonitorEventAssignee { id: number; username: string; displayName: string }

export interface MonitorEventDetail {
  event: MonitorEvent
  logs: Array<Record<string, unknown> & {
    id: number; actionCode?: string; fromStatus?: string; toStatus: string
    operatorName: string; operationNote?: string; createdAt: string
  }>
}

export interface MonitorEventActionInput {
  status: 'ACKNOWLEDGED' | 'OBSERVING' | 'RESOLVED' | 'IGNORED' | 'CLOSED'
  assigneeUserId?: number
  observeUntil?: string
  resolutionCode?: 'FIXED' | 'EXPECTED_TEST' | 'BUSINESS_ACCEPTED' | 'FALSE_POSITIVE' | 'TECH_ACTION_REQUIRED' | 'OTHER'
  note?: string
}

export type MonitorActionType = 'RATE_LIMIT' | 'DISABLE' | 'EXTEND_DISABLE' | 'RESTORE'
export type MonitorActionStatus = 'PENDING' | 'ACCEPTED' | 'EXECUTING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'RECOVERY_PENDING' | 'RECOVERED'

export interface MonitorActionOrder {
  id: number
  actionNo: string
  eventId: number
  eventNo: string
  eventTitle: string
  eventStatus: string
  ruleId: number
  ruleCode: string
  resourceType: 'GDS' | 'OTA'
  targetKey: string
  target?: Record<string, string>
  actionType: MonitorActionType
  occurrenceNo: number
  permanentFlag: boolean | number
  requestNote: string
  requestedByName: string
  assigneeUserId: number
  assigneeUserName: string
  actionStatus: MonitorActionStatus
  plannedStartAt: string
  plannedEndAt?: string | null
  acceptedAt?: string | null
  executedAt?: string | null
  recoveredAt?: string | null
  executionReference?: string | null
  executionNote?: string | null
  failureReason?: string | null
  createdAt: string
  updatedAt: string
}

export interface MonitorActionOrderDetail {
  order: MonitorActionOrder
  logs: Array<Record<string, unknown> & {
    id: number; actionCode: string; fromStatus?: string; toStatus: string
    operatorName: string; operationNote?: string; createdAt: string
  }>
}

export interface MonitorActionOrderCreateInput {
  actionType: Exclude<MonitorActionType, 'RESTORE'>
  assigneeUserId: number
  plannedStartAt?: string
  requestNote: string
}

export interface MonitorActionOrderUpdateInput {
  action: 'ACCEPT' | 'START' | 'SUCCESS' | 'FAIL' | 'CANCEL' | 'RECOVER'
  executionReference?: string
  note?: string
}

export interface MonitorOverview {
  available: boolean
  source: string
  ruleSummary: { totalRules?: number; activeRules?: number; scheduledRules?: number; pausedRules?: number }
  eventSummary: { totalEvents?: number; openEvents?: number; acknowledgedEvents?: number; escalatedEvents?: number; overdueEvents?: number }
  pendingNotifications: number
  failedRuns: number
  recentRuns: MonitorRun[]
  attentionEvents: MonitorEvent[]
  topRules: Array<{ ruleId: number; ruleCode: string; ruleName?: string; eventCount: number }>
}

export interface PagedResult<T> { rows: T[]; total: number; page: number; pageSize: number }

export interface MonitorNotifyEndpoint {
  id: number
  endpointCode: string
  endpointName: string
  channel: 'WECOM'
  webhookMasked: string
  webhookConfigured: boolean
  mentionedUserIds: string[]
  mentionedMobiles: string[]
  smartPlacementEnabled: boolean
  status: 'ACTIVE' | 'DISABLED'
  updatedByName?: string
  updatedAt?: string
}

export interface MonitorNotifyEndpointInput {
  endpointName: string
  webhookUrl?: string
  mentionedUserIds: string[]
  mentionedMobiles: string[]
  smartPlacementEnabled: boolean
  status: 'ACTIVE' | 'DISABLED'
}

export interface MonitorRuleInput {
  templateCode: 'ORDER_SEGMENT_THRESHOLD' | 'GDS_QUERY_RATIO_DAILY' | 'OTA_SUCCESS_RATE_DAILY'
  ruleName: string
  severity: string
  effectiveStartAt?: string
  effectiveEndAt?: string
  ownerUserName?: string
  scheduleSeconds?: number
  changeReason?: string
  notifyPolicy?: { channels: string[]; wecomEndpointIds?: number[] }
  groupDimensions?: ResourceGrainDimension[]
  conditions: Array<{ fieldCode: string; operatorCode: string; value: string | number | string[]; conditionRole?: string }>
}

export interface MonitorMessageTemplate {
  id: number
  templateCode: string
  templateName: string
  eventCode: string
  channel: 'WECOM'
  titleTemplate: string
  bodyTemplate: string
  fieldSchema: { allowedFields?: string[]; fieldLabels?: Record<string, string> }
  versionNo: number
  status: 'ACTIVE' | 'DISABLED'
}

export interface MonitorMessageTemplateCopyInput {
  sourceTemplateId: number
  templateName: string
  titleTemplate: string
  bodyTemplate: string
  status: 'ACTIVE' | 'DISABLED'
}

export interface MonitorNotifyRoute {
  id: number
  routeCode: string
  routeName: string
  eventCode: string
  channel: 'WECOM'
  endpointId: number | null
  endpointName?: string | null
  templateId: number
  templateCode: string
  templateName: string
  recipientStrategy: 'TASK_ASSIGNEE' | 'ATTENTION_OWNER' | 'RULE_OWNER' | 'NONE'
  useSmartDefaultEndpoints: boolean
  priorityNo: number
  status: 'ACTIVE' | 'DISABLED'
}

export interface MonitorNotifyRouteInput {
  routeName: string
  eventCode: string
  endpointId?: number | null
  templateId: number
  recipientStrategy: MonitorNotifyRoute['recipientStrategy']
  useSmartDefaultEndpoints: boolean
  priorityNo: number
  status: 'ACTIVE' | 'DISABLED'
}

export interface MonitorDiagnosticCondition {
  fieldCode: string
  fieldName: string
  operatorCode: string
  expected: unknown
  actual: unknown
  passed: boolean
  conditionRole: string
  groupNo: number
}

export interface MonitorDiagnostic {
  rule: MonitorRule
  order: Record<string, unknown> | null
  event?: Record<string, unknown> | null
  matched: boolean
  conditions: MonitorDiagnosticCondition[]
  stages: Array<{ code: string; name: string; passed: boolean; message: string }>
  recentStats: Array<Record<string, unknown>>
}

export const monitoringApi = {
  overview: () => http.get<ApiEnvelope<MonitorOverview>>('/v1/monitoring/overview').then(response => response.data.data),
  templates: () => http.get<ApiEnvelope<MonitorRuleTemplate[]>>('/v1/monitoring/templates').then(response => response.data.data),
  createRule: (payload: MonitorRuleInput) => http.post<ApiEnvelope<{ id: number; ruleCode: string; status: string; versionNo: number }>>('/v1/monitoring/rules', payload).then(response => response.data.data),
  rules: (params: Record<string, unknown>) => http.get<ApiEnvelope<PagedResult<MonitorRule>>>('/v1/monitoring/rules', { params }).then(response => response.data.data),
  ruleDetail: (id: number) => http.get<ApiEnvelope<MonitorRuleDetail>>(`/v1/monitoring/rules/${id}`).then(response => response.data.data),
  diagnoseRule: (id: number, otaOrderNo: string) => http.get<ApiEnvelope<MonitorDiagnostic>>(`/v1/monitoring/rules/${id}/diagnose`, { params: { otaOrderNo } }).then(response => response.data.data),
  updateRuleStatus: (id: number, payload: { status: string; note?: string }) => http.patch<ApiEnvelope<{ id: number; status: string }>>(`/v1/monitoring/rules/${id}/status`, payload).then(response => response.data.data),
  events: (params: Record<string, unknown>) => http.get<ApiEnvelope<PagedResult<MonitorEvent>>>('/v1/monitoring/events', { params }).then(response => response.data.data),
  eventAssignees: () => http.get<ApiEnvelope<MonitorEventAssignee[]>>('/v1/monitoring/event-assignees').then(response => response.data.data),
  eventDetail: (id: number) => http.get<ApiEnvelope<MonitorEventDetail>>(`/v1/monitoring/events/${id}`).then(response => response.data.data),
  updateEventStatus: (id: number, payload: MonitorEventActionInput) => http.patch<ApiEnvelope<{ id: number; status: string }>>(`/v1/monitoring/events/${id}/status`, payload).then(response => response.data.data),
  actionOrders: (params: Record<string, unknown>) => http.get<ApiEnvelope<PagedResult<MonitorActionOrder>>>('/v1/monitoring/action-orders', { params }).then(response => response.data.data),
  actionOrderDetail: (id: number) => http.get<ApiEnvelope<MonitorActionOrderDetail>>(`/v1/monitoring/action-orders/${id}`).then(response => response.data.data),
  createActionOrder: (eventId: number, payload: MonitorActionOrderCreateInput) => http.post<ApiEnvelope<{ id: number; actionNo: string; status: string; occurrenceNo: number; permanent: boolean; plannedStartAt: string; plannedEndAt?: string }>>(`/v1/monitoring/events/${eventId}/action-orders`, payload).then(response => response.data.data),
  updateActionOrder: (id: number, payload: MonitorActionOrderUpdateInput) => http.patch<ApiEnvelope<{ id: number; status: string; eventStatus: string }>>(`/v1/monitoring/action-orders/${id}/status`, payload).then(response => response.data.data),
  runs: (params: Record<string, unknown> = {}) => http.get<ApiEnvelope<MonitorRun[]>>('/v1/monitoring/runs', { params }).then(response => response.data.data),
  notifyEndpoints: () => http.get<ApiEnvelope<MonitorNotifyEndpoint[]>>('/v1/monitoring/notify-endpoints').then(response => response.data.data),
  createNotifyEndpoint: (payload: MonitorNotifyEndpointInput) => http.post<ApiEnvelope<{ id: number }>>('/v1/monitoring/notify-endpoints', payload).then(response => response.data.data),
  updateNotifyEndpoint: (id: number, payload: MonitorNotifyEndpointInput) => http.put<ApiEnvelope<{ id: number }>>(`/v1/monitoring/notify-endpoints/${id}`, payload).then(response => response.data.data),
  testNotifyEndpoint: (id: number) => http.post<ApiEnvelope<{ id: number; success: boolean; message: string }>>(`/v1/monitoring/notify-endpoints/${id}/test`).then(response => response.data.data),
  messageTemplates: () => http.get<ApiEnvelope<MonitorMessageTemplate[]>>('/v1/monitoring/message-templates').then(response => response.data.data),
  createMessageTemplate: (payload: MonitorMessageTemplateCopyInput) => http.post<ApiEnvelope<{ id: number; templateCode: string; eventCode: string; status: string }>>('/v1/monitoring/message-templates', payload).then(response => response.data.data),
  updateMessageTemplate: (id: number, payload: { titleTemplate: string; bodyTemplate: string; status: 'ACTIVE' | 'DISABLED' }) => http.put<ApiEnvelope<{ id: number; versionNo: number; status: string }>>(`/v1/monitoring/message-templates/${id}`, payload).then(response => response.data.data),
  notifyRoutes: () => http.get<ApiEnvelope<MonitorNotifyRoute[]>>('/v1/monitoring/notify-routes').then(response => response.data.data),
  createNotifyRoute: (payload: MonitorNotifyRouteInput) => http.post<ApiEnvelope<{ id: number }>>('/v1/monitoring/notify-routes', payload).then(response => response.data.data),
  updateNotifyRoute: (id: number, payload: MonitorNotifyRouteInput) => http.put<ApiEnvelope<{ id: number }>>(`/v1/monitoring/notify-routes/${id}`, payload).then(response => response.data.data),
}
