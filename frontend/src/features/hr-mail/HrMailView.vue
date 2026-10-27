<template>
  <div class="hr-mail-page">
    <PageHeader
      eyebrow="HR REPORT MAIL"
      title="HR报表邮件"
      description="上传周报或月报，核对部门邮件和附件后确认发送。正文沿用原报表规则，不使用AI改写。"
    >
      <a-button :loading="configLoading" @click="loadConfig">刷新服务状态</a-button>
    </PageHeader>
    <a-alert v-if="error" type="error" :message="error" show-icon closable @close="error = ''" />
    <div class="service-status">
      <a-tag :color="config?.storageReady ? 'green' : 'orange'"
        >私有存储：{{ config?.storageReady ? '就绪' : '未就绪' }}</a-tag
      >
      <a-tag :color="config?.mailConfigReady ? 'green' : 'orange'"
        >邮件配置：{{ config?.mailConfigReady ? '就绪' : '未就绪' }}</a-tag
      >
      <a-tag :color="config?.sendEnabled ? 'blue' : 'default'"
        >发送：{{ config?.sendEnabled ? '已启用' : '未启用' }}</a-tag
      >
      <span>邮件认证信息由服务器 .env 提供，不在页面输入或回显。</span>
    </div>
    <a-alert v-if="config?.error" type="warning" :message="config.error" show-icon />

    <a-tabs v-model:active-key="mode" :destroy-inactive-tab-pane="false">
      <a-tab-pane key="prepare" tab="准备邮件">
        <section class="upload-panel">
          <div class="section-heading">
            <h2>1. 上传报表与部门映射</h2>
            <span>仅支持 .xlsx；选择后立即上传，文件名保留在下方。</span>
          </div>
          <a-alert
            v-if="config && !config.permissions.upload"
            type="warning"
            message="没有上传与解析权限（hr.mail.upload），可在历史记录查看有权限的批次。"
            show-icon
          />
          <div class="upload-grid">
            <div v-for="entry in uploadEntries" :key="entry.kind" class="upload-field">
              <label :for="`hr-upload-${entry.kind}`">{{ entry.label }}</label>
              <input
                :id="`hr-upload-${entry.kind}`"
                type="file"
                accept=".xlsx"
                :disabled="!canUpload || sending || creating || uploading[entry.kind]"
                @change="uploadFile(entry.kind, $event)"
              />
              <span class="file-name">{{ uploadNames[entry.kind] || '未选择文件' }}</span>
              <span v-if="uploading[entry.kind]" role="status">上传中…</span>
              <span v-else-if="uploads[entry.kind]" class="success-text">已上传</span>
              <span v-if="uploadErrors[entry.kind]" class="error-text" role="alert">{{
                uploadErrors[entry.kind]
              }}</span>
            </div>
          </div>
          <div class="prepare-actions">
            <label class="type-field"
              ><span>本次报表类型</span
              ><a-radio-group v-model:value="reportType" :disabled="creating || sending"
                ><a-radio-button value="week">周报</a-radio-button
                ><a-radio-button value="month">月报</a-radio-button></a-radio-group
              ></label
            >
            <a-button type="primary" :disabled="!canCreate" :loading="creating" @click="createBatch"
              >解析并生成预览</a-button
            >
            <span class="muted">需要本次类型报表和部门映射。改文件或类型后须重新解析、逐封预览。</span>
          </div>
          <p v-if="draftBatch && draftBatch.status !== 'PREVIEW'" class="muted">
            下方保留已提交批次的真实状态。继续上传可准备下一批；已有记录始终可在历史中查询。
          </p>
        </section>
      </a-tab-pane>
      <a-tab-pane key="history" tab="历史记录">
        <FilterPanel
          stacked
          :instant="false"
          :loading="historyLoading"
          :show-reset="false"
          hint="仅展示本人批次；管理员可查看全部。修改条件后点击查询。"
        >
          <label
            ><span>关键词</span
            ><a-input
              v-model:value="filters.search"
              placeholder="批次、周期、部门关键词"
              allow-clear
              @press-enter="loadHistory(1, true)"
          /></label>
          <label><span>周期类型</span><a-select v-model:value="filters.reportType" :options="typeOptions" /></label>
          <label><span>批次状态</span><a-select v-model:value="filters.status" :options="statusOptions" /></label>
          <template #actions
            ><a-button type="primary" :loading="historyLoading" @click="loadHistory(1, true)">查询</a-button
            ><a-button :disabled="historyLoading" @click="resetHistory">重置</a-button></template
          >
        </FilterPanel>
        <a-table
          row-key="id"
          :columns="historyColumns"
          :data-source="historyItems"
          :loading="historyLoading"
          :pagination="false"
          :scroll="{ x: 1120, y: 'min(360px, 48vh)' }"
          size="small"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'type'">{{ record.reportType === 'week' ? '周报' : '月报' }}</template>
            <template v-else-if="column.key === 'status'"
              ><a-tag>{{ batchLabels[record.status as BatchStatus] }}</a-tag></template
            >
            <template v-else-if="column.key === 'result'"
              >接受 {{ record.success }} / 失败 {{ record.failed }} / 未知 {{ record.unknown }}</template
            >
            <template v-else-if="column.key === 'action'"
              ><a-button type="link" size="small" :disabled="sending" @click="openHistory(record.id)"
                >查看详情</a-button
              ></template
            >
          </template>
          <template #emptyText>暂无符合条件的历史批次</template>
        </a-table>
        <div class="pagination">
          <span>共 {{ historyTotal }} 个批次</span
          ><a-pagination
            :current="query.page"
            :page-size="15"
            :total="historyTotal"
            :show-size-changer="false"
            @change="changePage"
          />
        </div>
      </a-tab-pane>
    </a-tabs>

    <a-spin :spinning="detailLoading">
      <section v-if="activeBatch" class="batch-panel">
        <div class="section-heading">
          <h2>{{ mode === 'prepare' ? '2. 核对部门邮件' : '批次详情' }}</h2>
          <a-button :loading="refreshing" :disabled="sending" @click="refreshBatch()">刷新批次状态</a-button>
        </div>
        <div class="batch-meta">
          <span>批次 {{ activeBatch.id }}</span
          ><span>{{ activeBatch.reportType === 'week' ? '周报' : '月报' }} · {{ activeBatch.period }}</span>
          <span>创建：{{ activeBatch.createdAt }}</span
          ><span>操作人：{{ activeBatch.operator }}</span
          ><a-tag color="blue">{{ batchLabels[activeBatch.status] }}</a-tag>
        </div>
        <div class="counts" aria-live="polite">
          <span>总计 {{ activeBatch.total }}</span
          ><span>服务已接受 {{ activeBatch.success }}</span
          ><span>失败 {{ activeBatch.failed }}</span
          ><span>结果未知 {{ activeBatch.unknown }}</span>
        </div>
        <p class="muted">服务已接受不等于最终投递成功。发送中逐封更新；失败不会自动重试。</p>
        <a-alert
          v-if="activeBatch.unknown || activeBatch.status === 'INTERRUPTED' || uncertainIds.includes(activeBatch.id)"
          type="warning"
          message="存在结果未知、任务中断或提交未核实，请先核实邮件服务及审计记录，不要直接重新发送。"
          show-icon
        />
        <a-alert v-if="pollNotice" type="warning" :message="pollNotice" show-icon />
        <a-alert
          v-for="(warning, index) in activeBatch.warnings || []"
          :key="index"
          type="warning"
          :message="warning"
          show-icon
        />
        <div v-if="activeBatch.status === 'PREVIEW'" class="selection-actions">
          <a-button size="small" :disabled="sending" @click="selectAll">全选</a-button
          ><a-button size="small" :disabled="sending" @click="selectedIds = []">取消全选</a-button
          ><a-button size="small" :disabled="sending" @click="selectAll">仅有效</a-button>
          <span>已选 {{ chosenItems.length }} 封，待预览 {{ remainingPreviews }} 封；无效、缺邮箱部门不能发送。</span>
        </div>
        <a-table
          row-key="id"
          :columns="itemColumns"
          :data-source="activeBatch.items"
          :pagination="false"
          :row-selection="rowSelection"
          :scroll="{ x: 1460, y: 'min(480px, 52vh)' }"
          size="small"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'department'"
              ><span class="cell-text">{{ record.dept_name }}</span
              ><span class="muted cell-text">{{ record.dept_leader || '未配置负责人' }}</span></template
            >
            <template v-else-if="column.key === 'mail'"
              ><span class="cell-text">收：{{ record.to || '缺少收件邮箱' }}</span
              ><span class="muted cell-text">抄：{{ record.cc || '无' }}</span></template
            >
            <template v-else-if="column.key === 'indicators'"
              ><span class="cell-text">{{ indicatorText(record.indicators) }}</span></template
            >
            <template v-else-if="column.key === 'valid'"
              ><a-tag :color="record.valid && record.to ? 'green' : 'red'">{{
                !record.to ? '缺邮箱 · 禁止发送' : record.valid ? '有效' : '无效 · 禁止发送'
              }}</a-tag
              ><span class="error-text cell-text">{{ (record.errors || []).join('；') }}</span></template
            >
            <template v-else-if="column.key === 'status'"
              ><a-tag :color="itemColor(record.status)">{{ itemLabels[record.status as ItemStatus] }}</a-tag
              ><span class="error-text cell-text">{{ record.error }}</span></template
            >
            <template v-else-if="column.key === 'preview'"
              ><a-button type="link" size="small" :disabled="sending" @click="openPreview(record)"
                >查看邮件及附件</a-button
              ><span v-if="receiptItems[record.id]" class="success-text cell-text">本版本已预览</span></template
            >
          </template>
          <template #emptyText>该批次没有可展示的部门邮件</template>
        </a-table>
        <div v-if="activeBatch.charts?.length" class="charts">
          <h3>报表图表</h3>
          <div class="chart-grid">
            <figure v-for="chart in activeBatch.charts" :key="chart.url">
              <figcaption>{{ chart.name }}</figcaption>
              <img
                v-if="chartUrl(chart.url)"
                :src="chartUrl(chart.url)"
                :alt="chart.name"
                loading="lazy"
                referrerpolicy="no-referrer"
              /><span v-else class="error-text">图表地址无效</span
              ><a-button size="small" :loading="downloading === chart.url" @click="download(chart)">下载图表</a-button>
            </figure>
          </div>
        </div>
        <div v-if="activeBatch.status === 'PREVIEW'" class="send-actions">
          <a-button type="primary" :disabled="Boolean(sendBlock)" :loading="sending" @click="confirmSend"
            >核对最终发送清单</a-button
          ><span>{{ sendBlock || `已完成 ${chosenItems.length} 封预览，可核对最终清单` }}</span>
        </div>
      </section>
      <a-empty
        v-else
        :description="mode === 'prepare' ? '上传报表与映射后，点击解析生成预览' : '请选择一个历史批次查看详情'"
      />
    </a-spin>

    <FormDialog
      v-model:open="previewOpen"
      title="部门邮件完整预览与附件核对"
      :width="1000"
      :busy="false"
      :error="previewError"
      ok-text="关闭预览"
      @submit="previewOpen = false"
    >
      <a-spin :spinning="previewLoading">
        <template v-if="preview">
          <dl class="preview-meta">
            <dt>部门</dt>
            <dd>{{ previewItem?.dept_name }}</dd>
            <dt>主题</dt>
            <dd>{{ preview.subject }}</dd>
            <dt>收件人</dt>
            <dd>{{ preview.to || '缺少邮箱，禁止发送' }}</dd>
            <dt>抄送</dt>
            <dd>{{ preview.cc || '无' }}</dd>
            <dt>部门附件</dt>
            <dd>
              <template v-if="preview.attachment"
                ><a-button
                  type="link"
                  :loading="downloading === preview.attachment.url"
                  @click="download(preview.attachment)"
                  >{{ preview.attachment.name }} · 加入导出任务</a-button
                ><code v-if="preview.attachment.sha256">SHA256 {{ preview.attachment.sha256 }}</code></template
              ><span v-else>无附件</span>
            </dd>
          </dl>
          <a-alert
            type="info"
            show-icon
            message="邮件正文为完整内容，预览区域可滚动；附件不在弹窗中截取展示，请通过页头“导出任务”下载完整原件核对。"
          />
          <p class="muted">脚本、链接跳转与远程资源已禁用，服务器邮件快照不会被修改。</p>
          <iframe
            title="邮件HTML正文预览"
            class="mail-frame"
            :srcdoc="previewDocument"
            sandbox=""
            referrerpolicy="no-referrer"
          />
          <details>
            <summary>查看全部部门指标与人员明细</summary>
            <pre>{{ detailText }}</pre>
          </details>
        </template>
        <a-empty v-else-if="!previewLoading" description="未取得邮件预览，请关闭后重新查看" />
      </a-spin>
    </FormDialog>
    <FormDialog
      v-model:open="confirmOpen"
      title="确认发送HR报表邮件"
      :width="1000"
      :busy="sending"
      :error="confirmError"
      :submit-disabled="Boolean(sendBlock)"
      ok-text="确认发送以上邮件"
      @submit="sendConfirmed"
    >
      <a-alert
        type="warning"
        message="确认后将立即提交发送。只发送下列已逐封预览且有效的部门；失败或结果未知不会自动重发。"
        show-icon
      />
      <p>
        批次 {{ confirmSnapshot?.batchId }} · 版本 {{ confirmSnapshot?.version }} · 共
        {{ confirmSnapshot?.items.length || 0 }} 封
      </p>
      <a-table
        row-key="id"
        :columns="confirmColumns"
        :data-source="confirmSnapshot?.items || []"
        :pagination="false"
        :scroll="{ x: 1080, y: 'min(400px, 45vh)' }"
        size="small"
      >
        <template #bodyCell="{ column, record }"
          ><template v-if="column.key === 'attachment'">{{ record.attachment?.name || '无附件' }}</template></template
        >
      </a-table>
      <p v-if="sendBlock" class="error-text">{{ sendBlock }}</p>
    </FormDialog>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TableProps } from 'ant-design-vue'
