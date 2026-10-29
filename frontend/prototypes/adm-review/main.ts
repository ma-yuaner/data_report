import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import { createRouter,createMemoryHistory } from 'vue-router'
import { createPinia } from 'pinia'
import 'ant-design-vue/dist/reset.css'
import App from './live/LiveApp.vue'
import AdmCenterView from '../../src/features/adm/AdmCenterView.vue'
import AdmDetailView from '../../src/features/adm/AdmDetailView.vue'
import ReferenceView from './live/ReferenceView.vue'
import ResourceGovernanceView from '../../src/views/ResourceGovernanceView.vue'
import GdsRouteGovernanceView from '../../src/views/GdsRouteGovernanceView.vue'
import '../../src/styles/main.css'
import './live/live.css'
const app = createApp(App)
const router=createRouter({history:createMemoryHistory(),routes:[{path:'/adm/workbench',component:AdmCenterView,meta:{title:'我的工作台',section:'ADM管理',admView:'workbench'}},{path:'/adm/cases',component:AdmCenterView,meta:{title:'ADM台账',section:'ADM管理',admView:'cases'}},{path:'/adm/cases/:caseId',component:AdmDetailView,meta:{title:'ADM详情',section:'ADM管理'}},{path:'/:pathMatch(.*)*',component:ReferenceView,meta:{title:'原系统菜单',section:'接入说明'}}]})
router.addRoute({path:'/resource-governance',redirect:'/resource-governance/gds'})
router.addRoute({path:'/resource-governance/gds',component:ResourceGovernanceView,meta:{title:'GDS资源治理',section:'资源治理',governanceLayer:'gds'}})
router.addRoute({path:'/resource-governance/ota',component:ResourceGovernanceView,meta:{title:'OTA渠道质量',section:'资源治理',governanceLayer:'ota'}})
for(const [name,page,title] of [['route-diagnosis','routes','航线配置诊断'],['whitelist','whitelist','白名单管理'],['execution','execution','治理执行'],['review','review','治理复盘']])router.addRoute({path:`/resource-governance/${name}`,component:GdsRouteGovernanceView,meta:{title,section:'资源治理',gdsRoutePage:page}})
for(const [from,to] of [['overview','gds'],['routes','route-diagnosis'],['configurations','route-diagnosis?view=configuration'],['quality','gds'],['whitelist','whitelist'],['events','execution'],['actions','execution?tab=actions'],['review','review']])router.addRoute({path:`/gds-route-governance/${from}`,redirect:`/resource-governance/${to}`})
app.use(createPinia());app.use(Antd);app.use(router)
// A new-tab detail link reopens this same offline artifact, never file:///adm or a production route.
document.addEventListener('click',event=>{const anchor=(event.target as Element|null)?.closest('a[target="_blank"]') as HTMLAnchorElement|null;const path=anchor?.getAttribute('href');if(anchor&&path?.startsWith('/adm/')){event.preventDefault();window.open(`${location.href.split('#')[0]}#${path}`,'_blank','noopener')}})
const requested=location.hash.slice(1)
const defaultRoute=decodeURIComponent(location.pathname).includes('资源治理')?'/resource-governance/gds':'/adm/workbench'
void router.push(/^\/(adm|resource-governance|gds-route-governance)\//.test(requested)?requested:defaultRoute).then(()=>router.isReady()).then(()=>app.mount('#app'))
