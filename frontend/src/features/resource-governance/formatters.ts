import type { GovernanceMetric } from './api'

export const integer = (value?: number | null) => (value == null ? '—' : new Intl.NumberFormat('zh-CN').format(value))
export const compact = (value?: number | null) =>
  value == null ? '—' : new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 2 }).format(value)
export const nullableCount = (value?: number | null) => (value == null ? '—' : integer(value))
export const percent = (value?: string | null) => (value == null ? '—' : `${Number(value).toFixed(2)}%`)
export const milliseconds = (value?: string | null) =>
  value == null ? '—' : `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(Number(value))} ms`
export const ratioText = (metric?: GovernanceMetric) =>
  metric?.ratioInfinite
    ? '∞'
    : metric?.queryToSegmentRatio == null
      ? '—'
      : `${integer(Math.round(Number(metric.queryToSegmentRatio)))} : 1`
type SuccessStage = 'search' | 'verify' | 'order'
export const successRate = (metric: GovernanceMetric | undefined, stage: SuccessStage) =>
  stage === 'search'
    ? metric?.searchSuccessRate
    : stage === 'verify'
      ? metric?.verifySuccessRate
      : metric?.orderSuccessRate
export const hasOtaTarget = (metric?: GovernanceMetric) =>
  Boolean(metric && Object.keys(metric.successTargets || {}).length)
export const rateClass = (metric: GovernanceMetric | undefined, stage: SuccessStage) => {
  const target = metric?.successTargets?.[stage]
  const actual = successRate(metric, stage)
  return {
    danger: target != null && actual != null && Number(actual) < Number(target),
    healthy: target != null && actual != null && Number(actual) >= Number(target),
  }
}
export const targetLabel = (metric: GovernanceMetric | undefined, stage: SuccessStage, fallback: string) =>
  metric?.successTargets?.[stage] == null ? fallback : `目标 ≥ ${percent(metric.successTargets[stage])}`
export const otaTargetSummary = (metric: GovernanceMetric) => {
  if (!hasOtaTarget(metric)) return '未配置'
  return `查 ${percent(metric.successTargets.search)} · 验 ${percent(metric.successTargets.verify)} · 单 ${percent(metric.successTargets.order)}`
}
