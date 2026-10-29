import { reactive } from 'vue'
export const scenarios=[
  {id:'normal',title:'正常样例',note:'查看原筛选、图表、下钻和导出；不产生真实业务操作。'},
  {id:'empty',title:'查询结果为零',note:'返回零条记录，区别于接口失败和数据尚未同步。'},
  {id:'partial',title:'航段数据不完整',note:'仅GDS汇总：保留请求量，航段及查定比为空；OTA及航线不适用。'},
  {id:'error',title:'查询失败与重试',note:'模拟服务不可用；切回正常样例可恢复，不使用旧结果冒充新结果。'},
  {id:'denied',title:'无查询权限',note:'模拟接口拒绝访问；菜单保留用于评审，不代表真实服务端权限。'},
] as const
export const reviewRuntime=reactive({scenario:'normal',revision:0})
export function selectScenario(value:string){if(scenarios.some(item=>item.id===value)){reviewRuntime.scenario=value;reviewRuntime.revision++}}
export function applyScenario(data:any){
  if(reviewRuntime.scenario==='error')throw Error('本机演练：查询服务暂不可用，请切换正常样例后重试')
  if(reviewRuntime.scenario==='denied')throw Error('本机演练：当前身份无权查询；正式权限由服务端校验')
  if(reviewRuntime.scenario==='empty'){
    const clear=(metric:any)=>{for(const key of Object.keys(metric)){if(typeof metric[key]==='number')metric[key]=0;if(/Rate|Ratio|Share/.test(key))metric[key]=null}metric.status='no_records';metric.breach=false;metric.ratioInfinite=false;metric.breachReasons=[];return metric}
    clear(data.summary);if(data.dimension)data.dimension.rows=[];if(data.rows)data.rows=[];data.rowCount=0;data.breachObjectCount=0;data.trend=[];data.apiGroups=[];data.resourceChannels=[];if(data.resourceStructure)for(const key of Object.keys(data.resourceStructure))data.resourceStructure[key]=key==='mpisShare'?null:0
  }
  if(reviewRuntime.scenario==='partial'&&data.dataSource?.key==='gds'){
    const partial=(metric:any)=>Object.assign(metric,{segmentCount:null,segmentMissingRowCount:1,queryToSegmentRatio:null,ratioInfinite:false,excessQueryCount:null,breach:false,breachReasons:[],status:'segment_partial'})
    partial(data.summary);for(const rows of [data.dimension?.rows,data.trend,data.apiGroups,data.resourceChannels])for(const row of rows||[])partial(row);data.segmentDataAvailable=false;data.breachObjectCount=0;data.notes.push('本机演练：航段同步不完整，不输出查定比或超标结论。')
  }
  return data
}
