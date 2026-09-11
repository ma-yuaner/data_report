import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  Alert, Avatar, Badge, Breadcrumb, Button, Card, ConfigProvider, Dropdown, Input,
  Layout, List, Menu, Progress, Result, Segmented, Select, Space, Spin, Table, Tabs, Tag,
} from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'

import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)
app.use(createPinia()).use(router)
;[
  Alert, Avatar, Badge, Breadcrumb, Button, Card, ConfigProvider, Dropdown, Input,
  Layout, List, Menu, Progress, Result, Segmented, Select, Space, Spin, Table, Tabs, Tag,
].forEach(component => app.use(component))
app.mount('#app')
