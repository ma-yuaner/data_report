<template>
  <div class="page-wrap monitoring-page">
    <PageHeader
      eyebrow="MONITORING CONTROL PLANE"
      title="监控中心"
      description="统一查看规则生效、事件命中、增量采集与通知链路运行情况"
    />

    <a-alert v-if="error" type="error" show-icon class="page-alert" :message="error" />

    <section class="monitor-hero">
      <div>
        <span class="hero-kicker">通用监控底座</span>
        <h2>规则、数据、命中、通知，全链路可追踪</h2>
        <p>智能投放是首个接入模板；后续订单航段、利润异常、状态超时等规则复用同一套运行底座。</p>
      </div>
      <div class="hero-state">
        <span class="state-dot" :class="{ online: overview?.available }" />
        <div><strong>{{ overview?.available ? '服务正常' : '等待数据' }}</strong><small>{{ overview?.source || 'MySQL · sibebid' }}</small></div>
        <a-button :loading="loading" @click="reloadAll"><ReloadOutlined />刷新</a-button>
      </div>
    </section>

    <div class="summary-grid">
      <article v-for="card in summaryCards" :key="card.key" class="summary-card">
        <span>{{ card.label }}</span>
        <strong :class="card.tone">{{ number(summaryValue(card.key)) }}</strong>
        <small>{{ card.note }}</small>
      </article>
    </div>

    <a-card class="monitor-panel" :bordered="false">
      <a-tabs v-model:activeKey="activeTab" @change="changeTab">
        <a-tab-pane key="rules" tab="监控规则">
          <div class="filter-grid rule-filters">
            <a-input v-model:value="ruleFilters.keyword" allow-clear placeholder="规则编号 / 名称 / 负责人" @press-enter="loadRules(1)">
              <template #prefix><SearchOutlined /></template>
            </a-input>
            <a-select v-model:value="ruleFilters.status" :options="ruleStatusOptions" />
            <a-select v-model:value="ruleFilters.template" :options="templateOptions" />
            <a-button type="primary" @click="loadRules(1)">查询</a-button>
            <a-button @click="resetRuleFilters">重置</a-button>
            <a-button v-if="canManageRules" type="primary" ghost @click="openCreateRule">新建规则</a-button>
          </div>
          <a-table row-key="id" :columns="ruleColumns" :data-source="rules?.rows || []" :loading="ruleLoading" :pagination="rulePagination" :scroll="{ x: 1280 }" @change="changeRulePage">
            <template #emptyText><a-empty description="暂无监控规则；投放成功后会自动生成" /></template>
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'rule'">
                <button class="link-cell" type="button" @click="openRule(record)"><strong>{{ record.ruleName }}</strong><small>{{ record.ruleCode }}</small></button>
              </template>
              <template v-else-if="column.key === 'template'"><div class="two-line"><strong>{{ record.templateName || templateName(record.templateCode) }}</strong><span>{{ record.businessType }}</span></div></template>
              <template v-else-if="column.key === 'grain'">
                <a-tag v-if="record.groupDimensions?.length" color="purple">按{{ grainText(record.groupDimensions) }}</a-tag>
                <span v-else class="muted-text">整范围汇总</span>
              </template>
              <template v-else-if="column.key === 'status'"><a-tag :color="ruleStatusMeta[record.status]?.color || 'default'">{{ ruleStatusMeta[record.status]?.label || record.status }}</a-tag></template>
              <template v-else-if="column.key === 'period'"><div class="two-line"><strong>{{ displayTime(record.effectiveStartAt) }}</strong><span>至 {{ displayTime(record.effectiveEndAt) }}</span></div></template>
              <template v-else-if="column.key === 'hit'"><div class="two-line numeric"><strong>{{ number(record.hitCount) }}</strong><span>{{ record.lastHitAt ? `最近 ${displayTime(record.lastHitAt)}` : '尚未命中' }}</span></div></template>
              <template v-else-if="column.key === 'owner'">{{ record.ownerUserName || '系统' }}</template>
              <template v-else-if="column.key === 'updatedAt'">{{ displayTime(record.updatedAt) }}</template>
              <template v-else-if="column.key === 'action'">
                <a-space><a-button size="small" @click="openRule(record)">详情</a-button><a-button v-if="['SMART_PLACEMENT_ORDER','ORDER_SEGMENT_THRESHOLD'].includes(record.templateCode)" size="small" type="link" @click="openDiagnostic(record)">诊断</a-button><a-button v-if="canManageRules" size="small" @click="openStatus(record)">状态</a-button></a-space>
              </template>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="events" tab="命中事件">
          <div class="filter-grid event-filters">
            <a-range-picker v-model:value="eventRange" :locale="dateLocale" value-format="YYYY-MM-DD" :allow-clear="false" />
            <a-input v-model:value="eventFilters.keyword" allow-clear placeholder="事件 / 规则 / 订单" @press-enter="loadEvents(1)" />
            <a-select v-model:value="eventFilters.status" :options="eventStatusOptions" />
            <a-select v-model:value="eventFilters.assigneeUserId" allow-clear :options="eventAssigneeOptions" placeholder="全部责任人" />
            <a-checkbox v-model:checked="eventFilters.onlyMine">只看我的</a-checkbox>
            <a-checkbox v-model:checked="eventFilters.overdueOnly">只看逾期</a-checkbox>
            <a-button type="primary" @click="loadEvents(1)">查询</a-button>
            <a-button @click="resetEventFilters">重置</a-button>
          </div>
          <a-table row-key="id" :columns="eventColumns" :data-source="events?.rows || []" :loading="eventLoading" :pagination="eventPagination" :scroll="{ x: 1520 }" @change="changeEventPage">
            <template #emptyText><a-empty description="所选期间暂无命中事件" /></template>
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'event'"><div class="two-line"><strong>{{ record.eventTitle }}</strong><span>{{ record.eventNo }}</span></div></template>
              <template v-else-if="column.key === 'entity'"><div class="two-line"><strong>{{ anomalyScopeText(record) || record.entityKey }}</strong><span>{{ anomalyScopeText(record) ? record.entityKey : record.entityType }}</span></div></template>
              <template v-else-if="column.key === 'rule'"><button class="inline-link" type="button" @click="openRuleById(record.ruleId)">{{ record.ruleCode }}</button></template>
              <template v-else-if="column.key === 'severity'"><a-tag :color="severityMeta[record.severity] || 'default'">{{ record.severity }}</a-tag></template>
              <template v-else-if="column.key === 'status'"><a-tag :color="eventStatusMeta[record.eventStatus]?.color || 'default'">{{ eventStatusMeta[record.eventStatus]?.label || record.eventStatus }}</a-tag></template>
              <template v-else-if="column.key === 'assignee'"><div class="two-line"><strong>{{ record.assigneeUserName || '待分配' }}</strong><span>{{ record.assigneeUserId ? `账号 #${record.assigneeUserId}` : '规则负责人待同步' }}</span></div></template>
              <template v-else-if="column.key === 'deadline'"><div class="two-line"><strong :class="{ 'overdue-text': isEventOverdue(record) }">{{ displayTime(record.observeUntil || record.dueAt) }}</strong><span>{{ record.observeUntil ? '观察截止' : '处理截止' }}</span></div></template>
              <template v-else-if="column.key === 'escalation'"><a-tag :color="record.escalationLevel ? 'volcano' : 'default'">{{ record.escalationLevel ? `L${record.escalationLevel}` : '未升级' }}</a-tag></template>
              <template v-else-if="column.key === 'occurredAt'">{{ displayTime(record.occurredAt) }}</template>
              <template v-else-if="column.key === 'action'"><a-button size="small" @click="openEventStatus(record)">{{ canManageEvents ? '处理' : '详情' }}</a-button></template>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="runs" tab="运行日志">
          <div class="run-toolbar"><p>检查分钟采集、规则匹配和通知发送是否连续成功。</p><a-button :loading="runLoading" @click="loadRuns"><ReloadOutlined />刷新日志</a-button></div>
          <a-table row-key="id" :columns="runColumns" :data-source="runs" :loading="runLoading" :pagination="false" :scroll="{ x: 1100 }">
            <template #emptyText><a-empty description="暂无运行日志；ETL接入并调度后会在这里展示" /></template>
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'run'"><div class="two-line"><strong>{{ jobTypeName(record.jobType) }}</strong><span>{{ record.runNo }}</span></div></template>
              <template v-else-if="column.key === 'status'"><a-tag :color="runStatusMeta[record.status]?.color || 'default'">{{ runStatusMeta[record.status]?.label || record.status }}</a-tag></template>
              <template v-else-if="column.key === 'volume'"><div class="run-volume"><span>读 {{ number(record.rowsRead) }}</span><span>写 {{ number(record.rowsWritten) }}</span><span>命中 {{ number(record.eventsCreated) }}</span></div></template>
              <template v-else-if="column.key === 'duration'">{{ duration(record.durationMs) }}</template>
              <template v-else-if="column.key === 'startedAt'">{{ displayTime(record.startedAt) }}</template>
              <template v-else-if="column.key === 'error'"><span class="error-text">{{ record.errorMessage || '—' }}</span></template>
            </template>
          </a-table>
        </a-tab-pane>

        <a-tab-pane key="notifications" tab="智能通知">
          <a-alert v-if="!canManageRules" class="endpoint-tip" type="warning" show-icon message="当前账号只能查看监控结果" description="智能通知包含Webhook和消息模板等敏感配置，请联系系统管理员授予监控规则管理权限。" />
          <div v-else>
          <div class="run-toolbar">
            <div><h3>智能投放通知</h3><p>配置是否启用企业微信、发送到哪个群、使用什么消息结构；订单匹配仍由五分钟调度执行。</p></div>
            <a-space><a-button :loading="endpointLoading" @click="loadNotificationModel"><ReloadOutlined />刷新</a-button><a-button type="primary" @click="openEndpoint()">新增通知群</a-button></a-space>
          </div>
          <a-alert class="endpoint-tip" type="success" show-icon message="智能收单发送链路" description="订单宽表 → 特征ETL → 规则匹配 → 命中事件 → 发件箱 → 企业微信；本页面负责群、模板和路由配置，不直接扫描订单。" />
          <a-alert class="endpoint-tip" type="info" show-icon message="@人员配置说明" description="企业微信机器人只有使用企业微信用户ID或手机号才能真正@到人员；群名称仅用于本系统识别，不参与发送。" />
          <a-table row-key="id" :columns="endpointColumns" :data-source="notifyEndpoints" :loading="endpointLoading" :pagination="false" :scroll="{ x: 980 }">
            <template #emptyText><a-empty description="尚未配置企业微信群机器人" /></template>
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'endpoint'"><div class="two-line"><strong>{{ record.endpointName }}</strong><span>{{ record.endpointCode }}</span></div></template>
              <template v-else-if="column.key === 'webhook'"><code>{{ record.webhookMasked || '未配置' }}</code></template>
              <template v-else-if="column.key === 'mentions'"><div class="two-line"><strong>用户ID {{ record.mentionedUserIds.length }} 人</strong><span>手机号 {{ record.mentionedMobiles.length }} 人</span></div></template>
              <template v-else-if="column.key === 'scope'"><a-tag :color="record.smartPlacementEnabled ? 'green' : 'default'">{{ record.smartPlacementEnabled ? '智能收单自动通知' : '仅规则手工选择' }}</a-tag></template>
              <template v-else-if="column.key === 'status'"><a-tag :color="record.status === 'ACTIVE' ? 'green' : 'default'">{{ record.status === 'ACTIVE' ? '启用' : '停用' }}</a-tag></template>
              <template v-else-if="column.key === 'updatedAt'">{{ displayTime(record.updatedAt) }}</template>
              <template v-else-if="column.key === 'action'"><a-space><a-button size="small" @click="openEndpoint(record)">编辑</a-button><a-button size="small" type="link" :disabled="record.status !== 'ACTIVE'" :loading="testingEndpointId === record.id" @click="testEndpoint(record)">测试发送</a-button></a-space></template>
            </template>
          </a-table>
          <div class="notification-model-grid">
            <section class="notification-model-card">
              <header><div><h3>消息模板</h3><p>从授权字段中编排智能收单消息；实际发送内容会保存快照，便于追溯。</p></div></header>
              <a-table row-key="id" size="small" :columns="messageTemplateColumns" :data-source="messageTemplates" :pagination="false">
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'template'"><div class="two-line"><strong>{{ record.templateName }}</strong><span>{{ record.eventCode }} · V{{ record.versionNo }}</span></div></template>
                  <template v-else-if="column.key === 'status'"><a-tag :color="record.status === 'ACTIVE' ? 'green' : 'default'">{{ record.status === 'ACTIVE' ? '启用' : '停用' }}</a-tag></template>
                  <template v-else-if="column.key === 'action'"><a-button size="small" @click="openMessageTemplate(record)">编辑</a-button></template>
                </template>
              </a-table>
            </section>
            <section class="notification-model-card">
              <header><div><h3>通知路由</h3><p>决定事件使用哪个模板、发到哪个群，并从ERP花名册动态解析@人员。</p></div><a-button type="primary" size="small" @click="openNotifyRoute()">新增路由</a-button></header>
              <a-table row-key="id" size="small" :columns="notifyRouteColumns" :data-source="notifyRoutes" :pagination="false" :scroll="{ x: 820 }">
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'route'"><div class="two-line"><strong>{{ record.routeName }}</strong><span>{{ record.eventCode }}</span></div></template>
                  <template v-else-if="column.key === 'target'"><div class="two-line"><strong>{{ record.endpointName || (record.useSmartDefaultEndpoints ? '全部智能默认群' : '—') }}</strong><span>{{ recipientStrategyLabel(record.recipientStrategy) }}</span></div></template>
                  <template v-else-if="column.key === 'status'"><a-tag :color="record.status === 'ACTIVE' ? 'green' : 'default'">{{ record.status === 'ACTIVE' ? '启用' : '停用' }}</a-tag></template>
                  <template v-else-if="column.key === 'action'"><a-button size="small" @click="openNotifyRoute(record)">编辑</a-button></template>
                </template>
              </a-table>
            </section>
          </div>
          </div>
        </a-tab-pane>

        <a-tab-pane key="diagnostic" tab="匹配诊断">
          <section class="diagnostic-panel">
            <header><div><h3>规则 × 订单逐项诊断</h3><p>输入OTA订单号后，直接查看特征采集、规则状态、每个条件及事件落库结果。</p></div><a-tag color="blue">只读诊断</a-tag></header>
            <div class="diagnostic-query">
              <a-select v-model:value="diagnosticForm.ruleId" :options="diagnosticRuleOptions" show-search option-filter-prop="label" placeholder="请选择监控规则" />
              <a-input v-model:value="diagnosticForm.otaOrderNo" allow-clear placeholder="请输入OTA订单号，例如 5868726369" @press-enter="runDiagnostic" />
              <a-button type="primary" :loading="diagnosticLoading" @click="runDiagnostic"><SearchOutlined />开始诊断</a-button>
            </div>
            <a-empty v-if="!diagnostic && !diagnosticLoading" description="选择规则并输入订单号后开始诊断" />
            <template v-else-if="diagnostic">
              <a-alert class="diagnostic-result" show-icon :type="diagnostic.matched ? 'success' : 'warning'" :message="diagnostic.matched ? '当前订单满足规则条件' : '当前订单未满足规则或尚未完成落库'" :description="diagnostic.order ? `订单 ${diagnostic.order.otaOrderNo || diagnosticForm.otaOrderNo} · 业务时间 ${displayTime(diagnostic.order.orderTime)}` : `订单 ${diagnosticForm.otaOrderNo} 尚未进入标准特征表`" />
              <div class="diagnostic-stages">
                <article v-for="stage in diagnostic.stages" :key="stage.code" :class="{ passed: stage.passed }"><span>{{ stage.passed ? '✓' : '!' }}</span><div><strong>{{ stage.name }}</strong><small>{{ stage.message }}</small></div></article>
              </div>
              <section v-if="diagnostic.conditions.length" class="diagnostic-conditions">
                <h4>条件核对</h4>
                <div class="diagnostic-condition-head"><span>条件</span><span>规则期望</span><span>订单实际</span><span>结果</span></div>
                <article v-for="item in diagnostic.conditions" :key="`${item.groupNo}-${item.fieldCode}-${item.operatorCode}`">
                  <div><strong>{{ item.fieldName }}</strong><small>{{ operatorName(item.operatorCode) }}</small></div>
                  <code>{{ diagnosticValue(item.expected) }}</code>
                  <code>{{ diagnosticValue(item.actual) }}</code>
                  <a-tag :color="item.passed ? 'green' : 'red'">{{ item.passed ? '通过' : '不通过' }}</a-tag>
                </article>
              </section>
            </template>
          </section>
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <a-drawer v-model:open="ruleDetailOpen" title="监控规则详情" :width="'min(780px, 100vw)'">
      <template v-if="ruleDetail">
        <div class="detail-hero"><span>{{ ruleDetail.rule.ruleCode }}</span><h2>{{ ruleDetail.rule.ruleName }}</h2><div><a-tag :color="ruleStatusMeta[ruleDetail.rule.status]?.color || 'default'">{{ ruleStatusMeta[ruleDetail.rule.status]?.label || ruleDetail.rule.status }}</a-tag><a-tag>{{ ruleDetail.rule.templateCode }}</a-tag><a-tag>版本 {{ ruleDetail.rule.currentVersionNo }}</a-tag></div></div>
        <section class="detail-section"><h3>运行信息</h3><div class="detail-grid"><div><label>负责人</label><span>{{ ruleDetail.rule.ownerUserName || '系统' }}</span></div><div><label>累计命中</label><span>{{ number(ruleDetail.rule.hitCount) }}</span></div><div><label>生效时间</label><span>{{ displayTime(ruleDetail.rule.effectiveStartAt) }}</span></div><div><label>失效时间</label><span>{{ displayTime(ruleDetail.rule.effectiveEndAt) }}</span></div></div></section>
        <section v-for="version in ruleDetail.versions" :key="version.id" class="detail-section"><h3>版本 {{ version.versionNo }} 条件</h3><p v-if="version.groupDimensions?.length" class="grain-hint">异常分析粒度：按{{ grainText(version.groupDimensions) }}分别生成异常，未配置时按整个范围汇总。</p><div class="condition-list"><article v-for="condition in version.conditions" :key="condition.id"><span>{{ fieldName(condition.fieldCode) }}</span><strong>{{ operatorName(condition.operatorCode) }}</strong><code>{{ formatConditionValue(condition.valueJson) }}</code><a-tag v-if="condition.conditionRole === 'EXCLUDE'" color="red">排除</a-tag></article></div></section>
      </template>
    </a-drawer>

    <a-modal v-model:open="statusOpen" title="调整规则状态" :footer="null" :mask-closable="false" width="min(560px, 94vw)">
      <a-alert v-if="statusRule" type="info" show-icon :message="statusRule.ruleName" :description="statusRule.ruleCode" />
      <a-form layout="vertical" class="status-form"><a-form-item label="目标状态" required><a-select v-model:value="statusForm.status" :options="statusActionOptions" /></a-form-item><a-form-item label="调整原因" :required="statusForm.status !== 'ACTIVE'"><a-textarea v-model:value="statusForm.note" :rows="4" placeholder="暂停或停用时必须填写，记录将进入审计日志" /></a-form-item></a-form>
      <div class="dialog-actions"><a-button @click="statusOpen=false">取消</a-button><a-button type="primary" :loading="saving" @click="saveStatus">确认调整</a-button></div>
    </a-modal>

    <a-modal v-model:open="createRuleOpen" :title="createRuleMeta.title" :footer="null" :mask-closable="false" width="min(780px, 94vw)">
      <a-alert type="info" show-icon :message="createRuleMeta.message" :description="createRuleMeta.description" />
      <a-form layout="vertical" class="rule-form">
        <div class="rule-form-grid">
          <a-form-item label="监控类型" required class="span-2"><a-segmented v-model:value="ruleForm.templateCode" :options="manualTemplateOptions" block /></a-form-item>
          <a-form-item label="规则名称" required class="span-2"><a-input v-model:value="ruleForm.ruleName" placeholder="例如：当日订单航段数不少于6段" /></a-form-item>
          <a-form-item label="告警等级" required><a-select v-model:value="ruleForm.severity" :options="severityOptions" /></a-form-item>
          <template v-if="ruleForm.templateCode === 'ORDER_SEGMENT_THRESHOLD'">
            <a-form-item label="航段判断" required><div class="compact-fields"><a-select v-model:value="ruleForm.segmentOperator" :options="segmentOperatorOptions" /><a-input-number v-model:value="ruleForm.segmentCount" :min="1" /></div></a-form-item>
            <a-form-item label="平台名称"><a-input v-model:value="ruleForm.platformName" placeholder="留空表示全部平台" /></a-form-item>
            <a-form-item label="站点名称"><a-input v-model:value="ruleForm.siteName" placeholder="留空表示全部站点" /></a-form-item>
            <a-form-item label="航司"><a-input v-model:value="ruleForm.airlineCode" placeholder="多个用逗号分隔" /></a-form-item>
            <a-form-item label="产品类型"><a-input v-model:value="ruleForm.productType" placeholder="多个用逗号分隔" /></a-form-item>
          </template>
          <template v-else-if="ruleForm.templateCode === 'GDS_QUERY_RATIO_DAILY'">
            <a-form-item label="GDS" required><a-input v-model:value="ruleForm.gdsCode" placeholder="例如：1A" /></a-form-item>
            <a-form-item label="PCC"><a-input v-model:value="ruleForm.pccCode" placeholder="留空表示全部PCC" /></a-form-item>
            <a-form-item label="平台编码"><a-input v-model:value="ruleForm.platformCode" placeholder="留空表示全部平台" /></a-form-item>
            <a-form-item label="站点编码"><a-input v-model:value="ruleForm.siteCode" placeholder="留空表示全部站点" /></a-form-item>
            <a-form-item label="接口分组"><a-input v-model:value="ruleForm.apiGroup" placeholder="留空表示全部接口" /></a-form-item>
            <a-form-item label="最小查询量" required><a-input-number v-model:value="ruleForm.minRequests" :min="1" style="width:100%" /></a-form-item>
            <a-form-item label="查定比上限" required><a-input-number v-model:value="ruleForm.maxQueryRatio" :min="1" :precision="2" style="width:100%" addon-after=": 1" /></a-form-item>
          </template>
          <template v-else>
            <a-form-item label="平台编码" required><a-input v-model:value="ruleForm.platformCode" placeholder="例如：CTRIP" /></a-form-item>
            <a-form-item label="站点编码"><a-input v-model:value="ruleForm.siteCode" placeholder="留空表示全部站点" /></a-form-item>
            <a-form-item label="接口分组"><a-input v-model:value="ruleForm.apiGroup" placeholder="留空表示全部接口" /></a-form-item>
            <a-form-item label="监控环节" required><a-select v-model:value="ruleForm.successStage" :options="successStageOptions" /></a-form-item>
            <a-form-item label="最小请求量" required><a-input-number v-model:value="ruleForm.minRequests" :min="1" style="width:100%" /></a-form-item>
            <a-form-item label="成功率下限" required><a-input-number v-model:value="ruleForm.minSuccessRate" :min="0" :max="100" :precision="2" style="width:100%" addon-after="%" /></a-form-item>
          </template>
          <a-form-item label="异常分析粒度"><a-select v-model:value="ruleForm.groupDimensions" mode="multiple" :options="grainOptions" allow-clear placeholder="留空按整个范围汇总告警" /></a-form-item>
          <a-form-item v-if="ruleForm.groupDimensions.length" label="拆分说明" class="span-2"><span class="grain-hint">命中时按所选维度分别生成异常，例如选择PCC后，查定比超限的PCC会各自产生一条异常，正常PCC不会产生。</span></a-form-item>
          <a-form-item label="生效时间"><a-date-picker v-model:value="ruleForm.effectiveStartAt" :locale="dateLocale" show-time value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" /></a-form-item>
          <a-form-item label="失效时间"><a-date-picker v-model:value="ruleForm.effectiveEndAt" :locale="dateLocale" show-time value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" /></a-form-item>
          <a-form-item label="负责人姓名"><a-input v-model:value="ruleForm.ownerUserName" placeholder="默认当前用户" /></a-form-item>
          <a-form-item label="创建原因"><a-input v-model:value="ruleForm.changeReason" placeholder="说明为什么需要该监控" /></a-form-item>
          <a-form-item label="企业微信通知群" class="span-2"><a-select v-model:value="ruleForm.notifyEndpointIds" mode="multiple" :options="notifyEndpointOptions" allow-clear placeholder="留空只发送站内通知" /></a-form-item>
        </div>
      </a-form>
      <div class="dialog-actions"><a-button @click="createRuleOpen=false">取消</a-button><a-button type="primary" :loading="saving" @click="saveNewRule">{{ ruleForm.templateCode === 'ORDER_SEGMENT_THRESHOLD' ? '创建并生效' : '创建日检查规则' }}</a-button></div>
    </a-modal>

    <a-modal v-model:open="eventStatusOpen" title="处理监控事件" :footer="null" :mask-closable="false" width="min(720px, 94vw)">
      <a-alert v-if="activeEvent" type="info" show-icon :message="activeEvent.eventTitle" :description="activeEvent.entityKey" />
      <a-form v-if="canProcessActiveEvent" layout="vertical" class="status-form">
        <div class="event-action-grid">
          <a-form-item label="处理动作" required><a-select v-model:value="eventStatusForm.status" :options="eventActionOptions" /></a-form-item>
          <a-form-item label="责任人" required><a-select v-model:value="eventStatusForm.assigneeUserId" show-search option-filter-prop="label" :options="eventAssigneeOptions" placeholder="请选择处理责任人" /></a-form-item>
          <a-form-item v-if="eventStatusForm.status === 'OBSERVING'" label="观察截止时间" required><a-date-picker v-model:value="eventStatusForm.observeUntil" show-time value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" /></a-form-item>
          <a-form-item v-if="terminalEventStatuses.includes(eventStatusForm.status)" label="处理结论" required><a-select v-model:value="eventStatusForm.resolutionCode" :options="eventResolutionOptions" placeholder="请选择处理结论" /></a-form-item>
        </div>
        <a-form-item label="处理说明" :required="eventStatusForm.status !== 'ACKNOWLEDGED'"><a-textarea v-model:value="eventStatusForm.note" :rows="3" placeholder="观察、解决、忽略或关闭时必须填写，内容会进入审计记录" /></a-form-item>
      </a-form>
      <section class="event-history">
        <h3>处理记录</h3>
        <a-spin :spinning="eventDetailLoading">
          <a-empty v-if="!eventDetail?.logs?.length" description="暂无处理记录" />
          <a-timeline v-else :items="eventHistoryItems" />
        </a-spin>
      </section>
      <div class="dialog-actions"><a-button @click="eventStatusOpen=false">关闭</a-button><a-button v-if="canProcessActiveEvent" type="primary" :loading="saving" @click="saveEventStatus">确认处理</a-button></div>
    </a-modal>

    <a-modal v-model:open="endpointOpen" :title="endpointForm.id ? '编辑企业微信通知群' : '新增企业微信通知群'" :footer="null" :mask-closable="false" width="min(680px, 94vw)">
      <a-alert type="warning" show-icon message="Webhook属于敏感凭据" description="保存后只展示掩码；编辑时留空表示继续使用原Webhook，不会把明文返回到浏览器。" />
      <a-form layout="vertical" class="endpoint-form">
        <a-form-item label="通知群名称" required><a-input v-model:value="endpointForm.endpointName" placeholder="例如：智能政策收单关注群" /></a-form-item>
        <a-form-item :label="endpointForm.id ? '企业微信Webhook（留空不修改）' : '企业微信Webhook'" :required="!endpointForm.id"><a-input-password v-model:value="endpointForm.webhookUrl" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." /></a-form-item>
        <a-form-item label="@企业微信用户ID" extra="多个用户ID用逗号分隔，可在企业微信通讯录中确认"><a-textarea v-model:value="endpointForm.mentionedUserIdsText" :rows="2" placeholder="zhangsan,lisi" /></a-form-item>
        <a-form-item label="@手机号" extra="多个手机号用逗号分隔；用户ID和手机号可同时配置"><a-textarea v-model:value="endpointForm.mentionedMobilesText" :rows="2" placeholder="13800000000,13900000000" /></a-form-item>
        <div class="endpoint-switches"><a-form-item label="自动用于智能投放收单"><a-switch v-model:checked="endpointForm.smartPlacementEnabled" /></a-form-item><a-form-item label="状态"><a-select v-model:value="endpointForm.status" :options="endpointStatusOptions" /></a-form-item></div>
      </a-form>
      <div class="dialog-actions"><a-button @click="endpointOpen=false">取消</a-button><a-button type="primary" :loading="saving" @click="saveEndpoint">保存配置</a-button></div>
    </a-modal>

    <a-modal v-model:open="messageTemplateOpen" title="编辑消息模板" :footer="null" :mask-closable="false" width="min(720px, 94vw)">
      <a-alert type="info" show-icon message="只允许使用下方授权字段" description="点击字段即可追加到正文；字段缺失时发送端统一展示“未填写”，不会执行任意代码或SQL。" />
      <a-form layout="vertical" class="endpoint-form">
        <a-form-item label="标题" required><a-input v-model:value="messageTemplateForm.titleTemplate" /></a-form-item>
        <a-form-item label="可用字段">
          <div class="template-field-list"><button v-for="field in activeTemplateFields" :key="field.code" type="button" @click="appendTemplateField(field)"><span>{{ field.label }}</span><code v-text="templateToken(field.code)" /></button></div>
        </a-form-item>
        <a-form-item label="正文" required><a-textarea v-model:value="messageTemplateForm.bodyTemplate" :rows="12" :maxlength="4000" show-count /></a-form-item>
        <a-form-item label="消息预览"><pre class="message-preview">{{ messageTemplatePreview }}</pre></a-form-item>
        <a-form-item label="状态"><a-select v-model:value="messageTemplateForm.status" :options="endpointStatusOptions" /></a-form-item>
      </a-form>
      <div class="dialog-actions"><a-button @click="messageTemplateOpen=false">取消</a-button><a-button type="primary" :loading="saving" @click="saveMessageTemplate">保存模板</a-button></div>
    </a-modal>

    <a-modal v-model:open="notifyRouteOpen" :title="notifyRouteForm.id ? '编辑通知路由' : '新增通知路由'" :footer="null" :mask-closable="false" width="min(760px, 94vw)">
      <a-form layout="vertical" class="endpoint-form"><a-form-item label="路由名称" required><a-input v-model:value="notifyRouteForm.routeName" /></a-form-item><div class="route-form-grid"><a-form-item label="事件类型" required><a-select v-model:value="notifyRouteForm.eventCode" :options="notificationEventOptions" @change="syncRouteTemplate" /></a-form-item><a-form-item label="消息模板" required><a-select v-model:value="notifyRouteForm.templateId" :options="routeTemplateOptions" /></a-form-item><a-form-item label="动态@人员" required><a-select v-model:value="notifyRouteForm.recipientStrategy" :options="recipientStrategyOptions" /></a-form-item><a-form-item label="指定通知群"><a-select v-model:value="notifyRouteForm.endpointId" :options="notifyEndpointOptions" allow-clear placeholder="可使用全部智能默认群" /></a-form-item><a-form-item label="使用全部智能默认群"><a-switch v-model:checked="notifyRouteForm.useSmartDefaultEndpoints" /></a-form-item><a-form-item label="状态"><a-select v-model:value="notifyRouteForm.status" :options="endpointStatusOptions" /></a-form-item></div></a-form>
      <div class="dialog-actions"><a-button @click="notifyRouteOpen=false">取消</a-button><a-button type="primary" :loading="saving" @click="saveNotifyRoute">保存路由</a-button></div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Drawer as ADrawer, Empty as AEmpty, Form as AForm, FormItem as AFormItem, RangePicker as ARangePicker, message } from 'ant-design-vue'
