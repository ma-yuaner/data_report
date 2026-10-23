<template>
  <div class="page-wrap route-governance-page">
    <PageHeader eyebrow="RESOURCE GOVERNANCE" :title="pageMeta.title" :description="pageMeta.description">
      <a-space>
        <a-button v-if="isLiveRouteView" @click="router.push('/resource-governance/gds')"><ApartmentOutlined />返回GDS总览</a-button>
        <a-tag :color="isLiveRouteView ? 'green' : 'orange'">{{ isLiveRouteView ? 'Hive实际数据' : '验收演示 · 假数据' }}</a-tag>
        <a-button v-if="!isLiveRouteView" @click="resetDemo"><ReloadOutlined />重置演示</a-button>
      </a-space>
    </PageHeader>

    <a-alert v-if="isLiveRouteView" class="preview-banner" type="success" show-icon
      message="航线视图已接入Hive日汇总"
      description="直接读取lywz.dws_gds_airroute_day；查询、验价、生单分阶段展示。本表没有出票航段分母，因此本页不计算航线查定比。" />
    <a-alert v-else class="preview-banner" type="warning" show-icon
      message="统一资源治理流程 · 当前页面仍为交互验收数据"
      description="航线视图已经接入真实Hive；配置诊断、白名单、治理执行和效果复盘仍不会触发真实上下线。" />

    <section class="module-nav">
      <button v-for="item in modulePages" :key="item.path" type="button" :class="{ active: page === item.key }" @click="router.push(item.path)">
        <component :is="item.icon" /><span>{{ item.label }}</span><small>{{ item.hint }}</small>
      </button>
    </section>

    <section v-if="page === 'routes'" class="workbench-switch">
      <div><strong>诊断视图</strong><span>先定位航线，再下钻到具体配置组合</span></div>
      <a-segmented v-model:value="diagnosisView" :options="[{ label: '航线视图', value: 'route' }, { label: '配置视图', value: 'configuration' }]" />
    </section>
    <section v-if="page === 'execution'" class="workbench-switch">
      <div><strong>治理工作台</strong><span>异常确认与技术执行使用同一条状态链</span></div>
      <a-segmented v-model:value="executionTab" :options="[{ label: '异常处置', value: 'events' }, { label: '上下线任务', value: 'actions' }]" />
    </section>

    <template v-if="page === 'overview'">
      <section class="metric-grid">
        <article class="metric-card tone-blue"><span>最新有效白名单</span><strong>16,284</strong><small>版本 W202610160430 · 04:30同步</small></article>
        <article class="metric-card tone-red"><span>异常航线 / 配置</span><strong>{{ breachedRouteCount }} / 2</strong><small>按规则分开识别，不混合判断</small></article>
        <article class="metric-card tone-orange"><span>待处置事件</span><strong>{{ store.openEventCount }}</strong><small>P0 1项 · P1 2项</small></article>
        <article class="metric-card tone-cyan"><span>执行中治理任务</span><strong>{{ store.activeActionCount }}</strong><small>待接单、控制中与待恢复</small></article>
      </section>

      <section class="flow-card">
        <div class="section-title"><div><span>CLOSED LOOP</span><h2>航线治理闭环</h2></div><a-tag color="green">流程可交互验收</a-tag></div>
        <div class="flow-track">
          <button v-for="(step, index) in flowSteps" :key="step.title" type="button" @click="router.push(step.path)">
            <b>{{ String(index + 1).padStart(2, '0') }}</b><span><strong>{{ step.title }}</strong><small>{{ step.text }}</small></span><ArrowRightOutlined v-if="index < flowSteps.length - 1" />
          </button>
        </div>
      </section>

      <div class="content-grid">
        <a-card class="panel-card" :bordered="false">
          <div class="section-title"><div><span>RISK ROUTES</span><h2>优先治理航线</h2></div><a-button type="link" @click="router.push('/gds-route-governance/routes')">查看全部</a-button></div>
          <div class="route-list">
            <button v-for="item in riskRoutes.slice(0, 4)" :key="item.id" type="button" @click="openRoute(item)">
              <span class="route-rank">{{ item.route }}</span><span><strong>{{ item.airline }} · {{ item.platform }}</strong><small>{{ item.gdsCode }} / {{ item.pccCode }} · {{ whitelistText(item.whitelistStatus) }}</small></span>
              <span class="route-number"><strong>{{ formatInteger(item.queryToSegmentRatio) }} : 1</strong><small>目标 ≤ 4,000 : 1</small></span><RightOutlined />
            </button>
          </div>
        </a-card>
        <a-card class="panel-card" :bordered="false">
          <div class="section-title"><div><span>EVENT QUEUE</span><h2>今日异常处置</h2></div><a-button type="link" @click="router.push('/gds-route-governance/events')">进入处置台</a-button></div>
          <div class="event-stack">
            <article v-for="event in store.events.slice(0, 3)" :key="event.id">
              <a-tag :color="severityColor(event.severity)">{{ event.severity }}</a-tag>
              <div><strong>{{ event.eventType }}</strong><small>{{ event.target }}</small></div>
              <span>{{ eventStatusText(event.status) }}</span>
            </article>
          </div>
        </a-card>
      </div>
    </template>

    <template v-else-if="page === 'routes'">
      <template v-if="diagnosisView === 'route'">
        <a-card v-if="!hasAnalysisEntry" class="panel-card route-entry-guide" :bordered="false">
          <div class="route-entry-icon"><BranchesOutlined /></div>
          <h2>请从GDS资源治理进入航线诊断</h2>
          <p>航线Hive数据量较大，直接打开本页不会发起查询。请先在GDS资源治理中定位GDS、PCC、平台、站点、资源通道或接口组，再通过“分析此项”带入范围。</p>
          <a-button type="primary" size="large" @click="router.push('/resource-governance/gds')"><ApartmentOutlined />前往GDS资源治理</a-button>
        </a-card>
        <template v-else>
        <a-alert v-if="routeContextTags.length" class="context-tip" type="info" show-icon
          message="已承接GDS资源治理的分析条件" :description="`当前航线查询范围：${routeContextTags.join(' · ')}`" />
        <FilterPanel :instant="false" @reset="resetFilters">
          <label><span>统计日期（完整业务日）</span><a-range-picker v-model:value="dateRange" value-format="YYYY-MM-DD" :allow-clear="false" /></label>
          <label><span>GDS</span><a-select v-model:value="filters.gds" allow-clear placeholder="全部GDS" :options="gdsOptions" /></label>
          <label><span>PCC</span><a-select v-model:value="filters.pcc" allow-clear placeholder="全部PCC" :options="pccOptions" /></label>
          <label><span>平台</span><a-select v-model:value="filters.platform" allow-clear placeholder="全部平台" :options="platformOptions" /></label>
          <label><span>站点</span><a-select v-model:value="filters.site" allow-clear placeholder="全部站点" :options="siteOptions" /></label>
          <label><span>资源通道</span><a-select v-model:value="filters.resourceChannel" allow-clear placeholder="全部通道" :options="resourceChannelOptions" @change="changeResourceChannel" /></label>
          <label><span>接口分组</span><a-select v-model:value="filters.apiGroup" allow-clear placeholder="全部接口组" :options="apiGroupOptions" /></label>
          <label><span>航线</span><a-input v-model:value="filters.route" allow-clear placeholder="例如 HKG-ICN" /></label>
          <label><span>航线/机场/城市/航司</span><a-input v-model:value="filters.keyword" allow-clear placeholder="例如 HKG-ICN / 7C" /></label>
          <template #actions><a-button type="primary" :loading="routeLoading" @click="loadRouteAnalysis"><ReloadOutlined />查询 / 刷新</a-button></template>
        </FilterPanel>

        <a-alert v-if="routeError" class="context-tip" type="error" show-icon message="GDS航线Hive查询失败" :description="routeError" />
        <a-alert v-else-if="routeLoading" class="context-tip route-loading-tip" type="warning" show-icon
          message="正在读取Hive航线数据，预计需要30–60秒"
          description="航线数据量较大，请耐心等待，不要重复刷新或离开当前页面。" />
        <a-alert v-else-if="routeAnalysis && !routeAnalysis.queryReady" class="context-tip" type="info" show-icon
          message="请先选择一个分析范围"
          description="筛选项已经按所选日期加载。为避免无条件扫描航线大表，请选择GDS、PCC、平台、站点、资源通道、接口分组或航线后查询。" />
        <a-alert v-else-if="routeAnalysis" class="context-tip" type="warning" show-icon
          message="接口失败量已接入，错误原因明细仍待数据补充"
          description="当前可按航线查看查询、验价、生单失败量、超时率和变价率；dws_gds_airroute_day暂不包含错误码与标准错误分类，页面不会推测失败原因。" />
        <section v-if="routeAnalysis?.queryReady" class="metric-grid compact">
          <article class="metric-card tone-blue"><span>查询请求量</span><strong>{{ formatInteger(routeAnalysis.summary.searchRequests) }}</strong><small>接口成功率 {{ formatRate(routeAnalysis.summary.searchSuccessRate) }} · 结果成功率 {{ formatRate(routeAnalysis.summary.searchResultSuccessRate) }}</small></article>
          <article class="metric-card tone-cyan"><span>验价请求量</span><strong>{{ formatInteger(routeAnalysis.summary.verifyRequests) }}</strong><small>成功率 {{ formatRate(routeAnalysis.summary.verifySuccessRate) }} · 失败 {{ formatInteger(routeAnalysis.summary.verifyFailure) }}</small></article>
          <article class="metric-card tone-orange"><span>生单请求量</span><strong>{{ formatInteger(routeAnalysis.summary.orderRequests) }}</strong><small>成功率 {{ formatRate(routeAnalysis.summary.orderSuccessRate) }} · 失败 {{ formatInteger(routeAnalysis.summary.orderFailure) }}</small></article>
          <article class="metric-card tone-green"><span>查询资源结构</span><strong>{{ formatInteger(routeAnalysis.summary.mpSearchRequests) }}</strong><small>MP / MPIS / NDC：{{ formatRate(routeAnalysis.summary.mpShare) }} / {{ formatRate(routeAnalysis.summary.mpisShare) }} / {{ formatRate(routeAnalysis.summary.ndcShare) }}</small></article>
        </section>

        <a-card class="panel-card" :bordered="false" :loading="routeLoading">
