import { defineStore } from 'pinia'

export type RouteRiskStatus = 'NORMAL' | 'WATCH' | 'BREACHED' | 'OFFLINE'
export type GovernanceEventStatus = 'OPEN' | 'ACKNOWLEDGED' | 'OBSERVING' | 'ACTION_PENDING' | 'ACTION_APPLIED' | 'RESOLVED'
export type GovernanceActionStatus = 'PENDING' | 'ACCEPTED' | 'EXECUTING' | 'SUCCEEDED' | 'RECOVERY_PENDING' | 'RECOVERED'

export interface RouteMetric {
  id: string
  route: string
  depCity: string
  arrCity: string
  airline: string
  gdsCode: string
  pccCode: string
  platform: string
  site: string
  queryCount: number
  segmentCount: number
  queryToSegmentRatio: number
  mpShare: number
  mpisShare: number
  ndcShare: number
  searchSuccessRate: number
  whitelistStatus: 'ACTIVE' | 'EXPIRING' | 'INACTIVE'
  riskStatus: RouteRiskStatus
  suggestion: string
}

export interface RouteConfiguration {
  id: string
  route: string
  platform: string
  gdsCode: string
  pccCode: string
  passengerScope: string
  tripType: string
  outboundDays: string
  returnDays: string
  channel: 'MP' | 'MPIS' | 'NDC'
  queryCount: number
  segmentCount: number
  ratio: number
  successRate: number
  status: '达标' | '观察' | '异常'
  suggestion: string
}

export interface WhitelistRecord {
  id: string
  route: string
  airline: string
  platform: string
  site: string
  gdsCode: string
  pccCode: string
  channel: string
  configCount: number
  effectiveFrom: string
  effectiveTo: string
  status: 'ACTIVE' | 'EXPIRING' | 'INACTIVE'
  version: string
  updatedAt: string
}

export interface QualityMetric {
  id: string
  gdsCode: string
  pccCode: string
  apiGroup: string
  platform: string
  searchRequests: number
  searchSuccessRate: number
  verifySuccessRate: number
  orderSuccessRate: number
  timeoutRate: number
  topFailure: string
  status: '正常' | '观察' | '异常'
}

export interface GovernanceEvent {
  id: string
  severity: 'P0' | 'P1' | 'P2'
  eventType: string
  target: string
  targetType: '航线' | '配置' | '接口'
  evidence: string
  actualValue: string
  threshold: string
  owner: string
  status: GovernanceEventStatus
  occurredAt: string
  dueAt: string
  whitelistVersion: string
  suggestion: string
}

export interface GovernanceAction {
  id: string
  eventId: string
  actionNo: string
  target: string
  targetType: string
  actionType: 'RATE_LIMIT' | 'DISABLE' | 'EXTEND_DISABLE' | 'RESTORE' | 'ROUTE_TO_MPIS'
  occurrenceNo: number
  durationMinutes: number | null
  permanent: boolean
  status: GovernanceActionStatus
  owner: string
  technicalOwner: string
  plannedStartAt: string
  plannedEndAt: string
  receiptNo: string
  note: string
}

