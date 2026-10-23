<template>
  <div class="page-wrap governance-page">
    <PageHeader eyebrow="RESOURCE GOVERNANCE" :title="pageTitle" :description="pageDescription">
      <a-space>
        <a-button v-if="isGds" @click="openRouteDiagnosis"><BranchesOutlined />航线配置诊断</a-button>
        <a-tag color="blue">实际数据 · MySQL ADS</a-tag>
      </a-space>
    </PageHeader>

    <a-alert
      class="source-banner"
      type="info"
      show-icon
      :message="`${data?.source || 'MySQL · sibebid'} · ${data?.table || (isGds ? 'bi_gds_resource_metric_day' : 'bi_ota_gds_request_day')}`"
      :description="`OTA与GDS独立计算，不跨层相加。${data?.summary.sourceUpdatedAt ? ' 数据更新：' + data.summary.sourceUpdatedAt : ''}`"
    />

    <section class="scope-panel">
      <div class="section-heading">
        <div>
          <h2>统计范围</h2>
          <span>默认本月至昨日 · 今日数据待小时表接入</span>
        </div>
        <a-tag color="blue">{{ layerLabel(draft.dataSource) }}</a-tag>
      </div>
      <div class="period-line">
        <a-segmented v-model:value="preset" :options="periodOptions" :disabled="loading" @change="applyPreset" />
        <div class="date-fields">
          <a-date-picker
            v-model:value="draft.startDate"
            :locale="dateLocale"
            value-format="YYYY-MM-DD"
            :allow-clear="false"
            :disabled-date="disabledDailyDate"
            @change="preset = 'custom'"
          />
          <span>至</span>
          <a-date-picker
            v-model:value="draft.endDate"
            :locale="dateLocale"
            value-format="YYYY-MM-DD"
            :allow-clear="false"
            :disabled-date="disabledDailyDate"
            @change="preset = 'custom'"
          />
        </div>
      </div>
      <div class="filter-grid">
        <label
          ><span>平台</span
          ><a-select
            v-model:value="draft.platform"
            allow-clear
            show-search
            placeholder="全部平台"
            :options="selectOptions(data?.options.platform)"
        /></label>
        <label
          ><span>站点</span
          ><a-select
            v-model:value="draft.site"
            allow-clear
            show-search
            placeholder="全部站点"
            :options="selectOptions(data?.options.site)"
        /></label>
        <label v-if="draft.dataSource === 'gds'"
          ><span>GDS</span
          ><a-select
            v-model:value="draft.gds"
            allow-clear
            show-search
            placeholder="全部GDS"
            :options="selectOptions(data?.options.gds)"
        /></label>
        <label v-if="draft.dataSource === 'gds'"
          ><span>PCC</span
          ><a-select
            v-model:value="draft.pcc"
            allow-clear
            show-search
            placeholder="全部PCC"
            :options="selectOptions(data?.options.pcc)"
        /></label>
        <label v-if="draft.dataSource === 'gds'"
          ><span>资源通道</span
          ><a-select
            v-model:value="draft.resourceChannel"
            allow-clear
            placeholder="全部通道"
            :options="resourceChannelOptions"
            @change="changeResourceChannel"
        /></label>
        <label
          ><span>接口分组</span
          ><a-select
            v-model:value="draft.apiGroup"
            allow-clear
            show-search
            placeholder="全部接口分组"
            :options="apiGroupOptions"
            @change="changeApiGroup"
        /></label>
      </div>
      <div class="scope-actions">
        <span>{{ pending ? '筛选条件已变更，点击查询后生效' : `当前为${layerLabel(applied.dataSource)}分析层` }}</span>
        <div>
          <a-switch
            v-model:checked="draft.breachOnly"
            checked-children="只看异常对象"
            un-checked-children="全部对象"
            :disabled="loading"
            @change="applyFilters"
          />
          <a-button :disabled="loading" @click="resetFilters">重置</a-button>
          <a-button
            :disabled="loading || !data?.available"
            :loading="exporting"
            data-telemetry-code="governance-export"
            @click="exportReport"
            ><DownloadOutlined />导出汇报</a-button
          >
          <a-button type="primary" :loading="loading" data-telemetry-code="governance-query" @click="applyFilters"
            >查询</a-button
          >
        </div>
      </div>
    </section>

    <div class="applied-scope">
      <strong>{{ applied.startDate }} 至 {{ applied.endDate }}</strong>
      <div>
        <a-tag color="blue">{{ layerLabel(applied.dataSource) }}</a-tag
        ><a-tag v-for="tag in appliedTags" :key="tag">{{ tag }}</a-tag>
      </div>
    </div>
    <a-alert v-if="error || data?.error" class="state-alert" type="error" show-icon :message="error || data?.error" />
    <a-alert
      v-else-if="isGds && data?.ratioApplicable && data?.summary.status === 'segment_partial'"
      class="state-alert"
      type="warning"
      show-icon
      message="所选范围的航段数只完成了部分同步"
      :description="`仍有 ${integer(data.summary.segmentMissingRowCount)} 条MP总体记录缺少航段数；为避免分母偏小，当前不计算查定比和超额查询。`"
    />
    <a-alert
      v-else-if="isGds && data?.ratioApplicable && data?.available && !data.segmentDataAvailable"
      class="state-alert"
      type="warning"
      show-icon
      message="MP总体航段数尚未完成同步"
      description="请检查bi_gds_resource_metric_day的MP_TOTAL记录；系统不会用PNR数或接口生单成功量替代航段数。"
    />
    <a-alert
      v-else-if="isGds && data?.available && !data.ratioApplicable"
      class="state-alert"
      type="info"
      show-icon
      :message="applied.resourceChannel === 'MPIS' ? '当前为MPIS通道质量分析' : '当前为接口分组质量分析'"
      description="MPIS和接口组只展示查询、验价、生单的请求、成功、失败和成功率；正式查定比只在MP总体口径计算。"
    />
    <a-alert
      v-else-if="!isGds && applied.platform && !hasOtaTarget(data?.summary)"
      class="state-alert"
      type="info"
      show-icon
      message="该平台尚未配置接口成功率目标"
      description="当前继续展示实际成功率，但不会标记达标或异常；配置平台目标后自动生效。"
    />

    <a-spin :spinning="loading" tip="正在查询GDS/OTA资源指标">
      <section class="governance-hero">
        <div class="hero-copy">
          <span
            >{{ layerLabel(applied.dataSource) }} LAYER · {{ data?.period.startDate || applied.startDate }} 至
            {{ data?.period.endDate || applied.endDate }}</span
          >
          <h2>{{ heroTitle }}</h2>
          <p>{{ heroDescription }}</p>
        </div>
        <div v-if="isGdsRatioScope" class="hero-ratio">
          <small>当前查定比</small>
          <strong :class="ratioTone">{{ ratioText(data?.summary) }}</strong>
          <span v-if="data?.targetRatio">目标 ≤ {{ integer(data.targetRatio) }} : 1</span>
          <span v-else>不同GDS按独立目标评估</span>
        </div>
        <div v-else-if="isGds" class="hero-ratio">
          <small>当前分析层级</small>
          <strong>{{ applied.apiGroup || applied.resourceChannel || '接口质量' }}</strong>
          <span>不重复分摊MP总体航段</span>
        </div>
        <div v-else class="hero-ratio">
          <small>渠道分析重点</small>
          <strong>接口链路</strong>
          <span>查询 → 验价 → 生单</span>
        </div>
      </section>

      <div class="kpi-grid">
        <article>
          <span>{{ isGdsRatioScope ? 'MP查询量' : '查询请求量' }}</span
          ><strong>{{ compact(data?.summary.searchRequests) }}</strong
          ><small>{{ isGdsRatioScope ? '已排除MPIS接口分组' : '当前范围的接口调用' }}</small>
        </article>
        <template v-if="isGdsRatioScope">
          <article>
            <span>航段数</span><strong>{{ nullableCount(data?.summary.segmentCount) }}</strong
            ><small>GDS查定比分母</small>
          </article>
          <article>
            <span>超额查询量</span><strong class="orange">{{ nullableCount(data?.summary.excessQueryCount) }}</strong
            ><small>{{ data?.targetRatio ? '查询量 − 航段数 × 目标值' : '选择已配置目标的GDS后计算' }}</small>
          </article>
          <article>
            <span>MPIS查询量</span><strong>{{ compact(data?.resourceStructure.mpisSearchRequests) }}</strong
            ><small>不计入正式查定比分子</small>
          </article>
          <article>
            <span>MPIS查询占比</span><strong>{{ percent(data?.resourceStructure.mpisShare) }}</strong
            ><small>MPIS ÷（MP + MPIS）</small>
          </article>
        </template>
        <template v-else-if="isGds">
          <article>
            <span>查询失败量</span><strong>{{ integer(data?.summary.searchFailure) }}</strong
            ><small>请求量 − 成功量</small>
          </article>
          <article>
            <span>验价请求量</span><strong>{{ integer(data?.summary.verifyRequests) }}</strong
            ><small>当前接口组验价调用</small>
          </article>
        </template>
        <template v-else>
          <article>
            <span>查询成功量</span><strong>{{ integer(data?.summary.searchSuccess) }}</strong
            ><small>成功率 {{ percent(data?.summary.searchSuccessRate) }}</small>
          </article>
          <article>
            <span>验价请求量</span><strong>{{ integer(data?.summary.verifyRequests) }}</strong
            ><small>渠道验价接口调用</small>
          </article>
        </template>
        <article>
          <span>查询成功率</span
          ><strong :class="rateClass(data?.summary, 'search')">{{ percent(data?.summary.searchSuccessRate) }}</strong
          ><small>{{ targetLabel(data?.summary, 'search', `${integer(data?.summary.searchSuccess)} 次成功`) }}</small>
        </article>
        <article>
          <span>验价成功率</span
          ><strong :class="rateClass(data?.summary, 'verify')">{{ percent(data?.summary.verifySuccessRate) }}</strong
          ><small>{{
            targetLabel(data?.summary, 'verify', `${integer(data?.summary.verifyRequests)} 次验价调用`)
          }}</small>
        </article>
        <article>
          <span>生单接口成功</span><strong>{{ integer(data?.summary.orderSuccess) }}</strong
          ><small>{{ isGds ? '接口成功，不等同航段数' : `成功率 ${percent(data?.summary.orderSuccessRate)}` }}</small>
        </article>
      </div>

      <section class="quality-strip">
        <div class="quality-heading">
          <strong>调用质量指标</strong><span>基于汇总基础量重新计算，不平均源表比率</span>
        </div>
        <div class="quality-grid">
          <article>
            <span>查询缓存命中率</span><strong>{{ percent(data?.summary.searchCacheRate) }}</strong>
          </article>
          <article>
            <span>验价缓存命中率</span><strong>{{ percent(data?.summary.verifyCacheRate) }}</strong>
          </article>
          <article>
            <span>平均查询耗时</span><strong>{{ milliseconds(data?.summary.avgSearchExecuteTime) }}</strong>
          </article>
          <article>
            <span>平均验价耗时</span><strong>{{ milliseconds(data?.summary.avgVerifyExecuteTime) }}</strong>
          </article>
          <article>
            <span>验价变价率</span><strong>{{ percent(data?.summary.verifyPriceChangeRate) }}</strong>
          </article>
          <article>
            <span>生单变价率</span><strong>{{ percent(data?.summary.orderPriceChangeRate) }}</strong>
          </article>
        </div>
      </section>

      <a-card v-if="isGds" :bordered="false" class="analysis-panel channel-panel">
        <template #title>
          <div class="panel-title">
            <div><strong>资源通道结构</strong><small>先比较MP与MPIS，再下钻普通MP、NDC或具体MPIS接口组</small></div>
            <a-tag color="blue">GDS → CHANNEL → API GROUP</a-tag>
          </div>
        </template>
        <a-table
          :columns="resourceChannelColumns"
          :data-source="data?.resourceChannels || []"
          row-key="value"
          :pagination="false"
          :scroll="{ x: 1180 }"
          :locale="{ emptyText: '当前范围暂无通道数据' }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'"
              ><div class="resource-name">
                <strong>{{ record.name }}</strong
                ><small>{{ record.value === 'MP' ? '参与查定比' : '独立观察迁移占比' }}</small>
              </div></template
            >
            <template v-else-if="column.key === 'search'">{{ integer(record.searchRequests) }}</template>
            <template v-else-if="column.key === 'share'"
              ><strong>{{ percent(record.queryShare) }}</strong></template
            >
            <template v-else-if="column.key === 'segment'">{{
              record.ratioApplicable ? nullableCount(record.segmentCount) : '不适用'
            }}</template>
            <template v-else-if="column.key === 'ratio'"
              ><strong v-if="record.ratioApplicable" :class="ratioClass(record)">{{ ratioText(record) }}</strong
              ><span v-else>不适用</span></template
            >
            <template v-else-if="column.key === 'searchRate'">{{ percent(record.searchSuccessRate) }}</template>
            <template v-else-if="column.key === 'verifyRate'">{{ percent(record.verifySuccessRate) }}</template>
            <template v-else-if="column.key === 'orderRate'">{{ percent(record.orderSuccessRate) }}</template>
            <template v-else-if="column.key === 'action'"
              ><a-button type="link" size="small" @click="openResourceChannelAnalysis(record)"
                >下钻接口组</a-button
              ></template
            >
          </template>
        </a-table>
      </a-card>

      <a-card v-if="isGds && applied.resourceChannel" :bordered="false" class="analysis-panel api-group-panel">
        <template #title>
          <div class="panel-title">
            <div>
              <strong>{{ applied.resourceChannel }}接口分组调用质量</strong
              ><small
                >{{
                  applied.resourceChannel === 'MP' ? '普通MP与NDC属于MP的下一级' : '仅展示MPIS接口组'
                }}；成功与失败均由基础量重算</small
              >
            </div>
            <a-tag color="purple">API GROUP</a-tag>
          </div>
        </template>
        <a-table
          :columns="apiGroupColumns"
          :data-source="data?.apiGroups || []"
          row-key="value"
          :pagination="{ pageSize: 20, showTotal: (total: number) => `共 ${total} 个接口组` }"
          :scroll="{ x: 1900 }"
          :locale="{ emptyText: '当前范围暂无接口分组数据' }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'"
              ><div class="resource-name">
                <strong>{{ record.name }}</strong
                ><small>接口分组</small>
              </div></template
            >
            <template v-else-if="column.key === 'searchRequest'">{{ integer(record.searchRequests) }}</template>
            <template v-else-if="column.key === 'searchSuccess'">{{ integer(record.searchSuccess) }}</template>
            <template v-else-if="column.key === 'searchFailure'">{{ integer(record.searchFailure) }}</template>
            <template v-else-if="column.key === 'searchRate'">{{ percent(record.searchSuccessRate) }}</template>
            <template v-else-if="column.key === 'searchFailureRate'">{{ percent(record.searchFailureRate) }}</template>
            <template v-else-if="column.key === 'verifyRequest'">{{ integer(record.verifyRequests) }}</template>
            <template v-else-if="column.key === 'verifySuccess'">{{ integer(record.verifySuccess) }}</template>
            <template v-else-if="column.key === 'verifyFailure'">{{ integer(record.verifyFailure) }}</template>
            <template v-else-if="column.key === 'verifyRate'">{{ percent(record.verifySuccessRate) }}</template>
            <template v-else-if="column.key === 'verifyFailureRate'">{{ percent(record.verifyFailureRate) }}</template>
            <template v-else-if="column.key === 'orderRequest'">{{ integer(record.orderRequests) }}</template>
            <template v-else-if="column.key === 'orderSuccess'">{{ integer(record.orderSuccess) }}</template>
            <template v-else-if="column.key === 'orderFailure'">{{ integer(record.orderFailure) }}</template>
            <template v-else-if="column.key === 'orderRate'">{{ percent(record.orderSuccessRate) }}</template>
            <template v-else-if="column.key === 'orderFailureRate'">{{ percent(record.orderFailureRate) }}</template>
            <template v-else-if="column.key === 'action'"
              ><a-button type="link" size="small" @click="openApiGroupAnalysis(record)">分析此项</a-button></template
            >
          </template>
        </a-table>
      </a-card>

      <div class="charts-grid">
        <a-card :bordered="false" class="analysis-panel">
          <template #title
            ><div class="panel-title">
              <div>
                <strong>{{ isGdsRatioScope ? 'MP查询量与查定比趋势' : '请求量与接口成功率趋势' }}</strong
                ><small>{{ isGdsRatioScope ? '按日汇总基础数量后重新计算' : '按日观察接口调用质量' }}</small>
              </div>
              <a-tag>{{ layerLabel(applied.dataSource) }}</a-tag>
            </div></template
          >
          <BaseChart
            v-if="data?.available && data.trend.length"
            :option="trendOption"
            :chart-label="isGdsRatioScope ? 'GDS MP查询量与查定比日趋势' : '接口请求量与成功率日趋势'"
          />
          <a-empty v-else description="所选范围暂无趋势数据" />
        </a-card>
        <a-card :bordered="false" class="analysis-panel">
          <template #title
            ><div class="panel-title">
              <div>
                <strong>接口调用规模与成功情况</strong><small>各接口独立统计，不作为同一批请求的转化漏斗</small>
              </div>
            </div></template
          >
          <div class="funnel-list">
            <div v-for="stage in funnel" :key="stage.label" class="funnel-row">
              <div>
                <span>{{ stage.label }}</span
                ><strong>{{ nullableCount(stage.value) }}</strong>
              </div>
              <a-progress :percent="stage.percent" :show-info="false" :stroke-color="stage.color" />
              <small>{{ stage.note }}</small>
            </div>
          </div>
        </a-card>
      </div>

      <a-card :bordered="false" class="analysis-panel dimension-panel">
        <template #title>
          <div class="dimension-header">
            <div>
              <strong>{{ applied.groupBy === 'combination' ? '四维组合超标观察榜' : '维度资源对比' }}</strong
              ><small>{{
                applied.breachOnly
                  ? `仅显示超过治理目标的异常对象，共 ${integer(data?.breachObjectCount)} 项`
                  : `${applied.groupBy === 'combination' ? '默认按超额查询量降序；当前榜单' : '默认按查询请求量降序，当前'}有 ${integer(data?.breachObjectCount)} 项超过治理目标`
              }}</small>
            </div>
            <a-segmented
              v-model:value="draftGroup"
              :options="dimensionOptions"
              :disabled="loading"
              data-telemetry-code="governance-dimension"
              @change="changeDimension"
            />
          </div>
        </template>
        <a-alert
          v-if="applied.groupBy === 'combination'"
          type="info"
          show-icon
          class="state-alert"
          message="当前仅四维组合，不是航线榜；超标待人工核对，不代表应关闭。"
          :description="`日数据截至${data?.period.endDate || applied.endDate}；${data?.dimension.truncated ? '结果超过500项，仅展示排序前500项，请缩小筛选范围。' : '最多展示500项，导出与当前查询榜单范围一致。'} 航线分母、预定归属和换配关联待补数据。`"
        />
        <a-table
          :columns="dimensionColumns"
          :data-source="data?.dimension.rows || []"
          row-key="value"
          :pagination="{
            pageSize: 20,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (total: number) => `共 ${total} 项`,
          }"
          :scroll="{ x: applied.groupBy === 'combination' ? 2050 : 1120 }"
          :locale="{ emptyText: '所选维度暂无数据' }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="['gds', 'pcc', 'platform', 'site'].includes(column.key)">{{
              record[column.key] || '未知编码'
            }}</template>
            <template v-else-if="column.key === 'quality'">{{
              !record.preciseScope
                ? '缺编码，不能精准定位'
                : ['ready', 'denominator_zero'].includes(record.status)
                  ? '同步标记正常，批次待核验'
                  : '航段未完整同步'
            }}</template>
            <template v-else-if="column.key === 'name'"
              ><div class="resource-name">
                <strong>{{ record.name }}</strong
                ><small>{{ data?.dimension.label }}</small>
              </div></template
            >
            <template v-else-if="column.key === 'ratio'"
              ><strong :class="ratioClass(record)">{{ ratioText(record) }}</strong></template
            >
            <template v-else-if="column.key === 'target'"
              >{{ record.targetRatio == null ? '未配置' : `${integer(record.targetRatio)} : 1`
              }}<small v-if="record.targetSource" style="display: block">{{ record.targetSource }}</small></template
            >
            <template v-else-if="column.key === 'search'">{{ integer(record.searchRequests) }}</template>
            <template v-else-if="column.key === 'searchSuccess'">{{ integer(record.searchSuccess) }}</template>
            <template v-else-if="column.key === 'segment'">{{ nullableCount(record.segmentCount) }}</template>
            <template v-else-if="column.key === 'excess'">{{ nullableCount(record.excessQueryCount) }}</template>
            <template v-else-if="column.key === 'searchRate'"
              ><strong :class="rateClass(record, 'search')">{{ percent(record.searchSuccessRate) }}</strong></template
            >
            <template v-else-if="column.key === 'verifyRate'"
              ><strong :class="rateClass(record, 'verify')">{{ percent(record.verifySuccessRate) }}</strong></template
            >
            <template v-else-if="column.key === 'verify'">{{ integer(record.verifyRequests) }}</template>
            <template v-else-if="column.key === 'orderRate'"
              ><strong :class="rateClass(record, 'order')">{{ percent(record.orderSuccessRate) }}</strong></template
            >
            <template v-else-if="column.key === 'successTarget'">{{ otaTargetSummary(record) }}</template>
            <template v-else-if="column.key === 'order'">{{ integer(record.orderRequests) }}</template>
            <template v-else-if="column.key === 'breach'"
              ><a-tag :color="record.breach ? 'red' : 'default'">{{ breachText(record) }}</a-tag></template
            >
            <template v-else-if="column.key === 'action'"
              ><a-button
                type="link"
                size="small"
                :disabled="applied.groupBy === 'combination' && !record.preciseScope"
                @click="openAnalysis(record)"
                >分析此项</a-button
              ></template
            >
          </template>
        </a-table>
      </a-card>
    </a-spin>

    <div class="notes">
      <InfoCircleOutlined />
      <div>
        <strong>当前版本边界</strong>
        <p v-for="note in data?.notes || []" :key="note">{{ note }}</p>
      </div>
    </div>

    <a-drawer v-model:open="drawerOpen" width="1080" :title="drawerTitle">
      <template #extra>
        <a-space>
          <a-button v-if="analysisScope.dataSource === 'gds'" type="link" @click="openAnalysisRoutes()"
            ><BranchesOutlined />按当前条件查看航线</a-button
          >
          <a-button v-if="analysisHistory.length > 1" type="link" @click="backAnalysis">返回上一级</a-button>
        </a-space>
      </template>
      <a-alert v-if="drawerError" class="state-alert" type="error" show-icon :message="drawerError" />
      <a-spin :spinning="drawerLoading" tip="正在分析该资源">
        <div class="drawer-scope">
          <span>{{ analysisData?.period.startDate }} 至 {{ analysisData?.period.endDate }}</span>
          <div>
            <a-tag color="blue">{{ layerLabel(applied.dataSource) }}</a-tag
            ><a-tag v-for="tag in analysisScopeTags" :key="tag">{{ tag }}</a-tag>
          </div>
        </div>
        <div class="drawer-kpis">
          <article>
            <span>查询量</span><strong>{{ integer(analysisData?.summary.searchRequests) }}</strong>
          </article>
          <template v-if="analysisIsGdsRatioScope">
            <article>
              <span>航段数</span><strong>{{ nullableCount(analysisData?.summary.segmentCount) }}</strong>
            </article>
            <article>
              <span>查定比</span
              ><strong :class="ratioClass(analysisData?.summary)">{{ ratioText(analysisData?.summary) }}</strong>
            </article>
            <article>
              <span>超额查询</span><strong>{{ nullableCount(analysisData?.summary.excessQueryCount) }}</strong>
            </article>
          </template>
          <template v-else>
            <article>
              <span>查询成功</span><strong>{{ integer(analysisData?.summary.searchSuccess) }}</strong>
            </article>
            <article>
              <span>验价成功</span><strong>{{ integer(analysisData?.summary.verifySuccess) }}</strong>
            </article>
            <article>
              <span>生单成功</span><strong>{{ integer(analysisData?.summary.orderSuccess) }}</strong>
            </article>
          </template>
        </div>
        <div class="analysis-switch">
          <a-segmented v-model:value="analysisView" :options="analysisViewOptions" @change="changeAnalysisView" />
        </div>
        <template v-if="analysisView === 'dimension'">
          <div class="analysis-toolbar">
            <div><strong>继续定位问题维度</strong><small>当前条件会一直保留，选择下一层维度继续下钻</small></div>
            <a-segmented
              v-if="analysisDimensionOptions.length"
              v-model:value="analysisGroup"
              :options="analysisDimensionOptions"
              @change="changeAnalysisDimension"
            />
            <a-tag v-else color="green">已到当前汇总表最细维度</a-tag>
          </div>
          <a-table
            class="daily-table"
            :columns="analysisDimensionColumns"
            :data-source="analysisData?.dimension.rows || []"
            row-key="value"
            :pagination="{ pageSize: 20, showTotal: (total: number) => `共 ${total} 项` }"
            :scroll="{ x: 1120 }"
            :locale="{ emptyText: '当前条件下暂无可继续分析的数据' }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'"
                ><div class="resource-name">
                  <strong>{{ record.name }}</strong
                  ><small>{{ analysisData?.dimension.label }}</small>
                </div></template
              >
              <template v-else-if="column.key === 'ratio'"
                ><strong :class="ratioClass(record)">{{ ratioText(record) }}</strong></template
              >
              <template v-else-if="column.key === 'target'">{{
                record.targetRatio == null ? '未配置' : `${integer(record.targetRatio)} : 1`
              }}</template>
              <template v-else-if="column.key === 'search'">{{ integer(record.searchRequests) }}</template>
              <template v-else-if="column.key === 'searchSuccess'">{{ integer(record.searchSuccess) }}</template>
              <template v-else-if="column.key === 'segment'">{{ nullableCount(record.segmentCount) }}</template>
              <template v-else-if="column.key === 'excess'">{{ nullableCount(record.excessQueryCount) }}</template>
              <template v-else-if="column.key === 'searchRate'"
                ><strong :class="rateClass(record, 'search')">{{ percent(record.searchSuccessRate) }}</strong></template
              >
              <template v-else-if="column.key === 'verifyRate'"
                ><strong :class="rateClass(record, 'verify')">{{ percent(record.verifySuccessRate) }}</strong></template
              >
              <template v-else-if="column.key === 'verify'">{{ integer(record.verifyRequests) }}</template>
              <template v-else-if="column.key === 'orderRate'"
                ><strong :class="rateClass(record, 'order')">{{ percent(record.orderSuccessRate) }}</strong></template
              >
              <template v-else-if="column.key === 'successTarget'">{{ otaTargetSummary(record) }}</template>
              <template v-else-if="column.key === 'order'">{{ integer(record.orderRequests) }}</template>
              <template v-else-if="column.key === 'breach'"
                ><a-tag :color="record.breach ? 'red' : 'default'">{{ breachText(record) }}</a-tag></template
              >
              <template v-else-if="column.key === 'action'"
                ><a-button
                  type="link"
                  size="small"
                  @click="hasNextAnalysisDimension ? continueAnalysis(record) : openAnalysisRoutes(record)"
                  >{{ hasNextAnalysisDimension ? '继续分析' : '查看航线' }}</a-button
                ></template
              >
            </template>
          </a-table>
        </template>
        <a-table
          v-else-if="analysisView === 'daily'"
          class="daily-table"
          :columns="analysisDailyColumns"
          :data-source="analysisData?.trend || []"
          row-key="date"
          :pagination="{ pageSize: 20 }"
          :scroll="{ x: 880 }"
          :locale="{ emptyText: '该资源暂无每日数据' }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'search'">{{ integer(record.searchRequests) }}</template>
            <template v-else-if="column.key === 'searchSuccess'"
              >{{ integer(record.searchSuccess) }} / {{ percent(record.searchSuccessRate) }}</template
            >
            <template v-else-if="column.key === 'segment'">{{ nullableCount(record.segmentCount) }}</template>
            <template v-else-if="column.key === 'ratio'"
              ><strong :class="ratioClass(record)">{{ ratioText(record) }}</strong></template
            >
            <template v-else-if="column.key === 'verify'"
              >{{ integer(record.verifyRequests) }} / {{ percent(record.verifySuccessRate) }}</template
            >
            <template v-else-if="column.key === 'order'"
              >{{ integer(record.orderSuccess) }} / {{ percent(record.orderSuccessRate) }}</template
            >
            <template v-else-if="column.key === 'excess'">{{ nullableCount(record.excessQueryCount) }}</template>
          </template>
        </a-table>
        <template v-else>
          <a-alert
            class="state-alert"
            type="info"
            show-icon
            message="已把当前分析条件带入Hive航线数据"
            description="航线数据直接读取lywz.dws_gds_airroute_day；保留日期、GDS、PCC、平台、站点、资源通道和接口分组。"
          />
          <a-alert
            v-if="analysisRouteError"
            class="state-alert"
            type="error"
            show-icon
            message="航线数据查询失败"
            :description="analysisRouteError"
          />
          <a-spin :spinning="analysisRouteLoading" tip="正在查询Hive航线数据">
            <div v-if="analysisRouteData?.queryReady" class="drawer-kpis">
              <article>
                <span>查询请求量</span><strong>{{ integer(analysisRouteData.summary.searchRequests) }}</strong>
              </article>
              <article>
                <span>查询成功率</span><strong>{{ percent(analysisRouteData.summary.searchSuccessRate) }}</strong>
              </article>
              <article>
                <span>验价成功率</span><strong>{{ percent(analysisRouteData.summary.verifySuccessRate) }}</strong>
              </article>
              <article>
                <span>生单成功率</span><strong>{{ percent(analysisRouteData.summary.orderSuccessRate) }}</strong>
              </article>
            </div>
            <a-table
              class="daily-table"
              :columns="analysisRouteColumns"
              :data-source="analysisRouteData?.rows || []"
              row-key="id"
              :pagination="{
                pageSize: 10,
                showSizeChanger: true,
                showTotal: (total: number) => `共 ${total} 个航线组合`,
              }"
              :scroll="{ x: 1120 }"
              :locale="{ emptyText: analysisRouteLoading ? '正在查询航线数据' : '当前条件下没有航线数据' }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'route'"
                  ><div class="resource-name">
                    <strong>{{ record.route }}</strong
                    ><small
                      >{{ record.depCity || record.depAirport || '—' }} →
                      {{ record.arrCity || record.arrAirport || '—' }}</small
                    >
                  </div></template
                >
                <template v-else-if="column.key === 'platform'"
                  ><div class="resource-name">
                    <strong>{{ record.platform || '—' }}</strong
                    ><small>{{ record.site || '全部站点' }}</small>
                  </div></template
                >
                <template v-else-if="column.key === 'gds'"
                  ><div class="resource-name">
                    <strong>{{ record.gdsCode || '—' }}</strong
                    ><small>{{ record.pccCode || '—' }}</small>
                  </div></template
                >
                <template v-else-if="column.key === 'search'">{{ integer(record.searchRequests) }}</template>
                <template v-else-if="column.key === 'searchRate'">{{ percent(record.searchSuccessRate) }}</template>
                <template v-else-if="column.key === 'verifyRate'">{{ percent(record.verifySuccessRate) }}</template>
                <template v-else-if="column.key === 'orderRate'">{{ percent(record.orderSuccessRate) }}</template>
                <template v-else-if="column.key === 'failure'"
                  >{{ integer(record.searchFailure) }} / {{ integer(record.verifyFailure) }} /
                  {{ integer(record.orderFailure) }}</template
                >
                <template v-else-if="column.key === 'action'"
                  ><a-button type="link" size="small" @click="openAnalysisRoute(record)">继续分析</a-button></template
                >
              </template>
            </a-table>
            <div class="drawer-route-actions">
              <span>当前展示 {{ integer(analysisRouteData?.rowCount) }} 个航线组合</span>
              <a-button type="primary" @click="openAnalysisRoutes()"><BranchesOutlined />进入完整航线诊断</a-button>
            </div>
          </a-spin>
        </template>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { BranchesOutlined, DownloadOutlined, InfoCircleOutlined } from '@ant-design/icons-vue'