<div class="section-title"><div><span>ROUTE PERFORMANCE</span><h2>航线接口质量明细</h2><p>按航线、平台/站点、GDS/PCC聚合；点击“分析此项”查看接口阶段与资源通道结构。</p></div><a-space><a-tag color="blue">{{ routeAnalysis?.queryReady ? routeAnalysis.rowCount : 0 }} 个组合</a-tag><a-tag v-if="routeAnalysis?.truncated" color="orange">仅展示前{{ routeAnalysis.resultLimit }}项</a-tag><a-button :loading="routeExporting" :disabled="routeLoading || routeExporting || !routeAnalysis?.queryReady || !routeAnalysis.rows.length || routeScopeChanged" @click="exportRoutes">导出航线名单</a-button></a-space></div>
          <p class="data-footnote">导出已查询范围的全部匹配组合，不限当前分页或页面前500项；默认最多2万项，超限请缩小范围。{{ routeScopeChanged ? '筛选已变更，请先查询再导出。' : '' }}</p>
          <a-table :data-source="routeAnalysis?.rows || []" :pagination="{ pageSize: 10, showSizeChanger: true, pageSizeOptions: ['10', '20', '50'] }" row-key="id" :scroll="{ x: 1900 }">
            <a-table-column title="航线" fixed="left" :width="170"><template #default="{ record }"><button class="link-cell" @click="openLiveRoute(record)"><strong>{{ record.route }}</strong><small>{{ record.depCity || record.depAirport || '—' }} → {{ record.arrCity || record.arrAirport || '—' }}</small></button></template></a-table-column>
            <a-table-column title="平台 / 站点" :width="180"><template #default="{ record }"><strong>{{ record.platform || '—' }}</strong><div class="cell-sub">{{ record.site || '全部站点' }}</div></template></a-table-column>
            <a-table-column title="GDS / PCC" :width="160"><template #default="{ record }"><strong>{{ record.gdsCode || '—' }}</strong><div class="cell-sub">{{ record.pccCode || '—' }}</div></template></a-table-column>
            <a-table-column title="查询阶段" :width="185" align="right"><template #default="{ record }"><strong>{{ formatInteger(record.searchRequests) }}</strong><div class="cell-sub">成功 {{ formatRate(record.searchSuccessRate) }} · 失败 {{ formatInteger(record.searchFailure) }}</div></template></a-table-column>
            <a-table-column title="验价阶段" :width="185" align="right"><template #default="{ record }"><strong>{{ formatInteger(record.verifyRequests) }}</strong><div class="cell-sub">成功 {{ formatRate(record.verifySuccessRate) }} · 失败 {{ formatInteger(record.verifyFailure) }}</div></template></a-table-column>
            <a-table-column title="生单阶段" :width="185" align="right"><template #default="{ record }"><strong>{{ formatInteger(record.orderRequests) }}</strong><div class="cell-sub">成功 {{ formatRate(record.orderSuccessRate) }} · 失败 {{ formatInteger(record.orderFailure) }}</div></template></a-table-column>
            <a-table-column title="普通MP / MPIS / NDC" :width="220"><template #default="{ record }"><div class="share-line"><i :style="{ width: shareWidth(record.mpShare) }" /><i :style="{ width: shareWidth(record.mpisShare) }" /><i :style="{ width: shareWidth(record.ndcShare) }" /></div><div class="share-label">{{ formatRate(record.mpShare) }} / {{ formatRate(record.mpisShare) }} / {{ formatRate(record.ndcShare) }}</div></template></a-table-column>
            <a-table-column title="结果成功率" :width="120" align="right"><template #default="{ record }">{{ formatRate(record.searchResultSuccessRate) }}</template></a-table-column>
            <a-table-column title="查询超时率" :width="115" align="right"><template #default="{ record }">{{ formatRate(record.searchTimeoutRate) }}</template></a-table-column>
            <a-table-column title="平均查询耗时" :width="125" align="right"><template #default="{ record }">{{ formatMilliseconds(record.avgSearchExecuteTime) }}</template></a-table-column>
            <a-table-column title="验价 / 生单变价率" :width="165" align="right"><template #default="{ record }">{{ formatRate(record.verifyPriceChangeRate) }}<div class="cell-sub">{{ formatRate(record.orderPriceChangeRate) }}</div></template></a-table-column>
            <a-table-column title="操作" fixed="right" :width="100"><template #default="{ record }"><a-button type="link" @click="openLiveRoute(record)">分析此项</a-button></template></a-table-column>
          </a-table>
          <a-empty v-if="!routeLoading && !routeError && routeAnalysis && !routeAnalysis.queryReady" description="请选择分析范围后点击“查询 / 刷新”" />
          <a-empty v-else-if="!routeLoading && !routeError && routeAnalysis?.queryReady && !(routeAnalysis.rows.length)" description="所选完整业务日和筛选条件没有航线汇总数据" />
          <div v-if="routeAnalysis" class="data-footnote">数据源：{{ routeAnalysis.source }} · {{ routeAnalysis.table }} · 最近源数据 {{ routeAnalysis.summary.sourceUpdatedAt || '—' }}</div>
        </a-card>
        </template>
      </template>
      <template v-else>
        <a-alert class="context-tip" type="info" show-icon message="配置治理粒度" description="同一航线按乘客人数、行程类型、去程提前天数、回程停留天数和MP/MPIS/NDC拆分，避免整条航线被粗暴下线。" />
        <a-alert class="context-tip" type="warning" show-icon message="配置视图尚未接入正式数据" description="当前只完成优先级1的Hive航线维度；该页仍为交互样板，不能作为上下线依据。" />
        <a-card class="panel-card" :bordered="false">
          <div class="section-title"><div><span>CONFIGURATION UNIT</span><h2>航线配置效率</h2></div><a-radio-group v-model:value="configView" button-style="solid"><a-radio-button value="all">全部</a-radio-button><a-radio-button value="异常">只看异常</a-radio-button></a-radio-group></div>
          <a-table :data-source="visibleConfigurations" :pagination="false" row-key="id" :scroll="{ x: 1450 }">
            <a-table-column title="配置 / 航线" fixed="left" :width="170"><template #default="{ record }"><strong>{{ record.id }}</strong><div class="cell-sub">{{ record.route }} · {{ record.platform }}</div></template></a-table-column>
            <a-table-column title="乘客 / 行程" :width="140"><template #default="{ record }">{{ record.passengerScope }}<div class="cell-sub">{{ record.tripType }}</div></template></a-table-column>
            <a-table-column title="去程 / 回程" :width="150"><template #default="{ record }">{{ record.outboundDays }}<div class="cell-sub">停留 {{ record.returnDays }}</div></template></a-table-column>
            <a-table-column title="通道" data-index="channel" :width="90"><template #default="{ text }"><a-tag :color="text === 'MPIS' ? 'green' : text === 'NDC' ? 'blue' : 'orange'">{{ text }}</a-tag></template></a-table-column>
            <a-table-column title="查询量" data-index="queryCount" :width="120" align="right"><template #default="{ text }">{{ formatInteger(text) }}</template></a-table-column>
            <a-table-column title="航段数" data-index="segmentCount" :width="100" align="right"><template #default="{ text }">{{ formatInteger(text) }}</template></a-table-column>
            <a-table-column title="查定比" :width="125" align="right"><template #default="{ record }"><strong :class="{ danger: record.ratio > 4000 }">{{ formatInteger(record.ratio) }} : 1</strong></template></a-table-column>
            <a-table-column title="成功率" :width="100" align="right"><template #default="{ record }">{{ record.successRate.toFixed(1) }}%</template></a-table-column>
            <a-table-column title="建议动作" data-index="suggestion" :width="260" />
            <a-table-column title="结论" fixed="right" :width="90"><template #default="{ record }"><a-tag :color="record.status === '达标' ? 'green' : record.status === '异常' ? 'red' : 'orange'">{{ record.status }}</a-tag></template></a-table-column>
          </a-table>
        </a-card>
      </template>
    </template>

    <template v-else-if="page === 'quality'">
      <section class="metric-grid compact">
        <article class="metric-card tone-blue"><span>查询成功率</span><strong>97.42%</strong><small>目标 ≥ 98%</small></article>
        <article class="metric-card tone-cyan"><span>验价成功率</span><strong>94.18%</strong><small>较昨日 -0.63%</small></article>
        <article class="metric-card tone-orange"><span>生单成功率</span><strong>91.36%</strong><small>1个接口组低于阈值</small></article>
        <article class="metric-card tone-red"><span>接口超时率</span><strong>1.83%</strong><small>1A_NDC异常贡献最高</small></article>
      </section>
      <a-card class="panel-card" :bordered="false">
        <div class="section-title"><div><span>API QUALITY</span><h2>接口组质量</h2><p>接口质量异常与航线效率异常分别判断，避免误下线。</p></div></div>
        <a-table :data-source="store.quality" :pagination="false" row-key="id">
          <a-table-column title="GDS / PCC"><template #default="{ record }"><strong>{{ record.gdsCode }}</strong><div class="cell-sub">{{ record.pccCode }}</div></template></a-table-column>
          <a-table-column title="接口组 / 平台"><template #default="{ record }"><strong>{{ record.apiGroup }}</strong><div class="cell-sub">{{ record.platform }}</div></template></a-table-column>
          <a-table-column title="查询量" data-index="searchRequests" align="right"><template #default="{ text }">{{ formatInteger(text) }}</template></a-table-column>
          <a-table-column title="查询成功率" align="right"><template #default="{ record }">{{ record.searchSuccessRate.toFixed(1) }}%</template></a-table-column>
          <a-table-column title="验价成功率" align="right"><template #default="{ record }">{{ record.verifySuccessRate.toFixed(1) }}%</template></a-table-column>
          <a-table-column title="生单成功率" align="right"><template #default="{ record }">{{ record.orderSuccessRate.toFixed(1) }}%</template></a-table-column>
          <a-table-column title="超时率" align="right"><template #default="{ record }"><span :class="{ danger: record.timeoutRate > 3 }">{{ record.timeoutRate.toFixed(1) }}%</span></template></a-table-column>
          <a-table-column title="主要失败原因" data-index="topFailure" />
          <a-table-column title="状态"><template #default="{ record }"><a-tag :color="record.status === '正常' ? 'green' : record.status === '异常' ? 'red' : 'orange'">{{ record.status }}</a-tag></template></a-table-column>
        </a-table>
      </a-card>
    </template>

    <template v-else-if="page === 'whitelist'">
      <a-alert class="context-tip" type="info" show-icon message="白名单只读展示" description="第一版只展示最新status=1配置、即将到期和历史失效记录；不直接修改生产白名单。所有异常与工单都保存命中时的白名单版本。" />
      <a-card class="panel-card" :bordered="false">
        <div class="section-title"><div><span>WHITELIST SNAPSHOT</span><h2>最新白名单快照</h2><p>当前演示版本 W202610160430</p></div><a-space><a-tag color="green">有效 4</a-tag><a-tag color="orange">即将到期 1</a-tag></a-space></div>
        <a-table :data-source="store.whitelist" :pagination="false" row-key="id" :scroll="{ x: 1320 }">
          <a-table-column title="白名单ID" data-index="id" fixed="left" :width="130" />
          <a-table-column title="航线 / 航司" :width="140"><template #default="{ record }"><strong>{{ record.route }}</strong><div class="cell-sub">{{ record.airline }}</div></template></a-table-column>
          <a-table-column title="平台 / 站点" :width="210"><template #default="{ record }"><strong>{{ record.platform }}</strong><div class="cell-sub">{{ record.site }}</div></template></a-table-column>
          <a-table-column title="GDS / PCC" :width="170"><template #default="{ record }">{{ record.gdsCode }}<div class="cell-sub">{{ record.pccCode }}</div></template></a-table-column>
          <a-table-column title="开放通道" data-index="channel" :width="130" />
          <a-table-column title="配置数" data-index="configCount" :width="90" align="right" />
          <a-table-column title="有效期" :width="210"><template #default="{ record }">{{ record.effectiveFrom }}<div class="cell-sub">至 {{ record.effectiveTo }}</div></template></a-table-column>
          <a-table-column title="版本" data-index="version" :width="160" />
          <a-table-column title="状态" fixed="right" :width="100"><template #default="{ record }"><a-tag :color="whitelistColor(record.status)">{{ whitelistText(record.status) }}</a-tag></template></a-table-column>
        </a-table>
      </a-card>
    </template>

    <template v-else-if="page === 'execution' && executionTab === 'events'">
      <a-card class="panel-card" :bordered="false">
        <div class="section-title"><div><span>EXCEPTION WORKBENCH</span><h2>异常处置台</h2><p>异常只代表发现问题；数据部确认后生成正式上下线任务。</p></div><a-tag color="orange">待处理 {{ store.openEventCount }}</a-tag></div>
        <a-table :data-source="store.events" :pagination="false" row-key="id" :scroll="{ x: 1500 }">
          <a-table-column title="等级" fixed="left" :width="70"><template #default="{ record }"><a-tag :color="severityColor(record.severity)">{{ record.severity }}</a-tag></template></a-table-column>
          <a-table-column title="异常 / 对象" :width="260"><template #default="{ record }"><strong>{{ record.eventType }}</strong><div class="cell-sub">{{ record.targetType }} · {{ record.target }}</div></template></a-table-column>
          <a-table-column title="实际 / 阈值" :width="180"><template #default="{ record }"><strong class="danger">{{ record.actualValue }}</strong><div class="cell-sub">要求 {{ record.threshold }}</div></template></a-table-column>
          <a-table-column title="命中证据" data-index="evidence" :width="330" />
          <a-table-column title="责任人 / 截止" :width="180"><template #default="{ record }">{{ record.owner }}<div class="cell-sub">{{ record.dueAt }}</div></template></a-table-column>
          <a-table-column title="白名单版本" data-index="whitelistVersion" :width="160" />
          <a-table-column title="状态" :width="110"><template #default="{ record }"><a-tag :color="eventStatusColor(record.status)">{{ eventStatusText(record.status) }}</a-tag></template></a-table-column>
          <a-table-column title="操作" fixed="right" :width="250"><template #default="{ record }"><a-space>
            <a-button v-if="record.status === 'OPEN'" size="small" @click="acknowledge(record.id)">确认</a-button>
            <a-button v-if="['OPEN','ACKNOWLEDGED'].includes(record.status)" size="small" @click="observe(record.id)">观察</a-button>
            <a-button v-if="['ACKNOWLEDGED','OBSERVING'].includes(record.status)" size="small" type="primary" danger @click="createAction(record.id)">生成任务</a-button>
            <a-button v-if="record.status === 'ACTION_PENDING'" size="small" type="link" @click="executionTab = 'actions'">查看任务</a-button>
          </a-space></template></a-table-column>
        </a-table>
      </a-card>
    </template>

    <template v-else-if="page === 'execution' && executionTab === 'actions'">
      <a-alert class="context-tip" type="success" show-icon message="技术执行边界清晰" description="本页演示数据部发出控制指令、技术接单、执行、成功、到期恢复和回执归档。验收操作不会触发生产系统。" />
      <a-card class="panel-card" :bordered="false">
        <div class="section-title"><div><span>ACTION ORDERS</span><h2>上下线任务</h2><p>按按钮依次模拟：接单 → 执行 → 生效 → 到期 → 恢复。</p></div><a-tag color="blue">{{ store.actions.length }} 个任务</a-tag></div>
        <a-table :data-source="store.actions" :pagination="false" row-key="id" :scroll="{ x: 1400 }">
          <a-table-column title="任务编号" fixed="left" data-index="actionNo" :width="180" />
          <a-table-column title="治理对象" :width="250"><template #default="{ record }"><strong>{{ record.target }}</strong><div class="cell-sub">{{ record.targetType }} · 来源 {{ record.eventId }}</div></template></a-table-column>
          <a-table-column title="动作" :width="140"><template #default="{ record }">{{ actionTypeText(record.actionType) }}<div class="cell-sub">第 {{ record.occurrenceNo }} 次</div></template></a-table-column>
          <a-table-column title="控制窗口" :width="210"><template #default="{ record }">{{ record.durationMinutes ? `${record.durationMinutes} 分钟` : '长期关闭' }}<div class="cell-sub">{{ record.plannedEndAt }}</div></template></a-table-column>
          <a-table-column title="技术负责人" data-index="technicalOwner" :width="140" />
          <a-table-column title="回执" :width="150"><template #default="{ record }">{{ record.receiptNo || '—' }}</template></a-table-column>
          <a-table-column title="状态" :width="120"><template #default="{ record }"><a-tag :color="actionStatusColor(record.status)">{{ actionStatusText(record.status) }}</a-tag></template></a-table-column>
          <a-table-column title="操作" fixed="right" :width="150"><template #default="{ record }"><a-button v-if="record.status !== 'RECOVERED'" size="small" type="primary" @click="advanceAction(record.id)">{{ nextActionText(record.status) }}</a-button><span v-else class="done-text"><CheckCircleOutlined /> 已闭环</span></template></a-table-column>
        </a-table>
      </a-card>
    </template>

    <template v-else-if="page === 'review'">
      <section class="metric-grid compact">
        <article class="metric-card tone-blue"><span>治理航线</span><strong>28</strong><small>本月涉及7个平台</small></article>
        <article class="metric-card tone-cyan"><span>无效查询压降</span><strong>18.6%</strong><small>较治理前减少1,284万次</small></article>
        <article class="metric-card tone-green"><span>MPIS迁移量</span><strong>6.42M</strong><small>MPIS占比提升11.3%</small></article>
        <article class="metric-card tone-orange"><span>恢复后复发</span><strong>3</strong><small>进入下一阶梯处置</small></article>
      </section>
      <div class="content-grid review-grid">
        <a-card class="panel-card" :bordered="false">
          <div class="section-title"><div><span>EFFECT CHANGE</span><h2>治理前后对比</h2></div></div>
          <div class="effect-bars">
            <div v-for="item in effectRows" :key="item.label"><span>{{ item.label }}</span><div><i class="before" :style="{ width: `${item.before}%` }" /><i class="after" :style="{ width: `${item.after}%` }" /></div><strong>{{ item.text }}</strong></div>
          </div>
          <div class="legend"><span><i class="before" />治理前</span><span><i class="after" />治理后</span></div>
        </a-card>
        <a-card class="panel-card" :bordered="false">
          <div class="section-title"><div><span>LOOP STATUS</span><h2>闭环结果</h2></div></div>
          <div class="review-status-list">
            <article><span>已恢复并达标</span><strong>{{ recoveredActions }}</strong><small>完成执行、恢复及回执</small></article>
            <article><span>控制已生效</span><strong>{{ appliedActions }}</strong><small>等待控制窗口到期</small></article>
            <article><span>待技术处理</span><strong>{{ pendingActions }}</strong><small>已生成正式控制指令</small></article>
          </div>
        </a-card>
      </div>
    </template>

    <a-drawer v-model:open="routeDrawerOpen" title="航线诊断" width="620">
      <template v-if="selectedLiveRoute">
        <div class="drawer-hero"><div><span>{{ selectedLiveRoute.gdsCode || '—' }} · {{ selectedLiveRoute.pccCode || '—' }}</span><h2>{{ selectedLiveRoute.route }}</h2><p>{{ selectedLiveRoute.platform || '—' }} · {{ selectedLiveRoute.site || '全部站点' }}</p></div><a-tag color="green">Hive实际数据</a-tag></div>
        <div class="drawer-metrics"><article><span>查询请求</span><strong>{{ formatInteger(selectedLiveRoute.searchRequests) }}</strong></article><article><span>验价请求</span><strong>{{ formatInteger(selectedLiveRoute.verifyRequests) }}</strong></article><article><span>生单请求</span><strong>{{ formatInteger(selectedLiveRoute.orderRequests) }}</strong></article></div>
        <a-descriptions bordered :column="2" size="small">
          <a-descriptions-item label="查询接口成功率">{{ formatRate(selectedLiveRoute.searchSuccessRate) }}</a-descriptions-item><a-descriptions-item label="查询结果成功率">{{ formatRate(selectedLiveRoute.searchResultSuccessRate) }}</a-descriptions-item>
          <a-descriptions-item label="验价成功率">{{ formatRate(selectedLiveRoute.verifySuccessRate) }}</a-descriptions-item><a-descriptions-item label="生单成功率">{{ formatRate(selectedLiveRoute.orderSuccessRate) }}</a-descriptions-item>
          <a-descriptions-item label="查询超时率">{{ formatRate(selectedLiveRoute.searchTimeoutRate) }}</a-descriptions-item><a-descriptions-item label="查询缓存率">{{ formatRate(selectedLiveRoute.searchCacheRate) }}</a-descriptions-item>
          <a-descriptions-item label="查询失败量">{{ formatInteger(selectedLiveRoute.searchFailure) }}</a-descriptions-item><a-descriptions-item label="验价失败量">{{ formatInteger(selectedLiveRoute.verifyFailure) }}</a-descriptions-item>
          <a-descriptions-item label="生单失败量">{{ formatInteger(selectedLiveRoute.orderFailure) }}</a-descriptions-item><a-descriptions-item label="验价超时率">{{ formatRate(selectedLiveRoute.verifyTimeoutRate) }}</a-descriptions-item>
          <a-descriptions-item label="生单超时率">{{ formatRate(selectedLiveRoute.orderTimeoutRate) }}</a-descriptions-item><a-descriptions-item label="验价变价率">{{ formatRate(selectedLiveRoute.verifyPriceChangeRate) }}</a-descriptions-item>
          <a-descriptions-item label="直飞方案数">{{ formatInteger(selectedLiveRoute.directFlightCount) }}</a-descriptions-item><a-descriptions-item label="中转方案数">{{ formatInteger(selectedLiveRoute.connectingFlightCount) }}</a-descriptions-item>
          <a-descriptions-item label="最近源数据" :span="2">{{ selectedLiveRoute.sourceUpdatedAt || '—' }}</a-descriptions-item>
        </a-descriptions>
        <div class="drawer-section-title"><strong>资源通道结构</strong><span>按查询请求量计算</span></div>
        <div class="channel-grid">
          <article><span>普通MP</span><strong>{{ formatInteger(selectedLiveRoute.mpSearchRequests) }}</strong><small>{{ formatRate(selectedLiveRoute.mpShare) }}</small></article>
          <article><span>MPIS</span><strong>{{ formatInteger(selectedLiveRoute.mpisSearchRequests) }}</strong><small>{{ formatRate(selectedLiveRoute.mpisShare) }}</small></article>
          <article><span>NDC</span><strong>{{ formatInteger(selectedLiveRoute.ndcSearchRequests) }}</strong><small>{{ formatRate(selectedLiveRoute.ndcShare) }}</small></article>
        </div>
        <a-alert class="drawer-note" type="info" show-icon message="当前下钻边界" description="查询日志没有实际航司字段，且本表没有出票航段分母；首版按航线与接口质量定位，不展示虚假的航司归因和查定比。" />
        <div class="drawer-actions"><a-button @click="routeDrawerOpen = false">关闭</a-button><a-button disabled>配置分析待接入</a-button></div>
      </template>
      <template v-else-if="selectedRoute">
        <div class="drawer-hero"><div><span>{{ selectedRoute.gdsCode }} · {{ selectedRoute.pccCode }}</span><h2>{{ selectedRoute.route }}</h2><p>{{ selectedRoute.airline }} · {{ selectedRoute.platform }} · {{ selectedRoute.site }}</p></div><a-tag :color="riskColor(selectedRoute.riskStatus)">{{ riskText(selectedRoute.riskStatus) }}</a-tag></div>
        <div class="drawer-metrics"><article><span>MP查询量</span><strong>{{ formatInteger(selectedRoute.queryCount) }}</strong></article><article><span>航段数</span><strong>{{ formatInteger(selectedRoute.segmentCount) }}</strong></article><article><span>查定比</span><strong class="danger">{{ formatInteger(selectedRoute.queryToSegmentRatio) }} : 1</strong></article></div>
        <a-descriptions bordered :column="2" size="small">
          <a-descriptions-item label="白名单">{{ whitelistText(selectedRoute.whitelistStatus) }}</a-descriptions-item><a-descriptions-item label="查询成功率">{{ selectedRoute.searchSuccessRate.toFixed(1) }}%</a-descriptions-item>
          <a-descriptions-item label="MP占比">{{ selectedRoute.mpShare }}%</a-descriptions-item><a-descriptions-item label="MPIS占比">{{ selectedRoute.mpisShare }}%</a-descriptions-item>
          <a-descriptions-item label="建议动作" :span="2">{{ selectedRoute.suggestion }}</a-descriptions-item>
        </a-descriptions>
        <div class="drawer-section-title"><strong>高风险配置</strong><span>按该航线继续下钻</span></div>
        <div class="drawer-configs"><article v-for="item in routeConfigurations" :key="item.id"><span><strong>{{ item.id }} · {{ item.channel }}</strong><small>{{ item.passengerScope }} · {{ item.tripType }} · 去程{{ item.outboundDays }}</small></span><span><b :class="{ danger: item.ratio > 4000 }">{{ formatInteger(item.ratio) }} : 1</b><small>{{ item.status }}</small></span></article><a-empty v-if="!routeConfigurations.length" description="当前假数据暂无配置记录" /></div>
        <div class="drawer-actions"><a-button @click="routeDrawerOpen = false">关闭</a-button><a-button type="primary" @click="openConfigurationView">进入配置分析</a-button></div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  AlertOutlined, ApartmentOutlined, ArrowRightOutlined, AuditOutlined, BranchesOutlined,
  CheckCircleOutlined, FileProtectOutlined, ProfileOutlined, ReloadOutlined, RightOutlined,
  SafetyCertificateOutlined, ThunderboltOutlined,
} from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import FilterPanel from '@/components/FilterPanel.vue'
import { fetchGdsRouteAnalysis, exportGdsRouteAnalysis, type GdsRouteScope, type GdsRouteAnalysisData, type GdsRouteMetricRow } from '@/api/resourceGovernance'
import { useGdsRouteGovernanceStore, type GovernanceActionStatus, type GovernanceEventStatus, type RouteMetric, type RouteRiskStatus } from '@/stores/gdsRouteGovernance'

