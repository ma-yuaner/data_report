import { createApp } from 'vue'
import { Button, Select, Input, InputNumber, Checkbox, Alert, Tabs, Tag, Modal, DatePicker } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import './style.css'
const app = createApp(App)
for (const component of [Button, Select, Input, InputNumber, Checkbox, Alert, Tabs, Tag, Modal, DatePicker])
  app.use(component)
app.mount('#app')
