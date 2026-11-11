<template>
  <a-modal :open="open" width="920px" :footer="null" wrap-class-name="v05-modal adm-basic-info-modal" @cancel="close">
    <div v-if="detail && line" class="prototype-info-modal">
      <header class="prototype-info-head"><div><h2>{{ editable ? '编辑订单基础信息' : '订单基础信息' }}</h2><p>{{ detail.case.admNo }} · {{ line.lineInternalNo }}</p></div></header>
      <div v-if="editable" class="v05-form-grid prototype-edit-grid">
        <label>系统主单ID<a-input :value="detail.case.internalNo" readonly /></label><label>内部明细ID<a-input :value="line.lineInternalNo" readonly /></label>
        <label>OTA平台<a-select v-model:value="form.otaCode" allow-clear :options="options.ota" @change="(v?: string) => pick('ota', v)" /></label><label>OTA订单号<a-input v-model:value="form.otaOrderNo" /></label>
        <label>供应商<a-select v-model:value="form.supplierCode" allow-clear :options="options.supplier" @change="(v?: string) => pick('supplier', v)" /></label><label>航司<a-input v-model:value="form.airlineName" /></label>
        <label>票号<a-input v-model:value="form.ticketNo" /></label><label>PNR编码<a-input v-model:value="form.pnr" /></label>
        <label><span class="form-field-label">业务归属部门 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true" v-model:value="form.departmentCode" :options="options.department" @change="(v: string) => pick('department', v)" /></label><label><span class="form-field-label">负责组长 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true" :disabled="!canChangeAdmLeader(line)" v-model:value="form.leaderId" :options="leaderOptions" show-search option-filter-prop="label" placeholder="搜索姓名、部门或账号" @change="pickLeader" /></label>
        <label>操作人员<a-input :value="line.operatorName || '未分配'" readonly /></label><label>截止时间（继承主单）<a-input :value="detail.case.replyDeadline || '—'" readonly /></label>
        <label>本笔ADM金额（原币）<a-input :value="`${detail.case.currency} ${line.originalAmount}`" readonly /></label><label>本笔ADM金额（人民币）<a-input :value="`¥ ${line.cnyAmount}`" readonly /></label>
        <label><span class="form-field-label">差异类型 <span class="form-required-mark" aria-hidden="true">*</span></span><a-select aria-required="true" v-model:value="form.diffTypeCode" :options="options.diffType" @change="(v: string) => pick('diffType', v)" /></label>
        <label class="wide"><span class="form-field-label">细分差异原因 <span class="form-required-mark" aria-hidden="true">*</span></span><a-textarea aria-required="true" v-model:value="form.differenceReason" :rows="3" /></label>
        <label class="wide">订单情况说明<a-textarea v-model:value="form.investigationNote" :rows="3" /></label>
      </div>
      <div v-else class="basic-info-grid">
        <dl><dt>系统主单ID</dt><dd>{{ detail.case.internalNo }}</dd></dl><dl><dt>ADM单号</dt><dd>{{ detail.case.admNo }}</dd></dl>
        <dl><dt>内部明细ID</dt><dd>{{ line.lineInternalNo }}</dd></dl><dl><dt>OTA平台</dt><dd>{{ line.otaName || '未填写' }}</dd></dl>
        <dl><dt>OTA订单号</dt><dd>{{ line.otaOrderNo || '未填写' }}</dd></dl><dl><dt>供应商</dt><dd>{{ line.supplierName || '未填写' }}</dd></dl>
        <dl><dt>航司</dt><dd>{{ line.airlineName || '未填写' }}</dd></dl><dl><dt>票号</dt><dd>{{ line.ticketNo || '未填写' }}</dd></dl>
        <dl><dt>PNR编码</dt><dd>{{ line.pnr || '未填写' }}</dd></dl><dl><dt>业务归属部门</dt><dd>{{ line.departmentName }}</dd></dl>
        <dl><dt>负责组长</dt><dd>{{ line.leaderName || '未分配' }}</dd></dl><dl><dt>操作人员</dt><dd>{{ line.operatorName || '未分配' }}</dd></dl>
        <dl><dt>本笔ADM金额（原币）</dt><dd>{{ detail.case.currency }} {{ line.originalAmount }}</dd></dl><dl><dt>本笔ADM金额（人民币）</dt><dd>¥ {{ line.cnyAmount }}</dd></dl>
        <dl><dt>截止时间（继承主单）</dt><dd>{{ detail.case.replyDeadline || '—' }}</dd></dl><dl><dt>差异类型</dt><dd>{{ line.diffTypeName || '未填写' }}</dd></dl>
        <dl class="wide"><dt>细分差异原因</dt><dd>{{ line.differenceReason || '未填写' }}</dd></dl><dl class="wide"><dt>订单情况说明</dt><dd>{{ line.investigationNote || '未填写' }}</dd></dl>
      </div>
      <section class="inherited-master-attachments">
        <header><div><h3>继承的主单公共附件</h3><p>同一 ADM 主单下所有明细均可查看，仅提供在线预览。</p></div><span>{{ masterAttachments.length }} 份</span></header>
        <p v-if="!masterAttachments.length" class="attachment-empty">当前主单暂无公共附件</p>
        <a-list v-else :data-source="masterAttachments" size="small">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta :title="item.originalFileName" :description="`${attachmentCategoryLabel(item.category)} · ${item.uploadedByName || '未知上传人'} · ${item.uploadedAt || '未记录时间'}`" />
              <a-button size="small" @click="previewAttachment(item)">预览</a-button>
            </a-list-item>
          </template>
        </a-list>
      </section>
      <a-alert v-if="editable" type="info" show-icon message="订单金额涉及主单分配平衡，请使用完整处理记录中的金额调整功能。" class="block" />
      <footer class="prototype-info-footer"><a-button @click="close">关闭</a-button><a-button v-if="editable" type="primary" :loading="saving" @click="save">保存基础信息</a-button></footer>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { admApi, admPersonOptions, canChangeAdmLeader, errorText, type AdmCaseDetail, type AdmConfig, type AdmLine, type Fields, type Option } from './api'