import BaseChart from '@/components/BaseChart.vue'
import PageHeader from '@/components/PageHeader.vue'
import { useResourceGovernance } from './useResourceGovernance'
import { analysisRouteColumns, apiGroupColumns, resourceChannelColumns } from './columns'
import {
  compact,
  hasOtaTarget,
  integer,
  milliseconds,
  nullableCount,
  otaTargetSummary,
  percent,
  rateClass,
  ratioText,
  targetLabel,
} from './formatters'

const {
  analysisDailyColumns,
  analysisData,
  analysisDimensionColumns,
  analysisDimensionOptions,
  analysisGroup,
  analysisHistory,
  analysisIsGdsRatioScope,
  analysisRouteData,
  analysisRouteError,
  analysisRouteLoading,
  analysisScope,
  analysisScopeTags,
  analysisView,
  analysisViewOptions,
  apiGroupOptions,
  applied,
  appliedTags,
  applyFilters,
  applyPreset,
  backAnalysis,
  breachText,
  changeAnalysisDimension,
  changeAnalysisView,
  changeApiGroup,
  changeDimension,
  changeResourceChannel,
  continueAnalysis,
  data,
  dimensionColumns,
  dimensionOptions,
  disabledDailyDate,
  draft,
  draftGroup,
  drawerError,
  drawerLoading,
  drawerOpen,
  drawerTitle,
  error,
  exportReport,
  exporting,
  funnel,
  hasNextAnalysisDimension,
  heroDescription,
  heroTitle,
  isGds,
  isGdsRatioScope,
  layerLabel,
  loading,
  openAnalysis,
  openAnalysisRoute,
  openAnalysisRoutes,
  openApiGroupAnalysis,
  openResourceChannelAnalysis,
  openRouteDiagnosis,
  pageDescription,
  pageTitle,
  pending,
  periodOptions,
  preset,
  ratioClass,
  ratioTone,
  resetFilters,
  resourceChannelOptions,
  route,
  selectOptions,
  trendOption,
} = useResourceGovernance()
</script>

