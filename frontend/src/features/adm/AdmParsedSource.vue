<template>
  <section aria-label="解析来件核对">
    <p><b>解析原件：</b><span v-for="file in source.files" :key="file.id" style="margin-right:12px">{{ file.name }}</span></p>
    <p>正式金额 {{ source.candidate?.adm.amount }} {{ source.candidate?.adm.currency }}；开具日期 {{ source.candidate?.adm.issuedDate || '未提供' }}；Airline Code {{ source.candidate?.adm.airlineCode || '未提供' }}</p>
    <p>报表日期 {{ source.candidate?.adm.reportingDate || '未提供' }}；原件截止日期 {{ source.candidate?.adm.dueDate || '未提供' }}。台账处理截止时间请按业务要求填写。</p>
    <p>{{ source.candidate?.adm.reason }}</p>
    <a-alert v-for="issue in source.issues || []" :key="`${issue.path}-${issue.code}`" :type="issue.level === 'error' ? 'error' : 'warning'" :message="`${issue.path}：${issue.message}`" style="margin:6px 0" />
    <div style="overflow-x:auto;max-height:280px">
      <table class="ant-table" style="width:100%;white-space:normal">
        <thead><tr><th>航司 PNR</th><th>GDS 编码</th><th>来源未明 PNR</th><th>关联票号 / 类型</th><th>航段 / 日期</th><th>GDS / PCC</th></tr></thead>
        <tbody><tr v-for="(line, index) in source.candidate?.lines || []" :key="index">
          <td>{{ codes(line.airlinePnrs) }}</td><td>{{ codes(line.gdsPnrs) }}</td><td>{{ codes(line.pnrs) }}</td>
          <td>{{ line.ticketNumber || '—' }} / {{ line.ticketType === 'virtual' ? '虚拟票号（不匹配真实出票）' : line.ticketType === 'real' ? '真实票号' : '待核对' }}</td>
          <td>{{ line.flight }} {{ line.origin }}–{{ line.destination }}<br>{{ line.flightDate }}</td><td>{{ line.gds || '—' }} / {{ line.pcc || '—' }}</td>
        </tr></tbody>
      </table>
    </div>
    <p v-for="fee in source.attachmentFees || []" :key="fee.lineIndex">明细 {{ fee.lineIndex + 1 }} 附件费用：{{ fee.amount }} {{ fee.currency || '币种未明确' }}（{{ fee.headerLocator }} / {{ fee.rowLocator }}）；不自动分摊正式金额。</p>
    <details><summary>查看字段来源及原文</summary>
      <p v-for="(evidence, index) in source.candidate?.evidence || []" :key="index">{{ evidence.path }} · {{ source.segments?.find(s => s.id === evidence.segmentId)?.locator }}：{{ evidence.quote }}</p>
    </details>
  </section>
</template>
<script setup lang="ts">
import type { ParseTask } from '../adm-parsing/api'
defineProps<{ source: Pick<ParseTask, 'candidate' | 'files' | 'issues' | 'attachmentFees' | 'relatedDocuments' | 'segments'> }>()
function codes(value: unknown) { return Array.isArray(value) ? value.join('、') || '—' : '—' }
</script>