import PageHeader from '@/components/PageHeader.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import FormDialog from '@/components/FormDialog.vue'
import { privateFileUrl } from './api'
import { sandboxDocument } from './preview'
import { useHrMail, batchLabels, itemLabels, eligible } from './useHrMail'
import type { BatchStatus, ItemStatus, MailItem, UploadKind } from './types'

const {
  mode,
  config,
  configLoading,
  loadConfig,
  error,
  reportType,
  uploads,
  uploading,
  uploadNames,
  uploadErrors,
  uploadFile,
  canUpload,
  canCreate,
  creating,
  createBatch,
  draftBatch,
  historyItems,
  historyTotal,
  historyLoading,
  detailLoading,
  filters,
  query,
  loadHistory,
  openHistory,
  activeBatch,
  selectedIds,
  chosenItems,
  receiptItems,
  remainingPreviews,
  sendBlock,
  previewOpen,
  previewLoading,
  previewError,
  preview,
  previewItem,
  openPreview,
  confirmOpen,
  confirmError,
  confirmSnapshot,
  sending,
  confirmSend,
  sendConfirmed,
  refreshing,
  refreshBatch,
  pollNotice,
  download,
  downloading,
  uncertainIds,
} = useHrMail()
const uploadEntries: { kind: UploadKind; label: string }[] = [
  { kind: 'week', label: '周报Excel' },
  { kind: 'month', label: '月报Excel' },
  { kind: 'mapping', label: '部门与收抄送映射Excel' },
]
const typeOptions = [
  { value: '', label: '全部类型' },
  { value: 'week', label: '周报' },
  { value: 'month', label: '月报' },
]
const statusOptions = [
  { value: '', label: '全部状态' },
  ...Object.entries(batchLabels).map(([value, label]) => ({ value, label })),
]
const historyColumns = [
  { title: '批次', dataIndex: 'id', width: 190 },
  { title: '类型', key: 'type', width: 70 },
  { title: '周期', dataIndex: 'period', width: 180 },
  { title: '创建时间', dataIndex: 'createdAt', width: 175 },
  { title: '操作人', dataIndex: 'operator', width: 110 },
  { title: '状态', key: 'status', width: 110 },
  { title: '总封数', dataIndex: 'total', width: 75 },
  { title: '逐封结果', key: 'result', width: 240 },
  { title: '操作', key: 'action', width: 100 },
]
const itemColumns = [
  { title: '部门 / 负责人', key: 'department', width: 170 },
  { title: '收件人 / 抄送', key: 'mail', width: 260 },
  { title: '主题', dataIndex: 'subject', width: 240 },
  { title: '部门指标（完整内容见预览）', key: 'indicators', width: 240 },
  { title: '校验', key: 'valid', width: 190 },
  { title: '发送结果 / 原因', key: 'status', width: 200 },
  { title: '邮件预览', key: 'preview', width: 170 },
]
const confirmColumns = [
  { title: '部门', dataIndex: 'dept_name', width: 140 },
  { title: '主题', dataIndex: 'subject', width: 260 },
  { title: '收件人', dataIndex: 'to', width: 230 },
  { title: '抄送', dataIndex: 'cc', width: 230 },
  { title: '附件', key: 'attachment', width: 220 },
]
const rowSelection = computed<TableProps<MailItem>['rowSelection']>(() =>
  activeBatch.value?.status !== 'PREVIEW'
    ? undefined
    : {
        selectedRowKeys: selectedIds.value,
        onChange: (keys) => {
          selectedIds.value = keys.map(String)
        },
        getCheckboxProps: (item) => ({ disabled: !eligible(item) || sending.value }),
      },
)
function selectAll() {
  selectedIds.value = activeBatch.value?.items.filter(eligible).map((item) => item.id) ?? []
}
function resetHistory() {
  filters.value = { search: '', reportType: '', status: '' }
  void loadHistory(1, true)
}
function changePage(page: number) {
  void loadHistory(page)
}
function indicatorText(indicators: Record<string, unknown>) {
  return (
    Object.entries(indicators || {})
      .map(
        ([name, value]) =>
          `${name}：${value == null ? '缺失' : typeof value === 'object' ? JSON.stringify(value) : String(value)}`,
      )
      .join('；') || '无指标'
  )
}
function itemColor(status: ItemStatus) {
  return status === 'SUCCESS'
    ? 'green'
    : status === 'FAILED' || status === 'UNKNOWN'
      ? 'red'
      : status === 'SENDING'
        ? 'blue'
        : 'default'
}
function chartUrl(url: string) {
  try {
    return privateFileUrl(url)
  } catch {
    return undefined
  }
}
const previewDocument = computed(() => (preview.value ? sandboxDocument(preview.value.html_body) : ''))
const detailText = computed(() =>
  JSON.stringify({ 部门指标: previewItem.value?.indicators, 人员明细: previewItem.value?.persons ?? [] }, null, 2),
)
</script>