const routes: RouteMetric[] = [
  { id: 'R-HKG-ICN', route: 'HKG-ICN', depCity: '香港', arrCity: '首尔', airline: '7C', gdsCode: '1A', pccCode: 'HKGH228DF', platform: '携程', site: '香港携程一部', queryCount: 12846200, segmentCount: 2238, queryToSegmentRatio: 5740, mpShare: 76, mpisShare: 19, ndcShare: 5, searchSuccessRate: 96.8, whitelistStatus: 'ACTIVE', riskStatus: 'BREACHED', suggestion: '将高频配置迁移至MPIS，观察后临时下线低效组合' },
  { id: 'R-BKK-HKG', route: 'BKK-HKG', depCity: '曼谷', arrCity: '香港', airline: 'HX', gdsCode: '1A', pccCode: 'HKGH228DF', platform: 'Traveloka', site: 'Traveloka-HK', queryCount: 9241300, segmentCount: 2011, queryToSegmentRatio: 4595, mpShare: 69, mpisShare: 24, ndcShare: 7, searchSuccessRate: 98.1, whitelistStatus: 'ACTIVE', riskStatus: 'WATCH', suggestion: '连续观察2天并提高MPIS流量占比' },
  { id: 'R-KUL-RGN', route: 'KUL-RGN', depCity: '吉隆坡', arrCity: '仰光', airline: '8M', gdsCode: '1A', pccCode: 'HKGH228DF', platform: '携程', site: '乐游携程一部', queryCount: 7820400, segmentCount: 1024, queryToSegmentRatio: 7637, mpShare: 88, mpisShare: 9, ndcShare: 3, searchSuccessRate: 91.4, whitelistStatus: 'ACTIVE', riskStatus: 'BREACHED', suggestion: '立即检查失败码，限制MP并迁移有效组合' },
  { id: 'R-SIN-HKG', route: 'SIN-HKG', depCity: '新加坡', arrCity: '香港', airline: 'SQ', gdsCode: '1A', pccCode: 'HKGH228DF', platform: '同程', site: '同程普通', queryCount: 4623300, segmentCount: 1540, queryToSegmentRatio: 3002, mpShare: 52, mpisShare: 39, ndcShare: 9, searchSuccessRate: 99.2, whitelistStatus: 'ACTIVE', riskStatus: 'NORMAL', suggestion: '保持当前配置' },
  { id: 'R-HKG-NRT', route: 'HKG-NRT', depCity: '香港', arrCity: '东京', airline: 'HX', gdsCode: '1A', pccCode: 'HKGH228DF', platform: '飞猪', site: '飞猪国际', queryCount: 3158700, segmentCount: 506, queryToSegmentRatio: 6242, mpShare: 81, mpisShare: 14, ndcShare: 5, searchSuccessRate: 95.7, whitelistStatus: 'EXPIRING', riskStatus: 'BREACHED', suggestion: '白名单即将到期，复核后再决定续期或下线' },
  { id: 'R-MNL-HKG', route: 'MNL-HKG', depCity: '马尼拉', arrCity: '香港', airline: 'PR', gdsCode: '1G', pccCode: '52N6', platform: '携程', site: '香港携程一部', queryCount: 2184300, segmentCount: 732, queryToSegmentRatio: 2984, mpShare: 47, mpisShare: 44, ndcShare: 9, searchSuccessRate: 98.7, whitelistStatus: 'ACTIVE', riskStatus: 'NORMAL', suggestion: '保持当前配置' },
]

const configurations: RouteConfiguration[] = [
  { id: 'CFG-10021', route: 'HKG-ICN', platform: '携程', gdsCode: '1A', pccCode: 'HKGH228DF', passengerScope: '1成人', tripType: '往返', outboundDays: '4-7天', returnDays: '4-7天', channel: 'MP', queryCount: 3680000, segmentCount: 402, ratio: 9154, successRate: 95.2, status: '异常', suggestion: '迁移MPIS并临时关闭MP配置' },
  { id: 'CFG-10022', route: 'HKG-ICN', platform: '携程', gdsCode: '1A', pccCode: 'HKGH228DF', passengerScope: '1成人', tripType: '单程', outboundDays: '8-15天', returnDays: '—', channel: 'MPIS', queryCount: 1280000, segmentCount: 572, ratio: 2238, successRate: 99.1, status: '达标', suggestion: '扩大MPIS流量' },
  { id: 'CFG-10023', route: 'KUL-RGN', platform: '携程', gdsCode: '1A', pccCode: 'HKGH228DF', passengerScope: '1成人', tripType: '往返', outboundDays: '16-30天', returnDays: '8-15天', channel: 'MP', queryCount: 2450000, segmentCount: 186, ratio: 13172, successRate: 88.4, status: '异常', suggestion: '下线该配置并检查失败码' },
  { id: 'CFG-10024', route: 'BKK-HKG', platform: 'Traveloka', gdsCode: '1A', pccCode: 'HKGH228DF', passengerScope: '2成人', tripType: '单程', outboundDays: '1-3天', returnDays: '—', channel: 'NDC', queryCount: 960000, segmentCount: 218, ratio: 4404, successRate: 97.2, status: '观察', suggestion: '继续观察2天' },
  { id: 'CFG-10025', route: 'SIN-HKG', platform: '同程', gdsCode: '1A', pccCode: 'HKGH228DF', passengerScope: '1成人', tripType: '往返', outboundDays: '8-15天', returnDays: '4-7天', channel: 'MPIS', queryCount: 1730000, segmentCount: 684, ratio: 2529, successRate: 99.4, status: '达标', suggestion: '保持并扩大覆盖' },
]

