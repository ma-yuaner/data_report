import { createApp } from 'vue'
import { Layout, Menu, Button, Input, Tag } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import '../../src/styles/main.css'
import '../shared/review.css'
import App from './App.vue'
import './style.css'
const app = createApp(App)
for (const component of [Layout, Menu, Button, Input, Tag]) app.use(component)
app.mount('#app')
