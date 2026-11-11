<template>
  <a-modal :open="open" width="920px" :footer="null" wrap-class-name="v05-modal adm-basic-info-modal" @cancel="close">
    <div v-if="detail" class="prototype-info-modal">
      <header class="prototype-info-head">
        <div><h2>{{ editable ? '编辑 ADM 主单基础信息' : 'ADM 主单基础信息' }}</h2><p>{{ detail.case.admNo }} · 系统记录 {{ detail.case.internalNo }}</p></div>
      </header>
      <div v-if="editable" class="v05-form-grid prototype-edit-grid">
        <label>系统主单ID<a-input :value="detail.case.internalNo" readonly /></label>
        <label>当前状态<a-input :value="label(detail.case.caseStatus)" readonly /></label>
        <label><span class="form-field-label">ADM单号 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.admNo" /></label>
        <label><span class="form-field-label">下发方类型 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true" v-model:value="form.issuerType"  :options="detail.case.lineDefaults ? issuerTypes.filter((item) => item.value !== 'PLATFORM') : issuerTypes" @change="issuerChanged" /></label>
        <label v-if="detail.case.lineDefaults || form.issuerType === 'AIRLINE'" class="wide"><span class="form-field-label">下发方名称 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.issuerName" /></label>
        <label v-else class="wide"><span class="form-field-label">下发方名称 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true" v-model:value="form.issuerCode" show-search :filter-option="filterOption" :options="issuerOptions" @change="issuerSelected" /></label>
        <label>ADM负责人<a-input :value="detail.case.coordinatorName || '—'" readonly /></label>
        <label>原币币种<a-input :value="detail.case.currency" readonly /></label>
        <label>原币总金额<a-input :value="`${detail.case.currency} ${detail.case.originalAmount}`" readonly /></label>
        <label>人民币总金额<a-input :value="`¥ ${detail.case.cnyAmount}`" readonly /></label>
        <label><span class="form-field-label">下发日期 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.issuedDate" type="date" /></label>
        <label><span class="form-field-label">主单回复截止时间 <span class="form-required-mark" aria-hidden="true">*</span></span><a-input aria-required="true" v-model:value="form.replyDeadline" type="datetime-local" /></label>
        <template v-if="detail.case.lineDefaults">
          <label>关联航司<a-input :value="detail.case.airlineName" readonly /></label>
          <label>归属部门<a-input :value="detail.case.lineDefaults.departmentName" readonly /></label>
          <label>负责组长<a-input :value="detail.case.lineDefaults.leaderName" readonly /></label>
          <label>差异类型<a-input :value="detail.case.lineDefaults.diffTypeName" readonly /></label>
          <label class="wide">细分差异原因<a-textarea :value="detail.case.lineDefaults.differenceReason" readonly /></label>
        </template>
        <label class="wide">主单备注<a-textarea v-model:value="form.remark" :rows="3" /></label>
      </div>
      <div v-else class="basic-info-grid">
        <dl><dt>系统主单ID</dt><dd>{{ detail.case.internalNo }}</dd></dl><dl><dt>ADM单号</dt><dd>{{ detail.case.admNo }}</dd></dl>
        <dl><dt>当前状态</dt><dd>{{ label(detail.case.caseStatus) }}</dd></dl><dl><dt>下发方类型</dt><dd>{{ label(detail.case.issuerType) }}</dd></dl>
        <dl><dt>下发方名称</dt><dd>{{ detail.case.issuerName }}</dd></dl><dl><dt>ADM负责人</dt><dd>{{ detail.case.coordinatorName || '—' }}</dd></dl>
        <dl><dt>原币币种</dt><dd>{{ detail.case.currency }}</dd></dl><dl><dt>原币总金额</dt><dd>{{ detail.case.currency }} {{ detail.case.originalAmount }}</dd></dl>
        <dl><dt>人民币总金额</dt><dd>¥ {{ detail.case.cnyAmount }}</dd></dl><dl><dt>下发日期</dt><dd>{{ detail.case.issuedDate || '—' }}</dd></dl>
        <dl><dt>主单回复截止时间</dt><dd>{{ detail.case.replyDeadline || '—' }}</dd></dl><dl><dt>汇率快照</dt><dd>{{ detail.fxSnapshot?.rateValue || '—' }} · {{ detail.fxSnapshot?.sourceUpdatedAt || detail.fxSnapshot?.rateDate || '—' }}</dd></dl>
        <dl><dt>订单完成情况</dt><dd>{{ completed }} / {{ activeLines }}</dd></dl><dl><dt>最近更新</dt><dd>{{ detail.case.updatedAt || '—' }}</dd></dl>
        <template v-if="detail.case.lineDefaults">
          <dl><dt>关联航司</dt><dd>{{ detail.case.airlineName || '—' }}</dd></dl>
          <dl><dt>归属部门</dt><dd>{{ detail.case.lineDefaults.departmentName }}</dd></dl>
          <dl><dt>负责组长</dt><dd>{{ detail.case.lineDefaults.leaderName }}</dd></dl>
          <dl><dt>差异类型</dt><dd>{{ detail.case.lineDefaults.diffTypeName }}</dd></dl>
          <dl class="wide"><dt>细分差异原因</dt><dd>{{ detail.case.lineDefaults.differenceReason }}</dd></dl>
        </template>
        <dl class="wide"><dt>主单备注</dt><dd>{{ detail.case.remark || '未填写' }}</dd></dl>
        <dl class="wide"><dt>主单公共附件</dt><dd>{{ attachmentNames }}</dd></dl>
      </div>
      <a-alert v-if="editable" type="info" show-icon message="金额和币种涉及明细分配及冻结汇率，不在基础信息中直接修改。" class="block" />
      <footer class="prototype-info-footer"><a-button @click="close">关闭</a-button><a-button v-if="editable" type="primary" :loading="saving" @click="save">保存基础信息</a-button></footer>
    </div>
    <div v-else class="prototype-info-loading"><a-spin size="large" tip="正在读取主单基础信息…" /></div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { admApi, errorText, label, type AdmCaseDetail, type Fields, type Option } from './api'