import dateLocale from 'ant-design-vue/es/date-picker/locale/zh_CN'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { monitoringApi, type MonitorDiagnostic, type MonitorEvent, type MonitorEventActionInput, type MonitorEventAssignee, type MonitorEventDetail, type MonitorMessageTemplate, type MonitorNotifyEndpoint, type MonitorNotifyEndpointInput, type MonitorNotifyRoute, type MonitorNotifyRouteInput, type MonitorOverview, type MonitorRule, type MonitorRuleDetail, type MonitorRuleInput, type MonitorRun, type PagedResult, type ResourceGrainDimension } from '@/api/monitoring'

const authStore = useAuthStore()
const loading = ref(false); const error = ref(''); const activeTab = ref('rules')
const overview = ref<MonitorOverview>(); const rules = ref<PagedResult<MonitorRule>>(); const events = ref<PagedResult<MonitorEvent>>(); const runs = ref<MonitorRun[]>([])
const ruleLoading = ref(false); const eventLoading = ref(false); const runLoading = ref(false)
const rulePage = ref(1); const rulePageSize = ref(30); const eventPage = ref(1); const eventPageSize = ref(30)
const ruleFilters = ref({ keyword: '', status: '', template: '' })
const today = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' })
const monthStart = `${today.slice(0, 7)}-01`
const eventRange = ref<[string, string]>([monthStart, today]); const eventFilters = ref<{ keyword: string; status: string; assigneeUserId?: number; onlyMine: boolean; overdueOnly: boolean }>({ keyword: '', status: '', onlyMine: false, overdueOnly: false })
const ruleDetailOpen = ref(false); const ruleDetail = ref<MonitorRuleDetail>(); const statusOpen = ref(false); const statusRule = ref<MonitorRule>(); const saving = ref(false)
const diagnostic = ref<MonitorDiagnostic>(); const diagnosticLoading = ref(false); const diagnosticForm = ref<{ ruleId?: number; otaOrderNo: string }>({ otaOrderNo: '' })
const statusForm = ref({ status: 'PAUSED', note: '' })
const canManageRules = computed(() => Boolean(authStore.user?.isAdmin) || Boolean(authStore.user?.permissions?.includes('monitor.rule.manage')))
const canManageEvents = computed(() => Boolean(authStore.user?.isAdmin) || Boolean(authStore.user?.permissions?.includes('monitor.event.manage')))
const createRuleOpen = ref(false)
const eventStatusOpen = ref(false); const activeEvent = ref<MonitorEvent>(); const eventAssignees = ref<MonitorEventAssignee[]>([]); const eventDetail = ref<MonitorEventDetail>(); const eventDetailLoading = ref(false)
const eventStatusForm = ref<MonitorEventActionInput & { status: MonitorEventActionInput['status']; observeUntil?: string; resolutionCode?: MonitorEventActionInput['resolutionCode'] }>({ status: 'ACKNOWLEDGED', note: '' })
const defaultRuleForm = () => ({
  templateCode: 'ORDER_SEGMENT_THRESHOLD' as MonitorRuleInput['templateCode'], ruleName: '', severity: 'P2',
  segmentOperator: 'GTE', segmentCount: 6, platformName: '', siteName: '', airlineCode: '', productType: '',
  gdsCode: '1A', pccCode: '', platformCode: '', siteCode: '', apiGroup: '', minRequests: 100,
  maxQueryRatio: 4000, successStage: 'search', minSuccessRate: 95, groupDimensions: [] as ResourceGrainDimension[],
  effectiveStartAt: '', effectiveEndAt: '', ownerUserName: authStore.user?.displayName || '',
  changeReason: '', notifyEndpointIds: [] as number[],
})
const ruleForm = ref(defaultRuleForm())
const notifyEndpoints = ref<MonitorNotifyEndpoint[]>([]); const endpointLoading = ref(false); const endpointOpen = ref(false); const testingEndpointId = ref<number>()
const emptyEndpointForm = () => ({ id: undefined as number | undefined, endpointName: '', webhookUrl: '', mentionedUserIdsText: '', mentionedMobilesText: '', smartPlacementEnabled: true, status: 'ACTIVE' as 'ACTIVE' | 'DISABLED' })
const endpointForm = ref(emptyEndpointForm())
const messageTemplates = ref<MonitorMessageTemplate[]>([]); const notifyRoutes = ref<MonitorNotifyRoute[]>([]); const messageTemplateOpen = ref(false); const notifyRouteOpen = ref(false)
const messageTemplateForm = ref({ id: 0, titleTemplate: '', bodyTemplate: '', status: 'ACTIVE' as 'ACTIVE' | 'DISABLED' })
const emptyNotifyRouteForm = () => ({ id: undefined as number | undefined, routeName: '', eventCode: 'SMART_ORDER_MATCHED', templateId: undefined as number | undefined, recipientStrategy: 'TASK_ASSIGNEE' as MonitorNotifyRouteInput['recipientStrategy'], endpointId: undefined as number | undefined, useSmartDefaultEndpoints: true, priorityNo: 100, status: 'ACTIVE' as 'ACTIVE' | 'DISABLED' })
const notifyRouteForm = ref(emptyNotifyRouteForm())

