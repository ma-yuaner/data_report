import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  fetchResourceGovernance,
  type GovernanceData,
  type GovernanceDimension,
  type GovernanceLayer,
  type GovernanceMetric,
  type GovernanceScope,
} from './api'
import { gdsDimensionColumns, gdsCombinationColumns, otaDimensionColumns, interfaceDimensionColumns } from './columns'
import { integer, hasOtaTarget } from './formatters'
import { gdsDimensions, otaDimensions } from './dimensions'
import { useGovernanceAnalysis } from './useGovernanceAnalysis'
import { useGovernanceCharts } from './useGovernanceCharts'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'

export function useResourceGovernance() {
  const shanghaiDate = (value = new Date()) => value.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
  const route = useRoute()
  const router = useRouter()
  const routeLayer = (): GovernanceLayer => (route.meta.governanceLayer === 'ota' ? 'ota' : 'gds')
  const today = shanghaiDate()
  const reportingCutoffValue = new Date(`${today}T12:00:00+08:00`)
  reportingCutoffValue.setDate(reportingCutoffValue.getDate() - 1)
  const reportingCutoff = shanghaiDate(reportingCutoffValue)
  const monthStart = `${reportingCutoff.slice(0, 7)}-01`
  const emptyScope = (layer: GovernanceLayer = routeLayer()): GovernanceScope => ({
    startDate: monthStart,
    endDate: reportingCutoff,
    dataSource: layer,
    groupBy: layer === 'gds' ? 'combination' : 'platform',
    platform: '',
    site: '',
    gds: '',
    resourceChannel: '',
    pcc: '',
    apiGroup: '',
    breachOnly: false,
  })
  const draft = ref<GovernanceScope>(emptyScope())
  const applied = ref<GovernanceScope>({ ...draft.value })
  const preset = ref('month')
  const draftGroup = ref<GovernanceDimension>('gds')
  const data = ref<GovernanceData>()
  const loading = ref(false)
  const exporting = ref(false)
  const error = ref('')
  let requestId = 0

  const periodOptions = [
    { label: '昨日', value: 'yesterday' },
    { label: '近7个完整日', value: 'seven' },
    { label: '本月至昨日', value: 'month' },
    { label: '自定义', value: 'custom' },
  ]
  const dimensionOptions = computed(() => (draft.value.dataSource === 'gds' ? gdsDimensions : otaDimensions))
  const pending = computed(() => JSON.stringify(draft.value) !== JSON.stringify(applied.value))
  const isGds = computed(() => applied.value.dataSource === 'gds')
  const isGdsRatioScope = computed(() => isGds.value && data.value?.ratioApplicable !== false)
  const pageTitle = computed(() => (isGds.value ? 'GDS资源治理' : 'OTA渠道质量'))
  const pageDescription = computed(() =>
    isGds.value ? '按GDS与PCC分析查询量、航段数和查定比' : '按平台与站点分析查询、验价和生单接口成功率',
  )
  const openRouteDiagnosis = () => router.push('/resource-governance/route-diagnosis')
  const layerLabel = (layer: GovernanceLayer) => (layer === 'gds' ? 'GDS资源层' : 'OTA渠道层')
  const selectOptions = (values?: string[]) => (values || []).map((value) => ({ label: value, value }))
  const resourceChannelOptions = [
    { label: 'MP（含普通MP、NDC）', value: 'MP' },
    { label: 'MPIS', value: 'MPIS' },
  ]
  const apiGroupOptions = computed(() => {
    const values = data.value?.options.apiGroup || []
    const channel = draft.value.resourceChannel
    const filtered = !channel
      ? values
      : values.filter((value) =>
          channel === 'MPIS' ? value.toUpperCase().endsWith('_MPIS') : !value.toUpperCase().endsWith('_MPIS'),
        )
    return selectOptions(filtered)
  })
  const disabledDailyDate = (value: { format?: (format: string) => string } | null) =>
    Boolean(value?.format && value.format('YYYY-MM-DD') > reportingCutoff)
  const ratioClass = (metric?: GovernanceMetric) => {
    const target = metric?.targetRatio ?? data.value?.targetRatio
    return {
      danger: Boolean(
        target != null &&
        (metric?.ratioInfinite || (metric?.queryToSegmentRatio != null && Number(metric.queryToSegmentRatio) > target)),
      ),
      healthy: Boolean(
        target != null && metric?.queryToSegmentRatio != null && Number(metric.queryToSegmentRatio) <= target,
      ),
    }
  }
  const ratioTone = computed(() => ratioClass(data.value?.summary))
  const breachText = (metric?: GovernanceMetric) => {
    if (!metric) return '—'
    if (metric.breach) return metric.breachReasons?.[0] || '超过治理目标'
    if (isGds.value && metric.targetRatio == null) return '未配置目标'
    if (!isGds.value && !hasOtaTarget(metric)) return '未配置目标'
    if (metric.status === 'segment_data_missing' || metric.status === 'segment_partial') return '航段数未同步'
    if (metric.status === 'no_records') return '无数据'
    return '正常'
  }
  const appliedTags = computed(
    () =>
      [
        applied.value.platform && `平台：${applied.value.platform}`,
        applied.value.site && `站点：${applied.value.site}`,
        applied.value.gds && `GDS：${applied.value.gds}`,
        applied.value.resourceChannel && `资源通道：${applied.value.resourceChannel}`,
        applied.value.pcc && `PCC：${applied.value.pcc}`,
        applied.value.apiGroup && `接口组：${applied.value.apiGroup}`,
      ].filter(Boolean) as string[],
  )
  const heroTitle = computed(() => {
    const summary = data.value?.summary
    if (!summary || summary.status === 'no_records') return '当前范围暂无资源调用数据'
    if (!isGds.value) return '当前为OTA渠道接口链路分析'
    if (!data.value?.ratioApplicable)
      return `${applied.value.apiGroup || applied.value.resourceChannel || '接口分组'}调用质量分析`
    if (summary.status === 'segment_field_missing' || summary.status === 'segment_data_missing')
      return '查询链路已接入，航段数待补齐'
    if (summary.status === 'segment_partial') return '航段数同步不完整，暂不输出查定比'
    if (summary.ratioInfinite) return '存在查询但没有航段数'
    if (data.value?.targetRatio == null)
      return applied.value.gds ? '当前GDS尚未配置治理目标' : '请选择具体GDS查看目标达标情况'
    if (Number(summary.queryToSegmentRatio) > data.value.targetRatio) return '当前查定比高于阶段治理目标'
    return '当前查定比处于阶段目标范围内'
  })
  const heroDescription = computed(() => {
    const summary = data.value?.summary
    if (!isGds.value) return 'OTA渠道层只分析查询、验价与生单接口表现，不计算航段查定比。'
    if (!data.value?.ratioApplicable) return '当前只分析接口分组的请求、成功与失败；正式MP查定比返回总体口径后查看。'
    if (!summary?.queryToSegmentRatio) return '页面不会使用PNR数或直连生单接口成功量替代航段数。'
    if (data.value?.targetRatio == null) return '不同GDS目标不同；首版已配置1A目标为4000:1，筛选具体GDS后判断是否达标。'
    const gap = Math.round(Number(summary.queryToSegmentRatio) - data.value.targetRatio)
    return gap > 0
      ? `每个航段仍需多消耗约 ${integer(gap)} 次查询，优先从下方高查询量资源开始下钻。`
      : `当前低于目标约 ${integer(Math.abs(gap))} 次查询，请继续观察航段数与业务量是否稳定。`
  })

  const { funnel, trendOption } = useGovernanceCharts(data, isGdsRatioScope)

  const dimensionColumns = computed(() =>
    isGdsRatioScope.value
      ? applied.value.groupBy === 'combination'
        ? gdsCombinationColumns
        : gdsDimensionColumns
      : isGds.value
        ? interfaceDimensionColumns
        : otaDimensionColumns,
  )

  function applyPreset(value: string | number) {
    const selected = String(value)
    if (selected === 'custom') return
    const end = new Date(`${reportingCutoff}T12:00:00+08:00`)
    if (selected === 'yesterday') draft.value.startDate = reportingCutoff
    if (selected === 'seven') {
      const start = new Date(end)
      start.setDate(start.getDate() - 6)
      draft.value.startDate = shanghaiDate(start)
    }
    if (selected === 'month') draft.value.startDate = monthStart
    draft.value.endDate = reportingCutoff
  }
  function changeResourceChannel(value: unknown) {
    const channel = String(value || '')
    if (!draft.value.apiGroup) return
    const isMpisGroup = draft.value.apiGroup.toUpperCase().endsWith('_MPIS')
    if ((channel === 'MPIS') !== isMpisGroup) draft.value.apiGroup = ''
  }
  function changeApiGroup(value: unknown) {
    const apiGroup = String(value || '')
    if (!apiGroup || draft.value.dataSource !== 'gds') return
    draft.value.resourceChannel = apiGroup.toUpperCase().endsWith('_MPIS') ? 'MPIS' : 'MP'
  }
  function resetFilters() {
    const layer = draft.value.dataSource
    draft.value = { ...emptyScope(), dataSource: layer, groupBy: layer === 'gds' ? 'gds' : 'platform' }
    draftGroup.value = draft.value.groupBy
    preset.value = 'month'
  }
  function applyFilters() {
    draft.value.groupBy = draftGroup.value
    if (draft.value.groupBy === 'combination' && (draft.value.apiGroup || draft.value.resourceChannel === 'MPIS')) {
      draft.value.groupBy = 'gds'
      draftGroup.value = 'gds'
    }
    void load({ ...draft.value })
  }
  async function exportReport() {
    exporting.value = true
    try {
      const task = await useComprehensiveExportStore().createBackground(
        applied.value.dataSource === 'gds' ? 'resource_governance_gds' : 'resource_governance_ota',
        { ...applied.value },
      )
      message.success(task.reused ? '相同条件的任务正在进行，已打开导出任务' : '已加入导出任务，可在页头查看进度')
    } catch (failure) {
      message.error(failure instanceof Error ? failure.message : '资源治理汇报导出失败')
    } finally {
      exporting.value = false
    }
  }
  function changeDimension(value: string | number) {
    draft.value.groupBy = String(value) as GovernanceDimension
    if (draft.value.groupBy === 'combination') {
      draft.value.apiGroup = ''
      draft.value.resourceChannel = 'MP'
    }
    void load({ ...draft.value })
  }
  async function load(scope: GovernanceScope) {
    const id = ++requestId
    loading.value = true
    error.value = ''
    try {
      const result = await fetchResourceGovernance(scope)
      if (id !== requestId) return
      data.value = result
      applied.value = { ...scope, groupBy: result.dimension.key }
      draft.value = { ...applied.value }
      draftGroup.value = result.dimension.key
    } catch (failure) {
      if (id === requestId) error.value = failure instanceof Error ? failure.message : '资源治理查询失败'
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  const analysis = useGovernanceAnalysis(applied, data)

  onMounted(() => {
    void load({ ...draft.value })
  })
  watch(
    () => route.meta.governanceLayer,
    () => {
      const next = emptyScope(routeLayer())
      draft.value = next
      applied.value = { ...next }
      draftGroup.value = next.groupBy
      preset.value = 'month'
      void load({ ...next })
    },
  )
  return {
    ...analysis,
    apiGroupOptions,
    applied,
    appliedTags,
    applyFilters,
    applyPreset,
    breachText,
    changeApiGroup,
    changeDimension,
    changeResourceChannel,
    data,
    dimensionColumns,
    dimensionOptions,
    disabledDailyDate,
    draft,
    draftGroup,
    error,
    exportReport,
    exporting,
    funnel,
    heroDescription,
    heroTitle,
    isGds,
    isGdsRatioScope,
    layerLabel,
    loading,
    openRouteDiagnosis,
    pageDescription,
    pageTitle,
    pending,
    periodOptions,
    preset,
    ratioClass,
    ratioTone,
    resetFilters,
    resourceChannelOptions,
    route,
    selectOptions,
    trendOption,
  }
}