type PageKey = 'overview' | 'routes' | 'configurations' | 'quality' | 'whitelist' | 'events' | 'actions' | 'execution' | 'review'

const route = useRoute()
const router = useRouter()
const store = useGdsRouteGovernanceStore()
const page = computed(() => String(route.meta.gdsRoutePage || 'overview') as PageKey)
const isLiveRouteView = computed(() => page.value === 'routes' && diagnosisView.value === 'route')
const hasAnalysisEntry = computed(() => route.query.entry === 'gds-analysis')
const routeDrawerOpen = ref(false)
const selectedRoute = ref<RouteMetric | null>(null)
const selectedLiveRoute = ref<GdsRouteMetricRow | null>(null)
const diagnosisView = ref<'route' | 'configuration'>(route.query.view === 'configuration' ? 'configuration' : 'route')
const executionTab = ref<'events' | 'actions'>(route.query.tab === 'actions' ? 'actions' : 'events')
const configView = ref<'all' | '异常'>('all')
const dateRange = ref<[string, string] | null>(null)
const filters = reactive({
  gds: undefined as string | undefined,
  pcc: undefined as string | undefined,
  platform: undefined as string | undefined,
  site: undefined as string | undefined,
  resourceChannel: undefined as string | undefined,
  apiGroup: undefined as string | undefined,
  route: undefined as string | undefined,
  keyword: '',
})
const routeAnalysis = ref<GdsRouteAnalysisData | null>(null)
const routeLoading = ref(false)
const routeError = ref('')
const routeExporting = ref(false)
const loadedRouteScope = ref<GdsRouteScope | null>(null)
const currentRouteScope = computed<GdsRouteScope>(() => ({
  startDate: dateRange.value?.[0] || '', endDate: dateRange.value?.[1] || '',
  ...filters, keyword: filters.keyword.trim(),
}))
const routeScopeChanged = computed(() => JSON.stringify(currentRouteScope.value) !== JSON.stringify(loadedRouteScope.value))
const exportRoutes = async () => {
  if (routeLoading.value || routeExporting.value || routeScopeChanged.value || !loadedRouteScope.value) return
  routeExporting.value = true
  try {
    await exportGdsRouteAnalysis({ ...loadedRouteScope.value })
    message.success('航线名单已导出')
  } catch (error) {
    message.error(error instanceof Error ? error.message : '导出失败，请缩小范围后重试')
  } finally { routeExporting.value = false }
}

