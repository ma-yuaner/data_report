<template>
  <div class="task-form">
        <section class="form-section">
          <header class="section-heading"><span>1</span><div><h3>执行结果</h3><p>{{ amending ? '仅调整当前登记内容，不改变投放结果或执行流程。' : '先选择结果，系统按成功或失败展示对应必填字段。' }}</p></div></header>
          <div class="form-grid three">
            <PlacementField label="投放结果" required><a-select :disabled="amending" v-model:value="executionForm.result" :options="executionResultOptions" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'SUCCESS'" label="外部政策 ID" required hint="用于订单匹配和外部追溯"><a-input v-model:value="executionForm.externalPolicyId" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'SUCCESS'" label="外部政策名称" hint="外部系统中的政策名称"><a-input v-model:value="executionForm.externalPolicyName" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'SUCCESS'" label="实际投放时间" required><a-date-picker v-model:value="executionForm.actualPlacementAt" :locale="dateLocale" show-time value-format="YYYY-MM-DD HH:mm:ss" placeholder="请选择实际投放时间" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'SUCCESS'" label="政策生效时间" required hint="监控从登记成功时间与政策生效时间中较晚的时间开始"><a-date-picker v-model:value="executionForm.effectiveStartAt" :locale="dateLocale" show-time value-format="YYYY-MM-DD HH:mm:ss" placeholder="请选择政策生效时间" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'SUCCESS'" label="长期有效"><a-switch v-model:checked="executionForm.longTerm" checked-children="是" un-checked-children="否" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'SUCCESS'" label="政策失效时间" :required="!executionForm.longTerm"><a-date-picker v-model:value="executionForm.effectiveEndAt" :disabled="executionForm.longTerm" :locale="dateLocale" show-time value-format="YYYY-MM-DD HH:mm:ss" placeholder="请选择政策失效时间" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'FAILED'" label="失败类型" required><a-select v-model:value="executionForm.failureType" :options="failureTypeOptions" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'FAILED'" label="是否重新执行" hint="开启后任务仍保持执行中"><a-switch :disabled="amending" v-model:checked="executionForm.retryRequired" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'FAILED' && executionForm.retryRequired" label="下次处理时间" required><a-date-picker v-model:value="executionForm.nextHandleAt" :locale="dateLocale" show-time value-format="YYYY-MM-DD HH:mm:ss" placeholder="请选择下次处理时间" /></PlacementField>
            <PlacementField v-if="executionForm.result === 'FAILED'" class="span-3" label="失败原因" required><a-textarea v-model:value="executionForm.failureReason" :rows="3" /></PlacementField>
          </div>
        </section>
        <section v-if="executionForm.result === 'SUCCESS'" class="form-section">
          <header class="section-heading"><span>2</span><div><h3>实际投放条件</h3><p>默认带出审核任务条件；实际值有变化时在这里修改，后续匹配使用实际条件。</p></div></header>
          <div class="form-grid three">
            <PlacementField label="平台名称" required hint="选择后自动带出平台编码"><a-select v-model:value="executionForm.platformName" :options="executionPlatformOptions" :loading="dimensionsLoading" show-search option-filter-prop="label" allow-clear placeholder="请选择平台" @change="selectExecutionPlatform" /></PlacementField>
            <PlacementField label="平台编码" hint="由平台名称自动带出"><a-input v-model:value="executionForm.platformCode" readonly /></PlacementField>
            <PlacementField label="产品类型"><a-select v-model:value="executionForm.productType" :options="executionProductOptions" :loading="dimensionsLoading" show-search option-filter-prop="label" allow-clear placeholder="请选择产品类型" /></PlacementField>
            <PlacementField label="实际订单来源" hint="支持多选；两个都选或留空均表示匹配全部订单来源"><a-select v-model:value="executionForm.orderSource" mode="multiple" :options="orderSourceOptions" allow-clear placeholder="不限订单来源" /></PlacementField>
            <PlacementField label="站点名称"><a-select v-model:value="executionForm.siteName" :options="executionSiteOptions" :loading="dimensionsLoading" show-search option-filter-prop="label" allow-clear placeholder="请选择站点" @change="selectExecutionSite" /></PlacementField>
            <PlacementField label="站点编码" hint="由站点名称自动带出"><a-input v-model:value="executionForm.siteCode" readonly /></PlacementField>
            <PlacementField label="航司" required><a-select v-model:value="executionForm.airlineCode" :options="executionAirlineOptions" :loading="dimensionsLoading" show-search option-filter-prop="label" allow-clear placeholder="请选择航司" /></PlacementField>
            <PlacementField label="航段类型"><a-select v-model:value="executionForm.segmentType" :options="segmentTypeOptions" allow-clear placeholder="请选择航段类型" /></PlacementField>
            <PlacementField label="出发地"><PlacementLocationSelect v-model:type="executionForm.departureType" v-model:code="executionForm.departureCode" label="实际出发地" /></PlacementField>
            <PlacementField label="目的地"><PlacementLocationSelect v-model:type="executionForm.arrivalType" v-model:code="executionForm.arrivalCode" label="实际目的地" /></PlacementField>
            <PlacementField label="航班号"><a-input v-model:value="executionForm.flightNos" /></PlacementField>
            <PlacementField label="包含舱位"><a-input v-model:value="executionForm.includeCabins" /></PlacementField>
            <PlacementField label="排除舱位"><a-input v-model:value="executionForm.excludeCabins" /></PlacementField>
            <PlacementField label="投放渠道"><a-input v-model:value="executionForm.placementChannel" /></PlacementField>
            <PlacementField label="亏损阈值下限（CNY）" hint="可选；上下限都留空表示不限制预估利润"><a-input-number v-model:value="executionForm.lossThresholdMin" :min="0" :precision="2" placeholder="可不填" /></PlacementField>
            <PlacementField label="亏损阈值上限（CNY）" hint="如填写，必须与下限同时填写"><a-input-number v-model:value="executionForm.lossThresholdMax" :min="0" :precision="2" placeholder="可不填" /></PlacementField>
            <PlacementField label="投放凭证地址" hint="填写可访问的截图或外部记录地址"><a-input v-model:value="executionForm.proofUrl" /></PlacementField>
          </div>
        </section>
        <section class="form-section">
          <header class="section-heading"><span>{{ executionForm.result === 'SUCCESS' ? 3 : 2 }}</span><div><h3>执行说明</h3><p>记录本次操作补充信息，便于后续追溯。</p></div></header>
          <div class="form-grid one"><PlacementField label="执行说明"><a-textarea v-model:value="executionForm.executionNote" :rows="3" /></PlacementField></div>
        </section>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { DatePicker as ADatePicker } from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import PlacementField from '@/components/PlacementField.vue'
