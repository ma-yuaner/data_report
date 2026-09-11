<template><div ref="chartElement" class="base-chart" role="img" :aria-label="chartLabel"></div></template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ECharts, EChartsCoreOption } from 'echarts/core'

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{ option: EChartsCoreOption; chartLabel: string }>()
const chartElement = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined

onMounted(() => {
  if (!chartElement.value) return
  chart = echarts.init(chartElement.value)
  chart.setOption(props.option)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(chartElement.value)
})

watch(() => props.option, (option) => chart?.setOption(option, true), { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
})
</script>