const props = defineProps<{ open: boolean; detail: AdmCaseDetail | null; line: AdmLine | null; editable: boolean; config: AdmConfig | null }>()
const emit = defineEmits<{ close: []; saved: [detail: AdmCaseDetail] }>()
const saving = ref(false), masters = reactive<Record<string, Option[]>>({ department: [], diffType: [], ota: [], supplier: [] }), form = reactive<Fields>({})
const map = (items: Option[], plain = false) => items.map(item => ({ value: item.code, label: plain ? item.name : `${item.name}（${item.code}）` }))
const options = computed(() => ({ department: map(masters.department), diffType: map(masters.diffType, true), ota: map(masters.ota), supplier: map(masters.supplier) }))
const leaderOptions = computed(() => admPersonOptions(props.config?.people.leader || [], true))
const masterAttachments = computed(() => (props.detail?.attachments || []).filter(
  item => item.recordStatus === 'ACTIVE' && item.sourceLineId == null,
))
const attachmentCategoryLabel = (value: unknown) => ({
  ADM_ORIGINAL: 'ADM原始附件', APPEAL: '申诉附件', COLLECTION: '回款凭证', OTHER: '其他附件',
} as Record<string, string>)[String(value || '')] || String(value || '未分类')
function reset() { const l = props.line; if (!l) return; Object.assign(form, { otaCode: l.otaCode || undefined, otaName: l.otaName || '', otaOrderNo: l.otaOrderNo || '', supplierCode: l.supplierCode || undefined, supplierName: l.supplierName || '', airlineCode: l.airlineCode || '', airlineName: l.airlineName || '', ticketNo: l.ticketNo || '', pnr: l.pnr || '', departmentCode: l.departmentCode, departmentName: l.departmentName, leaderId: Number(l.leaderId), leaderName: l.leaderName, diffTypeCode: l.diffTypeCode, diffTypeName: l.diffTypeName, differenceReason: l.differenceReason || '', investigationNote: l.investigationNote || '' }) }
function close() { emit('close') }
function pick(kind: string, value?: string) { const item = masters[kind].find(option => option.code === value); const nameKey = `${kind}Name`; form[nameKey] = item?.name || '' }
function pickLeader(value: number) { form.leaderName = props.config?.people.leader.find(item => Number(item.id) === Number(value))?.name || '' }
async function previewAttachment(item: Fields) { if (!props.detail) return; try { const response = await admApi.file(props.detail.case.id, item.id, 'preview'); const url = URL.createObjectURL(response.data); window.open(url, '_blank', 'noopener'); window.setTimeout(() => URL.revokeObjectURL(url), 60_000) } catch (error) { void message.error(errorText(error)) } }
async function save() { if (!props.detail || !props.line) return; saving.value = true; try { const detail = await admApi.updateLine(props.detail.case.id, props.line.id, form); emit('saved', detail); void message.success('订单基础信息已保存') } catch (error) { void message.error(errorText(error)) } finally { saving.value = false } }
watch(() => [props.open, props.line?.id], async ([open]) => { if (!open) return; reset(); if (props.editable) { const kinds = ['department', 'diffType', 'ota', 'supplier']; const results = await Promise.allSettled(kinds.map(kind => admApi.options(kind))); results.forEach((result, index) => { if (result.status === 'fulfilled') masters[kinds[index]] = result.value }) } }, { immediate: true })
</script>
