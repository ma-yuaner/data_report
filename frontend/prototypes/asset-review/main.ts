import { createApp } from 'vue'
import { Alert, Button, Input, Modal, Select, Table, Tag, Textarea } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import '../../src/styles/main.css'
import '../shared/review.css'
import App from './App.vue'
const app = createApp(App)
for (const component of [Alert, Button, Input, Modal, Select, Table, Tag]) app.use(component)
app.component('ATextarea', Textarea)
app.mount('#app')
