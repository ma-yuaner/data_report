<template>
  <div class="page-wrap smart-placement-page">
    <PageHeader eyebrow="SMART PLACEMENT" title="投放政策" description="从分析机会、两级审核、政策认领到投放登记的完整协作闭环">
      <a-button type="primary" data-telemetry-code="placement-task-create" data-telemetry-name="新建投放机会" @click="openCreate">新建投放机会</a-button>
    </PageHeader>

    <a-alert type="info" show-icon class="page-alert" message="真实业务流程"
      description="页面连接MySQL智能投放表；当前首版由管理员执行两级经理审核，普通账号可创建、认领和登记本人任务。" />
    <a-alert v-if="error" type="error" show-icon class="page-alert" :message="error" />

    <section class="summary-grid">
      <article v-for="item in summaryCards" :key="item.key" class="summary-card">
        <span>{{ item.label }}</span><strong :class="item.tone">{{ number(data?.summary[item.key] || 0) }}</strong><small>{{ item.note }}</small>
      </article>
    </section>

    <a-card :bordered="false" class="panel-card flow-card">
      <template #title><div class="panel-title"><span>业务流转</span><small>所有审核、认领、执行和关注动作均保留操作日志</small></div></template>
      <a-steps :current="3" size="small" :items="flowSteps" />
    </a-card>

    <a-card :bordered="false" class="panel-card">
      <div class="filter-bar">
        <a-input v-model:value="filters.keyword" allow-clear placeholder="任务编号、机会名称或航程" @press-enter="load(1)" />
        <a-select v-model:value="filters.status" :options="statusFilterOptions" />
        <a-input v-model:value="filters.platform" allow-clear placeholder="平台名称" />
        <a-input v-model:value="filters.airline" allow-clear placeholder="航司编码" />
        <a-button type="primary" :loading="loading" @click="load(1)"><SearchOutlined />查询</a-button>
        <a-button :disabled="loading" @click="resetFilters"><ReloadOutlined />重置</a-button>
      </div>
      <a-table :loading="loading" :columns="columns" :data-source="data?.rows || []" row-key="id" :pagination="pagination" :scroll="{ x: 1500 }" @change="changePage">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'opportunity'">
            <button class="task-link" type="button" @click="openDetail(record)"><strong>{{ record.opportunityName }}</strong><small>{{ record.taskNo }}</small></button>
          </template>
          <template v-else-if="column.key === 'scope'">
            <div class="scope-cell"><strong>{{ record.platformName }}</strong><span>{{ record.siteName || '全部站点' }}</span></div>
          </template>
          <template v-else-if="column.key === 'route'">
            <div class="scope-cell"><strong>{{ record.airlineCode }}</strong><span>{{ record.routeText || routeName(record) }}</span></div>
          </template>
          <template v-else-if="column.key === 'cabins'">
            <div class="scope-cell"><span>包含：{{ record.includeCabins || '不限' }}</span><span class="exclude">排除：{{ record.excludeCabins || '无' }}</span></div>
          </template>
          <template v-else-if="column.key === 'estimate'">
            <div class="scope-cell"><strong>{{ money(record.estimatedMonthProfitCny) }} 元</strong><span>{{ number(record.estimatedMonthTicketCount) }} 票/月</span></div>
          </template>
          <template v-else-if="column.key === 'priority'"><a-tag :color="priorityDisplay(record.priority).color">{{ priorityDisplay(record.priority).label }}</a-tag></template>
          <template v-else-if="column.key === 'status'"><a-tag :color="statusDisplay(record.status).color">{{ statusDisplay(record.status).label }}</a-tag></template>
          <template v-else-if="column.key === 'owner'">{{ record.currentAssigneeName || '—' }}</template>
          <template v-else-if="column.key === 'due'">{{ displayTime(record.expectedCompleteAt) }}</template>
          <template v-else-if="column.key === 'action'">
            <a-space>
              <a-button type="link" size="small" @click="openDetail(record)">详情</a-button>
              <a-button v-if="isReviewable(record)" type="link" size="small" @click="openReview(record)">审核</a-button>
              <a-button v-if="record.status === 'CLAIMABLE'" type="link" size="small" @click="openClaim(record)">认领</a-button>
              <a-button v-if="record.status === 'IN_PROGRESS'" type="link" size="small" @click="openExecution(record)">登记投放</a-button>
              <a-button v-if="record.status === 'MONITORING'" type="link" size="small" @click="router.push('/smart-analysis/placement/orders')">查看收单</a-button>
            </a-space>
          </template>
        </template>
        <template #emptyText><a-empty :description="error || '当前条件没有投放任务'" /></template>
      </a-table>
    </a-card>

    <a-modal
      v-model:open="createOpen"
      title="新建投放机会"
      width="min(1240px, 96vw)"
      wrap-class-name="placement-create-modal"
      :footer="null"
      :mask-closable="false"
    >
      <div class="form-intro">
        <div class="intro-mark">01</div>
        <div class="intro-copy"><strong>填写机会的业务条件与分析依据</strong><span>共 36 个业务字段，10 项必填；每个字段独立录入，选填项留空即表示不限。</span></div>
        <div class="field-legend"><span class="required-dot">必填字段</span><span>选填字段</span></div>
      </div>

      <a-form layout="vertical" class="task-form">
        <section class="form-section">
          <header class="section-heading"><span>1</span><div><h3>分析来源</h3><p>记录机会从哪里发现，以及使用哪段历史数据完成判断。</p></div><em>5 个字段</em></header>
          <div class="form-grid three">
            <PlacementField class="span-2" label="机会名称" required hint="用于任务池与审核列表识别，例如：携程东南亚航线低价机会"><a-input v-model:value="taskForm.opportunityName" placeholder="请输入机会名称" /></PlacementField>
            <PlacementField label="机会来源" required hint="选择本次机会的发现渠道"><a-select v-model:value="taskForm.opportunitySource" :options="sourceOptions" /></PlacementField>
            <PlacementField label="分析规则编号" hint="由规则识别时填写；人工创建可以留空"><a-input v-model:value="taskForm.analysisRuleCode" placeholder="请输入规则编号" /></PlacementField>
            <PlacementField label="分析开始日期" required hint="历史样本统计的起始日期"><a-date-picker v-model:value="taskForm.analysisStartDate" value-format="YYYY-MM-DD" /></PlacementField>
            <PlacementField label="分析结束日期" required hint="历史样本统计的截止日期"><a-date-picker v-model:value="taskForm.analysisEndDate" value-format="YYYY-MM-DD" /></PlacementField>
          </div>
        </section>

        <section class="form-section">
          <header class="section-heading"><span>2</span><div><h3>投放范围</h3><p>名称、编码、航程和舱位分别落库，后续订单匹配直接使用这些字段。</p></div><em>13 个字段</em></header>
          <div class="form-grid three">
            <PlacementField label="平台名称" required hint="例如：携程、同程、去哪儿"><a-input v-model:value="taskForm.platformName" placeholder="请输入平台名称" /></PlacementField>
            <PlacementField label="平台编码" hint="平台在业务系统中的唯一编码"><a-input v-model:value="taskForm.platformCode" placeholder="例如：CTRIP" /></PlacementField>
            <PlacementField label="产品类型" hint="例如：公布转私有、私有运价"><a-input v-model:value="taskForm.productType" placeholder="请输入产品类型" /></PlacementField>
            <PlacementField label="站点名称" hint="例如：乐游携程一部"><a-input v-model:value="taskForm.siteName" placeholder="请输入站点名称" /></PlacementField>
            <PlacementField label="站点编码" hint="站点在业务系统中的编码"><a-input v-model:value="taskForm.siteCode" placeholder="请输入站点编码" /></PlacementField>
            <PlacementField label="航司" required hint="填写二字航司代码，例如：HO"><a-input v-model:value="taskForm.airlineCode" placeholder="请输入航司代码" /></PlacementField>
            <PlacementField label="航程类型" hint="单程、往返或多程"><a-select v-model:value="taskForm.journeyType" :options="journeyOptions" allow-clear placeholder="请选择航程类型" /></PlacementField>
            <PlacementField label="出发地" hint="填写城市或机场三字码"><a-input v-model:value="taskForm.departureCode" placeholder="例如：PVG" /></PlacementField>
            <PlacementField label="到达地" hint="填写城市或机场三字码"><a-input v-model:value="taskForm.arrivalCode" placeholder="例如：KUL" /></PlacementField>
            <PlacementField class="span-3" label="完整航程" hint="多段航程按实际顺序填写，例如：PVG-KUL,KUL-PVG"><a-input v-model:value="taskForm.routeText" placeholder="请输入完整航程" /></PlacementField>
            <PlacementField label="航班号" hint="多个航班号使用英文逗号分隔"><a-input v-model:value="taskForm.flightNos" placeholder="例如：HO1366,HO1365" /></PlacementField>
            <PlacementField label="包含舱位" hint="允许匹配的舱位，例如：Y,B,M"><a-input v-model:value="taskForm.includeCabins" placeholder="请输入包含舱位" /></PlacementField>
            <PlacementField label="排除舱位" hint="明确禁止匹配的舱位，例如：X,N"><a-input v-model:value="taskForm.excludeCabins" placeholder="请输入排除舱位" /></PlacementField>
          </div>
          <div class="field-tip"><strong>舱位规则：</strong>包含舱位与排除舱位不能出现相同值；不限制时保持为空。</div>
        </section>

        <section class="form-section">
          <header class="section-heading"><span>3</span><div><h3>适用时间</h3><p>订单日期控制何时进单，起飞日期控制航班适用范围，政策有效期控制实际投放窗口。</p></div><em>7 个字段</em></header>
          <div class="form-grid three">
            <PlacementField label="订单开始日期" hint="订单进入匹配范围的起始日期"><a-date-picker v-model:value="taskForm.orderStartDate" value-format="YYYY-MM-DD" /></PlacementField>
            <PlacementField label="订单结束日期" hint="订单进入匹配范围的截止日期"><a-date-picker v-model:value="taskForm.orderEndDate" value-format="YYYY-MM-DD" /></PlacementField>
            <PlacementField label="期望完成时间" required hint="投放人员应完成执行登记的时间"><a-date-picker v-model:value="taskForm.expectedCompleteAt" show-time value-format="YYYY-MM-DD HH:mm:ss" /></PlacementField>
            <PlacementField label="起飞开始日期" hint="适用航班的最早起飞日期"><a-date-picker v-model:value="taskForm.travelStartDate" value-format="YYYY-MM-DD" /></PlacementField>
            <PlacementField label="起飞结束日期" hint="适用航班的最晚起飞日期"><a-date-picker v-model:value="taskForm.travelEndDate" value-format="YYYY-MM-DD" /></PlacementField>
            <PlacementField label="建议生效时间" hint="建议政策开始生效的时间"><a-date-picker v-model:value="taskForm.suggestedEffectiveStart" show-time value-format="YYYY-MM-DD HH:mm:ss" /></PlacementField>
            <PlacementField label="建议失效时间" hint="建议政策停止匹配的时间"><a-date-picker v-model:value="taskForm.suggestedEffectiveEnd" show-time value-format="YYYY-MM-DD HH:mm:ss" /></PlacementField>
          </div>
        </section>

        <section class="form-section">
          <header class="section-heading"><span>4</span><div><h3>策略与收益测算</h3><p>明确准备如何投放、历史依据和预估价值，供两级审核判断是否值得执行。</p></div><em>9 个字段</em></header>
          <div class="form-grid three">
            <PlacementField class="span-2" label="建议投放方式" required hint="写清执行动作、范围和测试周期"><a-input v-model:value="taskForm.placementMethod" placeholder="例如：价格下调20元，小流量测试3天" /></PlacementField>
            <PlacementField label="优先级" required hint="用于任务排序和处理时效"><a-select v-model:value="taskForm.priority" :options="priorityOptions" /></PlacementField>
            <PlacementField label="建议调整值" hint="填写具体价格、返点或比例调整数值"><a-input-number v-model:value="taskForm.adjustmentValue" :precision="4" placeholder="请输入数值" /></PlacementField>
            <PlacementField label="调整单位" hint="说明调整值是金额、比例或百分点"><a-select v-model:value="taskForm.adjustmentUnit" :options="adjustmentOptions" allow-clear placeholder="请选择单位" /></PlacementField>
            <div class="metric-hint"><span>口径提示</span><strong>以下均为业务估算值</strong><small>不直接作为财务结算结果</small></div>
            <PlacementField label="历史票数（票）" hint="所选历史样本内的出票票数"><a-input-number v-model:value="taskForm.historicalTicketCount" :min="0" placeholder="请输入票数" /></PlacementField>
            <PlacementField label="历史航段数（段）" hint="所选历史样本内的航段总数"><a-input-number v-model:value="taskForm.historicalSegmentCount" :min="0" placeholder="请输入航段数" /></PlacementField>
            <PlacementField label="历史利润（CNY）" hint="历史样本的业务估算利润"><a-input-number v-model:value="taskForm.historicalProfitCny" :precision="4" placeholder="请输入金额" /></PlacementField>
            <PlacementField label="预估月票数（票）" hint="预计政策每月可匹配的票数"><a-input-number v-model:value="taskForm.estimatedMonthTicketCount" :min="0" placeholder="请输入票数" /></PlacementField>
            <PlacementField label="预估月利润（CNY）" hint="预计政策每月带来的业务利润"><a-input-number v-model:value="taskForm.estimatedMonthProfitCny" :precision="4" placeholder="请输入金额" /></PlacementField>
          </div>
        </section>

        <section class="form-section conclusion-section">
          <header class="section-heading"><span>5</span><div><h3>结论与风险</h3><p>说明为什么值得投放，以及执行过程中需要重点防范什么。</p></div><em>2 个字段</em></header>
          <div class="form-grid one">
            <PlacementField label="分析结论" required hint="说明数据依据、主要发现以及为什么建议投放"><a-textarea v-model:value="taskForm.analysisConclusion" :rows="4" placeholder="请输入分析结论" /></PlacementField>
            <PlacementField label="风险提示" hint="说明航司、舱位、价格、库存或履约风险"><a-textarea v-model:value="taskForm.riskNote" :rows="3" placeholder="请输入风险提示" /></PlacementField>
          </div>
        </section>

        <div class="modal-actions">
          <span>保存草稿不会进入审核流程</span>
          <div><a-button @click="createOpen=false">取消</a-button><a-button :loading="saving" @click="saveTask(false)">保存草稿</a-button><a-button type="primary" :loading="saving" @click="saveTask(true)">提交数据审核</a-button></div>
        </div>
      </a-form>
    </a-modal>

    <a-modal v-model:open="reviewOpen" :title="reviewStage === 'DATA_MANAGER' ? '数据部经理审核' : '政策经理审核'" :confirm-loading="saving" @ok="submitReview">
      <a-alert type="info" show-icon class="modal-alert" :message="activeTask?.opportunityName" :description="`${activeTask?.platformName || ''} · ${activeTask?.airlineCode || ''} · ${activeTask?.routeText || routeName(activeTask)}`" />
      <a-form layout="vertical">
        <a-checkbox-group v-if="reviewStage === 'DATA_MANAGER'" v-model:value="reviewChecks" class="review-checks" :options="reviewCheckOptions" />
        <a-form-item label="审核结果" required><a-select v-model:value="reviewForm.result" :options="reviewResultOptions" /></a-form-item>
        <a-form-item v-if="reviewStage === 'POLICY_MANAGER'" label="政策可执行性"><a-select v-model:value="reviewForm.policyExecutableLevel" :options="executableOptions" /></a-form-item>
        <a-form-item label="风险等级"><a-select v-model:value="reviewForm.riskLevel" :options="priorityOptions" allow-clear /></a-form-item>
        <a-form-item label="审核意见" :required="reviewForm.result !== 'APPROVED'"><a-textarea v-model:value="reviewForm.comment" :rows="3" /></a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="claimOpen" title="认领投放任务" :confirm-loading="saving" @ok="submitClaim">
      <a-form layout="vertical"><a-form-item label="计划完成时间" required><a-date-picker v-model:value="claimForm.plannedCompleteAt" show-time value-format="YYYY-MM-DD HH:mm:ss" /></a-form-item><a-form-item label="认领备注"><a-textarea v-model:value="claimForm.note" :rows="3" /></a-form-item></a-form>
    </a-modal>

    <a-modal v-model:open="executionOpen" title="登记投放结果" width="min(820px, 95vw)" :confirm-loading="saving" @ok="submitExecution">
      <a-form layout="vertical" class="task-form"><div class="form-grid">
        <a-form-item label="投放结果" required><a-select v-model:value="executionForm.result" :options="executionResultOptions" /></a-form-item>
        <a-form-item v-if="executionForm.result === 'SUCCESS'" label="外部政策ID" required><a-input v-model:value="executionForm.externalPolicyId" /></a-form-item>
        <a-form-item v-if="executionForm.result === 'SUCCESS'" label="实际投放时间" required><a-date-picker v-model:value="executionForm.actualPlacementAt" show-time value-format="YYYY-MM-DD HH:mm:ss" /></a-form-item>
        <a-form-item v-if="executionForm.result === 'SUCCESS'" label="生效时间" required><a-date-picker v-model:value="executionForm.effectiveStartAt" show-time value-format="YYYY-MM-DD HH:mm:ss" /></a-form-item>
        <a-form-item v-if="executionForm.result === 'SUCCESS'" label="失效时间" required><a-date-picker v-model:value="executionForm.effectiveEndAt" show-time value-format="YYYY-MM-DD HH:mm:ss" /></a-form-item>
        <a-form-item label="平台名称"><a-input v-model:value="executionForm.platformName" /></a-form-item>
        <a-form-item label="站点名称"><a-input v-model:value="executionForm.siteName" /></a-form-item>
        <a-form-item label="航司"><a-input v-model:value="executionForm.airlineCode" /></a-form-item>
        <a-form-item label="出发地"><a-input v-model:value="executionForm.departureCode" /></a-form-item>
        <a-form-item label="到达地"><a-input v-model:value="executionForm.arrivalCode" /></a-form-item>
        <a-form-item label="航程"><a-input v-model:value="executionForm.routeText" /></a-form-item>
        <a-form-item label="航班号"><a-input v-model:value="executionForm.flightNos" /></a-form-item>
        <a-form-item label="包含舱位"><a-input v-model:value="executionForm.includeCabins" /></a-form-item>
        <a-form-item label="排除舱位"><a-input v-model:value="executionForm.excludeCabins" /></a-form-item>
        <a-form-item label="产品类型"><a-input v-model:value="executionForm.productType" /></a-form-item>
        <a-form-item v-if="executionForm.result === 'FAILED'" label="失败类型" required><a-input v-model:value="executionForm.failureType" /></a-form-item>
        <a-form-item v-if="executionForm.result === 'FAILED'" class="span-2" label="失败原因" required><a-textarea v-model:value="executionForm.failureReason" :rows="3" /></a-form-item>
        <a-form-item v-if="executionForm.result === 'FAILED'" label="重新执行"><a-switch v-model:checked="executionForm.retryRequired" /></a-form-item>
        <a-form-item class="span-2" label="执行说明"><a-textarea v-model:value="executionForm.executionNote" :rows="2" /></a-form-item>
      </div></a-form>
    </a-modal>

    <a-drawer v-model:open="detailOpen" title="投放任务详情" :width="'min(760px, 100vw)'">
      <a-spin :spinning="detailLoading"><template v-if="detail">
        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="任务编号">{{ detail.task.taskNo }}</a-descriptions-item><a-descriptions-item label="状态"><a-tag :color="statusMeta[detail.task.status as PlacementTaskStatus].color">{{ statusMeta[detail.task.status as PlacementTaskStatus].label }}</a-tag></a-descriptions-item>
          <a-descriptions-item label="机会名称" :span="2">{{ detail.task.opportunityName }}</a-descriptions-item>
          <a-descriptions-item label="平台">{{ detail.task.platformName }}</a-descriptions-item><a-descriptions-item label="站点">{{ detail.task.siteName || '全部站点' }}</a-descriptions-item>
          <a-descriptions-item label="航司">{{ detail.task.airlineCode }}</a-descriptions-item><a-descriptions-item label="航程">{{ detail.task.routeText || `${detail.task.departureCode || '不限'}-${detail.task.arrivalCode || '不限'}` }}</a-descriptions-item>
          <a-descriptions-item label="包含舱位">{{ detail.task.includeCabins || '不限' }}</a-descriptions-item><a-descriptions-item label="排除舱位">{{ detail.task.excludeCabins || '无' }}</a-descriptions-item>
          <a-descriptions-item label="建议投放" :span="2">{{ detail.task.placementMethod }}</a-descriptions-item>
          <a-descriptions-item label="分析结论" :span="2">{{ detail.task.analysisConclusion }}</a-descriptions-item>
          <a-descriptions-item label="风险提示" :span="2">{{ detail.task.riskNote || '无' }}</a-descriptions-item>
        </a-descriptions>
        <a-divider>流转记录</a-divider>
        <a-timeline :items="detail.logs.map(log => ({ color: log.toStatus === 'REJECTED' ? 'red' : 'blue', children: `${displayTime(log.createdAt)} · ${log.operatorName} · ${log.operationNote || log.actionCode}` }))" />
      </template></a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import PlacementField from '@/components/PlacementField.vue'
