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
      if (!silent) this.loading = true
      try {
        this.tasks = await listComprehensiveExports()
        this.lastError = ''
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : '导出任务状态获取失败'
      } finally {
        if (!silent) this.loading = false
        this.refreshing = false
      }
    },
    startPolling() {
      if (this.pollingTimer != null || typeof window === 'undefined') return
      void this.refresh()
      this.pollingTimer = window.setInterval(() => { void this.refresh(true) }, 2_000)
    },
    stopPolling() {
      if (this.pollingTimer != null) window.clearInterval(this.pollingTimer)
      this.pollingTimer = undefined
    },
    async create(scope: FilterScope, business: BusinessKey) {
      const task = await createComprehensiveExport(scope, business)
      this.drawerOpen = true
      await this.refresh(true)
      return task
    },
    async cancel(id: string) {
      await cancelComprehensiveExport(id)
      await this.refresh(true)
    },
    async createRoutes(scope: GdsRouteScope) {
      const task = await createGdsRouteExport(scope)
      this.drawerOpen = true
      await this.refresh(true)
      return task
    },
    async createBackground(
      kind: 'resource_governance_gds' | 'resource_governance_ota' | 'smart_trend_daily' | 'smart_trend_monthly' | 'smart_dimensions' | 'smart_details' | 'adm_cases' | 'adm_lines',
      payload: Record<string, unknown>,
    ) {
      const task = await createBackgroundExport(kind, payload)
      this.drawerOpen = true
      await this.refresh(true)
      return task
    },
  },
})
