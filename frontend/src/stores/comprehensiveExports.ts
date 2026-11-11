import { defineStore } from 'pinia'
import {
  cancelComprehensiveExport,
  createBackgroundExport,
  createComprehensiveExport,
  createGdsRouteExport,
  listComprehensiveExports,
  type ComprehensiveExportTask,
} from '@/api/comprehensiveExport'
import type { BusinessKey, FilterScope } from '@/api/comprehensive'
import type { GdsRouteScope } from '@/api/resourceGovernance'

const activeStatuses = new Set(['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'])

export const useComprehensiveExportStore = defineStore('comprehensive-exports', {
  state: () => ({
    tasks: [] as ComprehensiveExportTask[],
    drawerOpen: false,
    loading: false,
    refreshing: false,
    taskRevision: 0,
    lastError: '',
    pollingTimer: undefined as number | undefined,
  }),
  getters: {
    activeCount: state => state.tasks.filter(task => activeStatuses.has(task.status)).length,
  },
  actions: {
    async refresh(silent = false) {
      if (this.refreshing) return
      this.refreshing = true
      const revision = this.taskRevision
      if (!silent) this.loading = true
      try {
        const tasks = await listComprehensiveExports()
        if (revision === this.taskRevision) this.tasks = tasks
        this.lastError = ''
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : '导出任务状态获取失败'
      } finally {
        if (!silent) this.loading = false
        this.refreshing = false
      }
    },
    startPolling() {
      if (!this.activeCount || this.pollingTimer != null || typeof window === 'undefined') return
      this.pollingTimer = window.setInterval(() => { void this.refresh(true) }, 2_000)
    },
    stopPolling() {
      if (this.pollingTimer != null) window.clearInterval(this.pollingTimer)
      this.pollingTimer = undefined
    },
    rememberTask(task: ComprehensiveExportTask) {
      this.taskRevision += 1
      const index = this.tasks.findIndex(item => item.id === task.id)
      if (index < 0) this.tasks.unshift(task)
      else this.tasks[index] = task
    },
    async create(scope: FilterScope, business: BusinessKey) {
      const task = await createComprehensiveExport(scope, business)
      this.rememberTask(task)
      this.drawerOpen = true
      await this.refresh(true)
      return task
    },
    async cancel(id: string) {
      this.rememberTask(await cancelComprehensiveExport(id))
      await this.refresh(true)
    },
    async createRoutes(scope: GdsRouteScope) {
      const task = await createGdsRouteExport(scope)
      this.rememberTask(task)
      this.drawerOpen = true
      await this.refresh(true)
      return task
    },
    async createBackground(
      kind: 'resource_governance_gds' | 'resource_governance_ota' | 'smart_trend_daily' | 'smart_trend_monthly' | 'smart_dimensions' | 'smart_details' | 'hr_mail_file' | 'smart_missed_orders' | 'adm_operator_excel' | 'adm_attachment' | 'adm_import_template',
      payload: Record<string, unknown>,
    ) {
      const task = await createBackgroundExport(kind, payload)
      this.rememberTask(task)
      this.drawerOpen = true
      await this.refresh(true)
      return task
    },
  },
})
