<template>
  <a-drawer v-model:open="store.drawerOpen" title="导出任务" width="480">
    <a-alert class="task-note" type="info" show-icon message="后台导出" description="切换或刷新页面不会中断任务；任务可取消。文件首次下载完成后会自动从服务器清理。查询正在执行时需等当前查询返回后完成取消。" />
    <a-alert v-if="store.lastError" class="task-note" type="error" show-icon :message="store.lastError" />
    <a-spin :spinning="store.loading">
      <a-empty v-if="!store.tasks.length" description="暂无导出任务" />
      <div v-else class="task-list">
        <article v-for="task in store.tasks" :key="task.id" class="task-card">
          <header>
            <div><strong>{{ task.taskLabel || task.businessLabel + '宽表明细' }}</strong><span>{{ task.startDate }}<template v-if="task.endDate !== task.startDate"> 至 {{ task.endDate }}</template></span></div>
            <a-tag :color="statusMeta(task.status).color">{{ statusMeta(task.status).label }}</a-tag>
          </header>
          <a-progress v-if="isActive(task.status)" :percent="percent(task)" :status="task.status === 'CANCEL_REQUESTED' ? 'exception' : 'active'" />
          <div class="task-meta"><span>{{ task.message || statusMeta(task.status).label }}</span><span>{{ progressText(task) }}</span></div>
          <footer>
            <a-button v-if="task.canPrioritize" size="small" :loading="prioritizingId === task.id" @click="prioritize(task)">
              优先处理
            </a-button>
            <a-button v-if="task.canCancel" size="small" danger :disabled="task.status === 'CANCEL_REQUESTED'" @click="cancel(task)">
              {{ task.status === 'CANCEL_REQUESTED' ? '正在取消' : '取消任务' }}
            </a-button>
            <a-button v-if="task.canDownload" type="primary" size="small" @click="download(task.id)"><DownloadOutlined />下载文件</a-button>
          </footer>
        </article>
      </div>
    </a-spin>
  </a-drawer>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { DownloadOutlined } from '@ant-design/icons-vue'
import { comprehensiveExportDownloadUrl, type ComprehensiveExportStatus, type ComprehensiveExportTask } from '@/api/comprehensiveExport'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'

const store = useComprehensiveExportStore()
const prioritizingId = ref('')
const formatter = new Intl.NumberFormat('zh-CN')
const number = (value: number) => formatter.format(value || 0)
const isActive = (status: ComprehensiveExportStatus) => ['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'].includes(status)
const awaitingTotal = (task: ComprehensiveExportTask) => isActive(task.status) && !task.totalRows
const progressText = (task: ComprehensiveExportTask) => {
  if (awaitingTotal(task)) return '处理中'
  const unit = task.businessType === 'hr_mail_file' ? '个文件' : '条'
  return `${number(task.processedRows)} / ${number(task.totalRows)} ${unit}`
}
const percent = (task: ComprehensiveExportTask) => task.status === 'QUEUED' ? 0 : Math.min(99, Math.round(task.processedRows * 100 / Math.max(1, task.totalRows)))
const statusMeta = (status: ComprehensiveExportStatus) => ({
  QUEUED: { label: '排队中', color: 'default' },
  RUNNING: { label: '导出中', color: 'processing' },
  CANCEL_REQUESTED: { label: '正在取消', color: 'warning' },
  CANCELLED: { label: '已取消', color: 'default' },
  SUCCEEDED: { label: '已完成', color: 'success' },
  DOWNLOADED: { label: '已下载', color: 'blue' },
  FAILED: { label: '失败', color: 'error' },
  EXPIRED: { label: '已过期', color: 'default' },
}[status])

async function cancel(task: ComprehensiveExportTask) {
  try { await store.cancel(task.id); message.success(task.status === 'QUEUED' ? '任务已取消' : '取消请求已提交') }
  catch (error) { message.error(error instanceof Error ? error.message : '取消失败') }
}
async function runPrioritize(task: ComprehensiveExportTask) {
  prioritizingId.value = task.id
  try {
    const result = await store.prioritize(task.id)
    message.success(result.preemptedTaskId ? '当前任务将停止并从头重新排队，已优先处理所选任务' : '已将任务移到队首')
  } catch (error) {
    message.error(error instanceof Error ? error.message : '优先处理失败')
  } finally {
    prioritizingId.value = ''
  }
}
function prioritize(task: ComprehensiveExportTask) {
  const running = store.tasks.find(item => item.status === 'RUNNING')
  if (!running) {
    void runPrioritize(task)
    return
  }
  Modal.confirm({
    title: '优先处理这个任务？',
    content: `正在运行的“${running.taskLabel || running.businessLabel}”会在当前批次结束后停止，并排到该任务后从 0 重新导出。已完成进度不会保留。`,
    okText: '优先处理',
    cancelText: '暂不调整',
    onOk: () => runPrioritize(task),
  })
}
function download(id: string) { window.location.assign(comprehensiveExportDownloadUrl(id)) }
</script>

<style scoped>
.task-note { margin-bottom: 16px; }
.task-list { display: grid; gap: 12px; }
.task-card { padding: 14px; border: 1px solid #e5eaf1; border-radius: 10px; background: #fff; }
.task-card header, .task-card footer, .task-meta { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.task-card header { margin-bottom: 12px; }
.task-card header div { min-width: 0; display: grid; gap: 3px; }
.task-card header strong { color: #334155; }
.task-card header span, .task-meta { color: #69768a; font-size: 12px; }
.task-card footer { justify-content: flex-end; margin-top: 12px; }
</style>
