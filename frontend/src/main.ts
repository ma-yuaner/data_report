import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  Alert, Avatar, Badge, Breadcrumb, Button, Card, ConfigProvider, Dropdown, Input,
  Layout, List, Menu, Modal, Progress, Result, Segmented, Select, Space, Spin, Switch, Table, Tabs, Tag,
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
  authStore.clear()
  const current = router.currentRoute.value
  if (current.name && current.name !== 'login') {
    void router.replace({ name: 'login', query: { redirect: current.fullPath } })
  }
})
app.use(router)
;[
  Alert, Avatar, Badge, Breadcrumb, Button, Card, ConfigProvider, Dropdown, Input,
  Layout, List, Menu, Modal, Progress, Result, Segmented, Select, Space, Spin, Switch, Table, Tabs, Tag,
].forEach(component => app.use(component))
app.mount('#app')
