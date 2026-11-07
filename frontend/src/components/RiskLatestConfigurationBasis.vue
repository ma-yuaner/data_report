<template>
  <section class="latest-basis">
    <h4>最新配置依据（仅提醒）</h4>
    <template v-if="observation && run">
      <p>按本次核查留存的历史事实重新匹配；观察时间 {{ formatDateTimeDisplay(run.observedAt) }}。{{ previousOnly ? '以下为上次成功发布依据，本次尚未完整更新。' : '' }}</p>
      <p v-if="run.sourceChangedAfterSnapshot">本轮观察后检测到配置再次变化，以下结果截至本轮固定配置版本。</p>
      <p>{{ latestConfigStatus(observation.status) }}：{{ observation.reason }}</p>
      <template v-if="observation.configuration">
        <p>规则 {{ observation.configuration.ruleId || '未可靠匹配' }} · v{{ observation.configuration.configurationVersion ?? '未记录' }}</p>
        <p>源更新时间：{{ time(observation.configuration.sourceUpdatedAt) }}；登记有效期：{{ time(observation.configuration.sourceStart) }} 至 {{ time(observation.configuration.sourceEnd) }}。登记有效期不证明某次修改的真实生效时刻。</p>
        <div v-if="observation.configuration.conditions?.length" class="table-wrap"><table>
          <thead><tr><th>条件</th><th>{{ previousOnly ? '上次成功配置要求' : '配置要求' }}</th><th>本单历史事实</th><th>{{ previousOnly ? '上次成功匹配结果' : '匹配结果' }}</th></tr></thead>
          <tbody><tr v-for="condition in observation.configuration.conditions" :key="condition.field"><td>{{ condition.label || condition.field }}</td><td>{{ condition.value === '' ? '不限' : condition.value }}</td><td>{{ condition.actual ?? '未记录' }}</td><td>{{ condition.outcome === 'matched' ? '符合' : condition.outcome === 'rank_only' ? '不限制适用范围' : '证据不足' }}</td></tr></tbody>
        </table></div>
        <p v-else>该规则未记录额外匹配条件；是否可靠适用以本次观察状态为准。</p>
        <p v-if="observation.latestStopLoss != null">配置项 {{ observation.configuration.jsonPath || '未记录' }}，基础值 {{ observation.configuration.baseAmount ?? '未记录' }} 元<span v-if="observation.configuration.extraSegments"> ＋ {{ observation.configuration.extraSegments }} 段 × {{ observation.configuration.extraPerSegment ?? '未记录' }} 元</span>；{{ previousOnly ? '上次成功' : '最新' }}单票止损值 {{ observation.latestStopLoss }} 元/CNY。</p>
      </template>
      <h4>与出票时依据相比</h4>
      <div v-if="observation.changes?.length" class="table-wrap"><table><thead><tr><th>变化字段</th><th>原值</th><th>观察值</th></tr></thead><tbody><tr v-for="change in observation.changes" :key="change.field"><td>{{ change.label || change.field }}</td><td>{{ display(change.before) }}</td><td>{{ display(change.after) }}</td></tr></tbody></table></div>
      <p v-else>{{ observation.configurationChanged === false ? '可比较的配置字段未发现变化。' : '原配置比较依据不完整或本次未匹配，不能认定与原依据无变化。' }}</p>
      <details v-if="observation.lastSuccessful"><summary>上次可用依据（本次未取得适用数值）</summary><RiskLatestConfigurationBasis :observation="observation.lastSuccessful" :run="{ ...run, observedAt: observation.lastSuccessful.observedAt, sourceHash: observation.lastSuccessful.sourceHash }" :previous-only="true" /></details>
      <p class="muted">发布完成：{{ time(run.completedAt) }}；观察版本 {{ run.sourceHash }}。配置观察不重算原结论，也不改变人工核实状态。</p>
    </template>
    <p v-else>该历史事实版本尚无成功发布的最新配置观察。每日06:00触发刷新；查看页面不会启动任务。</p>
  </section>
</template>
<script setup lang="ts">
import { latestConfigStatus, type LatestConfigRun, type LatestConfigTicket } from '@/api/riskLatestConfig'
import { formatDateTimeDisplay } from '@/utils/dateTimeDisplay'
defineProps<{ observation?: LatestConfigTicket; run?: LatestConfigRun | null; previousOnly?: boolean }>()
const time = (value?: string | null) => value ? formatDateTimeDisplay(value) : '未记录'
const display = (value: unknown) => value == null ? '未记录' : typeof value === 'object' ? JSON.stringify(value) : String(value)
</script>
<style scoped>
.latest-basis{border-top:1px solid #dce6f5;margin-top:20px;padding-top:8px;overflow-wrap:anywhere}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;padding:8px;border-bottom:1px solid #e5eaf0}th{background:#f5f7fa}.muted{color:#69768a;font-size:12px}
</style>