const pageDefinitions: Record<PageKey, { title: string; description: string }> = {
  overview: { title: 'GDS航线治理', description: '从最新白名单、航线效率和接口质量发现问题，形成可审计的上下线闭环。' },
  routes: { title: '航线配置诊断', description: '先按GDS、PCC、平台、航司和航线定位问题，再下钻具体配置组合。' },
  configurations: { title: '配置分析', description: '在航线下面继续识别乘客、行程、日期区间和接口通道的低效组合。' },
  quality: { title: '接口质量', description: '分别监控查询、验价、生单成功率、超时率和失败原因。' },
  whitelist: { title: '白名单管理', description: '查看最新有效白名单、即将到期配置及历史版本，不直接修改生产配置。' },
  events: { title: '异常处置', description: '确认规则命中证据，选择观察或生成正式治理任务。' },
  actions: { title: '上下线任务', description: '管理技术接单、执行、控制生效、到期恢复及回执记录。' },
  execution: { title: '治理执行', description: '在同一工作台完成异常确认、任务生成、技术执行、恢复和回执归档。' },
  review: { title: '治理复盘', description: '对比治理前后查定比、无效查询、MPIS迁移和异常复发情况。' },
}
const pageMeta = computed(() => pageDefinitions[page.value])
const modulePages = [
  { key: 'gds', label: 'GDS资源治理', hint: '总览与接口质量', path: '/resource-governance/gds', icon: ApartmentOutlined },
  { key: 'ota', label: 'OTA渠道质量', hint: '平台接口质量', path: '/resource-governance/ota', icon: ThunderboltOutlined },
  { key: 'routes', label: '航线配置诊断', hint: '航线到配置', path: '/resource-governance/route-diagnosis', icon: BranchesOutlined },
  { key: 'whitelist', label: '白名单管理', hint: '准入范围', path: '/resource-governance/whitelist', icon: FileProtectOutlined },
  { key: 'execution', label: '治理执行', hint: '异常到回执', path: '/resource-governance/execution', icon: AuditOutlined },
  { key: 'review', label: '治理复盘', hint: '效果追踪', path: '/resource-governance/review', icon: SafetyCertificateOutlined },
] as const
const flowSteps = [
  { title: '白名单同步', text: '确定有效航线和配置版本', path: '/gds-route-governance/whitelist' },
  { title: '指标识别', text: '航线、配置与接口分别计算', path: '/gds-route-governance/routes' },
  { title: '规则命中', text: '生成带证据的异常事件', path: '/gds-route-governance/events' },
  { title: '人工确认', text: '观察、忽略或发起治理', path: '/gds-route-governance/events' },
  { title: '技术执行', text: '下线、限流、迁移和恢复', path: '/gds-route-governance/actions' },
  { title: '效果复盘', text: '压降、迁移与复发分析', path: '/gds-route-governance/review' },
]