<style scoped>
.hr-mail-page {
  min-width: 0;
}
.hr-mail-page > .ant-alert {
  margin-bottom: 12px;
}
.service-status,
.prepare-actions,
.selection-actions,
.send-actions,
.batch-meta,
.counts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.service-status {
  margin-bottom: 16px;
}
.service-status > span:last-child,
.muted,
.section-heading > span {
  color: #69768a;
  font-size: 13px;
}
.upload-panel,
.batch-panel {
  min-width: 0;
  padding: 20px;
  background: #fff;
  border: 1px solid #e4e9ef;
  border-radius: 12px;
  margin-bottom: 16px;
}
.section-heading {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
h2,
h3 {
  margin: 0;
  font-size: 16px;
  color: #182235;
}
.upload-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin: 16px 0;
}
.upload-field {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  border: 1px solid #edf0f5;
  border-radius: 8px;
}
.upload-field > label {
  font-weight: 500;
}
.upload-field input {
  width: 100%;
  min-width: 0;
}
.file-name,
.batch-meta > span,
dd,
code {
  overflow-wrap: anywhere;
}
.type-field {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.prepare-actions {
  margin-top: 16px;
}
.batch-meta {
  color: #69768a;
  margin-bottom: 16px;
}
.counts {
  font-variant-numeric: tabular-nums;
  margin-bottom: 8px;
}
.batch-panel > .ant-alert {
  margin-bottom: 12px;
}
.selection-actions {
  margin: 16px 0 12px;
}
.cell-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.error-text {
  color: #b42318;
  font-size: 13px;
}
.success-text {
  color: #16774a;
  font-size: 13px;
}
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 16px 0 24px;
}
.send-actions {
  padding-top: 16px;
}
.send-actions > span {
  color: #69768a;
  font-size: 13px;
}
.preview-meta {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 10px 12px;
}
.preview-meta dt {
  color: #69768a;
}
.preview-meta dd {
  margin: 0;
  white-space: pre-wrap;
}
.preview-meta code {
  display: block;
  font-size: 12px;
}
.preview-meta .ant-btn {
  padding: 0;
  height: auto;
  white-space: normal;
  text-align: left;
}
.mail-frame {
  display: block;
  width: 100%;
  height: 440px;
  border: 1px solid #e4e9ef;
  background: white;
}
details {
  margin-top: 16px;
}
summary {
  cursor: pointer;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 280px;
  overflow: auto;
  background: #f6f8fb;
  padding: 12px;
}
.charts {
  margin-top: 20px;
}
.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
  margin-top: 12px;
}
figure {
  margin: 0;
  min-width: 0;
}
figure img {
  display: block;
  max-width: 100%;
  max-height: 320px;
  object-fit: contain;
  margin: 8px 0;
}
.hr-mail-page :deep(.ant-table-cell) {
  overflow-wrap: anywhere;
}
@media (max-width: 1024px) {
  .upload-grid {
    grid-template-columns: 1fr;
  }
  .upload-panel,
  .batch-panel {
    padding: 16px;
  }
}
@media (max-height: 600px) {
  .mail-frame {
    height: 280px;
  }
}
</style>
