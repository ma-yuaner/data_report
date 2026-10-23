import { defineStore } from 'pinia'
import {
  cancelComprehensiveExport,
  createComprehensiveExport,
  listComprehensiveExports,
  type ComprehensiveExportTask,
} from '@/api/comprehensiveExport'
import type { BusinessKey, FilterScope } from '@/api/comprehensive'

const activeStatuses = new Set(['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'])

export const useComprehensiveExportStore = defineStore('comprehensive-exports', {
  state: () => ({
    tasks: [] as ComprehensiveExportTask[],
    drawerOpen: false,
    loading: false,
    lastError: '',
    pollingTimer: undefined as number | undefined,
  }),
  getters: {
    activeCount: state => state.tasks.filter(task => activeStatuses.has(task.status)).length,
  },
  actions: {
    async refresh() {
      if (this.loading) return
      this.loading = true
      try {
        this.tasks = await listComprehensiveExports()
        this.lastError = ''
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : '导出任务状态获取失败'
      } finally {
        this.loading = false
      }
    },
    startPolling() {
      if (this.pollingTimer != null || typeof window === 'undefined') return
      void this.refresh()
      this.pollingTimer = window.setInterval(() => { void this.refresh() }, 2_000)
    },
    stopPolling() {
      if (this.pollingTimer != null) window.clearInterval(this.pollingTimer)
      this.pollingTimer = undefined
    },
    async create(scope: FilterScope, business: BusinessKey) {
      const task = await createComprehensiveExport(scope, business)
      this.drawerOpen = true
      await this.refresh()
      return task
    },
    async cancel(id: string) {
      await cancelComprehensiveExport(id)
      await this.refresh()
    },
  },
})