const toOptions = (values: string[] = []) => values.map(value => ({ value, label: value }))
const gdsOptions = computed(() => toOptions(routeAnalysis.value?.options.gds))
const pccOptions = computed(() => toOptions(routeAnalysis.value?.options.pcc))
const platformOptions = computed(() => toOptions(routeAnalysis.value?.options.platform))
const siteOptions = computed(() => toOptions(routeAnalysis.value?.options.site))
const resourceChannelOptions = [{ value: 'MP', label: 'MP（含普通MP、NDC）' }, { value: 'MPIS', label: 'MPIS' }]
const apiGroupOptions = computed(() => {
  const values = routeAnalysis.value?.options.apiGroup || []
  const channel = filters.resourceChannel
  return toOptions(!channel ? values : values.filter(value => channel === 'MPIS' ? value.toUpperCase().endsWith('_MPIS') : !value.toUpperCase().endsWith('_MPIS')))
})
const routeContextTags = computed(() => [
  filters.gds && `GDS：${filters.gds}`,
  filters.pcc && `PCC：${filters.pcc}`,
  filters.platform && `平台：${filters.platform}`,
  filters.site && `站点：${filters.site}`,
  filters.resourceChannel && `资源通道：${filters.resourceChannel}`,
  filters.apiGroup && `接口组：${filters.apiGroup}`,
  filters.route && `航线：${filters.route}`,
].filter(Boolean) as string[])
const riskRoutes = computed(() => [...store.routes].filter(item => item.riskStatus !== 'NORMAL').sort((a, b) => b.queryToSegmentRatio - a.queryToSegmentRatio))
const breachedRouteCount = computed(() => store.routes.filter(item => item.riskStatus === 'BREACHED').length)
const visibleConfigurations = computed(() => configView.value === '异常' ? store.configurations.filter(item => item.status === '异常') : store.configurations)
const routeConfigurations = computed(() => selectedRoute.value ? store.configurations.filter(item => item.route === selectedRoute.value?.route) : [])
const recoveredActions = computed(() => store.actions.filter(item => item.status === 'RECOVERED').length)
const appliedActions = computed(() => store.actions.filter(item => ['SUCCEEDED', 'RECOVERY_PENDING'].includes(item.status)).length)
const pendingActions = computed(() => store.actions.filter(item => ['PENDING', 'ACCEPTED', 'EXECUTING'].includes(item.status)).length)
const effectRows = [
  { label: 'HKG-ICN 查定比', before: 92, after: 63, text: '5,740 → 3,930' },
  { label: 'KUL-RGN 无效查询', before: 86, after: 46, text: '-46.2%' },
  { label: 'MP流量占比', before: 78, after: 59, text: '78% → 59%' },
  { label: 'MPIS流量占比', before: 22, after: 48, text: '22% → 48%' },
]

