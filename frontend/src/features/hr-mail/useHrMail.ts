import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import { hrMailApi, privateFileScope } from './api'
import type {
  Batch,
  BatchSummary,
  HistoryQuery,
  MailConfig,
  MailFile,
  MailItem,
  MailPreview,
  ReportType,
  Upload,
  UploadKind,
} from './types'

const errorText = (error: unknown) => (error instanceof Error ? error.message : '请求失败，请稍后查询状态')
export const batchLabels = {
  PREVIEW: '待预览确认',
  QUEUED: '排队中',
  RUNNING: '发送中',
  COMPLETED: '已结束',
  INTERRUPTED: '已中断',
}
export const itemLabels = {
  PENDING: '待发送',
  SENDING: '发送中',
  SUCCESS: '服务已接受',
  FAILED: '失败',
  UNKNOWN: '结果未知',
  SKIPPED: '已跳过',
}
export const eligible = (item: MailItem) => item.valid && Boolean(item.to?.trim()) && item.status === 'PENDING'

export function useHrMail() {
  const auth = useAuthStore()
  const exportTasks = useComprehensiveExportStore()
  const mode = ref<'prepare' | 'history'>('prepare')
  const config = ref<MailConfig>()
  const configLoading = ref(false)
  const error = ref('')
  const reportType = ref<ReportType>('week')
  const uploads = ref<Partial<Record<UploadKind, Upload>>>({})
  const uploading = ref<Partial<Record<UploadKind, boolean>>>({})
  const uploadNames = ref<Partial<Record<UploadKind, string>>>({})
  const uploadErrors = ref<Partial<Record<UploadKind, string>>>({})
  const creating = ref(false)
  const draftBatch = ref<Batch>()
  const historyBatch = ref<Batch>()
  const historyItems = ref<BatchSummary[]>([])
  const historyTotal = ref(0)
  const historyLoading = ref(false)
  const detailLoading = ref(false)
  const filters = ref({ search: '', reportType: '', status: '' })
  const query = ref<HistoryQuery>({ page: 1, pageSize: 15, ...filters.value })
  const selectedIds = ref<string[]>([])
  const receipts = ref<Record<string, { version: number; items: Record<string, string> }>>({})
  const previewOpen = ref(false)
  const previewLoading = ref(false)
  const previewError = ref('')
  const preview = ref<MailPreview>()
  const previewItem = ref<MailItem>()
  const confirmOpen = ref(false)
  const confirmError = ref('')
  const confirmSnapshot = ref<{
    batchId: string
    version: number
    items: MailItem[]
    receipts: Record<string, string>
  }>()
  const sending = ref(false)
  const uncertainIds = ref<string[]>([])
  const refreshing = ref(false)
  const pollNotice = ref('')
  const downloading = ref('')
  let ownerEpoch = 0
  let prepareSequence = 0
  let historySequence = 0
  let detailSequence = 0
  let previewSequence = 0
  let refreshSequence = 0
  const uploadSequence: Record<UploadKind, number> = { week: 0, month: 0, mapping: 0 }
  let timer: ReturnType<typeof setTimeout> | undefined
  let pollRounds = 0
  let disposed = false
  const activeBatch = computed(() => (mode.value === 'prepare' ? draftBatch.value : historyBatch.value))
  const canUpload = computed(() => Boolean(config.value?.permissions.upload && config.value.storageReady))
  const uploadBusy = computed(() => Object.values(uploading.value).some(Boolean))
  const canCreate = computed(
    () =>
      canUpload.value &&
      !creating.value &&
      !sending.value &&
      !uploadBusy.value &&
      Boolean(uploads.value[reportType.value] && uploads.value.mapping),
  )
  const chosenItems = computed(
    () => activeBatch.value?.items.filter((item) => selectedIds.value.includes(item.id)) ?? [],
  )
  const receiptItems = computed(() => {
    const batch = activeBatch.value
    if (!batch || receipts.value[batch.id]?.version !== batch.version) return {}
    return receipts.value[batch.id]?.items ?? {}
  })
  const remainingPreviews = computed(() => chosenItems.value.filter((item) => !receiptItems.value[item.id]).length)
  const sendBlock = computed(() => {
    const batch = activeBatch.value
    if (!config.value?.permissions.send) return '没有发送权限（hr.mail.send）'
    if (!config.value.mailConfigReady || !config.value.sendEnabled) return '服务器邮件配置或发送开关未就绪'
    if (!batch || batch.status !== 'PREVIEW') return '仅待预览批次可首次发送'
    if (uncertainIds.value.includes(batch.id)) return '上次提交结果未知，请刷新并人工核实，禁止直接重发'
    if (sending.value || detailLoading.value || refreshing.value || creating.value || uploadBusy.value)
      return '操作进行中，请稍候'
    if (!chosenItems.value.length) return '请选择部门'
    if (chosenItems.value.some((item) => !eligible(item))) return '选择中存在无效或缺邮箱部门'
    if (remainingPreviews.value) return `请逐封预览所选邮件（还有 ${remainingPreviews.value} 封）`
    return ''
  })
  const alive = (epoch: number) => !disposed && ownerEpoch === epoch
  function stopPoll() {
    if (timer) clearTimeout(timer)
    timer = undefined
  }
  function invalidatePreview() {
    prepareSequence++
    previewSequence++
    previewOpen.value = false
    preview.value = undefined
    previewItem.value = undefined
    previewLoading.value = false
    confirmOpen.value = false
    confirmSnapshot.value = undefined
    selectedIds.value = []
    if (draftBatch.value?.status === 'PREVIEW') {
      delete receipts.value[draftBatch.value.id]
      draftBatch.value = undefined
    }
  }
  async function loadConfig() {
    const epoch = ownerEpoch
    configLoading.value = true
    try {
      const result = await hrMailApi.config()
      if (alive(epoch)) {
        config.value = result
        error.value = ''
      }
    } catch (cause) {
      if (alive(epoch)) error.value = errorText(cause)
    } finally {
      if (alive(epoch)) configLoading.value = false
    }
  }
  async function uploadFile(kind: UploadKind, event: Event) {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    input.value = ''
    if (!file || !canUpload.value || sending.value || creating.value) return
    invalidatePreview()
    const sequence = ++uploadSequence[kind]
    const epoch = ownerEpoch
    delete uploads.value[kind]
    uploadNames.value[kind] = file.name
    uploadErrors.value[kind] = ''
    uploading.value[kind] = true
    try {
      const result = await hrMailApi.upload(file, kind)
      if (alive(epoch) && sequence === uploadSequence[kind]) {
        uploads.value[kind] = result
        message.success(`${result.name} 上传完成`)
      }
    } catch (cause) {
      if (alive(epoch) && sequence === uploadSequence[kind]) uploadErrors.value[kind] = errorText(cause)
    } finally {
      if (alive(epoch) && sequence === uploadSequence[kind]) uploading.value[kind] = false
    }
  }
  async function createBatch() {
    if (!canCreate.value) return
    const report = uploads.value[reportType.value]
    const mapping = uploads.value.mapping
    if (!report || !mapping) return
    invalidatePreview()
    const sequence = ++prepareSequence
    const epoch = ownerEpoch
    creating.value = true
    error.value = ''
    try {
      const result = await hrMailApi.create(reportType.value, report.id, mapping.id)
      if (!alive(epoch) || sequence !== prepareSequence) return
      draftBatch.value = result
      selectedIds.value = result.items.filter(eligible).map((item) => item.id)
      message.success('解析完成，请逐封核对邮件及部门附件')
      void loadHistory()
    } catch (cause) {
      if (alive(epoch) && sequence === prepareSequence) error.value = errorText(cause)
    } finally {
      if (alive(epoch)) creating.value = false
    }
  }
  async function loadHistory(page = query.value.page, applyFilters = false) {
    const sequence = ++historySequence
    const epoch = ownerEpoch
    const requestQuery = applyFilters ? { page: 1, pageSize: 15, ...filters.value } : { ...query.value, page }
    historyLoading.value = true
    try {
      const result = await hrMailApi.history(requestQuery)
      if (!alive(epoch) || sequence !== historySequence) return
      historyItems.value = result.items
      historyTotal.value = result.total
      query.value = requestQuery
    } catch (cause) {
      if (alive(epoch) && sequence === historySequence) error.value = errorText(cause)
    } finally {
      if (alive(epoch) && sequence === historySequence) historyLoading.value = false
    }
  }
  function updateBatch(result: Batch) {
    const old = draftBatch.value?.id === result.id ? draftBatch.value : historyBatch.value
    if (old && old.version !== result.version) delete receipts.value[result.id]
    if (draftBatch.value?.id === result.id) draftBatch.value = result
    if (historyBatch.value?.id === result.id) historyBatch.value = result
    if (result.status !== 'PREVIEW') uncertainIds.value = uncertainIds.value.filter((id) => id !== result.id)
    if (activeBatch.value?.id === result.id)
      selectedIds.value = selectedIds.value.filter((id) =>
        result.items.some((item) => item.id === id && eligible(item)),
      )
  }
  async function openHistory(id: string) {
    const sequence = ++detailSequence
    const epoch = ownerEpoch
    historyBatch.value = undefined
    detailLoading.value = true
    error.value = ''
    try {
      const result = await hrMailApi.batch(id)
      if (!alive(epoch) || sequence !== detailSequence) return
      historyBatch.value = result
      selectedIds.value = result.items.filter(eligible).map((item) => item.id)
    } catch (cause) {
      if (alive(epoch) && sequence === detailSequence) error.value = errorText(cause)
    } finally {
      if (alive(epoch) && sequence === detailSequence) detailLoading.value = false
    }
  }
  async function refreshBatch() {
    const batch = activeBatch.value
    if (!batch || refreshing.value) return
    const epoch = ownerEpoch
    const sequence = ++refreshSequence
    refreshing.value = true
    try {
      const result = await hrMailApi.batch(batch.id)
      if (alive(epoch) && sequence === refreshSequence && activeBatch.value?.id === batch.id) {
        updateBatch(result)
        pollNotice.value = ''
      }
    } catch (cause) {
      if (alive(epoch) && sequence === refreshSequence)
        pollNotice.value = `状态刷新失败：${errorText(cause)}。请手动刷新核实，未自动重发。`
    } finally {
      if (alive(epoch) && sequence === refreshSequence) refreshing.value = false
      if (alive(epoch)) schedulePoll()
    }
  }
  function schedulePoll() {
    stopPoll()
    if (disposed || document.hidden || !activeBatch.value || !['QUEUED', 'RUNNING'].includes(activeBatch.value.status))
      return
    if (pollRounds >= 90) {
      pollNotice.value = '自动刷新已暂停（约6分钟），可手动刷新查看最新状态；不会自动重发。'
      return
    }
    timer = setTimeout(() => {
      pollRounds++
      void refreshBatch()
    }, 4000)
  }
  function visibilityChanged() {
    if (document.hidden) stopPoll()
    else schedulePoll()
  }
  async function openPreview(item: MailItem) {
    const batch = activeBatch.value
    if (!batch || sending.value) return
    const sequence = ++previewSequence
    const epoch = ownerEpoch
    previewOpen.value = true
    previewLoading.value = true
    preview.value = undefined
    previewItem.value = item
    previewError.value = ''
    try {
      const result = await hrMailApi.preview(batch.id, item.id)
      if (
        !alive(epoch) ||
        sequence !== previewSequence ||
        activeBatch.value?.id !== batch.id ||
        activeBatch.value.version !== batch.version ||
        !previewOpen.value
      )
        return
      preview.value = result
      if (batch.status === 'PREVIEW' && result.receipt) {
        if (receipts.value[batch.id]?.version !== batch.version)
          receipts.value[batch.id] = { version: batch.version, items: {} }
        receipts.value[batch.id]!.items[item.id] = result.receipt
      }
    } catch (cause) {
      if (alive(epoch) && sequence === previewSequence) previewError.value = errorText(cause)
    } finally {
      if (alive(epoch) && sequence === previewSequence) previewLoading.value = false
    }
  }
  function confirmSend() {
    const batch = activeBatch.value
    if (!batch || sendBlock.value) return
    confirmSnapshot.value = {
      batchId: batch.id,
      version: batch.version,
      items: [...chosenItems.value],
      receipts: Object.fromEntries(chosenItems.value.map((item) => [item.id, receiptItems.value[item.id]!])),
    }
    confirmError.value = ''
    confirmOpen.value = true
  }
  async function sendConfirmed() {
    const snapshot = confirmSnapshot.value
    const batch = activeBatch.value
    if (!snapshot || !batch || sending.value) return
    if (
      sendBlock.value ||
      snapshot.batchId !== batch.id ||
      snapshot.version !== batch.version ||
      snapshot.items
        .map((item) => item.id)
        .sort()
        .join(',') !== [...selectedIds.value].sort().join(',')
    ) {
      confirmError.value = '批次或选择已变化，请关闭并重新核对清单'
      return
    }
    const epoch = ownerEpoch
    sending.value = true
    confirmError.value = ''
    try {
      const result = await hrMailApi.send(
        batch.id,
        snapshot.version,
        snapshot.items.map((item) => item.id),
        snapshot.receipts,
      )
      if (!alive(epoch)) return
      updateBatch(result)
      confirmOpen.value = false
      message.success('发送请求已受理，请查看逐封结果')
      void loadHistory()
      pollRounds = 0
      schedulePoll()
    } catch (cause) {
      if (!alive(epoch)) return
      // Never retry an ambiguous POST, even when the last visible status is PREVIEW.
      uncertainIds.value.push(batch.id)
      confirmError.value = `${errorText(cause)}。本次提交结果尚需核实，请关闭窗口并刷新批次；不要直接重发。`
    } finally {
      if (alive(epoch)) sending.value = false
    }
  }
  async function download(file: MailFile) {
    if (downloading.value) return
    const epoch = ownerEpoch
    downloading.value = file.url
    try {
      const scope = privateFileScope(file.url)
      const task = await exportTasks.createBackground('hr_mail_file', scope)
      if (alive(epoch))
        message.success(task.reused ? '相同附件任务正在进行，已打开导出任务' : '已加入导出任务，可在页头查看并下载')
    } catch (cause) {
      if (alive(epoch)) message.error(errorText(cause))
    } finally {
      if (alive(epoch)) downloading.value = ''
    }
  }
  watch(reportType, invalidatePreview)
  watch(mode, () => {
    previewSequence++
    previewOpen.value = false
    preview.value = undefined
    confirmOpen.value = false
    selectedIds.value = activeBatch.value?.items.filter(eligible).map((item) => item.id) ?? []
  })
  watch(
    () => `${activeBatch.value?.id ?? ''}:${activeBatch.value?.status ?? ''}`,
    () => {
      pollRounds = 0
      pollNotice.value = ''
      schedulePoll()
    },
  )
  watch(
    () => auth.user?.id,
    () => {
      ownerEpoch++
      stopPoll()
      invalidatePreview()
      config.value = undefined
      draftBatch.value = undefined
      historyBatch.value = undefined
      historyItems.value = []
      historyTotal.value = 0
      filters.value = { search: '', reportType: '', status: '' }
      query.value = { page: 1, pageSize: 15, ...filters.value }
      reportType.value = 'week'
      uploads.value = {}
      uploadNames.value = {}
      uploadErrors.value = {}
      uploading.value = {}
      receipts.value = {}
      uncertainIds.value = []
      error.value = ''
      creating.value = false
      sending.value = false
      refreshing.value = false
      detailLoading.value = false
      historyLoading.value = false
      downloading.value = ''
      if (auth.user) {
        void loadConfig()
        void loadHistory(1)
      }
    },
    { immediate: true },
  )
  document.addEventListener('visibilitychange', visibilityChanged)
  onBeforeUnmount(() => {
    disposed = true
    ownerEpoch++
    stopPoll()
    document.removeEventListener('visibilitychange', visibilityChanged)
  })
  return {
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
    uploadBusy,
    creating,
    createBatch,
    draftBatch,
    historyItems,
    historyTotal,
    historyLoading,
    detailLoading,
    historyBatch,
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
  }
}
