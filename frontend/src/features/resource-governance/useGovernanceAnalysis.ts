import { computed, ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import {
  fetchResourceGovernance,
  fetchGdsRouteAnalysis,
  type GovernanceData,
  type GovernanceScope,
  type GovernanceDimension,
  type GovernanceLayer,
  type GdsRouteAnalysisData,
  type GdsRouteMetricRow,
  type GovernanceMetric,
} from './api'
import {
  gdsDimensionColumns,
  otaDimensionColumns,
  interfaceDimensionColumns,
  gdsDailyColumns,
  otaDailyColumns,
} from './columns'
import { gdsAnalysisDimensions, otaDimensions } from './dimensions'
import { routeDiagnosisQuery, routeDiagnosisNavigationQuery } from './navigation'

export function useGovernanceAnalysis(applied: Ref<GovernanceScope>, data: Ref<GovernanceData | undefined>) {
  const router = useRouter()
  const analysisRouteExporting = ref(false)
  const drawerOpen = ref(false)
  const drawerLoading = ref(false)
  const drawerError = ref('')
  const drawerTitle = ref('资源日汇总')
  const analysisData = ref<GovernanceData>()
  const analysisScope = ref<GovernanceScope>({ ...applied.value })
  const analysisHistory = ref<GovernanceScope[]>([])
  type AnalysisView = 'dimension' | 'daily' | 'route'
  const analysisView = ref<AnalysisView>('dimension')
  const analysisGroup = ref<GovernanceDimension>('gds')
  const analysisRouteData = ref<GdsRouteAnalysisData>()
  const analysisRouteLoading = ref(false)
  const analysisRouteError = ref('')
  const analysisIsGdsRatioScope = computed(
    () => analysisScope.value.dataSource === 'gds' && analysisData.value?.ratioApplicable !== false,
  )
  const analysisDimensionColumns = computed(() =>
    analysisIsGdsRatioScope.value
      ? gdsDimensionColumns
      : analysisScope.value.dataSource === 'gds'
        ? interfaceDimensionColumns
        : otaDimensionColumns,
  )
  const analysisDailyColumns = computed(() => (analysisIsGdsRatioScope.value ? gdsDailyColumns : otaDailyColumns))
  let drawerRequestId = 0
  const dimensionsForLayer = (layer: GovernanceLayer) => (layer === 'gds' ? gdsAnalysisDimensions : otaDimensions)
  const analysisViewOptions = computed(() =>
    analysisScope.value.dataSource === 'gds'
      ? [
          { label: '定位问题', value: 'dimension' },
          { label: '日汇总', value: 'daily' },
          { label: '航线分析', value: 'route' },
        ]
      : [
          { label: '定位问题', value: 'dimension' },
          { label: '日汇总', value: 'daily' },
        ],
  )
  const nextAnalysisGroup = (scope: GovernanceScope, after?: GovernanceDimension) => {
    const available = dimensionsForLayer(scope.dataSource)
      .map((item) => item.value as GovernanceDimension)
      .filter((key) => !scope[key])
    if (!available.length) return undefined
    const order = dimensionsForLayer(scope.dataSource).map((item) => item.value as GovernanceDimension)
    const afterIndex = after ? order.indexOf(after) : -1
    return available.find((key) => order.indexOf(key) > afterIndex) || available[0]
  }
  const analysisDimensionOptions = computed(() =>
    dimensionsForLayer(analysisScope.value.dataSource).filter(
      (item) => !analysisScope.value[item.value as GovernanceDimension],
    ),
  )
  const hasNextAnalysisDimension = computed(() => analysisDimensionOptions.value.length > 0)
  const analysisScopeTags = computed(
    () =>
      [
        analysisScope.value.platform && `平台：${analysisScope.value.platform}`,
        analysisScope.value.site && `站点：${analysisScope.value.site}`,
        analysisScope.value.gds && `GDS：${analysisScope.value.gds}`,
        analysisScope.value.resourceChannel && `资源通道：${analysisScope.value.resourceChannel}`,
        analysisScope.value.pcc && `PCC：${analysisScope.value.pcc}`,
        analysisScope.value.apiGroup && `接口组：${analysisScope.value.apiGroup}`,
      ].filter(Boolean) as string[],
  )

  async function loadAnalysis(scope: GovernanceScope) {
    const id = ++drawerRequestId
    analysisScope.value = { ...scope }
    analysisGroup.value = scope.groupBy
    drawerLoading.value = true
    drawerError.value = ''
    analysisData.value = undefined
    try {
      const result = await fetchResourceGovernance(scope)
      if (id === drawerRequestId) {
        analysisData.value = result
        drawerError.value = result.error
      }
    } catch (failure) {
      if (id === drawerRequestId) drawerError.value = failure instanceof Error ? failure.message : '资源分析失败'
    } finally {
      if (id === drawerRequestId) drawerLoading.value = false
    }
  }
  async function loadAnalysisRouteData() {
    if (analysisScope.value.dataSource !== 'gds') return
    analysisRouteLoading.value = true
    analysisRouteError.value = ''
    analysisRouteData.value = undefined
    try {
      analysisRouteData.value = await fetchGdsRouteAnalysis(routeDiagnosisQuery(analysisScope.value))
    } catch (failure) {
      analysisRouteError.value = failure instanceof Error ? failure.message : 'GDS航线Hive查询失败'
    } finally {
      analysisRouteLoading.value = false
    }
  }
  async function exportAnalysisRoutes() {
    if (analysisRouteExporting.value || drawerLoading.value || analysisRouteLoading.value || analysisScope.value.dataSource !== 'gds') return
    const scope = routeDiagnosisQuery({ ...analysisScope.value })
    analysisRouteExporting.value = true
    try {
      const task = await useComprehensiveExportStore().createRoutes(scope)
      message.success(task.reused ? '相同条件的任务正在进行，已打开导出任务' : '已加入导出任务，可在页头查看进度、取消或下载')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '创建导出任务失败')
    } finally { analysisRouteExporting.value = false }
  }
  async function changeAnalysisView(value: string | number) {
    analysisView.value = String(value) as AnalysisView
    if (analysisView.value === 'route') await loadAnalysisRouteData()
  }
  async function openAnalysis(record: { value: string; name: string } & Partial<GovernanceMetric>) {
    const dimension = applied.value.groupBy
    if (dimension === 'combination' && !record.preciseScope) return
    const scope =
      dimension === 'combination'
        ? {
            ...applied.value,
            gds: record.gds || '',
            pcc: record.pcc || '',
            platform: record.platform || '',
            site: record.site || '',
          }
        : { ...applied.value, [dimension]: record.value }
    scope.groupBy = nextAnalysisGroup(scope, dimension) || dimension
    drawerTitle.value = `${record.name} · ${data.value?.dimension.label || '资源'}分析`
    drawerOpen.value = true
    analysisView.value = nextAnalysisGroup(scope) ? 'dimension' : 'daily'
    analysisHistory.value = [{ ...scope }]
    await loadAnalysis(scope)
  }
  async function openApiGroupAnalysis(record: { value: string; name: string }) {
    const scope = {
      ...applied.value,
      resourceChannel: record.value.toUpperCase().endsWith('_MPIS') ? 'MPIS' : 'MP',
      apiGroup: record.value,
    }
    scope.groupBy = nextAnalysisGroup(scope) || 'gds'
    drawerTitle.value = `${record.name} · 接口分组分析`
    drawerOpen.value = true
    analysisView.value = 'dimension'
    analysisHistory.value = [{ ...scope }]
    await loadAnalysis(scope)
  }
  async function openResourceChannelAnalysis(record: { value: string; name: string }) {
    const scope = {
      ...applied.value,
      resourceChannel: record.value,
      apiGroup: '',
      groupBy: 'apiGroup' as GovernanceDimension,
    }
    drawerTitle.value = `${record.name} · 接口组下钻`
    drawerOpen.value = true
    analysisView.value = 'dimension'
    analysisHistory.value = [{ ...scope }]
    await loadAnalysis(scope)
  }
  async function changeAnalysisDimension(value: string | number) {
    const scope = { ...analysisScope.value, groupBy: String(value) as GovernanceDimension }
    analysisHistory.value[analysisHistory.value.length - 1] = { ...scope }
    await loadAnalysis(scope)
  }
  async function continueAnalysis(record: { value: string; name: string }) {
    const current = analysisData.value?.dimension.key || analysisGroup.value
    const scope = { ...analysisScope.value, [current]: record.value }
    const next = nextAnalysisGroup(scope, current)
    scope.groupBy = next || current
    analysisHistory.value.push({ ...scope })
    if (!next) analysisView.value = 'daily'
    await loadAnalysis(scope)
  }
  function openAnalysisRoutes(record?: { value: string; name: string }) {
    const scope = { ...analysisScope.value }
    if (record) {
      const current = analysisData.value?.dimension.key || analysisGroup.value
      scope[current] = record.value
    }
    drawerOpen.value = false
    void router.push({ path: '/resource-governance/route-diagnosis', query: routeDiagnosisNavigationQuery(scope) })
  }
  function openAnalysisRoute(record: GdsRouteMetricRow) {
    drawerOpen.value = false
    void router.push({
      path: '/resource-governance/route-diagnosis',
      query: { ...routeDiagnosisNavigationQuery(analysisScope.value), route: record.route },
    })
  }
  async function backAnalysis() {
    if (analysisHistory.value.length <= 1) return
    analysisHistory.value.pop()
    const previous = analysisHistory.value[analysisHistory.value.length - 1]
    analysisView.value = 'dimension'
    await loadAnalysis({ ...previous })
  }

  return {
    analysisDailyColumns,
    analysisData,
    analysisDimensionColumns,
    analysisDimensionOptions,
    analysisGroup,
    analysisHistory,
    analysisIsGdsRatioScope,
    analysisRouteData,
    analysisRouteError,
    analysisRouteLoading,
    analysisRouteExporting,
    exportAnalysisRoutes,
    analysisScope,
    analysisScopeTags,
    analysisView,
    analysisViewOptions,
    backAnalysis,
    changeAnalysisDimension,
    changeAnalysisView,
    continueAnalysis,
    drawerError,
    drawerLoading,
    drawerOpen,
    drawerTitle,
    hasNextAnalysisDimension,
    openAnalysis,
    openAnalysisRoute,
    openAnalysisRoutes,
    openApiGroupAnalysis,
    openResourceChannelAnalysis,
  }
}
