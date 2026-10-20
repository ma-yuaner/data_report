import { computed, type Ref } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import type { GovernanceData } from './api'
import { integer, compact, percent } from './formatters'

export function useGovernanceCharts(data: Ref<GovernanceData | undefined>, isGdsRatioScope: Ref<boolean>) {
  const funnel = computed(() => {
    const summary = data.value?.summary
    const progress = (value?: string | null) => (value == null ? 0 : Math.min(100, Math.max(0, Number(value))))
    return [
      {
        label: '查询接口',
        value: summary?.searchRequests ?? 0,
        percent: progress(summary?.searchSuccessRate),
        color: '#3278c8',
        note: `成功 ${integer(summary?.searchSuccess)} · 失败 ${integer(summary?.searchFailure)} · 成功率 ${percent(summary?.searchSuccessRate)}`,
      },
      {
        label: '验价接口',
        value: summary?.verifyRequests ?? 0,
        percent: progress(summary?.verifySuccessRate),
        color: '#e19337',
        note: `成功 ${integer(summary?.verifySuccess)} · 失败 ${integer(summary?.verifyFailure)} · 成功率 ${percent(summary?.verifySuccessRate)}`,
      },
      {
        label: '生单接口',
        value: summary?.orderRequests ?? 0,
        percent: progress(summary?.orderSuccessRate),
        color: '#8067c9',
        note: `成功 ${integer(summary?.orderSuccess)} · 失败 ${integer(summary?.orderFailure)} · 成功率 ${percent(summary?.orderSuccessRate)}`,
      },
    ]
  })

  const trendOption = computed<EChartsCoreOption>(() =>
    isGdsRatioScope.value
      ? {
          color: ['#4b85d1', '#d66a67', '#2a9b78'],
          tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => integer(Number(value)) },
          legend: {
            top: 2,
            data: data.value?.targetRatio == null ? ['查询请求量', '查定比'] : ['查询请求量', '查定比', '目标值'],
          },
          grid: { left: 64, right: 72, top: 44, bottom: 34 },
          xAxis: {
            type: 'category',
            data: data.value?.trend.map((item) => item.date.slice(5)) || [],
            axisLabel: { color: '#8090a5' },
          },
          yAxis: [
            {
              type: 'value',
              name: '请求量',
              axisLabel: { formatter: (value: number) => compact(value), color: '#8090a5' },
              splitLine: { lineStyle: { color: '#edf1f6' } },
            },
            {
              type: 'value',
              name: '查定比',
              axisLabel: { formatter: (value: number) => integer(value), color: '#8090a5' },
              splitLine: { show: false },
            },
          ],
          series: [
            {
              name: '查询请求量',
              type: 'bar',
              barMaxWidth: 20,
              data: data.value?.trend.map((item) => item.searchRequests) || [],
              itemStyle: { borderRadius: [4, 4, 0, 0] },
            },
            {
              name: '查定比',
              type: 'line',
              yAxisIndex: 1,
              smooth: true,
              connectNulls: false,
              data:
                data.value?.trend.map((item) =>
                  item.ratioInfinite
                    ? null
                    : item.queryToSegmentRatio == null
                      ? null
                      : Number(item.queryToSegmentRatio),
                ) || [],
              symbolSize: 7,
            },
            ...(data.value?.targetRatio == null
              ? []
              : [
                  {
                    name: '目标值',
                    type: 'line',
                    yAxisIndex: 1,
                    symbol: 'none',
                    lineStyle: { type: 'dashed', width: 1.5 },
                    data: data.value?.trend.map(() => data.value?.targetRatio) || [],
                  },
                ]),
          ],
        }
      : {
          color: ['#4b85d1', '#2a9b78', '#e19337', '#8067c9'],
          tooltip: { trigger: 'axis' },
          legend: { top: 2, data: ['查询请求量', '查询成功率', '验价成功率', '生单成功率'] },
          grid: { left: 64, right: 72, top: 44, bottom: 34 },
          xAxis: {
            type: 'category',
            data: data.value?.trend.map((item) => item.date.slice(5)) || [],
            axisLabel: { color: '#8090a5' },
          },
          yAxis: [
            {
              type: 'value',
              name: '请求量',
              axisLabel: { formatter: (value: number) => compact(value), color: '#8090a5' },
              splitLine: { lineStyle: { color: '#edf1f6' } },
            },
            {
              type: 'value',
              name: '成功率',
              min: 0,
              max: 100,
              axisLabel: { formatter: '{value}%', color: '#8090a5' },
              splitLine: { show: false },
            },
          ],
          series: [
            {
              name: '查询请求量',
              type: 'bar',
              barMaxWidth: 20,
              data: data.value?.trend.map((item) => item.searchRequests) || [],
              itemStyle: { borderRadius: [4, 4, 0, 0] },
            },
            {
              name: '查询成功率',
              type: 'line',
              yAxisIndex: 1,
              smooth: true,
              data:
                data.value?.trend.map((item) =>
                  item.searchSuccessRate == null ? null : Number(item.searchSuccessRate),
                ) || [],
            },
            {
              name: '验价成功率',
              type: 'line',
              yAxisIndex: 1,
              smooth: true,
              data:
                data.value?.trend.map((item) =>
                  item.verifySuccessRate == null ? null : Number(item.verifySuccessRate),
                ) || [],
            },
            {
              name: '生单成功率',
              type: 'line',
              yAxisIndex: 1,
              smooth: true,
              data:
                data.value?.trend.map((item) =>
                  item.orderSuccessRate == null ? null : Number(item.orderSuccessRate),
                ) || [],
            },
          ],
        },
  )
  return { funnel, trendOption }
}
