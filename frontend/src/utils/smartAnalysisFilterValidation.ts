import type { SmartFilters } from '@/api/smartAnalysis'

const DATE_FIELDS = [
  'startDate', 'endDate', 'firstDepStart', 'firstDepEnd', 'orderStart', 'orderEnd',
] as const satisfies readonly (keyof SmartFilters)[]

const dateRanges = (filters: SmartFilters) => [
  ['出票日期', filters.startDate, filters.endDate],
  ['首段起飞日期', filters.firstDepStart, filters.firstDepEnd],
  ['进单日期', filters.orderStart, filters.orderEnd],
] as const

export function isExactOtaOrderQuery(filters: SmartFilters, page: string) {
  return page === 'detail' && Boolean(filters.otaOrderNo.trim())
}

export function normalizeSmartAnalysisFilters(filters: SmartFilters, page: string): SmartFilters {
  const normalized = { ...filters, otaOrderNo: filters.otaOrderNo.trim() }
  if (isExactOtaOrderQuery(normalized, page)) {
    for (const field of DATE_FIELDS) normalized[field] = ''
  }
  return normalized
}

export function validateSmartAnalysisFilters(filters: SmartFilters, page: string) {
  if (isExactOtaOrderQuery(filters, page)) return ''
  const ranges = dateRanges(filters)
  if (!ranges.some(([, start, end]) => start && end)) return '出票、首段起飞、进单日期至少选择一个完整范围。'
  for (const [label, start, end] of ranges) {
    if (Boolean(start) !== Boolean(end)) return `请同时选择${label}的开始和结束日期。`
    if (start && end && start > end) return `${label}开始日期不能晚于结束日期。`
  }
  return ''
}
