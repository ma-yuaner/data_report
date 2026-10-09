import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import type { SmartFilters, SmartType } from '@/api/smartAnalysis'

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
    countryRoute: '', zoneRoute: '', tcRoute: '', department: '', profitBand: '',
  }
}

export const useSmartAnalysisStore = defineStore('smart-analysis', () => {
  const draft = reactive<SmartFilters>(emptyFilters())
  const applied = reactive<SmartFilters>(emptyFilters())
  const smartType = ref<SmartType>('all')

  function apply() { Object.assign(applied, draft) }
  function reset() {
    Object.assign(draft, emptyFilters())
    Object.assign(applied, draft)
    smartType.value = 'all'
  }
  function setPreset(kind: 'today' | 'yesterday' | 'week') {
    const today = businessToday()
    const end = new Date(`${today}T12:00:00+08:00`)
    if (kind === 'yesterday') end.setDate(end.getDate() - 1)
    const start = new Date(end)
    if (kind === 'week') start.setDate(start.getDate() - 6)
    draft.startDate = start.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
    draft.endDate = end.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  }
  function applyDimensionPath(path: { key: keyof SmartFilters; value: string }[]) {
    for (const item of path) draft[item.key] = item.value
    apply()
  }

  return { draft, applied, smartType, apply, reset, setPreset, applyDimensionPath }
})