import { useAuthStore } from '@/stores/auth'
import {
  claimPlacementTask, createPlacementTask, executePlacementTask, fetchPlacementTask,
  fetchPlacementTasks, reviewPlacementTask, type PlacementPriority,
  type PlacementTaskDetail, type PlacementTaskInput, type PlacementTaskList,
  type PlacementTaskRow, type PlacementTaskStatus,
} from '@/api/smartPlacement'

const router = useRouter()
const authStore = useAuthStore()
const data = ref<PlacementTaskList>()
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const filters = ref({ keyword: '', status: '', platform: '', airline: '' })
const page = ref(1)
const pageSize = ref(30)
const createOpen = ref(false)
const reviewOpen = ref(false)
const claimOpen = ref(false)
const executionOpen = ref(false)
const detailOpen = ref(false)
const detailLoading = ref(false)
const detail = ref<PlacementTaskDetail>()
const activeTask = ref<PlacementTaskRow>()
const reviewStage = ref<'DATA_MANAGER' | 'POLICY_MANAGER'>('DATA_MANAGER')
const reviewChecks = ref<string[]>(['dataMetricConfirmed', 'sampleSufficient', 'estimatedValueConfirmed'])
const reviewForm = ref({ result: 'APPROVED', comment: '', policyExecutableLevel: 'EXECUTABLE', riskLevel: 'MEDIUM' })
const claimForm = ref({ plannedCompleteAt: '', note: '' })
const executionForm = ref<Record<string, any>>({ result: 'SUCCESS', retryRequired: false })

