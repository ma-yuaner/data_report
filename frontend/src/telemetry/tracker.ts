import type { Router, RouteLocationNormalizedLoaded } from 'vue-router'
import type { AuthUser } from '@/api/auth'
import { ApiError, getCsrfToken } from '@/api/http'
import { telemetryApi, type TelemetryEventPayload } from '@/api/telemetry'

type UserProvider = () => AuthUser | null
type EventContext = Record<string, string | number | boolean | null | string[]>

const APP_VERSION = import.meta.env.VITE_APP_VERSION || 'web-v1'
const SENSITIVE_ROUTES = new Set(['login', 'change-password'])
const FLUSH_INTERVAL_MS = 5_000
const HEARTBEAT_INTERVAL_MS = 60_000
const MAX_QUEUE = 50

function identifier() { return crypto.randomUUID().replaceAll('-', '').toLowerCase() }
function pageCode(route: RouteLocationNormalizedLoaded) { return String(route.name || 'unknown-page') }
function moduleCode(route: RouteLocationNormalizedLoaded) { return String(route.meta.section || 'system').toLowerCase().replaceAll(' ', '-') }
function pageTitle(route: RouteLocationNormalizedLoaded) { return String(route.meta.title || route.name || '未知页面') }
function deviceType() { return window.innerWidth < 600 ? 'mobile' : window.innerWidth < 1024 ? 'tablet' : 'desktop' }
function trackable(route: RouteLocationNormalizedLoaded, user: AuthUser | null) {
  return Boolean(user && !user.mustChangePassword && !route.meta.public && !SENSITIVE_ROUTES.has(String(route.name || '')))
}

class TelemetryTracker {
  private current?: { visitId: string; route: RouteLocationNormalizedLoaded; activeMs: number; activeSince?: number }
  private previousPageCode = ''
  private navigationStartedAt = performance.now()
  private queue: TelemetryEventPayload[] = []
  private flushing = false
  private disabledUntil = 0

  constructor(private router: Router, private getUser: UserProvider) {}

  initialize() {
    this.router.beforeEach(() => {
      this.finishVisit('route_change')
      this.navigationStartedAt = performance.now()
      return true
    })
    this.router.afterEach((to, _from, failure) => {
      document.title = `${String(to.meta.title ?? '页面不存在')} · 企业数据中心`
      if (!failure) this.startVisit(to)
    })
    window.addEventListener('click', this.captureClick, true)
    window.addEventListener('data-report:api-result', this.captureApiResult as EventListener)
    window.addEventListener('error', () => this.track('frontend_error', { elementCode: 'window-error', elementName: '页面脚本错误', resultStatus: 'failed', errorCode: 'WINDOW_ERROR' }))
    window.addEventListener('unhandledrejection', () => this.track('frontend_error', { elementCode: 'unhandled-rejection', elementName: '未处理异步错误', resultStatus: 'failed', errorCode: 'UNHANDLED_REJECTION' }))
    document.addEventListener('visibilitychange', this.handleVisibility)
    window.addEventListener('beforeunload', () => this.finishVisit('unload', true))
    window.setInterval(() => {
      this.heartbeat()
      void this.flush()
    }, HEARTBEAT_INTERVAL_MS)
    window.setInterval(() => void this.flush(), FLUSH_INTERVAL_MS)
  }

  private temporarilyDisable(error: unknown) {
    if (error instanceof ApiError && error.status === 503) this.disabledUntil = Date.now() + 60_000
  }

  private startVisit(route: RouteLocationNormalizedLoaded) {
    const user = this.getUser()
    if (!trackable(route, user) || Date.now() < this.disabledUntil) return
    const visitId = identifier()
    const currentPageCode = pageCode(route)
    this.current = { visitId, route, activeMs: 0, activeSince: performance.now() }
    void telemetryApi.startVisit({
      visitId, moduleCode: moduleCode(route), pageCode: currentPageCode,
      routePath: route.path, pageTitle: pageTitle(route),
      referrerPageCode: this.previousPageCode || undefined,
      loadDurationMs: Math.max(0, Math.round(performance.now() - this.navigationStartedAt)),
      viewportWidth: window.innerWidth, viewportHeight: window.innerHeight,
      deviceType: deviceType(), appVersion: APP_VERSION,
    }).catch(error => this.temporarilyDisable(error))
    this.previousPageCode = currentPageCode
  }

  private commitActive() {
    if (!this.current?.activeSince) return
    this.current.activeMs += Math.max(0, performance.now() - this.current.activeSince)
    this.current.activeSince = document.visibilityState === 'visible' ? performance.now() : undefined
  }

  private heartbeat() {
    if (!this.current || Date.now() < this.disabledUntil) return
    this.commitActive()
    void telemetryApi.updateVisit(this.current.visitId, {
      activeDurationMs: Math.round(this.current.activeMs),
    }).catch(error => this.temporarilyDisable(error))
  }