const whitelist: WhitelistRecord[] = [
  { id: 'WL-240391', route: 'HKG-ICN', airline: '7C', platform: '携程', site: '香港携程一部', gdsCode: '1A', pccCode: 'HKGH228DF', channel: 'MP / MPIS', configCount: 18, effectiveFrom: '2026-09-01', effectiveTo: '2026-12-31', status: 'ACTIVE', version: 'W202610160430', updatedAt: '2026-10-16 04:30' },
  { id: 'WL-240392', route: 'BKK-HKG', airline: 'HX', platform: 'Traveloka', site: 'Traveloka-HK', gdsCode: '1A', pccCode: 'HKGH228DF', channel: 'MP / NDC', configCount: 12, effectiveFrom: '2026-10-01', effectiveTo: '2027-03-31', status: 'ACTIVE', version: 'W202610160430', updatedAt: '2026-10-16 04:30' },
  { id: 'WL-240393', route: 'KUL-RGN', airline: '8M', platform: '携程', site: '乐游携程一部', gdsCode: '1A', pccCode: 'HKGH228DF', channel: 'MP', configCount: 9, effectiveFrom: '2026-08-01', effectiveTo: '2026-12-31', status: 'ACTIVE', version: 'W202610160430', updatedAt: '2026-10-16 04:30' },
  { id: 'WL-240394', route: 'HKG-NRT', airline: 'HX', platform: '飞猪', site: '飞猪国际', gdsCode: '1A', pccCode: 'HKGH228DF', channel: 'MP / MPIS', configCount: 7, effectiveFrom: '2026-07-01', effectiveTo: '2026-10-20', status: 'EXPIRING', version: 'W202610160430', updatedAt: '2026-10-16 04:30' },
  { id: 'WL-230102', route: 'HKG-TPE', airline: 'CI', platform: '携程', site: '香港携程一部', gdsCode: '1A', pccCode: 'HKGH228DF', channel: 'MP', configCount: 5, effectiveFrom: '2026-01-01', effectiveTo: '2026-09-30', status: 'INACTIVE', version: 'W202610160430', updatedAt: '2026-10-16 04:30' },
]

const quality: QualityMetric[] = [
  { id: 'Q-1', gdsCode: '1A', pccCode: 'HKGH228DF', apiGroup: '1A', platform: '携程', searchRequests: 28600000, searchSuccessRate: 97.8, verifySuccessRate: 94.2, orderSuccessRate: 91.8, timeoutRate: 1.9, topFailure: 'NO FARE FOUND', status: '观察' },
  { id: 'Q-2', gdsCode: '1A', pccCode: 'HKGH228DF', apiGroup: '1A_MPIS', platform: '携程', searchRequests: 9420000, searchSuccessRate: 99.1, verifySuccessRate: 98.4, orderSuccessRate: 96.7, timeoutRate: 0.4, topFailure: 'PRICE CHANGED', status: '正常' },
  { id: 'Q-3', gdsCode: '1A', pccCode: 'HKGH228DF', apiGroup: '1A_NDC', platform: 'Traveloka', searchRequests: 3680000, searchSuccessRate: 92.6, verifySuccessRate: 86.3, orderSuccessRate: 80.1, timeoutRate: 5.8, topFailure: 'PROVIDER TIMEOUT', status: '异常' },
  { id: 'Q-4', gdsCode: '1G', pccCode: '52N6', apiGroup: '1G_MPIS', platform: '同程', searchRequests: 1760000, searchSuccessRate: 98.8, verifySuccessRate: 97.9, orderSuccessRate: 95.4, timeoutRate: 0.7, topFailure: 'SEGMENT CLOSED', status: '正常' },
]

const initialEvents: GovernanceEvent[] = [
  { id: 'EVT-20261016-001', severity: 'P1', eventType: '航线查定比超标', target: '1A · HKG-ICN · 携程', targetType: '航线', evidence: 'MP查询12,846,200，航段2,238，连续2天超标', actualValue: '5,740 : 1', threshold: '≤ 4,000 : 1', owner: '马远尔', status: 'OPEN', occurredAt: '2026-10-16 06:05', dueAt: '2026-10-16 10:05', whitelistVersion: 'W202610160430', suggestion: '先迁移MPIS，再临时下线低效配置' },
  { id: 'EVT-20261016-002', severity: 'P0', eventType: '配置效率异常', target: 'CFG-10023 · KUL-RGN', targetType: '配置', evidence: '查询2,450,000，航段186，搜索成功率仅88.4%', actualValue: '13,172 : 1', threshold: '≤ 4,000 : 1', owner: '马远尔', status: 'ACKNOWLEDGED', occurredAt: '2026-10-16 06:05', dueAt: '2026-10-16 07:05', whitelistVersion: 'W202610160430', suggestion: '关闭该MP配置并排查失败码' },
  { id: 'EVT-20261016-003', severity: 'P1', eventType: '接口成功率异常', target: '1A_NDC · Traveloka', targetType: '接口', evidence: '查询成功率92.6%，生单成功率80.1%，超时率5.8%', actualValue: '80.1%', threshold: '≥ 95%', owner: '技术接口组', status: 'OBSERVING', occurredAt: '2026-10-16 06:05', dueAt: '2026-10-17 06:05', whitelistVersion: 'W202610160430', suggestion: '观察24小时并排查PROVIDER TIMEOUT' },
]