const formatInteger = (value: number) => new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value)
const formatRate = (value: string | number | null | undefined) => value === null || value === undefined || value === '' ? '—' : `${Number(value).toFixed(2)}%`
const formatMilliseconds = (value: string | number | null | undefined) => value === null || value === undefined || value === '' ? '—' : `${new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(Number(value))} ms`
const shareWidth = (value: string | number | null | undefined) => `${Math.max(0, Math.min(100, Number(value || 0)))}%`
const whitelistText = (value: string) => ({ ACTIVE: '有效', EXPIRING: '即将到期', INACTIVE: '已失效' }[value] || value)
const whitelistColor = (value: string) => value === 'ACTIVE' ? 'green' : value === 'EXPIRING' ? 'orange' : 'default'
const riskText = (value: RouteRiskStatus) => ({ NORMAL: '达标', WATCH: '观察', BREACHED: '异常', OFFLINE: '已下线' }[value])
const riskColor = (value: RouteRiskStatus) => ({ NORMAL: 'green', WATCH: 'orange', BREACHED: 'red', OFFLINE: 'default' }[value])
const severityColor = (value: string) => value === 'P0' ? 'red' : value === 'P1' ? 'orange' : 'blue'
const eventStatusText = (value: GovernanceEventStatus) => ({ OPEN: '待处理', ACKNOWLEDGED: '已确认', OBSERVING: '观察中', ACTION_PENDING: '待技术执行', ACTION_APPLIED: '控制已生效', RESOLVED: '已闭环' }[value])
const eventStatusColor = (value: GovernanceEventStatus) => ({ OPEN: 'red', ACKNOWLEDGED: 'blue', OBSERVING: 'orange', ACTION_PENDING: 'purple', ACTION_APPLIED: 'cyan', RESOLVED: 'green' }[value])
const actionStatusText = (value: GovernanceActionStatus) => ({ PENDING: '待接单', ACCEPTED: '已接单', EXECUTING: '执行中', SUCCEEDED: '控制已生效', RECOVERY_PENDING: '待恢复', RECOVERED: '已恢复' }[value])
const actionStatusColor = (value: GovernanceActionStatus) => ({ PENDING: 'orange', ACCEPTED: 'blue', EXECUTING: 'processing', SUCCEEDED: 'cyan', RECOVERY_PENDING: 'purple', RECOVERED: 'green' }[value])
const actionTypeText = (value: string) => ({ RATE_LIMIT: '限流', DISABLE: '临时下线', EXTEND_DISABLE: '延长下线', RESTORE: '恢复上线', ROUTE_TO_MPIS: '迁移MPIS' }[value] || value)
const nextActionText = (value: GovernanceActionStatus) => ({ PENDING: '技术接单', ACCEPTED: '开始执行', EXECUTING: '确认生效', SUCCEEDED: '模拟到期', RECOVERY_PENDING: '确认恢复', RECOVERED: '已闭环' }[value])
const openRoute = (item: RouteMetric) => { selectedLiveRoute.value = null; selectedRoute.value = item; routeDrawerOpen.value = true }
const openLiveRoute = (item: GdsRouteMetricRow) => { selectedRoute.value = null; selectedLiveRoute.value = item; routeDrawerOpen.value = true }
const yesterday = () => {
  const value = new Date()
  value.setDate(value.getDate() - 1)
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}
const loadRouteAnalysis = async () => {
  if (!hasAnalysisEntry.value || !isLiveRouteView.value || !dateRange.value?.[0] || !dateRange.value?.[1]) return
  routeLoading.value = true
  routeError.value = ''
  const scope = { ...currentRouteScope.value }
  try {
    routeAnalysis.value = await fetchGdsRouteAnalysis(scope)
    loadedRouteScope.value = scope
  } catch (error) {
    routeAnalysis.value = null
    routeError.value = error instanceof Error ? error.message : '查询失败，请检查Hive连接与dws_gds_airroute_day数据。'
  } finally {
    routeLoading.value = false
  }
}
const resetFilters = () => {
  filters.gds = undefined; filters.pcc = undefined; filters.platform = undefined
  filters.site = undefined; filters.resourceChannel = undefined; filters.apiGroup = undefined; filters.route = undefined; filters.keyword = ''
  const day = yesterday(); dateRange.value = [day, day]
}
const changeResourceChannel = () => {
  if (!filters.apiGroup || !filters.resourceChannel) return
  const isMpis = filters.apiGroup.toUpperCase().endsWith('_MPIS')
  if ((filters.resourceChannel === 'MPIS') !== isMpis) filters.apiGroup = undefined
}
const resetDemo = () => { store.resetReview(); message.success('演示流程已恢复到初始状态') }
const acknowledge = (id: string) => { store.acknowledgeEvent(id); message.success('异常已确认，操作日志将在正式接口中留痕') }
const observe = (id: string) => { store.observeEvent(id); message.info('已进入观察状态') }
const createAction = (id: string) => { const created = store.createAction(id); if (created) { executionTab.value = 'actions'; message.success('已生成上下线任务') } else message.warning('该事件已有未结束任务') }
const advanceAction = (id: string) => { store.advanceAction(id); message.success('任务状态已更新，可继续点击完成下一步流转') }
const openConfigurationView = () => { diagnosisView.value = 'configuration'; routeDrawerOpen.value = false }