  private finishVisit(exitType: string, keepalive = false) {
    if (!this.current) return
    this.commitActive()
    const current = this.current
    this.current = undefined
    const payload = JSON.stringify({ activeDurationMs: Math.round(current.activeMs), exitType })
    if (keepalive && getCsrfToken()) {
      void fetch(`/api/v1/telemetry/visits/${current.visitId}`, {
        method: 'PATCH', credentials: 'same-origin', keepalive: true,
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() }, body: payload,
      }).catch(() => undefined)
      void this.flush(true)
      return
    }
    if (Date.now() >= this.disabledUntil) {
      void telemetryApi.updateVisit(current.visitId, JSON.parse(payload)).catch(error => this.temporarilyDisable(error))
    }
  }

  private handleVisibility = () => {
    if (!this.current) return
    this.commitActive()
    if (document.visibilityState === 'hidden') this.heartbeat()
    else this.current.activeSince = performance.now()
  }

  track(eventType: string, options: {
    elementCode?: string; elementName?: string; resultStatus?: string; durationMs?: number;
    errorCode?: string; requestId?: string; context?: EventContext;
  } = {}) {
    const current = this.current
    if (!current || Date.now() < this.disabledUntil) return
    this.queue.push({
      eventId: identifier(), visitId: current.visitId,
      moduleCode: moduleCode(current.route), pageCode: pageCode(current.route),
      routePath: current.route.path, eventType,
      elementCode: options.elementCode, elementName: options.elementName,
      resultStatus: options.resultStatus || 'unknown', durationMs: options.durationMs,
      errorCode: options.errorCode, requestId: options.requestId,
      context: options.context, eventVersion: 1,
      occurredAt: new Date().toISOString(), appVersion: APP_VERSION,
    })
    if (this.queue.length >= 20) void this.flush()
  }

  private captureClick = (event: MouseEvent) => {
    if (!this.current) return
    const path = event.composedPath().filter((item): item is HTMLElement => item instanceof HTMLElement)
    // Page visits and API results are automatic. Element telemetry is deliberately
    // restricted to explicitly marked controls and static tab labels so dynamic
    // business values rendered inside links/buttons are never collected.
    const target = path.find(item => item.matches('[data-telemetry-code], [role="tab"]'))
    if (!target || target.matches(':disabled, [aria-disabled="true"]')) return
    const tabCode = target.getAttribute('aria-controls') || target.getAttribute('id') || 'tab'
    const name = (target.dataset.telemetryName || target.getAttribute('aria-label') || (target.getAttribute('role') === 'tab' ? target.textContent : '') || target.tagName).replace(/\s+/g, ' ').trim().slice(0, 100)
    this.track(target.dataset.telemetryEvent || 'element_click', {
      elementCode: target.dataset.telemetryCode || `tab:${tabCode}`,
      elementName: name || '未命名控件', resultStatus: 'success',
    })
  }

  private captureApiResult = (event: CustomEvent<{ apiPath: string; method: string; statusCode: number; success: boolean; emptyResult: boolean; errorCode: string; durationMs: number }>) => {
    const detail = event.detail
    if (!detail || detail.apiPath.includes('/telemetry/')) return
    this.track(detail.success ? 'query_success' : 'query_failed', {
      elementCode: 'api-request', elementName: detail.apiPath,
      resultStatus: detail.success ? 'success' : 'failed', durationMs: detail.durationMs,
      errorCode: detail.errorCode || undefined,
      context: { apiPath: detail.apiPath, method: detail.method, statusCode: detail.statusCode },
    })
    if (detail.success && detail.emptyResult) {
      this.track('empty_result', {
        elementCode: 'api-request', elementName: detail.apiPath,
        resultStatus: 'empty', durationMs: detail.durationMs,
        context: { apiPath: detail.apiPath, method: detail.method, statusCode: detail.statusCode },
      })
    }
  }

  private async flush(keepalive = false) {
    if (this.flushing || !this.queue.length || Date.now() < this.disabledUntil) return
    this.flushing = true
    const events = this.queue.splice(0, MAX_QUEUE)
    try {
      if (keepalive && getCsrfToken()) {
        await fetch('/api/v1/telemetry/events', {
          method: 'POST', credentials: 'same-origin', keepalive: true,
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
          body: JSON.stringify({ events }),
        })
      } else await telemetryApi.events(events)
    } catch (error) {
      this.temporarilyDisable(error)
    } finally {
      this.flushing = false
      if (this.queue.length >= MAX_QUEUE) void this.flush()
    }
  }
}

let activeTracker: TelemetryTracker | undefined

export function initializeTelemetry(router: Router, getUser: UserProvider) {
  activeTracker = new TelemetryTracker(router, getUser)
  activeTracker.initialize()
}

export function trackTelemetryEvent(eventType: string, options?: Parameters<TelemetryTracker['track']>[1]) {
  activeTracker?.track(eventType, options)
}