const props = defineProps<{ open: boolean; detail: AdmCaseDetail | null; editable: boolean }>()
const emit = defineEmits<{ close: []; saved: [detail: AdmCaseDetail] }>()
const saving = ref(false), masters = reactive<{ ota: Option[]; supplier: Option[] }>({ ota: [], supplier: [] }), form = reactive<Fields>({})
const issuerTypes = [{ value: 'SUPPLIER', label: '供应商' }, { value: 'PLATFORM', label: '平台' }, { value: 'AIRLINE', label: '航司' }]
const issuerOptions = computed(() => (form.issuerType === 'PLATFORM' ? masters.ota : masters.supplier).map(item => ({ value: item.code, label: `${item.name}（${item.code}）` })))
const activeLines = computed(() => props.detail?.lines.filter(item => item.lineStatus !== 'VOIDED').length || 0)
const completed = computed(() => props.detail?.lines.filter(item => item.lineStatus === 'COMPLETED').length || 0)
const attachmentNames = computed(() => props.detail?.attachments?.filter(item => item.recordStatus === 'ACTIVE').map(item => item.originalFileName).join('、') || '无')
const filterOption = (input: string, option: Fields) => String(option.label || '').toLowerCase().includes(input.toLowerCase())
function reset() { const c = props.detail?.case; if (!c) return; Object.assign(form, { admNo: c.admNo, issuerType: c.issuerType, issuerCode: c.issuerCode || undefined, issuerName: c.issuerName, issuedDate: c.issuedDate, replyDeadline: String(c.replyDeadline || '').replace(' ', 'T').slice(0, 16), remark: c.remark || '' }) }
function close() { emit('close') }
function issuerChanged() { form.issuerCode = undefined; form.issuerName = '' }
function issuerSelected(value?: string) { const source = form.issuerType === 'PLATFORM' ? masters.ota : masters.supplier; form.issuerName = source.find(item => item.code === value)?.name || '' }
async function save() { if (!props.detail) return; saving.value = true; try { const detail = await admApi.updateCase(props.detail.case.id, form); emit('saved', detail); void message.success('主单基础信息已保存') } catch (error) { void message.error(errorText(error)) } finally { saving.value = false } }
watch(() => [props.open, props.detail?.case.id], async ([open]) => { if (!open) return; reset(); if (props.editable && !props.detail?.case.lineDefaults && (!masters.ota.length || !masters.supplier.length)) { const [ota, supplier] = await Promise.allSettled([admApi.options('ota'), admApi.options('supplier')]); if (ota.status === 'fulfilled') masters.ota = ota.value; if (supplier.status === 'fulfilled') masters.supplier = supplier.value } }, { immediate: true })
</script>
