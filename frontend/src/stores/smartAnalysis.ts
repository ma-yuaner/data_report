import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import type { SmartDimensionPath, SmartFilters, SmartStage, SmartTrendDate, SmartType } from '@/api/smartAnalysis'

export type SmartPage = 'comprehensive' | 'overview' | 'dimension' | 'detail'

interface SmartPageState {
  draft: SmartFilters
  applied: SmartFilters
  smartType: SmartType
}

function businessToday() {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
}

function emptyFilters(): SmartFilters {
  const today = businessToday()
  return {
    startDate: today, endDate: today,
    firstDepStart: '', firstDepEnd: '', orderStart: '', orderEnd: '',
    airline: '', platform: '', site: '', policy: '', leader: '', member: '',
    supplier: '', gds: '', productType: '', depAirport: '', arrAirport: '', route: '',
    depCity: '', arrCity: '', depCountry: '', arrCountry: '', depZone: '', arrZone: '',
    depArea: '', arrArea: '', flightWay: '', transferType: '', orderSource: '',
    routeCategory: '', ageType: '', ndc: '', routeLength: '', cityRoute: '',
    countryRoute: '', zoneRoute: '', tcRoute: '', profitBand: '',
  }
}

function pageState(): SmartPageState {
  return { draft: emptyFilters(), applied: emptyFilters(), smartType: 'all' }
}

export const useSmartAnalysisStore = defineStore('smart-analysis', () => {
  const pages = reactive<Record<SmartPage, SmartPageState>>({
    comprehensive: pageState(),
    overview: pageState(),
    dimension: pageState(),
    detail: pageState(),
  })
  const trendDate = ref<SmartTrendDate>('issue')
  const dimensionState = reactive({
    groups: ['airline', 'platform'] as string[],
    metrics: ['ticketCount', 'totalProfit', 'smartParticipated', 'smartSucceeded', 'smartUsed', 'smartUseRate', 'smartProfit', 'smartAverageProfit'] as string[],
    sortBy: 'smartProfit', direction: 'desc' as 'asc' | 'desc', page: 1, pageSize: 20,
  })
  const comprehensiveState = reactive({
    path: [] as SmartDimensionPath[],
    groupBy: 'platform',
    sortBy: 'smartProfit',
    direction: 'desc' as 'asc' | 'desc',
    page: 1,
    pageSize: 20,
  })
  const drillContext = ref<null | {
    sourcePath: string
    sourceTitle: string
    sourceFilters: SmartFilters
    sourceSmartType: SmartType
    stage: SmartStage
    tags: { label: string; value: string }[]
    scrollY: number
  }>(null)

  function apply(page: SmartPage) { Object.assign(pages[page].applied, pages[page].draft) }
  function reset(page: SmartPage) {
    Object.assign(pages[page].draft, emptyFilters())
    Object.assign(pages[page].applied, pages[page].draft)
    pages[page].smartType = 'all'
    if (page === 'overview') trendDate.value = 'issue'
  }
  function setPreset(page: SmartPage, kind: 'today' | 'yesterday' | 'week') {
    const today = businessToday()
    const end = new Date(`${today}T12:00:00+08:00`)
    if (kind === 'yesterday') end.setDate(end.getDate() - 1)
    const start = new Date(end)
    if (kind === 'week') start.setDate(start.getDate() - 6)
    pages[page].draft.startDate = start.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
    pages[page].draft.endDate = end.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
    pages[page].draft.firstDepStart = ''
    pages[page].draft.firstDepEnd = ''
    pages[page].draft.orderStart = ''
    pages[page].draft.orderEnd = ''
  }
  function applyDimensionPath(page: SmartPage, path: { key: keyof SmartFilters; value: string }[]) {
    for (const item of path) pages[page].draft[item.key] = item.value
    apply(page)
  }

  function beginDrill(input: {
    sourcePath: string
    sourceTitle: string
    sourcePage: Exclude<SmartPage, 'detail'>
    stage: SmartStage
    smartType?: SmartType
    tags?: { label: string; value: string }[]
    path?: { key: keyof SmartFilters; value: string }[]
  }) {
    const source = pages[input.sourcePage]
    const detail = pages.detail
    const selectedType = input.smartType ?? source.smartType
    drillContext.value = {
      sourcePath: input.sourcePath,
      sourceTitle: input.sourceTitle,
      sourceFilters: { ...source.applied },
      sourceSmartType: selectedType,
      stage: input.stage,
      tags: input.tags || [],
      scrollY: window.scrollY,
    }
    Object.assign(detail.draft, source.applied)
    Object.assign(detail.applied, source.applied)
    detail.smartType = selectedType
    if (input.path) applyDimensionPath('detail', input.path)
  }

  function restoreDrillSource() {
    const context = drillContext.value
    if (!context) return null
    drillContext.value = null
    return context
  }

  function clearDrill() { drillContext.value = null }

  return {
    pages, trendDate, dimensionState, comprehensiveState, drillContext,
    apply, reset, setPreset, applyDimensionPath, beginDrill, restoreDrillSource, clearDrill,
  }
})