<style scoped>
.governance-page {
  padding-bottom: 34px;
}
.source-banner,
.state-alert {
  margin-bottom: 15px;
  border-radius: 10px;
}
.scope-panel {
  margin-bottom: 14px;
  padding: 18px 20px;
  border: 1px solid #e3e9f1;
  border-radius: 13px;
  background: #fff;
  box-shadow: 0 6px 20px rgb(38 61 91 / 4%);
}
.section-heading,
.section-heading > div,
.scope-actions,
.scope-actions > div,
.period-line,
.date-fields,
.applied-scope,
.dimension-header,
.panel-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.section-heading,
.scope-actions,
.applied-scope,
.dimension-header,
.panel-title {
  justify-content: space-between;
}
.section-heading h2 {
  margin: 0;
  color: #26354b;
  font-size: 15px;
}
.section-heading span,
.scope-actions > span,
.panel-title small,
.dimension-header small {
  color: #8c98aa;
  font-size: 11px;
}
.period-line {
  margin: 17px 0;
  flex-wrap: wrap;
}
.date-fields {
  color: #7a8799;
  font-size: 12px;
}
.date-fields :deep(.ant-picker) {
  width: 145px;
}
.filter-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}
.filter-grid label {
  display: grid;
  gap: 7px;
  color: #63728a;
  font-size: 12px;
}
.filter-grid :deep(.ant-select) {
  width: 100%;
}
.scope-actions {
  margin-top: 17px;
  padding-top: 14px;
  border-top: 1px solid #edf1f5;
}
.applied-scope {
  margin: 13px 2px;
  flex-wrap: wrap;
  color: #4d5d75;
  font-size: 12px;
}
.applied-scope > div {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.governance-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 22px;
  align-items: center;
  margin-bottom: 14px;
  padding: 24px 26px;
  overflow: hidden;
  border-radius: 14px;
  color: #fff;
  background: linear-gradient(125deg, #17375f, #275f9f 68%, #2c7a8e);
  box-shadow: 0 12px 32px rgb(27 63 106 / 18%);
}
.hero-copy span,
.hero-ratio small,
.hero-ratio span {
  color: #c8dbf2;
  font-size: 10px;
  letter-spacing: 0.08em;
}
.hero-copy h2 {
  margin: 9px 0 7px;
  font-size: 21px;
}
.hero-copy p {
  margin: 0;
  color: #d7e4f3;
  font-size: 12px;
}
.hero-ratio {
  min-width: 200px;
  padding-left: 24px;
  border-left: 1px solid rgb(255 255 255 / 20%);
  text-align: right;
}
.hero-ratio strong {
  display: block;
  margin: 5px 0;
  font-size: 30px;
  letter-spacing: -0.04em;
}
.hero-ratio strong.danger {
  color: #ffd0c7;
}
.hero-ratio strong.healthy {
  color: #bff4db;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 11px;
  margin-bottom: 15px;
}
.kpi-grid article {
  min-width: 0;
  padding: 16px;
  border: 1px solid #e3e9f1;
  border-radius: 11px;
  background: #fff;
}
.kpi-grid span,
.kpi-grid small {
  display: block;
  color: #8a96a8;
  font-size: 10px;
}
.kpi-grid strong {
  display: block;
  margin: 12px 0 10px;
  color: #25364e;
  font-size: clamp(18px, 1.7vw, 25px);
  white-space: nowrap;
}
.kpi-grid strong.orange {
  color: #c8782c;
}
.quality-strip {
  margin-bottom: 15px;
  padding: 16px 18px;
  border: 1px solid #e3e9f1;
  border-radius: 12px;
  background: #fff;
}
.quality-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 13px;
  color: #33465f;
}
.quality-heading span {
  color: #929dae;
  font-size: 10px;
}
.quality-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}
.quality-grid article {
  padding: 11px 13px;
  border-radius: 9px;
  background: #f6f8fb;
}
.quality-grid span {
  display: block;
  color: #8996a8;
  font-size: 10px;
}
.quality-grid strong {
  display: block;
  margin-top: 7px;
  color: #30425b;
  font-size: 15px;
}
.charts-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(320px, 0.85fr);
  gap: 15px;
  margin-bottom: 15px;
}
.analysis-panel {
  min-width: 0;
  border: 1px solid #e3e9f1;
  border-radius: 12px;
}
.channel-panel,
.api-group-panel {
  margin-bottom: 15px;
}
.analysis-panel :deep(.ant-card-head) {
  min-height: 58px;
  border-color: #edf1f5;
}
.analysis-panel :deep(.ant-card-body) {
  padding: 18px 20px;
}
.panel-title > div,
.dimension-header > div {
  display: grid;
  gap: 4px;
}
.charts-grid :deep(.base-chart) {
  min-height: 300px;
  height: 300px;
}
.funnel-list {
  display: grid;
  gap: 18px;
  padding: 7px 2px;
}
.funnel-row > div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: #52617a;
  font-size: 12px;
}
.funnel-row small {
  color: #929dae;
  font-size: 10px;
}
.funnel-row :deep(.ant-progress) {
  margin: 5px 0 2px;
}
.dimension-panel {
  margin-bottom: 15px;
}
.dimension-header {
  width: 100%;
}
.resource-name {
  display: grid;
  gap: 3px;
}
.resource-name strong {
  color: #254a78;
}
.resource-name small {
  color: #98a3b3;
  font-size: 10px;
}
.danger {
  color: #c44752 !important;
}
.healthy {
  color: #218365 !important;
}
.notes {
  display: flex;
  gap: 10px;
  padding: 17px 2px;
  color: #8291a6;
  font-size: 11px;
  line-height: 1.7;
}
.notes p {
  margin: 4px 0 0;
}
.drawer-scope {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
  padding: 13px 15px;
  border-radius: 9px;
  color: #728096;
  background: #f5f8fb;
  font-size: 11px;
}
.drawer-scope > div {
  display: flex;
  justify-content: flex-end;
  gap: 5px;
  flex-wrap: wrap;
}
.drawer-kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 15px;
}
.drawer-kpis article {
  padding: 15px;
  border: 1px solid #e3e9f1;
  border-radius: 10px;
}
.drawer-kpis span {
  display: block;
  color: #8b97a8;
  font-size: 10px;
}
.drawer-kpis strong {
  display: block;
  margin-top: 9px;
  color: #2c3d55;
  font-size: 20px;
}
.analysis-switch {
  display: flex;
  justify-content: center;
  margin: 4px 0 16px;
}
.drawer-route-actions {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #7d899a;
  font-size: 11px;
}
.analysis-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
}
.analysis-toolbar > div {
  display: grid;
  gap: 4px;
  color: #34465f;
}
.analysis-toolbar small {
  color: #8b97a8;
  font-size: 10px;
}
.daily-table {
  border: 1px solid #e5eaf1;
  border-radius: 10px;
  overflow: hidden;
}
@media (max-width: 1250px) {
  .kpi-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .quality-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .filter-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (max-width: 900px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
  .filter-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .dimension-header {
    align-items: flex-start;
    flex-direction: column;
  }
  .governance-hero {
    grid-template-columns: 1fr;
  }
  .hero-ratio {
    padding: 15px 0 0;
    border-top: 1px solid rgb(255 255 255 / 20%);
    border-left: 0;
    text-align: left;
  }
}
@media (max-width: 600px) {
  .scope-panel {
    padding: 15px 12px;
  }
  .section-heading,
  .scope-actions,
  .quality-heading,
  .analysis-toolbar,
  .drawer-scope {
    align-items: flex-start;
    flex-direction: column;
  }
  .filter-grid,
  .kpi-grid,
  .quality-grid,
  .drawer-kpis {
    grid-template-columns: 1fr 1fr;
  }
  .date-fields :deep(.ant-picker) {
    width: 126px;
  }
}
</style>