onMounted(() => {
  store.hydrate()
  const queryValue = (key: string) => typeof route.query[key] === 'string' ? String(route.query[key]) : ''
  filters.gds = queryValue('gds') || undefined
  filters.pcc = queryValue('pcc') || undefined
  filters.platform = queryValue('platform') || undefined
  filters.site = queryValue('site') || undefined
  filters.resourceChannel = queryValue('resourceChannel') || undefined
  filters.apiGroup = queryValue('apiGroup') || undefined
  filters.route = queryValue('route') || undefined
  const startDate = queryValue('startDate')
  const endDate = queryValue('endDate')
  const defaultDay = yesterday()
  dateRange.value = startDate && endDate ? [startDate, endDate] : [defaultDay, defaultDay]
  if (hasAnalysisEntry.value) void loadRouteAnalysis()
})
</script>

<style scoped>
.route-governance-page { --ink: #1d2a3d; --muted: #758196; --line: #e5eaf0; --blue: #2f6fde; }
.preview-banner, .context-tip { margin-bottom: 16px; border-radius: 12px; }
.route-entry-guide { min-height: 330px; display: grid; place-items: center; align-content: center; gap: 14px; text-align: center; }
.route-entry-guide h2 { margin: 0; color: var(--ink); font-size: 22px; }
.route-entry-guide p { max-width: 680px; margin: 0 0 8px; color: var(--muted); font-size: 13px; line-height: 1.8; }
.route-entry-icon { width: 58px; height: 58px; display: grid; place-items: center; border-radius: 18px; color: #2f6fde; background: #edf4ff; font-size: 26px; }
.route-loading-tip { border-color: #f2d39b; background: #fff9ed; }
.module-nav { margin-bottom: 18px; padding: 8px; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 6px; border: 1px solid #e4e9ef; border-radius: 16px; background: #fff; box-shadow: 0 8px 30px rgba(33, 52, 78, .04); }
.module-nav button { min-width: 0; padding: 12px 8px; display: grid; grid-template-columns: 25px minmax(0, 1fr); grid-template-rows: auto auto; align-items: center; gap: 2px 7px; border: 0; border-radius: 11px; color: #526076; background: transparent; text-align: left; cursor: pointer; }
.module-nav button:hover { background: #f4f7fb; }
.module-nav button.active { color: #245eb8; background: #edf4ff; box-shadow: inset 0 0 0 1px #d8e6fb; }
.module-nav button :deep(.anticon) { grid-row: 1 / 3; font-size: 17px; }
.module-nav strong, .module-nav span { overflow: hidden; font-size: 12px; font-weight: 650; white-space: nowrap; text-overflow: ellipsis; }
.module-nav small { overflow: hidden; color: #98a3b2; font-size: 9px; white-space: nowrap; text-overflow: ellipsis; }
.workbench-switch { margin: -2px 0 16px; padding: 13px 16px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border: 1px solid #dfe7f1; border-radius: 12px; background: #f8fafd; }
.workbench-switch > div { display: grid; gap: 3px; }
.workbench-switch strong { color: #24354d; font-size: 13px; }
.workbench-switch span { color: #7c899b; font-size: 10px; }
.metric-grid { margin-bottom: 16px; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.metric-card { position: relative; overflow: hidden; min-height: 132px; padding: 20px; display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: 14px; background: #fff; box-shadow: 0 7px 24px rgba(31, 49, 73, .045); }
.metric-card::before { content: ''; width: 4px; position: absolute; inset: 0 auto 0 0; background: var(--tone); }
.metric-card::after { content: ''; width: 96px; height: 96px; position: absolute; right: -38px; top: -38px; border-radius: 50%; background: color-mix(in srgb, var(--tone) 8%, white); }
.metric-card span { color: #6d798d; font-size: 12px; }
.metric-card strong { margin: 10px 0 7px; color: var(--ink); font-size: 28px; line-height: 1; letter-spacing: -.04em; }
.metric-card small { margin-top: auto; color: #99a3b2; font-size: 10px; }
.tone-blue { --tone: #3576dc; }.tone-red { --tone: #d65b65; }.tone-orange { --tone: #e29335; }.tone-cyan { --tone: #2695a7; }.tone-green { --tone: #2e9a76; }
.metric-grid.compact .metric-card { min-height: 118px; }
.flow-card, .panel-card { margin-bottom: 16px; border: 1px solid var(--line); border-radius: 15px; background: #fff; box-shadow: 0 8px 28px rgba(30, 49, 74, .04); }
.flow-card { padding: 20px; }
.section-title { min-height: 40px; margin-bottom: 16px; display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.section-title > div > span { color: #547fc0; font-size: 9px; font-weight: 700; letter-spacing: .16em; }
.section-title h2 { margin: 3px 0 0; color: var(--ink); font-size: 18px; }
.section-title p { margin: 4px 0 0; color: var(--muted); font-size: 11px; }
.flow-track { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); }
.flow-track button { min-width: 0; min-height: 92px; padding: 14px 24px 14px 12px; position: relative; display: flex; align-items: flex-start; gap: 10px; border: 0; border-right: 1px solid #edf0f4; color: inherit; background: transparent; text-align: left; cursor: pointer; }
.flow-track button:last-child { border-right: 0; }
.flow-track button:hover { background: #f7f9fc; }
.flow-track b { width: 25px; height: 25px; flex: none; display: grid; place-items: center; border-radius: 8px; color: #2d69c5; background: #eaf2ff; font-size: 10px; }
.flow-track span { min-width: 0; display: grid; gap: 5px; }
.flow-track strong { color: #29364b; font-size: 12px; }
.flow-track small { color: #8b96a6; font-size: 9px; line-height: 1.5; }
.flow-track :deep(.anticon-arrow-right) { position: absolute; right: 6px; top: 20px; color: #c3cad4; }
.content-grid { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(360px, .75fr); gap: 16px; }
.route-list { display: grid; }
.route-list button { padding: 14px 4px; display: grid; grid-template-columns: 100px minmax(0, 1fr) 145px 20px; align-items: center; gap: 12px; border: 0; border-bottom: 1px solid #edf0f4; color: inherit; background: transparent; text-align: left; cursor: pointer; }
.route-list button:last-child { border-bottom: 0; }.route-list button:hover { background: #f8fafc; }
.route-rank { color: #244d89; font-size: 14px; font-weight: 700; }.route-list button > span { display: grid; gap: 4px; }.route-list small, .cell-sub { color: #8c97a7; font-size: 10px; }.route-number { text-align: right; }.route-number strong { color: #cf4b57; }
.event-stack { display: grid; gap: 9px; }.event-stack article { padding: 13px; display: grid; grid-template-columns: 40px minmax(0, 1fr) auto; align-items: center; gap: 10px; border-radius: 11px; background: #f7f9fc; }.event-stack article div { display: grid; gap: 3px; }.event-stack small { color: #8b96a6; font-size: 10px; }.event-stack article > span:last-child { color: #66758a; font-size: 10px; }
.link-cell { padding: 0; display: grid; gap: 3px; border: 0; color: #265fae; background: transparent; text-align: left; cursor: pointer; }
.danger { color: #cb4754 !important; }.share-line { height: 6px; display: flex; overflow: hidden; border-radius: 8px; background: #eef1f5; }.share-line i:nth-child(1) { background: #eb9b3a; }.share-line i:nth-child(2) { background: #35a481; }.share-line i:nth-child(3) { background: #4b79cf; }.share-label { margin-top: 5px; color: #8995a6; font-size: 9px; }
.data-footnote { margin-top: 14px; padding-top: 12px; border-top: 1px solid #edf0f4; color: #8a96a7; font-size: 10px; text-align: right; }
.done-text { color: #2f8f71; font-size: 11px; }.drawer-hero { margin-bottom: 16px; padding: 18px; display: flex; justify-content: space-between; border-radius: 14px; color: #fff; background: linear-gradient(135deg, #244a7e, #277f8a); }.drawer-hero span { font-size: 10px; opacity: .75; }.drawer-hero h2 { margin: 4px 0; color: #fff; font-size: 26px; }.drawer-hero p { margin: 0; font-size: 11px; opacity: .82; }.drawer-metrics { margin-bottom: 16px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }.drawer-metrics article { padding: 13px; display: grid; gap: 7px; border: 1px solid #e5eaf0; border-radius: 10px; }.drawer-metrics span { color: #8390a2; font-size: 10px; }.drawer-metrics strong { font-size: 16px; }.drawer-section-title { margin: 22px 0 10px; display: flex; justify-content: space-between; }.drawer-section-title span { color: #919cac; font-size: 10px; }.drawer-configs { display: grid; gap: 8px; }.drawer-configs article { padding: 12px; display: flex; justify-content: space-between; border-radius: 10px; background: #f6f8fb; }.drawer-configs article > span { display: grid; gap: 4px; }.drawer-configs small { color: #8d98a8; font-size: 10px; }.drawer-actions { margin-top: 20px; display: flex; justify-content: flex-end; gap: 8px; }
.channel-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }.channel-grid article { padding: 14px; display: grid; gap: 5px; border: 1px solid #e5eaf0; border-radius: 11px; background: #f8fafc; }.channel-grid span, .channel-grid small { color: #8490a2; font-size: 10px; }.channel-grid strong { color: #263650; font-size: 18px; }.drawer-note { margin-top: 16px; border-radius: 10px; }
.effect-bars { display: grid; gap: 18px; }.effect-bars > div { display: grid; grid-template-columns: 120px minmax(0, 1fr) 110px; align-items: center; gap: 12px; color: #657286; font-size: 11px; }.effect-bars > div > div { display: grid; gap: 4px; }.effect-bars i { height: 8px; display: block; border-radius: 8px; }.before { background: #d7dee8; }.after { background: #3a83cc; }.effect-bars strong { text-align: right; }.legend { margin-top: 18px; display: flex; justify-content: flex-end; gap: 15px; color: #8490a2; font-size: 10px; }.legend span { display: flex; align-items: center; gap: 5px; }.legend i { width: 12px; height: 6px; border-radius: 4px; }.review-status-list { display: grid; gap: 10px; }.review-status-list article { padding: 14px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 3px 12px; border-radius: 10px; background: #f7f9fc; }.review-status-list span { color: #657286; font-size: 11px; }.review-status-list strong { grid-row: 1 / 3; grid-column: 2; align-self: center; color: #263650; font-size: 22px; }.review-status-list small { color: #9aa4b3; font-size: 9px; }
@media (max-width: 1280px) { .module-nav { grid-template-columns: repeat(4, 1fr); }.flow-track { grid-template-columns: repeat(3, 1fr); }.flow-track button:nth-child(3) { border-right: 0; }.metric-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 900px) { .content-grid { grid-template-columns: 1fr; }.module-nav { grid-template-columns: repeat(2, 1fr); }.flow-track { grid-template-columns: 1fr; }.flow-track button { border-right: 0; border-bottom: 1px solid #edf0f4; }.metric-grid { grid-template-columns: 1fr; } }
</style>
