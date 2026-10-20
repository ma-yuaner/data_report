import type { GovernanceMetric } from './api'

export const gdsDimensionColumns = [
  { title: '资源', key: 'name', fixed: 'left' as const, width: 170 },
  {
    title: '查询请求量',
    key: 'search',
    width: 130,
    sorter: (a: GovernanceMetric, b: GovernanceMetric) => a.searchRequests - b.searchRequests,
  },
  { title: '航段数', key: 'segment', width: 110 },
  { title: '查定比', key: 'ratio', width: 125 },
  { title: '治理目标', key: 'target', width: 125 },
  { title: '超额查询', key: 'excess', width: 130 },
  { title: '查询成功率', key: 'searchRate', width: 120 },
  { title: '验价成功率', key: 'verifyRate', width: 120 },
  { title: '生单成功率', key: 'orderRate', width: 120 },
  { title: '异常判定', key: 'breach', width: 210 },
  { title: '操作', key: 'action', fixed: 'right' as const, width: 100 },
]

export const otaDimensionColumns = [
  { title: '资源', key: 'name', fixed: 'left' as const, width: 170 },
  {
    title: '查询请求量',
    key: 'search',
    width: 125,
    sorter: (a: GovernanceMetric, b: GovernanceMetric) => a.searchRequests - b.searchRequests,
  },
  { title: '查询成功量', key: 'searchSuccess', width: 120 },
  { title: '查询成功率', key: 'searchRate', width: 120 },
  { title: '验价请求量', key: 'verify', width: 120 },
  { title: '验价成功率', key: 'verifyRate', width: 120 },
  { title: '生单请求量', key: 'order', width: 120 },
  { title: '生单成功率', key: 'orderRate', width: 120 },
  { title: '平台成功率要求', key: 'successTarget', width: 235 },
  { title: '异常判定', key: 'breach', width: 210 },
  { title: '操作', key: 'action', fixed: 'right' as const, width: 100 },
]

export const interfaceDimensionColumns = [
  { title: '资源', key: 'name', fixed: 'left' as const, width: 170 },
  {
    title: '查询请求量',
    key: 'search',
    width: 125,
    sorter: (a: GovernanceMetric, b: GovernanceMetric) => a.searchRequests - b.searchRequests,
  },
  { title: '查询成功量', key: 'searchSuccess', width: 120 },
  { title: '查询成功率', key: 'searchRate', width: 120 },
  { title: '验价请求量', key: 'verify', width: 120 },
  { title: '验价成功率', key: 'verifyRate', width: 120 },
  { title: '生单请求量', key: 'order', width: 120 },
  { title: '生单成功率', key: 'orderRate', width: 120 },
  { title: '操作', key: 'action', fixed: 'right' as const, width: 100 },
]

export const resourceChannelColumns = [
  { title: '资源通道', key: 'name', fixed: 'left' as const, width: 220 },
  { title: '查询请求量', key: 'search', width: 135 },
  { title: '查询占比', key: 'share', width: 120 },
  { title: '航段数', key: 'segment', width: 115 },
  { title: '查定比', key: 'ratio', width: 130 },
  { title: '查询成功率', key: 'searchRate', width: 125 },
  { title: '验价成功率', key: 'verifyRate', width: 125 },
  { title: '生单成功率', key: 'orderRate', width: 125 },
  { title: '操作', key: 'action', fixed: 'right' as const, width: 120 },
]

export const apiGroupColumns = [
  { title: '接口分组', key: 'name', fixed: 'left' as const, width: 150 },
  { title: '查询请求', key: 'searchRequest', width: 110 },
  { title: '查询成功', key: 'searchSuccess', width: 110 },
  { title: '查询失败', key: 'searchFailure', width: 110 },
  { title: '查询成功率', key: 'searchRate', width: 115 },
  { title: '查询失败率', key: 'searchFailureRate', width: 115 },
  { title: '验价请求', key: 'verifyRequest', width: 110 },
  { title: '验价成功', key: 'verifySuccess', width: 110 },
  { title: '验价失败', key: 'verifyFailure', width: 110 },
  { title: '验价成功率', key: 'verifyRate', width: 115 },
  { title: '验价失败率', key: 'verifyFailureRate', width: 115 },
  { title: '生单请求', key: 'orderRequest', width: 110 },
  { title: '生单成功', key: 'orderSuccess', width: 110 },
  { title: '生单失败', key: 'orderFailure', width: 110 },
  { title: '生单成功率', key: 'orderRate', width: 115 },
  { title: '生单失败率', key: 'orderFailureRate', width: 115 },
  { title: '操作', key: 'action', fixed: 'right' as const, width: 100 },
]

export const gdsDailyColumns = [
  { title: '日期', dataIndex: 'date', width: 120, fixed: 'left' as const },
  { title: '查询请求量', key: 'search', width: 130 },
  { title: '航段数', key: 'segment', width: 110 },
  { title: '查定比', key: 'ratio', width: 130 },
  { title: '验价量 / 成功率', key: 'verify', width: 160 },
  { title: '生单成功 / 成功率', key: 'order', width: 170 },
  { title: '超额查询', key: 'excess', width: 130 },
]

export const otaDailyColumns = [
  { title: '日期', dataIndex: 'date', width: 120, fixed: 'left' as const },
  { title: '查询请求量', key: 'search', width: 130 },
  { title: '查询成功 / 成功率', key: 'searchSuccess', width: 170 },
  { title: '验价量 / 成功率', key: 'verify', width: 160 },
  { title: '生单成功 / 成功率', key: 'order', width: 170 },
]

export const analysisRouteColumns = [
  { title: '航线', key: 'route', fixed: 'left' as const, width: 160 },
  { title: '平台 / 站点', key: 'platform', width: 170 },
  { title: 'GDS / PCC', key: 'gds', width: 145 },
  { title: '查询量', key: 'search', width: 115 },
  { title: '查询成功率', key: 'searchRate', width: 115 },
  { title: '验价成功率', key: 'verifyRate', width: 115 },
  { title: '生单成功率', key: 'orderRate', width: 115 },
  { title: '查 / 验 / 生失败', key: 'failure', width: 160 },
  { title: '操作', key: 'action', fixed: 'right' as const, width: 100 },
]
