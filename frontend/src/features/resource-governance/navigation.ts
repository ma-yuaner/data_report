import type { GovernanceScope } from './api'

export const routeDiagnosisQuery = (scope: GovernanceScope) => ({
  startDate: scope.startDate,
  endDate: scope.endDate,
  platform: scope.platform || undefined,
  site: scope.site || undefined,
  gds: scope.gds || undefined,
  pcc: scope.pcc || undefined,
  resourceChannel: scope.resourceChannel || undefined,
  apiGroup: scope.apiGroup || undefined,
})
export const routeDiagnosisNavigationQuery = (scope: GovernanceScope) => ({
  ...routeDiagnosisQuery(scope),
  entry: 'gds-analysis',
})