const statusMeta: Record<PlacementTaskStatus, { label: string; color: string }> = {
  DRAFT: { label: '草稿', color: 'default' }, PENDING_DATA_REVIEW: { label: '待数据审核', color: 'orange' },
  PENDING_POLICY_REVIEW: { label: '待政策审核', color: 'gold' }, CLAIMABLE: { label: '待认领', color: 'blue' },
  IN_PROGRESS: { label: '执行中', color: 'processing' }, MONITORING: { label: '监控中', color: 'green' },
  FAILED: { label: '投放失败', color: 'red' }, REJECTED: { label: '已驳回', color: 'red' },
  CLOSED: { label: '已关闭', color: 'default' }, ENDED: { label: '已结束', color: 'default' },
}
const priorityMeta: Record<PlacementPriority, { label: string; color: string }> = { HIGH: { label: '高', color: 'red' }, MEDIUM: { label: '中', color: 'orange' }, LOW: { label: '低', color: 'blue' } }
const priorityDisplay = (value: unknown) => priorityMeta[String(value) as PlacementPriority] || { label: String(value || '—'), color: 'default' }
const statusDisplay = (value: unknown) => statusMeta[String(value) as PlacementTaskStatus] || { label: String(value || '—'), color: 'default' }
const statusFilterOptions = [{ label: '全部状态', value: '' }, ...Object.entries(statusMeta).map(([value, meta]) => ({ label: meta.label, value }))]
const priorityOptions = Object.entries(priorityMeta).map(([value, meta]) => ({ value, label: meta.label }))
const sourceOptions = [{ value: 'AUTO_ANALYSIS', label: '数据分析规则识别' }, { value: 'MANUAL', label: '人工发现' }, { value: 'MEETING', label: '会议要求' }]
const journeyOptions = [{ value: 'ONE_WAY', label: '单程' }, { value: 'ROUND_TRIP', label: '往返' }, { value: 'MULTI_CITY', label: '多程' }]
const adjustmentOptions = [{ value: 'CNY', label: '人民币金额' }, { value: 'PERCENT', label: '百分比' }, { value: 'OTHER', label: '其他' }]
const reviewResultOptions = [{ value: 'APPROVED', label: '通过' }, { value: 'RETURNED', label: '退回修改' }, { value: 'REJECTED', label: '驳回终止' }]
const executableOptions = [{ value: 'EXECUTABLE', label: '可执行' }, { value: 'CONDITIONAL', label: '有条件执行' }, { value: 'NOT_EXECUTABLE', label: '不可执行' }]
const executionResultOptions = [{ value: 'SUCCESS', label: '投放成功' }, { value: 'FAILED', label: '投放失败' }]
const reviewCheckOptions = [{ value: 'dataMetricConfirmed', label: '数据口径确认' }, { value: 'sampleSufficient', label: '样本充分性确认' }, { value: 'estimatedValueConfirmed', label: '预估价值确认' }]
const flowSteps = [{ title: '分析入池' }, { title: '数据审核' }, { title: '政策审核' }, { title: '政策认领' }, { title: '完成投放' }, { title: '订单匹配' }, { title: '来单关注' }]
const summaryCards: { key: PlacementTaskStatus; label: string; note: string; tone: string }[] = [
  { key: 'PENDING_DATA_REVIEW', label: '待数据经理审核', note: '确认口径和机会价值', tone: 'orange' },
  { key: 'PENDING_POLICY_REVIEW', label: '待政策经理审核', note: '确认政策可执行性', tone: 'orange' },
  { key: 'CLAIMABLE', label: '可认领', note: '审核通过待领取', tone: 'blue' },
  { key: 'IN_PROGRESS', label: '执行中', note: '已认领未完成投放', tone: 'blue' },
  { key: 'MONITORING', label: '监控中', note: '已登记政策并匹配订单', tone: 'green' },
  { key: 'FAILED', label: '投放失败', note: '等待重试或关闭', tone: 'red' },
]
const columns = [
  { title: '投放机会', key: 'opportunity', width: 240, fixed: 'left' as const }, { title: '平台 / 站点', key: 'scope', width: 180 },
  { title: '航司 / 航程', key: 'route', width: 180 }, { title: '舱位条件', key: 'cabins', width: 180 }, { title: '产品', dataIndex: 'productType', width: 130 },
  { title: '预估价值', key: 'estimate', width: 150 }, { title: '优先级', key: 'priority', width: 90 }, { title: '状态', key: 'status', width: 120 },
  { title: '负责人', key: 'owner', width: 110 }, { title: '截止时间', key: 'due', width: 155 }, { title: '操作', key: 'action', width: 235, fixed: 'right' as const },
]
const pagination = computed(() => ({ current: page.value, pageSize: pageSize.value, total: data.value?.total || 0, showSizeChanger: true, showTotal: (total: number) => `共 ${number(total)} 项` }))
const formatter = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const number = (value: number | null | undefined) => new Intl.NumberFormat('zh-CN').format(Number(value || 0))
const money = (value: string | number | null | undefined) => value == null ? '—' : formatter.format(Number(value))
const displayTime = (value: unknown) => value ? String(value).replace('T', ' ').slice(0, 16) : '—'
const routeName = (record?: Partial<PlacementTaskRow>) => [record?.departureCode, record?.arrivalCode].filter(Boolean).join('-') || '不限航程'
function businessToday() { return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }) }
function plusDays(day: string, amount: number) { const value = new Date(`${day}T00:00:00+08:00`); value.setDate(value.getDate() + amount); return value.toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' }) }
function blankTask(): PlacementTaskInput {
  const today = businessToday()
  return { opportunityName: '', opportunitySource: 'MANUAL', analysisRuleCode: '', analysisStartDate: `${today.slice(0, 7)}-01`, analysisEndDate: today, platformCode: '', platformName: '', siteCode: '', siteName: '', airlineCode: '', departureCode: '', arrivalCode: '', routeText: '', journeyType: '', flightNos: '', includeCabins: '', excludeCabins: '', productType: '', orderStartDate: today, orderEndDate: plusDays(today, 7), travelStartDate: today, travelEndDate: plusDays(today, 30), placementMethod: '', adjustmentUnit: 'CNY', analysisConclusion: '', riskNote: '', priority: 'MEDIUM', expectedCompleteAt: `${plusDays(today, 1)} 18:00:00`, suggestedEffectiveStart: `${today} 00:00:00`, suggestedEffectiveEnd: `${plusDays(today, 7)} 23:59:59`, submit: false }
}
const taskForm = ref<PlacementTaskInput>(blankTask())

async function load(targetPage = page.value) {
  loading.value = true; error.value = ''; page.value = targetPage
  try { data.value = await fetchPlacementTasks({ ...filters.value, page: page.value, pageSize: pageSize.value }) }
  catch (failure) { data.value = undefined; error.value = failure instanceof Error ? failure.message : '投放任务查询失败' }
  finally { loading.value = false }
}
function resetFilters() { filters.value = { keyword: '', status: '', platform: '', airline: '' }; void load(1) }
function changePage(value: { current?: number; pageSize?: number }) { const size = value.pageSize || pageSize.value; page.value = size === pageSize.value ? value.current || 1 : 1; pageSize.value = size; void load(page.value) }
function openCreate() { taskForm.value = blankTask(); createOpen.value = true }
function normalizeList(value?: string) { return String(value || '').replace(/，/g, ',').split(',').map(item => item.trim()).filter(Boolean).join(',') }
function validateTaskForm(values: PlacementTaskInput) {
  const required: [keyof PlacementTaskInput, string][] = [
    ['opportunityName', '机会名称'], ['opportunitySource', '机会来源'],
    ['analysisStartDate', '分析开始日期'], ['analysisEndDate', '分析结束日期'],
    ['platformName', '平台名称'], ['airlineCode', '航司'],
    ['placementMethod', '建议投放方式'], ['priority', '优先级'],
    ['expectedCompleteAt', '期望完成时间'], ['analysisConclusion', '分析结论'],
  ]
  const missing = required.find(([key]) => !String(values[key] ?? '').trim())
  if (missing) return `请填写${missing[1]}`
  if (values.analysisEndDate < values.analysisStartDate) return '分析结束日期不能早于开始日期'
  if (values.orderStartDate && values.orderEndDate && values.orderEndDate < values.orderStartDate) return '订单结束日期不能早于开始日期'
  if (values.travelStartDate && values.travelEndDate && values.travelEndDate < values.travelStartDate) return '起飞结束日期不能早于开始日期'
  if (values.suggestedEffectiveStart && values.suggestedEffectiveEnd && values.suggestedEffectiveEnd <= values.suggestedEffectiveStart) return '建议失效时间必须晚于生效时间'
  const included = new Set(normalizeList(values.includeCabins).toUpperCase().split(',').filter(Boolean))
  const excluded = normalizeList(values.excludeCabins).toUpperCase().split(',').filter(Boolean)
  const overlap = excluded.filter(item => included.has(item))
  return overlap.length ? `包含舱位和排除舱位不能重复：${overlap.join(',')}` : ''
}
async function saveTask(submit: boolean) {
  const values = {
    ...taskForm.value,
    flightNos: normalizeList(taskForm.value.flightNos),
    includeCabins: normalizeList(taskForm.value.includeCabins).toUpperCase(),
    excludeCabins: normalizeList(taskForm.value.excludeCabins).toUpperCase(),
  }
  const validationError = validateTaskForm(values)
  if (validationError) { message.warning(validationError); return }
  taskForm.value = values
  saving.value = true
  try { const result = await createPlacementTask({ ...values, submit }); message.success(submit ? `任务${result.taskNo}已提交审核` : `草稿${result.taskNo}已保存`); createOpen.value = false; await load(1) }
  catch (failure) { message.error(failure instanceof Error ? failure.message : '保存失败') }
  finally { saving.value = false }
}
const isReviewable = (row: PlacementTaskRow) => Boolean(authStore.user?.isAdmin) && ['PENDING_DATA_REVIEW', 'PENDING_POLICY_REVIEW'].includes(row.status)
function openReview(row: PlacementTaskRow) { activeTask.value = row; reviewStage.value = row.status === 'PENDING_DATA_REVIEW' ? 'DATA_MANAGER' : 'POLICY_MANAGER'; reviewForm.value = { result: 'APPROVED', comment: '', policyExecutableLevel: 'EXECUTABLE', riskLevel: 'MEDIUM' }; reviewChecks.value = ['dataMetricConfirmed', 'sampleSufficient', 'estimatedValueConfirmed']; reviewOpen.value = true }
async function submitReview() {
  if (!activeTask.value) return; saving.value = true
  try { await reviewPlacementTask(activeTask.value.id, { stage: reviewStage.value, ...reviewForm.value, dataMetricConfirmed: reviewChecks.value.includes('dataMetricConfirmed'), sampleSufficient: reviewChecks.value.includes('sampleSufficient'), estimatedValueConfirmed: reviewChecks.value.includes('estimatedValueConfirmed') }); message.success('审核结果已提交'); reviewOpen.value = false; await load() }
  catch (failure) { message.error(failure instanceof Error ? failure.message : '审核失败') } finally { saving.value = false }
}
function openClaim(row: PlacementTaskRow) { activeTask.value = row; claimForm.value = { plannedCompleteAt: row.expectedCompleteAt, note: '' }; claimOpen.value = true }
async function submitClaim() { if (!activeTask.value) return; saving.value = true; try { await claimPlacementTask(activeTask.value.id, claimForm.value); message.success('任务认领成功'); claimOpen.value = false; await load() } catch (failure) { message.error(failure instanceof Error ? failure.message : '认领失败') } finally { saving.value = false } }
function openExecution(row: PlacementTaskRow) { activeTask.value = row; const today = businessToday(); executionForm.value = { result: 'SUCCESS', retryRequired: false, externalPolicyId: '', actualPlacementAt: `${today} 12:00:00`, effectiveStartAt: `${today} 12:00:00`, effectiveEndAt: `${plusDays(today, 7)} 23:59:59`, platformName: row.platformName, siteName: row.siteName || '', airlineCode: row.airlineCode, departureCode: row.departureCode || '', arrivalCode: row.arrivalCode || '', routeText: row.routeText || '', flightNos: '', includeCabins: row.includeCabins || '', excludeCabins: row.excludeCabins || '', productType: row.productType || '', executionNote: '' }; executionOpen.value = true }
async function submitExecution() { if (!activeTask.value) return; saving.value = true; try { await executePlacementTask(activeTask.value.id, executionForm.value); message.success('投放结果已登记'); executionOpen.value = false; await load() } catch (failure) { message.error(failure instanceof Error ? failure.message : '登记失败') } finally { saving.value = false } }
async function openDetail(row: PlacementTaskRow) { detailOpen.value = true; detailLoading.value = true; detail.value = undefined; try { detail.value = await fetchPlacementTask(row.id) } catch (failure) { message.error(failure instanceof Error ? failure.message : '详情查询失败') } finally { detailLoading.value = false } }
onMounted(() => { void load(1) })
</script>

<style scoped>
:global(.placement-create-modal .ant-modal-content) { overflow: hidden; border: 1px solid #dfe6ef; border-radius: 14px; box-shadow: 0 24px 70px rgba(29,44,68,.22); }
:global(.placement-create-modal .ant-modal-header) { margin-bottom: 0; padding: 20px 24px 15px; border-bottom: 1px solid #edf0f5; }
:global(.placement-create-modal .ant-modal-title) { color: #20324d; font-size: 18px; font-weight: 700; }
:global(.placement-create-modal .ant-modal-body) { max-height: calc(100vh - 130px); overflow-y: auto; padding: 18px 24px 22px; background: #f7f9fc; }
.smart-placement-page { padding-bottom: 34px; }
.page-alert { margin-bottom: 14px; border-radius: 10px; }
.summary-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
.summary-card { padding: 16px 17px; border: 1px solid #e6ebf2; border-radius: 11px; background: #fff; box-shadow: 0 5px 18px rgba(28,45,72,.035); }
.summary-card span, .summary-card small { display: block; color: #7b8798; font-size: 11px; }
.summary-card strong { display: block; margin: 5px 0 2px; color: #26344b; font-size: 24px; }.summary-card strong.orange { color: #d97706; }.summary-card strong.blue { color: #2563eb; }.summary-card strong.green { color: #059669; }.summary-card strong.red { color: #dc2626; }
.panel-card { margin-bottom: 14px; border: 1px solid #e6ebf2 !important; border-radius: 12px; }
.flow-card :deep(.ant-card-body) { padding: 22px 26px; }
.panel-title { display: flex; align-items: center; justify-content: space-between; gap: 10px; }.panel-title small { color: #8a96a9; font-size: 11px; }
.filter-bar { display: grid; grid-template-columns: minmax(220px, 1fr) 170px 150px 120px auto auto; gap: 10px; margin-bottom: 16px; }
.task-link { padding: 0; border: 0; text-align: left; background: transparent; cursor: pointer; }.task-link strong, .task-link small, .scope-cell strong, .scope-cell span { display: block; }.task-link strong { color: #275fae; }.task-link small, .scope-cell span { margin-top: 3px; color: #8290a4; font-size: 11px; }.scope-cell .exclude { color: #c15b69; }
.form-intro { display: flex; align-items: center; gap: 14px; margin: 0 0 18px; padding: 14px 16px; border: 1px solid #cfe0fb; border-radius: 12px; background: linear-gradient(135deg,#f5f9ff,#fbfdff); }
.intro-mark { display: grid; flex: 0 0 42px; height: 42px; place-items: center; border-radius: 11px; color: #fff; font-weight: 700; background: #2867b7; box-shadow: 0 6px 14px rgba(40,103,183,.2); }.form-intro strong,.form-intro span { display: block; }.form-intro strong { color: #24354f; font-size: 14px; }.form-intro span { margin-top: 3px; color: #718096; font-size: 12px; line-height: 1.6; }
.intro-copy { min-width: 0; }.field-legend { display: flex; flex: none; gap: 8px; margin-left: auto; }.form-intro .field-legend span { position: relative; margin: 0; padding: 4px 9px 4px 18px; border: 1px solid #dfe6ef; border-radius: 999px; color: #758296; background: #fff; font-size: 10px; }.form-intro .field-legend span::before { position: absolute; top: 50%; left: 8px; width: 5px; height: 5px; border-radius: 50%; background: #a5afbd; transform: translateY(-50%); content: ''; }.form-intro .field-legend .required-dot { border-color: #f0c8cc; color: #b5424f; background: #fff8f8; }.form-intro .field-legend .required-dot::before { background: #d85866; }
.task-form { display: grid; gap: 14px; }.form-section { padding: 18px 20px 20px; border: 1px solid #e4eaf2; border-radius: 12px; background: #fff; }.form-section:nth-of-type(even) { background: #fbfcfe; }
.section-heading { display: flex; align-items: flex-start; gap: 11px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #edf1f6; }.section-heading > span { display: grid; flex: 0 0 27px; height: 27px; place-items: center; border-radius: 8px; color: #2867b7; font-size: 12px; font-weight: 700; background: #eaf2ff; }.section-heading > div { min-width: 0; }.section-heading h3 { margin: 1px 0 0; color: #253752; font-size: 15px; line-height: 1.3; }.section-heading p { margin: 4px 0 0; color: #8793a5; font-size: 11px; line-height: 1.5; }.section-heading em { flex: none; margin-left: auto; padding: 4px 8px; border-radius: 999px; color: #6e7f96; background: #f0f4f9; font-size: 10px; font-style: normal; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }.form-grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }.form-grid.one { grid-template-columns: 1fr; }.span-2 { grid-column: span 2; }.span-3 { grid-column: span 3; }
.task-form :deep(.ant-form-item) { margin-bottom: 16px; }.task-form :deep(.ant-form-item-label) { min-height: 29px; padding-bottom: 6px; }.task-form :deep(.ant-form-item-label > label) { height: auto; color: #46546a; font-size: 12px; font-weight: 600; }.task-form :deep(.ant-input),.task-form :deep(.ant-input-number),.task-form :deep(.ant-picker),.task-form :deep(.ant-select) { width: 100%; }.task-form :deep(.ant-input),.task-form :deep(.ant-picker),.task-form :deep(.ant-input-number),.task-form :deep(.ant-select-selector) { min-height: 38px; border-radius: 7px !important; }.task-form :deep(.ant-input-number-input) { height: 36px; }.task-form :deep(textarea.ant-input) { min-height: auto; padding-top: 9px; line-height: 1.65; }
.field-tip { margin: 12px 0 0; padding: 9px 12px; border-left: 3px solid #d79d30; border-radius: 4px 8px 8px 4px; color: #7d6840; font-size: 11px; background: #fff9ed; }.metric-hint { align-self: stretch; min-height: 100px; padding: 13px; border: 1px dashed #c8d8ee; border-radius: 10px; background: #f4f8fe; }.metric-hint span,.metric-hint strong,.metric-hint small { display: block; }.metric-hint span { color: #6f86a8; font-size: 10px; }.metric-hint strong { margin: 7px 0 3px; color: #355a8e; font-size: 13px; }.metric-hint small { color: #8b98aa; font-size: 10px; }.conclusion-section { padding-bottom: 20px; }
.modal-actions { position: sticky; bottom: 0; z-index: 2; display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 2px -2px -2px; padding: 14px 2px 2px; border-top: 1px solid #e7ecf3; background: rgba(255,255,255,.96); }.modal-actions > span { color: #8a96a8; font-size: 11px; }.modal-actions > div { display: flex; gap: 8px; }.modal-alert { margin-bottom: 16px; }.review-checks { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }
@media (max-width: 1180px) { .summary-grid { grid-template-columns: repeat(3, 1fr); } .filter-bar { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 820px) { .form-grid,.form-grid.three { grid-template-columns: repeat(2,minmax(0,1fr)); }.span-3 { grid-column: span 2; }.grid-placeholder { display: none; } }
@media (max-width: 600px) { .summary-grid, .form-grid, .form-grid.three, .review-checks { grid-template-columns: 1fr; }.span-2,.span-3 { grid-column: auto; }.filter-bar { grid-template-columns: 1fr 1fr; }.flow-card { overflow-x: auto; }.form-section { padding: 15px 14px; }.form-intro { align-items: flex-start; }.field-legend { display: none; }.modal-actions { align-items: stretch; flex-direction: column; }.modal-actions > div { display: grid; grid-template-columns: repeat(3,1fr); } }
</style>
