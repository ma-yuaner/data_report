import { computed, reactive } from 'vue'
import { definitions } from './all-definitions'
export const guideState=reactive({id:'',title:'ADM工作台',layer:'页面',field:'',component:'AdmCenterView',route:'/adm/workbench'})
export const currentDefinition=computed(()=>definitions.find(item=>item.id===guideState.id))
export { describe } from './semantics'