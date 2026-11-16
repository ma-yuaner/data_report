<template>
  <div class="asset-review">
    <header class="review-header"><strong>企业数据中台 / 数据资产</strong><span>设计评审 0.1 · 盘点快照只读 · 未接正式服务</span><a-button @click="showDocs = !showDocs">{{ showDocs ? '收起设计说明' : '设计说明与意见' }}</a-button></header>
    <div class="review-body">
      <main class="workspace" :style="showDocs ? { flexBasis: split + '%' } : undefined">
        <PageHeader eyebrow="" title="数据资产" description="找到数据、理解口径、追踪依赖、补齐治理缺口">
          <a-select v-model:value="role" aria-label="演练角色" style="width: 150px" :options="[{ value: 'reader', label: '查看者（演练）' }, { value: 'manager', label: '维护者（演练）' }]" />
        </PageHeader>
        <a-alert type="info" show-icon message="2026-11-16 盘点快照。1,067个对象、34,431字段；结构已采集，运行血缘及业务新鲜度尚未验证。" />
        <a-alert v-if="!dataset.tables.length" type="warning" message="未载入盘点快照。请使用打包后的评审HTML。" />
        <nav class="module-tabs" aria-label="资产模块导航"><button v-for="item in navigation" :key="item.key" :aria-pressed="page === item.key" :class="{ active: page === item.key }" @click="page = item.key">{{ item.title }}</button></nav>

        <section v-if="page === 'catalog'" class="catalog-layout">
          <aside class="database-tree" aria-label="连接与库"><h2>连接与库</h2><button :class="{ chosen: !database }" @click="setDatabase('')">全部对象 <b>{{ dataset.tables.length }}</b></button><template v-for="source in ['MYSQL', 'ERP_MYSQL', 'HIVE']" :key="source"><h3>{{ source }}</h3><button v-for="db in dataset.databases.filter(item => item.source === source)" :key="db.source + db.database" :class="{ chosen: database === db.source + '/' + db.database }" @click="setDatabase(db.source + '/' + db.database)">{{ db.database }} <b>{{ db.object_count }}</b></button></template><small>仅当前账号可见范围。连接地址与凭据不展示。</small></aside>
          <div class="catalog-main">
            <div class="filters"><label>名称 / 用途<a-input v-model:value="query" allow-clear placeholder="如 order issue，多个词同时匹配" @press-enter="search" /></label><label>分层候选<a-select v-model:value="layer" style="width: 145px" :options="layerOptions" /></label><a-button type="primary" @click="search">查询</a-button><a-button @click="resetFilters">重置</a-button></div>
            <div class="section-heading"><h2>资产目录</h2><span>当前筛选 {{ filtered.length }} 个 / 快照全部 {{ dataset.tables.length }} 个</span></div>
            <a-table :data-source="filtered" :columns="tableColumns" row-key="asset_id" size="small" :pagination="{ current: tablePage, pageSize: 10, showSizeChanger: false, onChange: (value: number) => tablePage = value }" :scroll="{ x: 980 }">
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'name'"><a-button type="link" class="object-link" @click="open(record.asset_id)">{{ record.table }}</a-button><div class="muted">{{ record.source }} / {{ record.database }}</div></template>
                <template v-else-if="column.key === 'layer'"><a-tag>{{ layerLabel(record.layer_candidate) }}</a-tag><small v-if="!['NOT_ASSIGNED', 'UNCLASSIFIED'].includes(record.layer_candidate)">名称推断</small></template>
                <template v-else-if="column.key === 'purpose'">{{ purpose(record) }}<a-tag v-if="drafts[record.asset_id]" color="orange">演练草稿</a-tag></template>
                <template v-else-if="column.key === 'gap'"><a-button type="link" @click="open(record.asset_id); page = 'governance'">{{ assetGaps(record.asset_id).length ? '查看缺口 ' + assetGaps(record.asset_id).length : '未发现已检查项缺口' }}</a-button></template>
              </template>
            </a-table>
            <article v-if="selected && detailOpen" class="detail-panel">
              <div class="section-heading"><div><h2>{{ selected.table }}</h2><small>{{ selected.source }} / {{ selected.database }} · {{ selected.object_type }}</small></div><a-button @click="page = 'lineage'">查看上下游</a-button></div>
              <dl class="metadata"><div><dt>业务用途</dt><dd>{{ purpose(selected) }}</dd></div><div><dt>业务粒度 / 负责人</dt><dd>{{ drafts[selected.asset_id]?.grain || '待确认' }} / {{ drafts[selected.asset_id]?.owner || '待确认' }}</dd></div><div><dt>结构采集时间</dt><dd>{{ displayTime(selected.collected_at) }}</dd></div><div><dt>业务数据更新到</dt><dd>未核验，不以结构采集时间代替</dd></div><div><dt>实例指纹</dt><dd>{{ selected.instance_id }}</dd></div><div><dt>字段 / 分区字段</dt><dd>{{ selected.column_count }} / {{ selected.partition_column_count }}</dd></div></dl>
              <h3>字段字典</h3><a-table :data-source="selectedColumns" :columns="columnColumns" :pagination="{ pageSize: 8, showSizeChanger: false }" row-key="name" size="small" :scroll="{ x: 730 }"><template #bodyCell="{ column, record }"><template v-if="column.key === 'comment'">{{ record.comment || '待补中文含义' }}</template><template v-else-if="column.key === 'partition'">{{ record.is_partition === '1' ? '分区字段' : '普通字段' }}</template><template v-else-if="column.key === 'nullable'">{{ record.nullable || '当前引擎未登记' }}</template></template></a-table>
            </article>
          </div>
        </section>

        <section v-else-if="page === 'lineage'" class="panel">
          <div class="filters"><label>中心对象<a-select v-model:value="selectedId" show-search option-filter-prop="label" style="width: min(560px, 60vw)" :options="objectOptions" /></label><label>证据范围<a-select v-model:value="edgeScope" style="width: 160px" :options="[{ value: 'definition', label: '定义 / 源码证据' }, { value: 'runtime', label: '仅实际运行证据' }]" /></label></div>
          <a-alert type="warning" show-icon message="此图解释已发现的定义依赖。两端对象存在不代表任务运行成功；外键关联不混入加工血缘。" />
          <a-alert v-if="edgeScope === 'runtime'" type="info" message="尚未采集运行证据，不能据此判断没有上下游或变更没有影响。" />
          <template v-else-if="selected">
            <div class="lineage-board"><div><h3>直接上游</h3><button v-for="node in upstreamNodes" :key="node.key" :disabled="!node.id" @click="selectedId = node.id"><strong>{{ node.label }}</strong><small>{{ node.id ? '查看该对象' : '端点未解析 / 未命中' }}</small></button><p v-if="!upstreamNodes.length">当前证据未覆盖上游</p></div><div class="center-node"><small>流向：左侧 → 中心 → 右侧</small><h2>{{ selected.table }}</h2><span>{{ selected.source }} / {{ selected.database }}</span><a-tag>结构已采集</a-tag><small>运行状态未验证</small></div><div><h3>直接下游</h3><button v-for="node in downstreamNodes" :key="node.key" :disabled="!node.id" @click="selectedId = node.id"><strong>{{ node.label }}</strong><small>{{ node.id ? '查看该对象' : '端点未解析 / 未命中' }}</small></button><p v-if="!downstreamNodes.length">当前证据未覆盖下游</p></div></div>
            <div class="section-heading"><h2>潜在下游影响 · 最多5跳</h2><span>已知定义范围内 {{ impacts.length }} 个对象；另有 {{ unresolvedFrontier }} 条未解析前沿证据</span></div><div class="impact-list"><button v-for="item in impacts" :key="item.asset_id" @click="selectedId = item.asset_id">第{{ item.depth }}跳 · {{ assetName(item.asset_id) }}</button><p v-if="!impacts.length">当前已解析证据未找到可遍历下游，不等于已验证无影响。</p></div>
            <h3>当前对象的依赖证据</h3><a-table :data-source="selectedEdges" :columns="edgeColumns" :pagination="{ pageSize: 6 }" :row-key="edgeKey" size="small" :scroll="{ x: 1000 }"><template #bodyCell="{ column, record }"><template v-if="column.key === 'type'">{{ edgeNames[record.edge_type] }}</template><template v-else-if="column.key === 'status'"><a-tag :color="record.endpoint_status === 'both_exist' ? 'blue' : 'orange'">{{ record.endpoint_status === 'both_exist' ? '两端对象已命中' : '端点待核对' }}</a-tag><small>运行未验证</small></template></template></a-table>
          </template>
        </section>

        <section v-else-if="page === 'governance'" class="panel">
          <div class="section-heading"><h2>治理清单</h2><span>类别存在重叠，不能相加作为问题表数</span></div>
          <div class="gap-filters"><button :class="{ chosen: !gapFilter }" @click="gapFilter = ''">全部缺口记录</button><button v-for="(name, key) in gapNames" :key="key" :class="{ chosen: gapFilter === key }" @click="gapFilter = String(key)">{{ name }} {{ dataset.gaps.filter(item => item.gap === key).length }}</button></div>
          <a-alert v-if="role === 'reader'" type="info" message="查看者仅可定位缺口。切换维护者可演练填写字典草稿；角色与保存均为本地模拟。" />
          <a-table :data-source="filteredGaps" :columns="gapColumns" :pagination="{ pageSize: 10 }" :row-key="(row: Gap) => row.gap_id ?? row.asset_id + row.gap + row.detail" size="small" :scroll="{ x: 850 }"><template #bodyCell="{ column, record }"><template v-if="column.key === 'asset'">{{ assetName(record.asset_id) }}</template><template v-else-if="column.key === 'name'">{{ gapNames[record.gap] }}</template><template v-else-if="column.key === 'action'"><a-button type="link" :disabled="!hasAsset(record.asset_id)" @click="open(record.asset_id); page = 'catalog'">定位对象</a-button><a-button type="link" :disabled="role !== 'manager' || !hasAsset(record.asset_id)" @click="edit(record.asset_id)">填写演练草稿</a-button></template></template></a-table>
        </section>

        <section v-else-if="page === 'collection'" class="panel">
          <div class="section-heading"><h2>元数据采集记录</h2><a-button :disabled="role !== 'manager'" @click="collectionScenario = collectionScenario === 'failed' ? 'normal' : 'failed'">{{ collectionScenario === 'failed' ? '恢复正常演练' : '演练采集失败' }}</a-button></div>
          <a-alert v-if="collectionScenario === 'failed'" type="error" show-icon message="演练：最新采集失败，继续展示2026-11-16上一成功快照。失败来源未变为零对象，本页未发起网络请求。" />
          <p>采集完成仅证明结构可读；数据是否按时到达、任务是否运行、业务是否可用分别核验。</p><a-table :data-source="dataset.databases" :columns="collectionColumns" :pagination="false" :row-key="(row: {source:string;database:string}) => row.source + row.database" size="small"><template #bodyCell="{ column, record }"><template v-if="column.key === 'time'">{{ displayTime(record.collected_at) }}</template><template v-else-if="column.key === 'status'"><a-tag :color="collectionScenario === 'failed' ? 'orange' : 'blue'">{{ collectionScenario === 'failed' ? '旧成功快照 · 演练' : '结构已采集' }}</a-tag></template></template></a-table>
        </section>

        <section v-else class="panel"><h2>指标口径与分析资产</h2><p>保留当前正式模块的指标口径、经营用表、历史分析资产与原权限。本轮设计补充表和字段引用，不修改公式。</p><a-table :data-source="retained" :columns="[{title:'原入口',dataIndex:'name'},{title:'设计调整',dataIndex:'change'},{title:'状态',dataIndex:'state'}]" row-key="name" :pagination="false" /><p class="muted">评审不调用正式接口，原指标与任务数量不在此重新计算。后续映射应保留引用原文及口径版本。</p></section>
      </main>
      <PanelDivider v-if="showDocs" v-model="split" :min="50" :max="75" />
      <PrdPanel v-if="showDocs" v-model="docTab" title="数据资产模块 0.1" subtitle="设计建议，尚未进入正式开发" :tabs="[{id:'requirements',title:'需求与规则'},{id:'scenarios',title:'演练与意见'}]">
        <template v-if="docTab === 'requirements'"><article v-for="item in requirements" :key="item.id"><h3>{{ item.id }} · {{ item.title }}</h3><p>{{ item.rule }}</p></article></template>
        <template v-else><h3>建议演练</h3><ol><li>目录选HIVE/lywz，搜索ods_otasearch，打开字段与上下游。</li><li>切到仅运行证据，核对“未采集”提示。</li><li>治理清单定位一个缺表用途对象，切换维护者填写草稿，再切回查看者。</li><li>演练采集失败，确认上一成功快照仍可查看。</li></ol><label>评审意见<a-textarea v-model:value="feedback" :rows="6" placeholder="注明AS编号和希望调整的行为" /></label><a-button @click="exportFeedback">导出本地评审意见</a-button><a-button @click="resetDemo">重置演练</a-button><p>草稿只存本次页面内存，关闭即丢失；意见可导出到本机。没有共享协作或生产审批。</p></template>
      </PrdPanel>
    </div>
    <a-modal v-model:open="editing" title="填写字典演练草稿" ok-text="保存演练草稿" @ok="saveDraft">
      <a-alert type="info" message="只改变本地演练草稿，不覆盖实库注释或盘点缺口统计。" /><p>{{ assetName(editId) }}</p><label class="form-field">业务用途<a-textarea v-model:value="draft.purpose" :rows="3" /></label><label class="form-field">业务粒度<a-input v-model:value="draft.grain" /></label><label class="form-field">负责人（演练文本）<a-input v-model:value="draft.owner" /></label><p v-if="draftError" role="alert" class="error">{{ draftError }}</p>
    </a-modal>
    <div v-if="notice" class="notice" role="status">{{ notice }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import PrdPanel from '../shared/PrdPanel.vue'
import PanelDivider from '../shared/PanelDivider.vue'
import { downstream, edgeNames, emptyDataset, filterAssets, gapNames } from './model'
import type { Asset, Dataset, Edge, Gap } from './model'
import { requirements } from './definition'
const dataset: Dataset = (window as unknown as { __ASSET_REVIEW_DATA__?: Dataset }).__ASSET_REVIEW_DATA__ ?? emptyDataset
const navigation = [{key:'catalog',title:'资产目录'},{key:'lineage',title:'血缘与影响'},{key:'governance',title:'治理清单'},{key:'collection',title:'采集记录'},{key:'retained',title:'指标与分析资产'}]
const page = ref('catalog'), showDocs = ref(false), split = ref(65), docTab = ref('requirements'), role = ref('reader')
const query = ref(''), appliedQuery = ref(''), database = ref(''), layer = ref(''), appliedLayer = ref(''), tablePage = ref(1)
const selectedId = ref(dataset.tables.find(row => row.source === 'HIVE' && row.table === 'ods_otasearch_log_inc')?.asset_id ?? dataset.tables[0]?.asset_id ?? '')
const detailOpen = ref(false)
const selected = computed(() => dataset.tables.find(row => row.asset_id === selectedId.value))
const filtered = computed(() => filterAssets(dataset.tables, appliedQuery.value, database.value, appliedLayer.value))
const selectedColumns = computed(() => dataset.columns.filter(row => row.asset_id === selectedId.value))
const objectOptions = dataset.tables.map(row => ({value:row.asset_id,label:row.source + '/' + row.database + '/' + row.table}))
const edgeScope = ref('definition'), gapFilter = ref(''), collectionScenario = ref('normal')
const selectedEdges = computed(() => dataset.edges.filter(row => row.source_asset_id === selectedId.value || row.target_asset_id === selectedId.value))
const impacts = computed(() => downstream(selectedId.value, dataset.edges))
const unresolvedFrontier = computed(() => { const ids = new Set([selectedId.value, ...impacts.value.map(row => row.asset_id)]); return dataset.edges.filter(row => ids.has(row.source_asset_id) && row.endpoint_status !== 'both_exist').length })
const filteredGaps = computed(() => dataset.gaps.filter(row => !gapFilter.value || row.gap === gapFilter.value))
const assetName = (id: string) => { const row = dataset.tables.find(item => item.asset_id === id); return row ? row.source + '/' + row.database + '/' + row.table : id }
const hasAsset = (id: string) => dataset.tables.some(row => row.asset_id === id)
function neighbors(up: boolean) { const result = new Map<string,{key:string;id:string;label:string}>(); for (const row of selectedEdges.value) { if ((up ? row.target_asset_id : row.source_asset_id) !== selectedId.value) continue; const id = up ? row.source_asset_id : row.target_asset_id; const label = id ? assetName(id) : up ? row.source_reference : row.target_reference; result.set(id || label, { key:id || label, id, label }) } return [...result.values()] }
const upstreamNodes = computed(() => neighbors(true)), downstreamNodes = computed(() => neighbors(false))
const layerLabel = (value: string) => value === 'NOT_ASSIGNED' ? '非数仓分层' : value === 'UNCLASSIFIED' ? '待分类' : value
const layerOptions = [{value:'',label:'全部'},...['ODS','DWD','DWS','ADS','DIM','NOT_ASSIGNED','UNCLASSIFIED'].map(value => ({value,label:layerLabel(value)}))]
const drafts = ref<Record<string,{purpose:string;grain:string;owner:string}>>({}), editing = ref(false), editId = ref(''), draft = ref({purpose:'',grain:'',owner:''}), draftError = ref(''), notice = ref(''), feedback = ref('')
const purpose = (row: Asset) => drafts.value[row.asset_id]?.purpose || (row.table_comment && row.table_comment !== 'VIEW' ? row.table_comment : '待补业务用途')
const assetGaps = (id: string) => dataset.gaps.filter(row => row.asset_id === id)
const displayTime = (value: string) => value ? new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(value)) + '（上海）' : '待确认'
function search() { appliedQuery.value = query.value; appliedLayer.value = layer.value; tablePage.value = 1 }
function setDatabase(value: string) { database.value = value; tablePage.value = 1 }
function resetFilters() { query.value='';appliedQuery.value='';layer.value='';appliedLayer.value='';database.value='';tablePage.value=1 }
function open(id: string) { selectedId.value=id; detailOpen.value=true }
function edit(id: string) { if(role.value !== 'manager')return;editId.value=id;draft.value={...(drafts.value[id] ?? {purpose:'',grain:'',owner:''})};draftError.value='';editing.value=true }
function saveDraft() { if(role.value !== 'manager'){draftError.value='查看者不能维护演练草稿';return} if(!draft.value.purpose.trim()){draftError.value='请填写演练用途，正式必填规则待评审确认';return}drafts.value[editId.value]={...draft.value};editing.value=false;notice.value='已保存本地演练草稿，盘点事实和缺口数量保持原样';setTimeout(()=>notice.value='',5000) }
function exportFeedback() { const blob=new Blob([JSON.stringify({version:'ASSET-REVIEW-0.1',feedback:feedback.value,drafts:drafts.value,scope:'local_design_review_only'},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='数据资产设计0.1_评审意见.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000) }
function resetDemo(){drafts.value={};feedback.value='';collectionScenario.value='normal';role.value='reader';notice.value='演练已重置';setTimeout(()=>notice.value='',3000)}
const edgeKey = (row: Edge) => row.evidence_id ?? row.source_reference + row.target_reference + row.evidence
const tableColumns=[{title:'表 / 视图',key:'name',width:270},{title:'业务用途',key:'purpose',width:300},{title:'分层',key:'layer',width:130},{title:'字段数',dataIndex:'column_count',width:80,align:'right' as const},{title:'治理缺口',key:'gap',width:200}]
const columnColumns=[{title:'字段',dataIndex:'name',width:210},{title:'类型',dataIndex:'type',width:170},{title:'中文含义',key:'comment',width:270},{title:'可空',key:'nullable',width:150},{title:'类别',key:'partition',width:100}]
const edgeColumns=[{title:'上游',dataIndex:'source_reference',width:250},{title:'下游',dataIndex:'target_reference',width:250},{title:'证据类型',key:'type',width:150},{title:'证据位置',dataIndex:'evidence',width:330},{title:'验证状态',key:'status',width:170}]
const gapColumns=[{title:'对象 / 引用',key:'asset',width:330},{title:'缺口',key:'name',width:160},{title:'细节',dataIndex:'detail',width:250},{title:'操作',key:'action',width:230}]
const collectionColumns=[{title:'连接',dataIndex:'source'},{title:'库',dataIndex:'database'},{title:'对象数',dataIndex:'object_count'},{title:'成功采集时间',key:'time'},{title:'结构状态',key:'status'}]
const retained=[{name:'经营用表',change:'纳入完整目录；保留原经营表的业务状态与指标引用',state:'设计保留'},{name:'指标口径',change:'关联表/字段、口径版本和时间定义，保留原公式',state:'设计保留'},{name:'分析资产',change:'关联脚本、SQL资产编号和依赖，不以任务数替代指标数',state:'设计保留'}]
</script>

<style scoped>
.asset-review{min-height:100vh;color:#182235;background:#f2f5f9;font-size:14px}.review-header{display:flex;align-items:center;gap:20px;background:white;border-bottom:1px solid #dbe3ee;padding:14px 24px}.review-header span{flex:1;color:#526176;font-size:13px}.review-body{display:flex;align-items:stretch;min-height:calc(100vh - 65px)}.workspace{flex:1;min-width:0;padding:24px;overflow:hidden}.workspace :deep(.page-header){margin-bottom:16px}.workspace :deep(.page-eyebrow:empty){display:none}.workspace :deep(.ant-table-cell){vertical-align:top;overflow-wrap:anywhere}.workspace :deep(.ant-table-content){scrollbar-width:auto}.module-tabs{display:flex;gap:24px;flex-wrap:wrap;margin:20px 0;border-bottom:1px solid #dbe3ee}.module-tabs button{border:0;border-bottom:2px solid transparent;background:transparent;padding:10px 0;cursor:pointer;color:#526176}.module-tabs .active{color:#1677ff;border-bottom-color:#1677ff}.catalog-layout{display:grid;grid-template-columns:190px minmax(0,1fr);gap:20px}.database-tree,.panel,.detail-panel{background:white;border:1px solid #e0e6ee;border-radius:6px;padding:18px}.database-tree{align-self:start}.database-tree h2,.section-heading h2{font-size:16px;margin:0}.database-tree h3{font-size:12px;color:#526176;margin:20px 0 6px}.database-tree button{width:100%;display:flex;justify-content:space-between;margin:4px 0;border:0;padding:9px 8px;background:transparent;text-align:left;cursor:pointer;border-radius:4px}.database-tree small{display:block;margin-top:20px;color:#64748b;line-height:1.6}.chosen{background:#e6f4ff!important;color:#0958d9}.catalog-main{min-width:0}.filters{display:flex;align-items:flex-end;gap:10px;flex-wrap:wrap;margin-bottom:16px}.filters label{display:grid;gap:7px}.filters label:first-child{flex:1;min-width:200px}.section-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap}.section-heading span,.muted,small{color:#64748b;font-size:12px}small{display:block}.object-link{padding:0;height:auto;white-space:normal;text-align:left}.detail-panel{margin-top:20px}.metadata{display:grid;grid-template-columns:1fr 1fr;gap:16px}.metadata div{min-width:0}.metadata dt{font-size:12px;color:#64748b;margin-bottom:5px}.metadata dd{margin:0;overflow-wrap:anywhere}.lineage-board{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;align-items:start;margin:20px 0;max-height:520px;overflow:auto}.lineage-board button{width:100%;padding:12px;text-align:left;background:white;border:1px solid #dbe3ee;border-radius:5px;margin:0 0 8px;cursor:pointer;overflow-wrap:anywhere}.lineage-board button:disabled{background:#fffbe6;color:#614700;cursor:default}.lineage-board strong{font-weight:500}.lineage-board small{margin-top:6px}.center-node{padding:22px 14px;border:1px solid #91caff;background:#f0f7ff;border-radius:6px;overflow-wrap:anywhere}.center-node h2{font-size:17px;margin:14px 0}.center-node .ant-tag{margin-top:12px}.impact-list,.gap-filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.impact-list button,.gap-filters button{padding:7px 10px;border:1px solid #dbe3ee;border-radius:4px;background:white;cursor:pointer}.form-field{display:grid;gap:6px;margin:16px 0}.error{color:#b42318}.notice{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);padding:12px 20px;background:#182235;color:white;border-radius:5px;z-index:2000}.asset-review :deep(.prd){min-width:280px;max-height:calc(100vh - 65px);position:sticky;top:0}.asset-review :deep(.prd-content){line-height:1.8}.asset-review :deep(.prd-content article){border-bottom:1px solid #e0e6ee;padding:8px 0}.asset-review button:focus-visible{outline:2px solid #1677ff;outline-offset:2px}@media(max-width:1100px){.review-body{display:block}.catalog-layout{grid-template-columns:160px minmax(0,1fr)}.asset-review :deep(.separator){display:none}.asset-review :deep(.prd){position:static;max-height:none;min-width:0}.review-header{flex-wrap:wrap}.lineage-board{grid-template-columns:1fr}.lineage-board .center-node{grid-row:1}}@media(max-width:700px){.workspace{padding:16px}.catalog-layout{display:block}.database-tree{margin-bottom:16px}.database-tree button{display:inline-flex;width:auto;margin-right:8px}.metadata{grid-template-columns:1fr}.module-tabs{gap:16px}}
</style>
