// Compatibility entry; new domain code imports the feature API directly.
export { fetchResourceGovernance, exportResourceGovernance, fetchGdsRouteAnalysis } from '@/features/resource-governance/api'
export type { GovernanceLayer, GovernanceDimension, GovernanceScope, GovernanceMetric, GovernanceChannelMetric, GovernanceData, GdsRouteScope, GdsRouteMetric, GdsRouteMetricRow, GdsRouteAnalysisData } from '@/features/resource-governance/api'
