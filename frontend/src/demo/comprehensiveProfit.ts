// 仅用于综合分析界面预览。全部记录为确定性合成示例，不是公司业务数据。
export type BusinessKey = 'issue' | 'refund' | 'change' | 'ancillary'
export type DimensionKey = 'platform' | 'airline' | 'department' | 'product'
export type PeriodPreset = 'today' | 'yesterday' | 'month' | 'year' | 'custom'

export interface FilterScope extends Record<DimensionKey, string> {
  startDate: string
  endDate: string
  preset: PeriodPreset
}
export interface DemoFact extends Record<DimensionKey, string> {
  date: string
  business: BusinessKey
  count: number
  profitCents: number
}
export interface BusinessMetric {
  count: number
  profitCents: number
}
export type MetricBuckets = Record<BusinessKey, BusinessMetric>
export interface DimensionRow {
  name: string
  metrics: MetricBuckets
  totalCents: number
}

export const businesses: Array<{ key: BusinessKey; label: string; countLabel: string; unit: string; color: string }> = [
  { key: 'issue', label: '出票', countLabel: '出票票数', unit: '票', color: '#3178f6' },
  { key: 'refund', label: '退票', countLabel: '退票记录数', unit: '条', color: '#16a085' },
  { key: 'change', label: '改签', countLabel: '改签记录数', unit: '条', color: '#8b6bd8' },
  { key: 'ancillary', label: '增值', countLabel: '增值购买数', unit: '笔', color: '#dc8b28' },
]
export const dimensions: Array<{ key: DimensionKey; label: string }> = [
  { key: 'platform', label: '平台' }, { key: 'airline', label: '航司' },
  { key: 'department', label: '部门' }, { key: 'product', label: '产品' },
]
export const periodOptions = [
  { label: '今日', value: 'today' }, { label: '昨日', value: 'yesterday' },
  { label: '本月', value: 'month' }, { label: '本年', value: 'year' },
  { label: '自定义', value: 'custom' },
]
export function formatDate(date: Date) {
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-')
}
export function todayScope(): FilterScope {
  const today = formatDate(new Date())
  return { startDate: today, endDate: today, preset: 'today', platform: '', airline: '', department: '', product: '' }
}
export function emptyMetrics(): MetricBuckets {
  return { issue: { count: 0, profitCents: 0 }, refund: { count: 0, profitCents: 0 }, change: { count: 0, profitCents: 0 }, ancillary: { count: 0, profitCents: 0 } }
}
export function aggregate(facts: DemoFact[]): MetricBuckets {
  const result = emptyMetrics()
  for (const fact of facts) {
    result[fact.business].count += fact.count
    result[fact.business].profitCents += fact.profitCents
  }
  return result
}
export function sumProfit(metrics: MetricBuckets) {
  return businesses.reduce((sum, business) => sum + metrics[business.key].profitCents, 0)
}
export function matchesScope(fact: DemoFact, scope: FilterScope) {
  return fact.date >= scope.startDate && fact.date <= scope.endDate
    && dimensions.every(dimension => !scope[dimension.key] || fact[dimension.key] === scope[dimension.key])
}
export function groupFacts(facts: DemoFact[], dimension: DimensionKey): DimensionRow[] {
  const groups = new Map<string, DimensionRow>()
  for (const fact of facts) {
    const name = fact[dimension]
    let row = groups.get(name)
    if (!row) {
      row = { name, metrics: emptyMetrics(), totalCents: 0 }
      groups.set(name, row)
    }
    row.metrics[fact.business].count += fact.count
    row.metrics[fact.business].profitCents += fact.profitCents
    row.totalCents += fact.profitCents
  }
  return [...groups.values()].sort((left, right) => right.totalCents - left.totalCents)
}
export function generateDemoFacts(today = new Date()): DemoFact[] {
  // 产品名称仅为布局占位；不代表各平台的真实产品字典或正式归属规则。
  const combinations = [
    ['携程', 'HO', '机票业务1部', '私有价（示例）'],
    ['携程', 'HU', '机票业务1部', '公布价（示例）'],
    ['携程', 'CZ', '机票业务2部', '差旅产品（示例）'],
    ['同程', 'HU', '机票业务6部', '公布价（示例）'],
    ['同程', 'CZ', '机票业务6部', '私有价（示例）'],
    ['去哪儿', '8M', '机票业务2部', '公布价（示例）'],
    ['去哪儿', 'HO', '机票业务2部', '差旅产品（示例）'],
    ['飞猪', 'CZ', '机票业务1部', '公布价（示例）'],
    ['飞猪', 'HU', '机票业务6部', '私有价（示例）'],
  ]
  const result: DemoFact[] = []
  const cursor = new Date(today.getFullYear(), 0, 0)
  const lastDay = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  while (cursor <= lastDay) {
    const seed = cursor.getMonth() * 31 + cursor.getDate()
    combinations.forEach(([platform, airline, department, product], index) => {
      const counts = [320 + index * 24 + seed % 37, 28 + index * 3 + seed % 7, 15 + index * 2 + seed % 5, 84 + index * 8 + seed % 11]
      const unitProfits = [index === 3 || index === 7 ? -18 : 33 - index, index === 1 || index === 5 ? -112 : 19 + index, index === 5 ? -78 : 12 + index, 11 + index]
      businesses.forEach((business, businessIndex) => {
        const count = counts[businessIndex]!
        result.push({ date: formatDate(cursor), platform: platform!, airline: airline!, department: department!, product: product!, business: business.key, count, profitCents: count * unitProfits[businessIndex]! * 100 })
      })
    })
    cursor.setDate(cursor.getDate() + 1)
  }
  return result
}
