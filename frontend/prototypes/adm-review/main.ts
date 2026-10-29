import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import { createRouter,createMemoryHistory } from 'vue-router'
import 'ant-design-vue/dist/reset.css'
import App from './live/LiveApp.vue'
import AdmCenterView from '../../src/features/adm/AdmCenterView.vue'
import AdmDetailView from '../../src/features/adm/AdmDetailView.vue'
import ReferenceView from './live/ReferenceView.vue'
import '../../src/styles/main.css'
import './live/live.css'
const app = createApp(App)
const router=createRouter({history:createMemoryHistory(),routes:[{path:'/adm/workbench',component:AdmCenterView,meta:{title:'我的工作台',section:'ADM管理',admView:'workbench'}},{path:'/adm/cases',component:AdmCenterView,meta:{title:'ADM台账',section:'ADM管理',admView:'cases'}},{path:'/adm/cases/:caseId',component:AdmDetailView,meta:{title:'ADM详情',section:'ADM管理'}},{path:'/:pathMatch(.*)*',component:ReferenceView,meta:{title:'原系统菜单',section:'接入说明'}}]})
app.use(Antd);app.use(router)
// A new-tab detail link reopens this same offline artifact, never file:///adm or a production route.
document.addEventListener('click',event=>{const anchor=(event.target as Element|null)?.closest('a[target="_blank"]') as HTMLAnchorElement|null;const path=anchor?.getAttribute('href');if(anchor&&path?.startsWith('/adm/')){event.preventDefault();window.open(`${location.href.split('#')[0]}#${path}`,'_blank','noopener')}})
void router.push(location.hash.startsWith('#/adm/')?location.hash.slice(1):'/adm/workbench').then(()=>router.isReady()).then(()=>app.mount('#app'))