const ruleStatusMeta: Record<string, { label: string; color: string }> = { ACTIVE: { label: '运行中', color: 'green' }, SCHEDULED: { label: '待生效', color: 'blue' }, PAUSED: { label: '已暂停', color: 'orange' }, EXPIRED: { label: '已过期', color: 'default' }, DISABLED: { label: '已停用', color: 'red' } }
const eventStatusMeta: Record<string, { label: string; color: string }> = { OPEN: { label: '待处理', color: 'red' }, ACKNOWLEDGED: { label: '已关注', color: 'blue' }, OBSERVING: { label: '观察中', color: 'purple' }, ESCALATED: { label: '已升级', color: 'volcano' }, RESOLVED: { label: '已解决', color: 'green' }, IGNORED: { label: '已忽略', color: 'default' }, CLOSED: { label: '已关闭', color: 'default' } }
const runStatusMeta: Record<string, { label: string; color: string }> = { RUNNING: { label: '运行中', color: 'processing' }, SUCCESS: { label: '成功', color: 'green' }, FAILED: { label: '失败', color: 'red' }, SKIPPED: { label: '跳过', color: 'default' } }
const severityMeta: Record<string, string> = { P0: 'red', P1: 'orange', P2: 'blue', P3: 'default' }
const templates = [{ value: 'SMART_PLACEMENT_ORDER', label: '智能投放收单匹配' }, { value: 'ORDER_SEGMENT_THRESHOLD', label: '订单航段阈值监控' }, { value: 'GDS_QUERY_RATIO_DAILY', label: 'GDS查定比日异常' }, { value: 'OTA_SUCCESS_RATE_DAILY', label: 'OTA成功率日异常' }, { value: 'METRIC_THRESHOLD', label: '经营指标阈值监控' }, { value: 'STATE_TIMEOUT', label: '业务状态超时监控' }]
const templateOptions = [{ value: '', label: '全部模板' }, ...templates]
const manualTemplateOptions = [{ value: 'ORDER_SEGMENT_THRESHOLD', label: '订单航段' }, { value: 'GDS_QUERY_RATIO_DAILY', label: 'GDS查定比（日）' }, { value: 'OTA_SUCCESS_RATE_DAILY', label: 'OTA成功率（日）' }]
const ruleStatusOptions = [{ value: '', label: '全部状态' }, ...Object.entries(ruleStatusMeta).map(([value, meta]) => ({ value, label: meta.label }))]
const eventStatusOptions = [{ value: '', label: '全部事件状态' }, ...Object.entries(eventStatusMeta).map(([value, meta]) => ({ value, label: meta.label }))]
const statusActionOptions = [{ value: 'ACTIVE', label: '启用' }, { value: 'PAUSED', label: '暂停' }, { value: 'DISABLED', label: '停用' }]
const severityOptions = ['P0', 'P1', 'P2', 'P3'].map(value => ({ value, label: value }))
const segmentOperatorOptions = [{ value: 'GTE', label: '大于等于' }, { value: 'GT', label: '大于' }, { value: 'EQ', label: '等于' }, { value: 'LTE', label: '小于等于' }, { value: 'LT', label: '小于' }]
const successStageOptions = [{ value: 'search', label: '查询成功率' }, { value: 'verify', label: '验价成功率' }, { value: 'order', label: '生单成功率' }]
const gdsGrainOptions = [{ value: 'pcc_code', label: '按PCC拆分' }, { value: 'gds_code', label: '按GDS拆分' }]
const otaGrainOptions = [{ value: 'ota_site_code', label: '按站点拆分' }, { value: 'ota_code', label: '按平台拆分' }, { value: 'source_api_group', label: '按接口组拆分' }]
const grainOptions = computed(() => ruleForm.value.templateCode === 'GDS_QUERY_RATIO_DAILY' ? gdsGrainOptions : ruleForm.value.templateCode === 'OTA_SUCCESS_RATE_DAILY' ? otaGrainOptions : [])
const grainLabels: Record<string, string> = { gds_code: 'GDS', pcc_code: 'PCC', ota_code: '平台', ota_site_code: '站点', source_api_group: '接口组' }
const grainText = (dimensions?: ResourceGrainDimension[]) => (dimensions || []).map(item => grainLabels[item] || item).join(' + ')
const anomalyScopeText = (event?: MonitorEvent) => {
  const scope = event?.scope || {}
  const parts = (['gds_code', 'pcc_code', 'ota_code', 'ota_site_code', 'source_api_group'] as const)
    .filter(field => scope[field])
    .map(field => `${grainLabels[field]}：${scope[field]}`)
  return parts.join(' · ')
}
const eventActionOptions = [{ value: 'ACKNOWLEDGED', label: '确认关注' }, { value: 'OBSERVING', label: '延后观察' }, { value: 'RESOLVED', label: '已解决' }, { value: 'IGNORED', label: '忽略' }, { value: 'CLOSED', label: '关闭' }]
const terminalEventStatuses: MonitorEventActionInput['status'][] = ['RESOLVED', 'IGNORED', 'CLOSED']
const eventResolutionOptions = [{ value: 'FIXED', label: '已整改恢复' }, { value: 'EXPECTED_TEST', label: '预期测试流量' }, { value: 'BUSINESS_ACCEPTED', label: '业务确认接受' }, { value: 'FALSE_POSITIVE', label: '规则误判' }, { value: 'TECH_ACTION_REQUIRED', label: '待技术执行上下线' }, { value: 'OTHER', label: '其他' }]
const endpointStatusOptions = [{ value: 'ACTIVE', label: '启用' }, { value: 'DISABLED', label: '停用' }]
const summaryCards = [{ key: 'activeRules', label: '运行规则', note: '当前生效规则', tone: 'green' }, { key: 'scheduledRules', label: '待生效', note: '等待有效期开始', tone: 'blue' }, { key: 'openEvents', label: '今日待处理', note: '尚未完成的命中事件', tone: 'orange' }, { key: 'overdueEvents', label: '处理逾期', note: '已超过当前处理期限', tone: 'red' }, { key: 'escalatedEvents', label: '已升级', note: '自动催办升级事件', tone: 'orange' }, { key: 'totalEvents', label: '今日命中', note: '今日全部事件', tone: 'violet' }, { key: 'pendingNotifications', label: '待发通知', note: '待发送及待重试', tone: 'red' }] as const
const ruleColumns = [{ title: '规则', key: 'rule', width: 260, fixed: 'left' as const }, { title: '模板 / 业务', key: 'template', width: 190 }, { title: '异常粒度', key: 'grain', width: 120 }, { title: '状态', key: 'status', width: 100 }, { title: '生效区间', key: 'period', width: 175 }, { title: '命中', key: 'hit', width: 150 }, { title: '负责人', key: 'owner', width: 110 }, { title: '更新时间', key: 'updatedAt', width: 150 }, { title: '操作', key: 'action', width: 130, fixed: 'right' as const }]
const eventColumns = [{ title: '事件', key: 'event', width: 280 }, { title: '业务对象', key: 'entity', width: 210 }, { title: '规则', key: 'rule', width: 150 }, { title: '等级', key: 'severity', width: 70 }, { title: '状态', key: 'status', width: 100 }, { title: '责任人', key: 'assignee', width: 140 }, { title: '处理期限', key: 'deadline', width: 150 }, { title: '升级', key: 'escalation', width: 80 }, { title: '命中次数', dataIndex: 'hitCount', width: 90 }, { title: '发生时间', key: 'occurredAt', width: 150 }, { title: '操作', key: 'action', width: 90, fixed: 'right' as const }]
const runColumns = [{ title: '任务 / 运行号', key: 'run', width: 250 }, { title: '状态', key: 'status', width: 100 }, { title: '数据量', key: 'volume', width: 270 }, { title: '耗时', key: 'duration', width: 100 }, { title: '开始时间', key: 'startedAt', width: 160 }, { title: '错误信息', key: 'error', width: 280 }]
const endpointColumns = [{ title: '通知群', key: 'endpoint', width: 220 }, { title: 'Webhook', key: 'webhook', width: 300 }, { title: '@人员', key: 'mentions', width: 140 }, { title: '使用范围', key: 'scope', width: 170 }, { title: '状态', key: 'status', width: 80 }, { title: '更新时间', key: 'updatedAt', width: 150 }, { title: '操作', key: 'action', width: 150, fixed: 'right' as const }]
const messageTemplateColumns = [{ title: '模板', key: 'template' }, { title: '状态', key: 'status', width: 80 }, { title: '操作', key: 'action', width: 80 }]
const notifyRouteColumns = [{ title: '路由', key: 'route', width: 220 }, { title: '模板', dataIndex: 'templateName', width: 170 }, { title: '群与收件人', key: 'target', width: 220 }, { title: '状态', key: 'status', width: 80 }, { title: '操作', key: 'action', width: 80 }]
const rulePagination = computed(() => ({ current: rulePage.value, pageSize: rulePageSize.value, total: rules.value?.total || 0, showSizeChanger: true, showTotal: (total: number) => `共 ${number(total)} 条` }))
const eventPagination = computed(() => ({ current: eventPage.value, pageSize: eventPageSize.value, total: events.value?.total || 0, showSizeChanger: true, showTotal: (total: number) => `共 ${number(total)} 条` }))
const eventAssigneeOptions = computed(() => eventAssignees.value.map(item => ({ value: item.id, label: `${item.displayName}（${item.username}）` })))
const canProcessActiveEvent = computed(() => canManageEvents.value && Boolean(activeEvent.value) && !['RESOLVED', 'IGNORED', 'CLOSED'].includes(String(activeEvent.value?.eventStatus || '')))
const eventHistoryItems = computed(() => (eventDetail.value?.logs || []).map(item => ({
  color: item.actionCode === 'ESCALATE' ? 'red' : item.toStatus === 'RESOLVED' ? 'green' : 'blue',
  children: `${displayTime(item.createdAt)} · ${eventActionName(item.actionCode || item.toStatus)} · ${item.operatorName || '系统'} · ${item.operationNote || '未填写说明'}`,
})))
const diagnosticRuleOptions = computed(() => (rules.value?.rows || []).filter(item => ['SMART_PLACEMENT_ORDER', 'ORDER_SEGMENT_THRESHOLD'].includes(item.templateCode)).map(item => ({ value: item.id, label: `${item.ruleCode} · ${item.ruleName}` })))
const createRuleMeta = computed(() => ({
  ORDER_SEGMENT_THRESHOLD: { title: '新建订单航段监控', message: '分钟级增量规则', description: '只检查新进或发生变化的订单，不扫描全部历史数据。' },
  GDS_QUERY_RATIO_DAILY: { title: '新建GDS查定比日规则', message: '每日资源异常检查', description: '每日ADS同步完成后汇总检查一次；GDS使用seg_num航段数计算查定比，航段未同步完整时不会误报。' },
  OTA_SUCCESS_RATE_DAILY: { title: '新建OTA成功率日规则', message: '每日接口质量检查', description: '每日按平台及可选站点、接口分组检查查询、验价或生单成功率。' },
}[ruleForm.value.templateCode]))
const notifyEndpointOptions = computed(() => notifyEndpoints.value.filter(item => item.status === 'ACTIVE').map(item => ({ value: item.id, label: item.endpointName })))
const notificationEventOptions = [{ value: 'SMART_ORDER_MATCHED', label: '智能收单命中' }, { value: 'SMART_ATTENTION_REMINDER', label: '关注首次催办' }, { value: 'SMART_ATTENTION_ESCALATED', label: '关注升级提醒' }, { value: 'SMART_POLICY_EXPIRED', label: '政策到期' }]
const recipientStrategyOptions = [{ value: 'TASK_ASSIGNEE', label: '投放任务负责人' }, { value: 'ATTENTION_OWNER', label: '订单关注负责人' }, { value: 'RULE_OWNER', label: '监控规则负责人' }, { value: 'NONE', label: '不动态@人员' }]
const routeTemplateOptions = computed(() => messageTemplates.value.filter(item => item.eventCode === notifyRouteForm.value.eventCode && item.status === 'ACTIVE').map(item => ({ value: item.id, label: item.templateName })))
const activeTemplate = computed(() => messageTemplates.value.find(item => item.id === messageTemplateForm.value.id))
const activeTemplateFields = computed(() => {
  const schema = activeTemplate.value?.fieldSchema
  return (schema?.allowedFields || []).map(code => ({ code, label: schema?.fieldLabels?.[code] || code }))
})
const templatePreviewSamples: Record<string, string> = {
  otaOrderNo: 'TVLK01FB26101311351071494', policyOperators: '张紫莹 / 罗满珍', airline: 'HX', platform: 'Traveloka',
  route: 'BKK-HKG', cabinCodes: 'O,O', productType: '非标产品', placementDiff: '未填写', smartType: '没有智能',
  estimatedProfit: '-52.19', orderTime: '2026-10-13 11:49:03', ticketTime: '2026-10-13 12:04:04',
  otaLatestTicketTime: '2026-10-13 11:49:02', holdTimeResult: '出票时间大于最晚出票时间', ruleCode: 'SPM-6-3',
  externalPolicyId: '6848075', remark: '请及时排查原因处理，并在群中回复信息。',
}
const messageTemplatePreview = computed(() => `${messageTemplateForm.value.titleTemplate}\n${messageTemplateForm.value.bodyTemplate}`.replace(
  /\{([A-Za-z][A-Za-z0-9_]*)\}/g,
  (_matched, code: string) => templatePreviewSamples[code] || '未填写',
))
const templateToken = (code: string) => `{${code}}`