import PlacementLocationSelect from '@/components/PlacementLocationSelect.vue'
import { usePlacementDimensions } from '@/composables/usePlacementDimensions'
import type { PlacementDimensionOptions } from '@/api/smartPlacement'
type Option = { value: string; label: string }
const props = defineProps<{ amending?: boolean; dimensions?: PlacementDimensionOptions; dimensionsLoading: boolean; executionResultOptions: Option[]; failureTypeOptions: Option[]; segmentTypeOptions: Option[]; orderSourceOptions: Option[] }>()
const executionForm = defineModel<Record<string, any>>({ required: true })
const { platformOptions: executionPlatformOptions, siteOptions: executionSiteOptions, productOptions: executionProductOptions, airlineOptions: executionAirlineOptions, selectPlatform: selectExecutionPlatform, selectSite: selectExecutionSite } = usePlacementDimensions(computed(() => props.dimensions), executionForm)
</script>
<style scoped>
.form-section { margin-bottom: 14px; padding: 17px; border: 1px solid var(--platform-border, #dfe7ef); border-radius: 12px; background: var(--platform-surface, #ffffff); }
.section-heading { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 13px; padding-bottom: 11px; border-bottom: 1px solid var(--platform-border, #dfe7ef); }
.section-heading > span { display: grid; flex: 0 0 26px; height: 26px; place-items: center; border-radius: 7px; color: #2867b7; font-size: 12px; font-weight: 700; background: var(--platform-selected, #eaf3fc); }
.section-heading > div { min-width: 0; }
.section-heading h3 { margin: 1px 0 2px; color: #263750; font-size: 14px; }
.section-heading p { margin: 0; color: var(--platform-secondary, #56697a); font-size: 12px; }
.section-heading em { flex: none; margin-left: auto; padding: 3px 8px; border-radius: 999px; color: var(--platform-secondary, #56697a); background: #f0f4f8; font-size: 12px; font-style: normal; }
.form-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 11px; }
.form-grid.three { grid-template-columns: repeat(3,minmax(0,1fr)); }
.form-grid.one { grid-template-columns: 1fr; }
.span-3 { grid-column: span 3; }
.task-form :deep(.ant-form-item) { margin-bottom: 16px; }
.task-form :deep(.ant-form-item-label) { min-height: 29px; padding-bottom: 6px; }
.task-form :deep(.ant-form-item-label > label) { height: auto; color: #46546a; font-size: 12px; font-weight: 600; }
.task-form :deep(.ant-input),.task-form :deep(.ant-input-number),.task-form :deep(.ant-picker),.task-form :deep(.ant-select) { width: 100%; }
.task-form :deep(.ant-input),.task-form :deep(.ant-picker),.task-form :deep(.ant-input-number),.task-form :deep(.ant-select-selector) { min-height: 38px; border-radius: 7px !important; }
.task-form :deep(.ant-input-number-input) { height: 36px; }
.task-form :deep(textarea.ant-input) { min-height: auto; padding-top: 9px; line-height: 1.65; }
@media (max-width: 820px) { .form-grid.three { grid-template-columns: repeat(2,minmax(0,1fr)); }.span-3 { grid-column: span 2; } }
@media (max-width: 600px) { .form-grid,.form-grid.three { grid-template-columns: 1fr; }.span-3 { grid-column: auto; } }
</style>
