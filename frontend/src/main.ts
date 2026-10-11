import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  Alert, Avatar, Badge, Breadcrumb, Button, Card, Checkbox, Col, ConfigProvider,
  DatePicker, Descriptions, Divider, Drawer, Dropdown, Empty, Form, Input,
  InputNumber, Layout, List, Menu, Modal, Pagination, Progress, Radio, Result,
  Row, Segmented, Select, Space, Spin, Steps, Switch, Table, Tabs, Tag, Timeline,
} from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'

import App from './App.vue'
import router from './router'
import { setAuthFailureHandler } from './api/http'
import { useAuthStore } from './stores/auth'
import { initializeTelemetry } from './telemetry/tracker'
import './styles/main.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
initializeTelemetry(router, () => useAuthStore(pinia).user)
setAuthFailureHandler((error) => {
  const authStore = useAuthStore(pinia)
  if (error.code === 'PASSWORD_CHANGE_REQUIRED' && authStore.user) {
    authStore.user.mustChangePassword = true
    void router.replace({ name: 'change-password', query: { first: '1' } })
    return
  }
  if (error.code === 'MENU_FORBIDDEN' && authStore.user) {
    void authStore.fetchMe(true).finally(() => {
      void router.replace({ name: 'home' })
    })
    return
  }
  authStore.clear()
  const current = router.currentRoute.value
  if (current.name && current.name !== 'login') {
    void router.replace({ name: 'login', query: { redirect: current.fullPath } })
  }
})
const refreshAccessOnReturn = () => {
  if (document.visibilityState === 'visible') {
    void useAuthStore(pinia).refreshAccessIfStale().catch(() => undefined)
  }
}
document.addEventListener('visibilitychange', refreshAccessOnReturn)
window.addEventListener('focus', refreshAccessOnReturn)
app.use(router)
;[
  Alert, Avatar, Badge, Breadcrumb, Button, Card, Checkbox, Col, ConfigProvider,
  DatePicker, Descriptions, Divider, Drawer, Dropdown, Empty, Form, Input,
  InputNumber, Layout, List, Menu, Modal, Pagination, Progress, Radio, Result,
  Row, Segmented, Select, Space, Spin, Steps, Switch, Table, Tabs, Tag, Timeline,
].forEach(component => app.use(component))
app.mount('#app')
