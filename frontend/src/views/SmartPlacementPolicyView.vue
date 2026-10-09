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

    <a-modal v-model:open="createOpen" title="新建投放分析机会" width="min(980px, 96vw)" :footer="null" :mask-closable="false">
      <a-form layout="vertical" class="task-form">
        <h3>分析信息</h3>
        <div class="form-grid">
          <a-form-item class="span-2" label="机会名称" required><a-input v-model:value="taskForm.opportunityName" /></a-form-item>
          <a-form-item label="机会来源" required><a-select v-model:value="taskForm.opportunitySource" :options="sourceOptions" /></a-form-item>
          <a-form-item label="分析规则编号"><a-input v-model:value="taskForm.analysisRuleCode" placeholder="人工新建可不填" /></a-form-item>
          <a-form-item label="分析开始日期" required><a-date-picker v-model:value="taskForm.analysisStartDate" value-format="YYYY-MM-DD" /></a-form-item>
          <a-form-item label="分析结束日期" required><a-date-picker v-model:value="taskForm.analysisEndDate" value-format="YYYY-MM-DD" /></a-form-item>
        </div>

        <h3>投放范围</h3>
        <div class="form-grid three">
          <a-form-item label="平台名称" required><a-input v-model:value="taskForm.platformName" /></a-form-item>
          <a-form-item label="平台编码"><a-input v-model:value="taskForm.platformCode" /></a-form-item>
          <a-form-item label="站点名称"><a-input v-model:value="taskForm.siteName" /></a-form-item>
          <a-form-item label="站点编码"><a-input v-model:value="taskForm.siteCode" /></a-form-item>
          <a-form-item label="航司" required><a-input v-model:value="taskForm.airlineCode" placeholder="例如 HO" /></a-form-item>
          <a-form-item label="航程类型"><a-select v-model:value="taskForm.journeyType" :options="journeyOptions" allow-clear /></a-form-item>
          <a-form-item label="出发地"><a-input v-model:value="taskForm.departureCode" placeholder="城市或机场编码" /></a-form-item>
          <a-form-item label="到达地"><a-input v-model:value="taskForm.arrivalCode" placeholder="城市或机场编码" /></a-form-item>
          <a-form-item label="完整航程"><a-input v-model:value="taskForm.routeText" placeholder="例如 PVG-KUL,KUL-PVG" /></a-form-item>
          <a-form-item label="航班号"><a-input v-model:value="taskForm.flightNos" placeholder="多个用英文逗号分隔" /></a-form-item>
          <a-form-item label="包含舱位"><a-input v-model:value="taskForm.includeCabins" placeholder="例如 Y,B,M" /></a-form-item>
          <a-form-item label="排除舱位"><a-input v-model:value="taskForm.excludeCabins" placeholder="例如 X,N；不能与包含舱位重复" /></a-form-item>
          <a-form-item label="产品类型"><a-input v-model:value="taskForm.productType" /></a-form-item>
          <a-form-item label="订单开始日期"><a-date-picker v-model:value="taskForm.orderStartDate" value-format="YYYY-MM-DD" /></a-form-item>
          <a-form-item label="订单结束日期"><a-date-picker v-model:value="taskForm.orderEndDate" value-format="YYYY-MM-DD" /></a-form-item>
          <a-form-item label="起飞开始日期"><a-date-picker v-model:value="taskForm.travelStartDate" value-format="YYYY-MM-DD" /></a-form-item>
          <a-form-item label="起飞结束日期"><a-date-picker v-model:value="taskForm.travelEndDate" value-format="YYYY-MM-DD" /></a-form-item>
        </div>

        <h3>投放建议与价值</h3>
        <div class="form-grid three">
          <a-form-item class="span-2" label="建议投放方式" required><a-input v-model:value="taskForm.placementMethod" /></a-form-item>
          <a-form-item label="优先级" required><a-select v-model:value="taskForm.priority" :options="priorityOptions" /></a-form-item>
          <a-form-item label="建议调整值"><a-input-number v-model:value="taskForm.adjustmentValue" :precision="4" /></a-form-item>
          <a-form-item label="调整单位"><a-select v-model:value="taskForm.adjustmentUnit" :options="adjustmentOptions" allow-clear /></a-form-item>
          <a-form-item label="期望完成时间" required><a-date-picker v-model:value="taskForm.expectedCompleteAt" show-time value-format="YYYY-MM-DD HH:mm:ss" /></a-form-item>
          <a-form-item label="历史票数"><a-input-number v-model:value="taskForm.historicalTicketCount" :min="0" /></a-form-item>
          <a-form-item label="历史航段数"><a-input-number v-model:value="taskForm.historicalSegmentCount" :min="0" /></a-form-item>
          <a-form-item label="历史利润CNY"><a-input-number v-model:value="taskForm.historicalProfitCny" :precision="4" /></a-form-item>
          <a-form-item label="预估月票数"><a-input-number v-model:value="taskForm.estimatedMonthTicketCount" :min="0" /></a-form-item>
          <a-form-item label="预估月利润CNY"><a-input-number v-model:value="taskForm.estimatedMonthProfitCny" :precision="4" /></a-form-item>
          <a-form-item label="建议生效时间"><a-date-picker v-model:value="taskForm.suggestedEffectiveStart" show-time value-format="YYYY-MM-DD HH:mm:ss" /></a-form-item>
          <a-form-item label="建议失效时间"><a-date-picker v-model:value="taskForm.suggestedEffectiveEnd" show-time value-format="YYYY-MM-DD HH:mm:ss" /></a-form-item>
          <a-form-item class="span-3" label="分析结论" required><a-textarea v-model:value="taskForm.analysisConclusion" :rows="3" /></a-form-item>
          <a-form-item class="span-3" label="风险提示"><a-textarea v-model:value="taskForm.riskNote" :rows="2" /></a-form-item>
        </div>
        <div class="modal-actions"><a-button @click="createOpen=false">取消</a-button><a-button :loading="saving" @click="saveTask(false)">保存草稿</a-button><a-button type="primary" :loading="saving" @click="saveTask(true)">提交数据审核</a-button></div>
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
async function saveTask(submit: boolean) {
  saving.value = true
  try { const result = await createPlacementTask({ ...taskForm.value, submit }); message.success(submit ? `任务${result.taskNo}已提交审核` : `草稿${result.taskNo}已保存`); createOpen.value = false; await load(1) }
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
.task-form h3 { margin: 14px 0 12px; padding-bottom: 7px; border-bottom: 1px solid #edf0f4; color: #33415a; font-size: 14px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }.form-grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }.span-2 { grid-column: span 2; }.span-3 { grid-column: span 3; }
.form-grid :deep(.ant-picker), .form-grid :deep(.ant-input-number) { width: 100%; }.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 10px; }.modal-alert { margin-bottom: 16px; }.review-checks { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 16px; }
@media (max-width: 1180px) { .summary-grid { grid-template-columns: repeat(3, 1fr); } .filter-bar { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 760px) { .summary-grid, .form-grid, .form-grid.three, .review-checks { grid-template-columns: 1fr; }.span-2,.span-3 { grid-column: auto; }.filter-bar { grid-template-columns: 1fr 1fr; }.flow-card { overflow-x: auto; } }
</style>