const number = (value: unknown) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))
const displayTime = (value: unknown) => value ? String(value).replace('T', ' ').slice(0, 16) : '—'
const duration = (value?: number) => value == null ? '—' : value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`
const templateName = (code: string) => templates.find(item => item.value === code)?.label || code
const jobTypeName = (value: string) => ({ FEATURE_ETL: '订单特征采集', RULE_MATCH: '规则匹配', RESOURCE_DAILY: '资源治理日检查', RESOURCE_LIFECYCLE: '资源异常升级', SMART_LIFECYCLE: '智能收单闭环', NOTIFY: '通知发送' }[value] || value)
const eventActionName = (value: string) => ({ ASSIGN: '分配责任人', ACKNOWLEDGE: '确认关注', OBSERVE: '延后观察', ESCALATE: '逾期升级', RESOLVE: '已解决', IGNORE: '已忽略', CLOSE: '已关闭', STATUS_CHANGE: '状态变更', ACKNOWLEDGED: '确认关注', OBSERVING: '延后观察', ESCALATED: '逾期升级', RESOLVED: '已解决', IGNORED: '已忽略', CLOSED: '已关闭' }[value] || value)
const isEventOverdue = (record: MonitorEvent) => !['RESOLVED', 'IGNORED', 'CLOSED'].includes(record.eventStatus) && Boolean(record.observeUntil || record.dueAt) && new Date(String(record.observeUntil || record.dueAt).replace(' ', 'T')).getTime() < Date.now()
const summaryValue = (key: typeof summaryCards[number]['key']) => key === 'pendingNotifications' ? overview.value?.pendingNotifications : key in (overview.value?.ruleSummary || {}) ? overview.value?.ruleSummary[key as keyof MonitorOverview['ruleSummary']] : overview.value?.eventSummary[key as keyof MonitorOverview['eventSummary']]
const fieldName = (code: string) => ({ platform_code: '平台编码', platform_name: '平台名称', site_code: '站点编码', site_name: '站点名称', ota_code: '平台编码', ota_site_code: '站点编码', gds_code: 'GDS', pcc_code: 'PCC', source_api_group: '接口分组', search_request_count_all: '查询请求量', verify_request_count_all: '验价请求量', order_request_count_all: '生单请求量', query_to_segment_ratio: '查定比', query_to_pnr_ratio: '查定比（历史口径字段）', search_success_rate: '查询成功率', verify_success_rate: '验价成功率', order_success_rate: '生单成功率', order_source: '订单来源', airline_code: '航司', departure_location_codes: '出发地', arrival_location_codes: '到达地', route_text: '航程', flight_nos: '航班号', cabin_codes: '舱位', product_type: '产品类型', journey_type: '航程类型', order_time: '订单时间', first_departure_time: '起飞时间', segment_count: '航段数' }[code] || code)
const operatorName = (code: string) => ({ EQ: '等于', IN: '属于', BETWEEN: '介于', OVERLAP: '存在交集', SUBSET_OF: '全部包含于', DISJOINT: '不得包含', GTE: '大于等于', GT: '大于', LTE: '小于等于', LT: '小于' }[code] || code)
const conditionScalar = (value: unknown) => String(value).replace(/^(\d{4}-\d{2}-\d{2})T(?=\d{2}:\d{2})/, '$1 ')
function formatConditionValue(raw: string) { try { const value = JSON.parse(raw); return Array.isArray(value) ? value.map(conditionScalar).join(' ～ ') : conditionScalar(value) } catch { return conditionScalar(raw) } }
function diagnosticValue(value: unknown) { if (value === null || value === undefined || value === '') return '—'; return Array.isArray(value) ? value.map(conditionScalar).join('、') : typeof value === 'object' ? JSON.stringify(value).replace(/"(\d{4}-\d{2}-\d{2})T(?=\d{2}:\d{2})/g, '"$1 ') : conditionScalar(value) }

async function loadOverview() { overview.value = await monitoringApi.overview() }
async function loadRules(target = rulePage.value) { ruleLoading.value = true; rulePage.value = target; try { rules.value = await monitoringApi.rules({ ...ruleFilters.value, page: target, pageSize: rulePageSize.value }) } finally { ruleLoading.value = false } }
async function loadEvents(target = eventPage.value) { eventLoading.value = true; eventPage.value = target; try { events.value = await monitoringApi.events({ ...eventFilters.value, startDate: eventRange.value[0], endDate: eventRange.value[1], page: target, pageSize: eventPageSize.value }) } finally { eventLoading.value = false } }
async function loadEventAssignees() { eventAssignees.value = await monitoringApi.eventAssignees() }
async function loadRuns() { runLoading.value = true; try { runs.value = await monitoringApi.runs({ limit: 100 }) } finally { runLoading.value = false } }
async function loadNotifyEndpoints() { endpointLoading.value = true; try { notifyEndpoints.value = await monitoringApi.notifyEndpoints() } catch (failure) { message.error(failure instanceof Error ? failure.message : '通知群配置加载失败') } finally { endpointLoading.value = false } }
async function loadNotificationModel() { if (!canManageRules.value) return; endpointLoading.value = true; try { ;[notifyEndpoints.value, messageTemplates.value, notifyRoutes.value] = await Promise.all([monitoringApi.notifyEndpoints(), monitoringApi.messageTemplates(), monitoringApi.notifyRoutes()]) } catch (failure) { message.error(failure instanceof Error ? failure.message : '通知模型加载失败') } finally { endpointLoading.value = false } }
async function reloadAll() { loading.value = true; error.value = ''; try { await Promise.all([loadOverview(), loadRules(), loadEvents(), loadRuns(), loadEventAssignees()]) } catch (failure) { error.value = failure instanceof Error ? failure.message : '监控中心加载失败' } finally { loading.value = false } }
function changeTab(key: string) { if (key === 'runs' && !runs.value.length) void loadRuns(); if (key === 'notifications' && canManageRules.value) void loadNotificationModel() }
function resetRuleFilters() { ruleFilters.value = { keyword: '', status: '', template: '' }; void loadRules(1) }
function resetEventFilters() { eventRange.value = [monthStart, today]; eventFilters.value = { keyword: '', status: '', onlyMine: false, overdueOnly: false }; void loadEvents(1) }
function changeRulePage(value: { current?: number; pageSize?: number }) { const size = value.pageSize || rulePageSize.value; rulePage.value = size === rulePageSize.value ? value.current || 1 : 1; rulePageSize.value = size; void loadRules(rulePage.value) }
function changeEventPage(value: { current?: number; pageSize?: number }) { const size = value.pageSize || eventPageSize.value; eventPage.value = size === eventPageSize.value ? value.current || 1 : 1; eventPageSize.value = size; void loadEvents(eventPage.value) }
async function openRule(record: MonitorRule) { ruleDetailOpen.value = true; ruleDetail.value = undefined; try { ruleDetail.value = await monitoringApi.ruleDetail(record.id) } catch (failure) { message.error(failure instanceof Error ? failure.message : '规则详情查询失败') } }
function openDiagnostic(record: MonitorRule) { diagnosticForm.value.ruleId = record.id; diagnostic.value = undefined; activeTab.value = 'diagnostic' }
async function runDiagnostic() {
  if (!diagnosticForm.value.ruleId) { message.warning('请选择监控规则'); return }
  if (!diagnosticForm.value.otaOrderNo.trim()) { message.warning('请输入OTA订单号'); return }
  diagnosticLoading.value = true; diagnostic.value = undefined
  try { diagnostic.value = await monitoringApi.diagnoseRule(diagnosticForm.value.ruleId, diagnosticForm.value.otaOrderNo.trim()) }
  catch (failure) { message.error(failure instanceof Error ? failure.message : '匹配诊断失败') }
  finally { diagnosticLoading.value = false }
}
async function openRuleById(id: number) { const record = rules.value?.rows.find(item => item.id === id) || { id } as MonitorRule; await openRule(record) }
function openStatus(record: MonitorRule) { statusRule.value = record; statusForm.value = { status: record.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE', note: '' }; statusOpen.value = true }
async function saveStatus() { if (!statusRule.value) return; saving.value = true; try { await monitoringApi.updateRuleStatus(statusRule.value.id, statusForm.value); message.success('规则状态已更新'); statusOpen.value = false; await Promise.all([loadOverview(), loadRules()]) } catch (failure) { message.error(failure instanceof Error ? failure.message : '规则状态更新失败') } finally { saving.value = false } }
const splitValues = (value: string) => value.replace(/，/g, ',').split(',').map(item => item.trim().toUpperCase()).filter(Boolean)
async function openCreateRule() { if (!notifyEndpoints.value.length) await loadNotifyEndpoints(); ruleForm.value = defaultRuleForm(); createRuleOpen.value = true }
async function saveNewRule() {
  if (!ruleForm.value.ruleName.trim()) { message.warning('请填写规则名称'); return }
  if (ruleForm.value.effectiveStartAt && ruleForm.value.effectiveEndAt && ruleForm.value.effectiveEndAt <= ruleForm.value.effectiveStartAt) { message.warning('失效时间必须晚于生效时间'); return }
  const conditions: MonitorRuleInput['conditions'] = []
  if (ruleForm.value.templateCode === 'ORDER_SEGMENT_THRESHOLD') {
    if (!ruleForm.value.segmentCount || ruleForm.value.segmentCount < 1) { message.warning('请填写有效航段阈值'); return }
    conditions.push({ fieldCode: 'segment_count', operatorCode: ruleForm.value.segmentOperator, value: ruleForm.value.segmentCount })
    if (ruleForm.value.platformName.trim()) conditions.push({ fieldCode: 'platform_name', operatorCode: 'EQ', value: ruleForm.value.platformName.trim() })
    if (ruleForm.value.siteName.trim()) conditions.push({ fieldCode: 'site_name', operatorCode: 'EQ', value: ruleForm.value.siteName.trim() })
    if (splitValues(ruleForm.value.airlineCode).length) conditions.push({ fieldCode: 'airline_code', operatorCode: 'IN', value: splitValues(ruleForm.value.airlineCode) })
    if (splitValues(ruleForm.value.productType).length) conditions.push({ fieldCode: 'product_type', operatorCode: 'IN', value: splitValues(ruleForm.value.productType) })
  } else if (ruleForm.value.templateCode === 'GDS_QUERY_RATIO_DAILY') {
    if (!ruleForm.value.gdsCode.trim()) { message.warning('请填写GDS'); return }
    if (!ruleForm.value.minRequests || ruleForm.value.minRequests < 1 || !ruleForm.value.maxQueryRatio || ruleForm.value.maxQueryRatio < 1) { message.warning('请填写有效的最小查询量和查定比上限'); return }
    conditions.push(
      { fieldCode: 'gds_code', operatorCode: 'EQ', value: ruleForm.value.gdsCode.trim().toUpperCase() },
      { fieldCode: 'search_request_count_all', operatorCode: 'GTE', value: ruleForm.value.minRequests },
      { fieldCode: 'query_to_segment_ratio', operatorCode: 'GT', value: ruleForm.value.maxQueryRatio },
    )
    if (ruleForm.value.pccCode.trim()) conditions.push({ fieldCode: 'pcc_code', operatorCode: 'EQ', value: ruleForm.value.pccCode.trim().toUpperCase() })
    if (ruleForm.value.platformCode.trim()) conditions.push({ fieldCode: 'ota_code', operatorCode: 'EQ', value: ruleForm.value.platformCode.trim().toUpperCase() })
    if (ruleForm.value.siteCode.trim()) conditions.push({ fieldCode: 'ota_site_code', operatorCode: 'EQ', value: ruleForm.value.siteCode.trim().toUpperCase() })
    if (ruleForm.value.apiGroup.trim()) conditions.push({ fieldCode: 'source_api_group', operatorCode: 'EQ', value: ruleForm.value.apiGroup.trim() })
  } else {
    if (!ruleForm.value.platformCode.trim()) { message.warning('请填写平台编码'); return }
    if (!ruleForm.value.minRequests || ruleForm.value.minRequests < 1 || ruleForm.value.minSuccessRate == null) { message.warning('请填写有效的最小请求量和成功率下限'); return }
    const requestField = `${ruleForm.value.successStage}_request_count_all`
    const rateField = `${ruleForm.value.successStage}_success_rate`
    conditions.push(
      { fieldCode: 'ota_code', operatorCode: 'EQ', value: ruleForm.value.platformCode.trim().toUpperCase() },
      { fieldCode: requestField, operatorCode: 'GTE', value: ruleForm.value.minRequests },
      { fieldCode: rateField, operatorCode: 'LT', value: ruleForm.value.minSuccessRate },
    )
    if (ruleForm.value.siteCode.trim()) conditions.push({ fieldCode: 'ota_site_code', operatorCode: 'EQ', value: ruleForm.value.siteCode.trim().toUpperCase() })
    if (ruleForm.value.apiGroup.trim()) conditions.push({ fieldCode: 'source_api_group', operatorCode: 'EQ', value: ruleForm.value.apiGroup.trim() })
  }
  const endpointIds = ruleForm.value.notifyEndpointIds
  const groupDimensions = ruleForm.value.templateCode === 'ORDER_SEGMENT_THRESHOLD' ? [] : ruleForm.value.groupDimensions
  const payload: MonitorRuleInput = { templateCode: ruleForm.value.templateCode, ruleName: ruleForm.value.ruleName.trim(), severity: ruleForm.value.severity, effectiveStartAt: ruleForm.value.effectiveStartAt || undefined, effectiveEndAt: ruleForm.value.effectiveEndAt || undefined, ownerUserName: ruleForm.value.ownerUserName.trim() || undefined, scheduleSeconds: ruleForm.value.templateCode === 'ORDER_SEGMENT_THRESHOLD' ? 60 : 86400, changeReason: ruleForm.value.changeReason.trim() || undefined, notifyPolicy: { channels: endpointIds.length ? ['IN_APP', 'WECOM'] : ['IN_APP'], wecomEndpointIds: endpointIds }, groupDimensions, conditions }
  saving.value = true
  try { const result = await monitoringApi.createRule(payload); message.success(`规则 ${result.ruleCode} 已创建`); createRuleOpen.value = false; await Promise.all([loadOverview(), loadRules(1)]) } catch (failure) { message.error(failure instanceof Error ? failure.message : '规则创建失败') } finally { saving.value = false }
}
async function openEventStatus(record: MonitorEvent) {
  activeEvent.value = record
  eventDetail.value = undefined
  eventStatusForm.value = { status: ['OPEN', 'ESCALATED'].includes(record.eventStatus) ? 'ACKNOWLEDGED' : 'RESOLVED', assigneeUserId: record.assigneeUserId || undefined, note: '' }
  eventStatusOpen.value = true
  eventDetailLoading.value = true
  try { eventDetail.value = await monitoringApi.eventDetail(record.id) }
  catch (failure) { message.error(failure instanceof Error ? failure.message : '事件处理记录加载失败') }
  finally { eventDetailLoading.value = false }
}
async function saveEventStatus() {
  if (!activeEvent.value) return
  const form = eventStatusForm.value
  if (!form.assigneeUserId) { message.warning('请选择处理责任人'); return }
  if (form.status === 'OBSERVING' && !form.observeUntil) { message.warning('请选择观察截止时间'); return }
  if (terminalEventStatuses.includes(form.status) && !form.resolutionCode) { message.warning('请选择处理结论'); return }
  if (form.status !== 'ACKNOWLEDGED' && !String(form.note || '').trim()) { message.warning('请填写处理说明'); return }
  const payload: MonitorEventActionInput = { status: form.status, assigneeUserId: form.assigneeUserId, note: String(form.note || '').trim() || undefined }
  if (form.status === 'OBSERVING') payload.observeUntil = form.observeUntil
  if (terminalEventStatuses.includes(form.status)) payload.resolutionCode = form.resolutionCode
  saving.value = true
  try { await monitoringApi.updateEventStatus(activeEvent.value.id, payload); message.success('事件处理结果已保存'); eventStatusOpen.value = false; await Promise.all([loadOverview(), loadEvents()]) }
  catch (failure) { message.error(failure instanceof Error ? failure.message : '事件处理失败') }
  finally { saving.value = false }
}

function openEndpoint(record?: MonitorNotifyEndpoint) {
  endpointForm.value = record ? { id: record.id, endpointName: record.endpointName, webhookUrl: '', mentionedUserIdsText: record.mentionedUserIds.join(','), mentionedMobilesText: record.mentionedMobiles.join(','), smartPlacementEnabled: record.smartPlacementEnabled, status: record.status } : emptyEndpointForm()
  endpointOpen.value = true
}
const mentionValues = (value: string) => value.replace(/[，；;\s]+/g, ',').split(',').map(item => item.trim()).filter(Boolean)
async function saveEndpoint() {
  if (!endpointForm.value.endpointName.trim()) { message.warning('请填写通知群名称'); return }
  if (!endpointForm.value.id && !endpointForm.value.webhookUrl.trim()) { message.warning('请填写企业微信Webhook'); return }
  const payload: MonitorNotifyEndpointInput = { endpointName: endpointForm.value.endpointName.trim(), webhookUrl: endpointForm.value.webhookUrl.trim() || undefined, mentionedUserIds: mentionValues(endpointForm.value.mentionedUserIdsText), mentionedMobiles: mentionValues(endpointForm.value.mentionedMobilesText), smartPlacementEnabled: endpointForm.value.smartPlacementEnabled, status: endpointForm.value.status }
  saving.value = true
  try { if (endpointForm.value.id) await monitoringApi.updateNotifyEndpoint(endpointForm.value.id, payload); else await monitoringApi.createNotifyEndpoint(payload); message.success('通知群配置已保存'); endpointOpen.value = false; await loadNotifyEndpoints() }
  catch (failure) { message.error(failure instanceof Error ? failure.message : '通知群配置保存失败') }
  finally { saving.value = false }
}
async function testEndpoint(record: MonitorNotifyEndpoint) {
  testingEndpointId.value = record.id
  try { await monitoringApi.testNotifyEndpoint(record.id); message.success(`测试消息已发送到“${record.endpointName}”`) }
  catch (failure) { message.error(failure instanceof Error ? failure.message : '测试发送失败') }
  finally { testingEndpointId.value = undefined }
}
const recipientStrategyLabel = (value: string) => recipientStrategyOptions.find(item => item.value === value)?.label || value
function openMessageTemplate(record: MonitorMessageTemplate) { messageTemplateForm.value = { id: record.id, titleTemplate: record.titleTemplate, bodyTemplate: record.bodyTemplate, status: record.status }; messageTemplateOpen.value = true }
function appendTemplateField(field: { code: string; label: string }) { const line = `【${field.label}】：{${field.code}}`; if (!messageTemplateForm.value.bodyTemplate.includes(`{${field.code}}`)) messageTemplateForm.value.bodyTemplate = `${messageTemplateForm.value.bodyTemplate.trim()}\n${line}`.trim() }
async function saveMessageTemplate() { const form = messageTemplateForm.value; if (!form.titleTemplate.trim() || !form.bodyTemplate.trim()) { message.warning('请完整填写消息标题和正文'); return } saving.value = true; try { await monitoringApi.updateMessageTemplate(form.id, { titleTemplate: form.titleTemplate.trim(), bodyTemplate: form.bodyTemplate.trim(), status: form.status }); message.success('消息模板已更新'); messageTemplateOpen.value = false; await loadNotificationModel() } catch (failure) { message.error(failure instanceof Error ? failure.message : '消息模板保存失败') } finally { saving.value = false } }
function syncRouteTemplate() { const template = messageTemplates.value.find(item => item.eventCode === notifyRouteForm.value.eventCode && item.status === 'ACTIVE'); notifyRouteForm.value.templateId = template?.id }
function openNotifyRoute(record?: MonitorNotifyRoute) { notifyRouteForm.value = record ? { id: record.id, routeName: record.routeName, eventCode: record.eventCode, templateId: record.templateId, recipientStrategy: record.recipientStrategy, endpointId: record.endpointId || undefined, useSmartDefaultEndpoints: record.useSmartDefaultEndpoints, priorityNo: record.priorityNo, status: record.status } : emptyNotifyRouteForm(); if (!record) syncRouteTemplate(); notifyRouteOpen.value = true }
async function saveNotifyRoute() { const form = notifyRouteForm.value; if (!form.routeName.trim() || !form.templateId) { message.warning('请填写路由名称并选择消息模板'); return } if (!form.endpointId && !form.useSmartDefaultEndpoints) { message.warning('请选择通知群，或启用全部智能默认群'); return } const payload: MonitorNotifyRouteInput = { routeName: form.routeName.trim(), eventCode: form.eventCode, templateId: form.templateId, recipientStrategy: form.recipientStrategy, endpointId: form.endpointId || null, useSmartDefaultEndpoints: form.useSmartDefaultEndpoints, priorityNo: form.priorityNo, status: form.status }; saving.value = true; try { if (form.id) await monitoringApi.updateNotifyRoute(form.id, payload); else await monitoringApi.createNotifyRoute(payload); message.success('通知路由已保存'); notifyRouteOpen.value = false; await loadNotificationModel() } catch (failure) { message.error(failure instanceof Error ? failure.message : '通知路由保存失败') } finally { saving.value = false } }

onMounted(() => { void reloadAll() })
</script>

<style scoped>
.monitoring-page { padding-bottom: 34px; }.page-alert { margin-bottom: 14px; border-radius: 10px; }
.monitor-hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; min-height: 138px; margin-bottom: 16px; padding: 26px 30px; overflow: hidden; border-radius: 16px; color: #fff; background: radial-gradient(circle at 88% 10%,rgba(56,189,248,.3),transparent 30%),linear-gradient(115deg,#182a4d,#174f77 58%,#087d83); box-shadow: 0 14px 34px rgba(23,47,84,.16); }.hero-kicker { color: #8fd9f4; font-size: 11px; font-weight: 800; letter-spacing: .14em; }.monitor-hero h2 { margin: 5px 0 7px; color: #fff; font-size: 22px; }.monitor-hero p { max-width: 760px; margin: 0; color: #d5e9f4; }.hero-state { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; min-width: 320px; padding: 14px 16px; border: 1px solid rgba(255,255,255,.2); border-radius: 12px; background: rgba(255,255,255,.09); backdrop-filter: blur(8px); }.hero-state strong,.hero-state small { display: block; }.hero-state small { margin-top: 2px; color: #c8dce8; font-size: 11px; }.state-dot { width: 10px; height: 10px; border-radius: 50%; background: #f59e0b; box-shadow: 0 0 0 5px rgba(245,158,11,.15); }.state-dot.online { background: #34d399; box-shadow: 0 0 0 5px rgba(52,211,153,.15); }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(145px,1fr)); gap: 12px; margin-bottom: 14px; }.summary-card { padding: 17px 18px; border: 1px solid #e6ecf3; border-radius: 12px; background: #fff; box-shadow: 0 5px 18px rgba(28,48,78,.045); }.summary-card span,.summary-card small { display: block; color: #7b8798; font-size: 11px; }.summary-card strong { display: block; margin: 7px 0 3px; color: #25334a; font-size: 24px; }.summary-card .green { color: #059669; }.summary-card .blue { color: #2563eb; }.summary-card .orange { color: #ea580c; }.summary-card .violet { color: #7c3aed; }.summary-card .red { color: #dc2626; }
.monitor-panel { border: 1px solid #e5ebf2 !important; border-radius: 14px; box-shadow: 0 7px 24px rgba(25,43,71,.05); }.monitor-panel :deep(.ant-card-body) { padding: 0 20px 20px; }.monitor-panel :deep(.ant-tabs-nav) { margin-bottom: 18px; }.filter-grid { display: grid; gap: 10px; margin-bottom: 16px; align-items: center; }.rule-filters { grid-template-columns: minmax(240px,1fr) 140px 205px auto auto auto; }.event-filters { grid-template-columns: 230px minmax(210px,1fr) 145px 190px auto auto auto auto; }.link-cell,.inline-link { padding: 0; border: 0; text-align: left; background: transparent; cursor: pointer; }.link-cell strong,.link-cell small,.two-line strong,.two-line span { display: block; }.link-cell strong,.inline-link { color: #2462ad; }.link-cell small,.two-line span { margin-top: 3px; color: #8591a3; font-size: 11px; }.numeric strong { font-size: 16px; }.run-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }.run-toolbar p { margin: 0; color: #667085; }.run-volume { display: flex; gap: 14px; }.error-text,.overdue-text { color: #b42318 !important; }
.event-action-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 0 14px; }.event-history { margin-top: 8px; padding: 14px 16px 2px; border: 1px solid #e6ebf2; border-radius: 12px; background: #fafcff; }.event-history h3 { margin: 0 0 14px; font-size: 15px; }.event-history-row { display: flex; justify-content: space-between; gap: 16px; }.event-history-row span,.event-history p { color: #667085; }.event-history p { margin: 4px 0 0; }
.detail-hero { margin: -8px 0 18px; padding: 20px; border: 1px solid #d9e4f2; border-radius: 13px; background: linear-gradient(135deg,#f3f7fd,#fff); }.detail-hero > span { color: #718198; font-size: 11px; }.detail-hero h2 { margin: 4px 0 10px; color: #253a58; font-size: 20px; }.detail-section { margin-bottom: 15px; padding: 16px; border: 1px solid #e4e9f0; border-radius: 11px; }.detail-section h3 { margin: 0 0 12px; color: #31445f; font-size: 14px; }.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }.detail-grid > div { padding: 10px 12px; border-radius: 8px; background: #f7f9fc; }.detail-grid label,.detail-grid span { display: block; }.detail-grid label { color: #8a95a8; font-size: 11px; }.detail-grid span { margin-top: 3px; color: #344054; }.condition-list { display: grid; gap: 8px; }.condition-list article { display: grid; grid-template-columns: 120px 90px minmax(0,1fr) auto; align-items: center; gap: 9px; padding: 10px 12px; border-radius: 8px; background: #f7f9fc; }.condition-list code { overflow: hidden; color: #344054; text-overflow: ellipsis; white-space: nowrap; }.status-form { margin-top: 18px; }.dialog-actions { display: flex; justify-content: flex-end; gap: 8px; margin: 18px -24px -24px; padding: 14px 24px; border-top: 1px solid #e5eaf1; }
.rule-form { margin-top: 18px; }.grain-hint { display: block; color: #7c8798; font-size: 11px; line-height: 1.6; }.muted-text { color: #98a2b3; font-size: 12px; }.rule-form-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 0 14px; }.rule-form-grid .span-2 { grid-column: span 2; }.compact-fields { display: grid; grid-template-columns: 48% 52%; }.compact-fields > :first-child { border-radius: 6px 0 0 6px; }.compact-fields > :last-child { width: 100%; margin-left: -1px; border-radius: 0 6px 6px 0; }
.endpoint-tip { margin-bottom: 14px; }.endpoint-form { margin-top: 16px; }.endpoint-switches,.route-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }.monitor-panel code { color: #526276; font-size: 12px; }.notification-model-grid { display: grid; grid-template-columns: .9fr 1.1fr; gap: 14px; margin-top: 18px; }.notification-model-card { min-width: 0; padding: 15px; border: 1px solid #e3e9f0; border-radius: 11px; background: #fbfcfe; }.notification-model-card > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }.notification-model-card h3,.notification-model-card p { margin: 0; }.notification-model-card p { margin-top: 4px; color: #7e8a9d; font-size: 11px; line-height: 1.5; }
.template-field-list { display: flex; flex-wrap: wrap; gap: 8px; }.template-field-list button { display: inline-flex; align-items: center; gap: 7px; padding: 6px 9px; border: 1px solid #d9e4f0; border-radius: 7px; color: #344054; background: #f8fbff; cursor: pointer; }.template-field-list button:hover { border-color: #69a5df; background: #eef6ff; }.template-field-list code { color: #4f6f95; }.message-preview { min-height: 180px; max-height: 340px; margin: 0; padding: 16px; overflow: auto; border: 1px solid #dce5ef; border-radius: 9px; color: #26384f; font: 13px/1.75 ui-monospace,SFMono-Regular,Consolas,monospace; white-space: pre-wrap; background: #f7f9fc; }
.diagnostic-panel { min-height: 420px; padding: 4px 2px 12px; }.diagnostic-panel > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 16px; }.diagnostic-panel h3,.diagnostic-panel p { margin: 0; }.diagnostic-panel h3 { color: #263b57; font-size: 17px; }.diagnostic-panel p { margin-top: 5px; color: #78869a; }.diagnostic-query { display: grid; grid-template-columns: minmax(280px,.9fr) minmax(280px,1.1fr) auto; gap: 10px; margin-bottom: 18px; }.diagnostic-result { margin-bottom: 14px; border-radius: 10px; }.diagnostic-stages { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; margin-bottom: 16px; }.diagnostic-stages article { display: flex; gap: 10px; min-height: 78px; padding: 13px; border: 1px solid #fed7aa; border-radius: 10px; background: #fff9f2; }.diagnostic-stages article.passed { border-color: #bbf7d0; background: #f3fcf6; }.diagnostic-stages article > span { display: grid; place-items: center; flex: 0 0 24px; height: 24px; border-radius: 50%; color: #fff; background: #f97316; }.diagnostic-stages article.passed > span { background: #10b981; }.diagnostic-stages strong,.diagnostic-stages small { display: block; }.diagnostic-stages small { margin-top: 5px; color: #69788d; line-height: 1.45; }.diagnostic-conditions { overflow: hidden; border: 1px solid #e3eaf2; border-radius: 11px; }.diagnostic-conditions h4 { margin: 0; padding: 13px 15px; color: #34465f; background: #f7f9fc; }.diagnostic-condition-head,.diagnostic-conditions article { display: grid; grid-template-columns: 1.1fr 1.2fr 1.2fr 90px; align-items: center; gap: 12px; padding: 10px 15px; }.diagnostic-condition-head { color: #8490a2; font-size: 11px; border-top: 1px solid #e8edf3; border-bottom: 1px solid #e8edf3; }.diagnostic-conditions article + article { border-top: 1px solid #edf1f5; }.diagnostic-conditions article strong,.diagnostic-conditions article small { display: block; }.diagnostic-conditions article small { margin-top: 2px; color: #8793a4; }.diagnostic-conditions code { overflow: hidden; color: #344054; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 1180px) { .summary-grid { grid-template-columns: repeat(3,1fr); }.rule-filters,.event-filters,.notification-model-grid { grid-template-columns: repeat(1,1fr); }.monitor-hero { align-items: flex-start; flex-direction: column; }.hero-state { width: 100%; } }
@media (max-width: 700px) { .summary-grid,.rule-filters,.event-filters,.detail-grid,.rule-form-grid,.diagnostic-query,.diagnostic-stages,.event-action-grid { grid-template-columns: 1fr; }.rule-form-grid .span-2 { grid-column: auto; }.hero-state { grid-template-columns: auto 1fr; min-width: 0; }.hero-state .ant-btn { grid-column: 1 / -1; }.condition-list article,.diagnostic-condition-head,.diagnostic-conditions article { grid-template-columns: 1fr; } }
</style>