const initialActions: GovernanceAction[] = [
  { id: 'ACT-1', eventId: 'EVT-20261015-008', actionNo: 'RA202610150001', target: '1A · HKG-NRT · CFG-9981', targetType: '航线配置', actionType: 'DISABLE', occurrenceNo: 2, durationMinutes: 240, permanent: false, status: 'SUCCEEDED', owner: '马远尔', technicalOwner: '技术接口组', plannedStartAt: '2026-10-15 18:30', plannedEndAt: '2026-10-15 22:30', receiptNo: 'TECH-88321', note: '配置已临时下线，等待到期恢复' },
]

const storageKey = 'gds-route-governance-review-state-v1'

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

export const useGdsRouteGovernanceStore = defineStore('gdsRouteGovernance', {
  state: () => ({
    routes: clone(routes),
    configurations: clone(configurations),
    whitelist: clone(whitelist),
    quality: clone(quality),
    events: clone(initialEvents),
    actions: clone(initialActions),
  }),
  getters: {
    openEventCount: state => state.events.filter(item => item.status !== 'RESOLVED').length,
    activeActionCount: state => state.actions.filter(item => !['RECOVERED'].includes(item.status)).length,
  },
  actions: {
    hydrate() {
      const raw = window.localStorage.getItem(storageKey)
      if (!raw) return
      try {
        const saved = JSON.parse(raw) as { events?: GovernanceEvent[]; actions?: GovernanceAction[] }
        if (saved.events) this.events = saved.events
        if (saved.actions) this.actions = saved.actions
      } catch { window.localStorage.removeItem(storageKey) }
    },
    persist() {
      window.localStorage.setItem(storageKey, JSON.stringify({ events: this.events, actions: this.actions }))
    },
    resetReview() {
      this.events = clone(initialEvents)
      this.actions = clone(initialActions)
      this.persist()
    },
    acknowledgeEvent(id: string) {
      const event = this.events.find(item => item.id === id)
      if (!event || event.status !== 'OPEN') return
      event.status = 'ACKNOWLEDGED'
      this.persist()
    },
    observeEvent(id: string) {
      const event = this.events.find(item => item.id === id)
      if (!event || ['ACTION_PENDING', 'ACTION_APPLIED', 'RESOLVED'].includes(event.status)) return
      event.status = 'OBSERVING'
      this.persist()
    },
    createAction(id: string) {
      const event = this.events.find(item => item.id === id)
      if (!event || this.actions.some(item => item.eventId === id && item.status !== 'RECOVERED')) return false
      const actionType: GovernanceAction['actionType'] = event.targetType === '接口' ? 'RATE_LIMIT' : event.targetType === '配置' ? 'DISABLE' : 'ROUTE_TO_MPIS'
      this.actions.unshift({
        id: `ACT-${Date.now()}`,
        eventId: event.id,
        actionNo: `RA${new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Shanghai' }).format(new Date()).replaceAll('-', '')}${String(this.actions.length + 1).padStart(4, '0')}`,
        target: event.target,
        targetType: event.targetType,
        actionType,
        occurrenceNo: 1,
        durationMinutes: 60,
        permanent: false,
        status: 'PENDING',
        owner: event.owner,
        technicalOwner: '待技术接单',
        plannedStartAt: '立即执行',
        plannedEndAt: '生效后60分钟',
        receiptNo: '',
        note: `由${event.id}生成，白名单版本${event.whitelistVersion}`,
      })
      event.status = 'ACTION_PENDING'
      this.persist()
      return true
    },
    advanceAction(id: string) {
      const action = this.actions.find(item => item.id === id)
      if (!action) return
      const event = this.events.find(item => item.id === action.eventId)
      const next: Record<GovernanceActionStatus, GovernanceActionStatus | null> = {
        PENDING: 'ACCEPTED', ACCEPTED: 'EXECUTING', EXECUTING: 'SUCCEEDED', SUCCEEDED: 'RECOVERY_PENDING', RECOVERY_PENDING: 'RECOVERED', RECOVERED: null,
      }
      const target = next[action.status]
      if (!target) return
      action.status = target
      if (target === 'ACCEPTED') action.technicalOwner = '技术接口组'
      if (target === 'SUCCEEDED') {
        action.receiptNo = `TECH-${String(Date.now()).slice(-6)}`
        action.note = '技术已执行并返回成功回执'
        if (event) event.status = 'ACTION_APPLIED'
      }
      if (target === 'RECOVERY_PENDING') action.note = '控制窗口到期，等待技术恢复'
      if (target === 'RECOVERED') {
        action.note = '技术已恢复上线，进入治理效果复盘'
        if (event) event.status = 'RESOLVED'
      }
      this.persist()
    },
  },
})
