<template>
  <div class="v05-app embedded">
    <main class="v05-main">
      <section v-if="isWorkbench" class="v05-page">
        <header class="v05-top">
          <div>
            <h1>我的工作台</h1>
            <p>{{ roleHint }}</p>
          </div>
          <div class="v05-actions">
            <button :disabled="!canOperatorWork" @click="claimAndExport">
              接单并导出（{{ exportableIds.length }}）</button
            ><button v-if="canOperatorWork" @click="operatorImportOpen = true">导入处理结果</button
            ><button :disabled="loading" @click="load">刷新任务</button>
          </div>
        </header>
        <div class="v05-metrics">
          <button
            v-for="item in workMetrics"
            :key="item.key"
            :class="{ selected: workMetric === item.key }"
            @click="workMetric = workMetric === item.key ? '' : item.key"
          >
            <span>{{ item.title }}</span
            ><strong>{{ item.value }}</strong>
          </button>
        </div>
        <a-alert v-if="error" type="error" show-icon :message="error" style="margin-top: 16px" />
        <div class="v05-work-list">
          <article v-for="task in visibleTasks" :key="`${task.caseId}-${task.lineId}-${task.kind}`">
            <div>
              <b>{{ task.internalNo }} / {{ task.lineInternalNo }}</b
              ><span>{{ task.role }}任务：{{ task.title }}</span>
            </div>
            <dl>
              <div>
                <dt>任务来源</dt>
                <dd>{{ task.previous }}</dd>
              </div>
              <div>
                <dt>下一步</dt>
                <dd>{{ task.next }}</dd>
              </div>
            </dl>
            <div class="v05-due">
              <small>处理截止</small><b :class="{ danger: task.overdue }">{{ task.deadline || '未设置' }}</b
              ><button class="primary" @click="openTask(task)">去处理 →</button>
            </div>
          </article>
          <div v-if="!loading && !visibleTasks.length" class="v05-card v05-empty">
            {{ workMetric ? '当前筛选下没有待办任务' : '当前账号暂无需要处理的ADM任务' }}
          </div>
        </div>
      </section>

      <section v-else class="v05-page">
        <header class="v05-top">
          <div>
            <h1>ADM 台账</h1>
            <p>查看公司 ADM 全貌、处理进度、结案阻断与当前风险。</p>
          </div>
          <div class="v05-actions">
            <button :disabled="!canCreate" @click="openImport">跨主单批量导入</button
            ><button :disabled="!canCreate" class="primary" @click="openCreate">＋ 新建 ADM</button>
          </div>
        </header>
        <p class="v05-label">主单指标 · 点击筛选台账</p>
        <div class="v05-metrics">
          <button
            v-for="item in masterMetrics"
            :key="item.key"
            :class="{ selected: metric === item.key }"
            @click="selectMetric(item.key)"
          >
            <span>{{ item.title }}</span
            ><strong>{{ item.value }}</strong>
          </button>
        </div>
        <p class="v05-label">订单指标 · 点击查看订单清单</p>
        <div class="v05-metrics">
          <button
            v-for="item in orderMetrics"
            :key="item.key"
            :class="{ selected: orderMetric === item.key }"
            @click="openGlobalOrders(item.key)"
          >
            <span>{{ item.title }}</span
            ><strong>{{ item.value }}</strong>
          </button>
        </div>
        <a-alert v-if="error" type="error" show-icon :message="error" style="margin-top: 16px" />
        <div class="v05-card">
          <div class="v05-toolbar">
            <label
              >⌕<input v-model="filters.search" placeholder="搜索 ADM 单号、内部主单编号、下发方" @keyup.enter="query"
            /></label>
            <div>
              <select v-model="filters.status" @change="query">
                <option value="">全部状态</option>
                <option v-for="status in config?.caseStatuses || []" :key="status" :value="status">
                  {{ label(status) }}
                </option></select
              ><button @click="resetFilters">重置</button>
            </div>
          </div>
          <div class="v05-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ADM 单号 / 下发方</th>
                  <th>金额</th>
                  <th>处理截止</th>
                  <th>订单进度</th>
                  <th>阶段分布</th>
                  <th>当前状态</th>
                  <th>结案阻断</th>
                  <th>风险标签</th>
                  <th>最近更新</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="record in visibleRows" :key="record.id">
                  <td>
                    <button class="link" @click="openCase(record.id)">{{ record.admNo }}</button
                    ><small>{{ label(record.issuerType) }} · {{ record.issuerName }}</small
                    ><small>系统记录：{{ record.internalNo }}</small>
                  </td>
                  <td>
                    <b>{{ record.currency }} {{ record.originalAmount }}</b
                    ><small>折合人民币 ¥ {{ record.cnyAmount }}</small>
                  </td>
                  <td>
                    {{ dateText(record.replyDeadline) }}<small>{{ riskText(record) }}</small>
                  </td>
                  <td>
                    <div class="progress"><i :style="{ width: progressWidth(record) }"></i></div>
                    <small>{{ Number(record.completedLineCount || 0) }} / {{ activeLineCount(record) }} 已完成</small>
                  </td>
                  <td>
                    <div class="stage-list">
                      <span v-for="stage in stageSummary(record.id)" :key="stage.label"
                        ><i></i>{{ stage.label }}<b>{{ stage.count }}</b></span
                      >
                    </div>
                  </td>
                  <td>
                    <span :class="['pill', statusTone(record.caseStatus)]">● {{ label(record.caseStatus) }}</span>
                  </td>
                  <td>{{ blockerText(record.id) }}</td>
                  <td>
                    <span :class="['pill', riskTone(record)]">{{ riskText(record) }}</span>
                  </td>
                  <td>{{ dateText(record.updatedAt) }}</td>
                  <td>
                    <div class="record-actions master-record-actions">
                      <button class="primary" @click="openCase(record.id)">{{ canEditMasterRow(record) ? '编辑完整处理记录' : '查看完整处理记录' }}</button>
                      <button @click="openMasterInfo(record)">{{ canEditMasterRow(record) ? '编辑基础信息' : '查看基础信息' }}</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="!loading && !visibleRows.length" class="empty">暂无符合条件的 ADM 主单</div>
          </div>
          <div class="v05-pager">
            <a-pagination
              v-model:current="page"
              v-model:page-size="pageSize"
              :total="total"
              show-size-changer
              @change="load"
            />
          </div>
        </div>
      </section>
    </main>

    <AdmMasterBasicModal :open="masterInfoOpen" :detail="selectedMasterDetail" :editable="selectedMasterEditable" @close="masterInfoOpen = false" @saved="masterInfoSaved" />

    <a-modal
      v-model:open="globalOrdersOpen"
      :title="`订单清单 · ${orderMetrics.find((item) => item.key === orderMetric)?.title || '全部订单明细'}`"
      width="1180px"
      :footer="null"
      wrap-class-name="v05-modal"
      ><div class="v05-table-wrap global-order-table">
        <table>
          <thead>
            <tr>
              <th>ADM单号 / 内部明细</th>
              <th>票号 / OTA订单号 / PNR</th>
              <th>业务部门 / 组长</th>
              <th>操作人员</th>
              <th>当前状态</th>
              <th>当前任务</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in globalOrders" :key="item.line.id">
              <td>
                <b>{{ item.detail.case.admNo }}</b
                ><small>{{ item.line.lineInternalNo }}</small>
              </td>
              <td>
                {{ item.line.ticketNo || '未填写票号'
                }}<small>OTA：{{ item.line.otaOrderNo || '未填写' }} · PNR：{{ item.line.pnr || '未填写' }}</small>
              </td>
              <td>
                {{ item.line.departmentName }}<small>组长：{{ item.line.leaderName || '未分配' }}</small>
              </td>
              <td>{{ item.line.operatorName || '未分配' }}</td>
              <td>
                <span :class="['pill', lineStatusTone(item.line.lineStatus)]">{{ label(item.line.lineStatus) }}</span>
              </td>
              <td>{{ lineTask(item.line.lineStatus) }}</td>
              <td>
                <button class="primary" @click="openGlobalLine(item.detail.case.id, item.line.id)">查看详情</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!globalOrders.length" class="empty">当前指标下没有订单明细</p>
      </div></a-modal
    >
    <a-modal v-model:open="operatorImportOpen" title="导入处理结果" :footer="null" wrap-class-name="v05-modal"
      ><p class="context">
        回传从本人工作台导出的单 Sheet Excel；系统按内部明细编号、当前操作员和数据版本校验，不接受新增订单行。
      </p>
      <div class="import-zone">
        <b>⇧<br />上传操作人员处理结果</b>
        <p>支持 .xlsx；导入前先预检，存在错误时不会写入业务数据。</p>
        <input type="file" accept=".xlsx" @change="selectOperatorImport" />
      </div>
      <a-alert
        v-if="operatorImportNotice"
        :type="operatorImportPreview?.canCommit ? 'success' : 'error'"
        show-icon
        :message="operatorImportNotice"
        style="margin-top: 14px"
      />
      <div v-if="operatorImportPreview?.rows?.length" class="v05-table-wrap">
        <table>
          <thead>
            <tr>
              <th>Excel行</th>
              <th>内部明细</th>
              <th>处理动作</th>
              <th>预检状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in operatorImportPreview.rows" :key="item.rowNumber">
              <td>{{ item.rowNumber }}</td>
              <td>{{ item.lineInternalNo }}</td>
              <td>{{ item.action }}</td>
              <td>{{ item.status }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="v05-modal-actions">
        <button @click="operatorImportOpen = false">取消</button
        ><button :disabled="!operatorImportFile || operatorImportBusy" @click="previewOperatorImport">预检文件</button
        ><button
          class="primary"
          :disabled="!operatorImportPreview?.canCommit || operatorImportBusy"
          @click="commitOperatorImport"
        >
          确认提交
        </button>
      </div></a-modal
    >
    <a-modal
      v-model:open="createOpen"
      :title="createStep === 1 ? '新建 ADM 主单' : '录入订单明细'"
      width="1180px"
      :footer="null"
      wrap-class-name="v05-modal"
      ><a-alert
        type="info"
        show-icon
        message="先填写主单，再录入一笔或多笔订单；明细金额合计必须等于主单金额。"
        style="margin-bottom: 16px"
      /><a-alert
        v-if="referenceError"
        type="warning"
        show-icon
        :message="referenceError"
        style="margin-bottom: 16px"
      /><template v-if="createStep === 1"
        ><div class="v05-form-grid">
          <label>ADM 单号 *<a-input v-model:value="form.admNo" /></label
          ><label
            >下发方类型 *<a-select
              v-model:value="form.issuerType"
              :options="issuerOptions"
              @change="issuerChanged" /></label
          ><label v-if="form.issuerType === 'AIRLINE'">航司名称 *<a-input v-model:value="form.issuerName" /></label
          ><label v-else
            >下发方 *<a-select
              v-model:value="form.issuerCode"
              show-search
              :filter-option="filterOption"
              :options="issuerMasterOptions"
              @change="issuerSelected" /></label
          ><label
            >原币币种 *<a-select
              v-model:value="form.currency"
              :options="currencyOptions"
              @change="loadExchangeRate" /></label
          ><label>原币总金额 *<a-input v-model:value="form.originalAmount" /></label
          ><label
            >换算汇率（对人民币）<a-input
              :value="fxLoading ? '读取中…' : fxSnapshot?.rateValue || '暂无可用汇率'"
              readonly /></label
          ><label>人民币总金额<a-input :value="masterCnyAmount" readonly /></label
          ><label
            >汇率日期 / 来源<a-input
              :value="fxSnapshot ? `${fxSnapshot.sourceUpdatedAt || '即时'} / ${fxSnapshot.actualSource}` : '—'"
              readonly /></label
          ><label>下发日期 *<a-input v-model:value="form.issuedDate" type="date" /></label
          ><label>处理截止 *<a-input v-model:value="form.replyDeadline" type="datetime-local" /></label
          ><label class="wide">备注（选填）<a-textarea v-model:value="form.remark" :rows="2" /></label
          ><label class="wide"
            >主单公共附件（选填）<input type="file" multiple @change="pickMasterFiles" /><span>{{
              masterFiles.map((file) => file.name).join('、') || '未选择附件'
            }}</span></label
          >
        </div>
        <p class="hint"><b>*</b> 为必填项。ADM负责人由系统自动记录；汇率保存为创建时快照。</p>
        <div class="v05-modal-actions">
          <button @click="createOpen = false">取消</button
          ><button class="primary" @click="createStep = 2">保存并录入订单</button>
        </div></template
      >
      <template v-else
        ><p class="context">
          <b>{{ form.admNo }}</b
          > {{ form.issuerName }} 原币总金额 {{ form.currency }} {{ form.originalAmount }} 处理截止
          {{ form.replyDeadline || '未设置' }}
        </p>
        <p class="v05-label">订单明细 · OTA平台、OTA订单号、供应商、航司、票号、PNR均为选填</p>
        <div v-for="(line, index) in form.lines" :key="line.key" class="v05-line-card">
          <header>
            <b>订单明细 {{ Number(index) + 1 }}</b
            ><button v-if="form.lines.length > 1" class="danger" @click="form.lines.splice(Number(index), 1)">
              移除
            </button>
          </header>
          <div class="v05-form-grid">
            <label>OTA订单号（选填）<a-input v-model:value="line.otaOrderNo" /></label
            ><label>票号（选填）<a-input v-model:value="line.ticketNo" /></label
            ><label>PNR编码（选填）<a-input v-model:value="line.pnr" /></label
            ><label
              >OTA平台（选填）<a-select
                v-model:value="line.otaCode"
                allow-clear
                :options="otaOptions"
                @change="(v?: string) => selectOption(line, 'ota', v)" /></label
            ><label
              >业务归属部门 *<a-select
                v-model:value="line.departmentCode"
                show-search
                :filter-option="filterOption"
                :options="departmentOptions"
                @change="(v: string) => selectOption(line, 'department', v)" /></label
            ><label
              >负责组长 *<a-select
                v-model:value="line.leaderId"
                :options="leaderOptions"
                @change="(v: string) => selectLeader(line, v)" /></label
            ><label>截止时间（继承主单）<a-input :value="form.replyDeadline" readonly /></label
            ><label
              >供应商（选填）<a-select
                v-model:value="line.supplierCode"
                allow-clear
                :options="supplierOptions"
                @change="(v?: string) => selectOption(line, 'supplier', v)" /></label
            ><label>航司（选填）<a-input v-model:value="line.airlineName" /></label
            ><label>ADM金额（原币） *<a-input v-model:value="line.originalAmount" /></label
            ><label>币种（继承主单）<a-input :value="form.currency" readonly /></label
            ><label>ADM金额（人民币，系统换算）<a-input :value="lineCnyAmount(Number(index))" readonly /></label
            ><label class="wide"
              >订单情况说明（选填）<a-textarea
                v-model:value="line.investigationNote"
                :rows="2"
                placeholder="填写当前已知的订单情况，操作员办理时可继续更新" /></label
            ><label
              >差异类型 *<a-select
                v-model:value="line.diffTypeCode"
                show-search
                :filter-option="filterOption"
                :options="diffTypeOptions"
                @change="(v: string) => selectOption(line, 'diffType', v)" /></label
            ><label class="wide">细分差异原因 *<a-textarea v-model:value="line.differenceReason" :rows="3" /></label>
          </div>
        </div>
        <section class="entry-extra">
          <h3>本次已录入 {{ form.lines.length }} 笔</h3>
          <div class="v05-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>序号</th>
                  <th>OTA订单号 / 票号 / PNR</th>
                  <th>部门 / 组长</th>
                  <th>原币金额</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, index) in form.lines" :key="`summary-${line.key}`">
                  <td>{{ Number(index) + 1 }}</td>
                  <td>
                    {{ line.otaOrderNo || '未填写' }} / {{ line.ticketNo || '未填写' }} / {{ line.pnr || '未填写' }}
                  </td>
                  <td>{{ line.departmentName || '未选择' }} / {{ line.leaderName || '未选择' }}</td>
                  <td>{{ form.currency }} {{ line.originalAmount || '0.00' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <a-alert v-if="createError" type="error" show-icon :message="createError" style="margin-top: 12px" />
        <div class="v05-modal-actions">
          <button @click="createStep = 1">返回主单</button><button @click="addLine">＋ 继续新增一笔</button
          ><button :disabled="saving" @click="createCase(true)">保存草稿</button
          ><button class="primary" :disabled="saving" @click="createCase(false)">保存并进入详情</button>
        </div></template
      >
    </a-modal>
    <a-modal
      v-model:open="importOpen"
      title="跨主单批量导入（19列）"
      :confirm-loading="importBusy"
      :ok-button-props="{ disabled: !preview?.canCommit }"
      @ok="commitImport"
      wrap-class-name="v05-modal"
      ><p>一行一笔订单；同号但不同主单请拆成两次上传。系统先预检，通过后再正式建单。</p>
      <div class="v05-actions">
        <button @click="downloadTemplate">下载 Excel 模板</button
        ><input type="file" accept=".xlsx" @change="selectImport" /><button
          :disabled="!importFile"
          @click="previewImport"
        >
          预检文件
        </button>
      </div>
      <a-alert
        v-if="preview"
        :type="preview.canCommit ? 'success' : 'warning'"
        show-icon
        :message="`共 ${preview.totalRows} 行，有效 ${preview.validRows} 行，错误 ${preview.failedRows} 行`"
        style="margin-top: 14px" />
      <p v-for="item in preview?.groups || []" :key="item.firstRow">
        第 {{ item.firstRow }} 行 · {{ item.admNo || '未识别' }} · {{ item.status }} {{ item.message || '' }}
      </p>
      <a-alert v-if="importError" type="error" show-icon :message="importError"
    /></a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import { useComprehensiveExportStore } from '@/stores/comprehensiveExports'
import { createOperationIdentifier } from '@/utils/operationIdentifier'
import AdmMasterBasicModal from './AdmMasterBasicModal.vue'
import {
  admApi,
  errorText,
  label,
  saveBlob,
  type AdmCaseDetail,
  type AdmCaseRow,
  type AdmConfig,
  type Fields,
  type FxSnapshot,
  type Option,
} from './api'
import './adm-v05.css'

const route = useRoute(),
  router = useRouter(),
  auth = useAuthStore(),
  exportTasks = useComprehensiveExportStore(),
  isWorkbench = computed(() => route.meta.admView === 'workbench')
const config = ref<AdmConfig | null>(null),
  rows = ref<AdmCaseRow[]>([]),
  details = ref<AdmCaseDetail[]>([]),
  loading = ref(false),
  error = ref(''),
  page = ref(1),
  pageSize = ref(20),
  total = ref(0),
  metric = ref(''),
  orderMetric = ref(''),
  workMetric = ref('')
const masterInfoOpen = ref(false),
  selectedMasterDetail = ref<AdmCaseDetail | null>(null),
  selectedMasterEditable = ref(false)
const filters = reactive({ search: '', status: '' })
async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await admApi.list({
      search: filters.search,
      status: filters.status,
      activeOnly: isWorkbench.value,
      page: page.value,
      pageSize: isWorkbench.value ? 100 : pageSize.value,
    })
    rows.value = result.items
    total.value = result.pagination.total
    details.value = isWorkbench.value
      ? await Promise.all(rows.value.map((item) => admApi.detail(item.id)))
      : []
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loading.value = false
  }
}
function query() {
  page.value = 1
  void load()
}
function resetFilters() {
  filters.search = ''
  filters.status = ''
  metric.value = ''
  query()
}
const myId = computed(() => Number(auth.user?.id)),
  now = () => Date.now(),
  dateText = (v: unknown) => (v ? String(v).replace('T', ' ').slice(0, 16) : '—')
const taskKind = (s: string) =>
  (
    ({
      PENDING_LEADER: 'assignLeader',
      PENDING_OPERATOR: 'assign',
      PENDING_ACCEPT: 'accept',
      PROCESSING: 'process',
      PENDING_REVIEW: 'review',
      WAITING_DIFF: 'diff',
      WAITING_COLLECTION: 'collection',
    }) as Fields
  )[s] || 'other'
const availableRoles = computed(() => {
  if (auth.user?.isAdmin) return ['ADM负责人', '组长', '操作人员']
  const p = config.value?.permissions,
    roles: string[] = []
  if (p?.review || p?.create || p?.collection || p?.close || p?.assignLeader) roles.push('ADM负责人')
  if (p?.assign || p?.assignOperator) roles.push('组长')
  if (p?.handle) roles.push('操作人员')
  return roles
})
const tasks = computed(() =>
  details.value.flatMap((detail) =>
    detail.lines
      .filter((line) => {
        const admin = !!auth.user?.isAdmin,
          p = config.value?.permissions || {},
          mineCoordinator = admin || Number(detail.case.coordinatorId) === myId.value,
          mineLeader = admin || Number(line.leaderId) === myId.value,
          mineOperator = admin || Number(line.operatorId) === myId.value
        return (
          ((admin || p.review || p.collection || p.close || p.assignLeader) &&
            mineCoordinator &&
            ['PENDING_LEADER', 'PENDING_REVIEW', 'WAITING_DIFF', 'WAITING_COLLECTION'].includes(line.lineStatus)) ||
          ((admin || p.assign || p.assignOperator) && mineLeader && line.lineStatus === 'PENDING_OPERATOR') ||
          ((admin || p.handle) && mineOperator && ['PENDING_ACCEPT', 'PROCESSING'].includes(line.lineStatus))
        )
      })
      .map((line) => {
        const role = ['PENDING_LEADER', 'PENDING_REVIEW', 'WAITING_DIFF', 'WAITING_COLLECTION'].includes(
          line.lineStatus,
        )
          ? 'ADM负责人'
          : line.lineStatus === 'PENDING_OPERATOR'
            ? '组长'
            : '操作人员'
        return {
          caseId: detail.case.id,
          lineId: line.id,
          operatorId: line.operatorId,
          internalNo: detail.case.internalNo,
          lineInternalNo: line.lineInternalNo,
          status: line.lineStatus,
          recoveryStatus: line.recoveryStatus,
          appealStatus: line.appealStatus,
          role,
          kind: taskKind(line.lineStatus),
          title: (
            {
              PENDING_LEADER: '分配负责组长',
              PENDING_OPERATOR: '分配操作人员',
              PENDING_ACCEPT: '确认接单',
              PROCESSING: '办理订单',
              PENDING_REVIEW: 'ADM负责人审核',
              WAITING_DIFF: '匹配差异单',
              WAITING_COLLECTION: '登记回款',
            } as Fields
          )[line.lineStatus],
          previous: `${line.departmentName} · ${line.leaderName || '未分配组长'} · ${line.operatorName || '未分配操作员'}`,
          next: (
            {
              PENDING_LEADER: '组长分配操作人员',
              PENDING_OPERATOR: '操作员接单',
              PENDING_ACCEPT: '进入订单办理',
              PROCESSING: '提交ADM负责人审核',
              PENDING_REVIEW: '通过或退回原操作员',
              WAITING_DIFF: '匹配后进入回款或完成',
              WAITING_COLLECTION: '累计回款完成',
            } as Fields
          )[line.lineStatus],
          deadline: detail.case.replyDeadline,
          overdue: !!detail.case.replyDeadline && new Date(detail.case.replyDeadline).getTime() < now(),
        }
      }),
  ),
)
const dueKind = (t: Fields) => {
  if (!t.deadline) return 'normal'
  const d = new Date(t.deadline).getTime() - now()
  return d < 0 ? 'late' : d < 86400000 ? 'soon' : 'normal'
}
const roleHint = computed(() =>
  availableRoles.value.length
    ? '合并展示当前账号需要处理的全部ADM任务，每笔任务标明本次办理职责。'
    : '当前账号仅有查看权限，可前往ADM台账查看数据。',
)
const workMetrics = computed(() => {
  const due = (k: string) => tasks.value.filter((t) => dueKind(t) === k).length,
    items: Fields[] = []
  if (availableRoles.value.includes('ADM负责人'))
    items.push(
      { key: 'assignLeader', title: '待分配组长', value: tasks.value.filter((t) => t.kind === 'assignLeader').length },
      { key: 'review', title: '待审核', value: tasks.value.filter((t) => t.kind === 'review').length },
      { key: 'collection', title: '待回款跟进', value: tasks.value.filter((t) => t.kind === 'collection').length },
      {
        key: 'close',
        title: '可以结案',
        value: details.value.filter(
          (d) => d.case.caseStatus === 'ACTIVE' && d.lines.every((l) => ['COMPLETED', 'VOIDED'].includes(l.lineStatus)),
        ).length,
      },
    )
  if (availableRoles.value.includes('组长'))
    items.push(
      { key: 'assign', title: '待分配操作员', value: tasks.value.filter((t) => t.kind === 'assign').length },
      {
        key: 'transfer',
        title: '转派申请',
        value: details.value.flatMap((d) => d.transfers || []).filter((t) => t.status === 'PENDING').length,
      },
    )
  if (availableRoles.value.includes('操作人员'))
    items.push(
      { key: 'accept', title: '待接单', value: tasks.value.filter((t) => t.kind === 'accept').length },
      { key: 'process', title: '本人待办理', value: tasks.value.filter((t) => t.kind === 'process').length },
      {
        key: 'codeReminder',
        title: '编码恢复提醒',
        value: allLines.value.filter((l) => l.recoveryStatus === 'REMINDER_DUE' && Number(l.operatorId) === myId.value)
          .length,
      },
      {
        key: 'appeal',
        title: '申诉中',
        value: allLines.value.filter((l) => l.appealStatus === 'IN_PROGRESS' && Number(l.operatorId) === myId.value)
          .length,
      },
    )
  items.push(
    { key: 'soon', title: '即将超时', value: due('soon') },
    { key: 'late', title: '已超时', value: due('late') },
  )
  return items
})
const visibleTasks = computed(() => {
  if (!workMetric.value) return tasks.value
  if (['soon', 'late'].includes(workMetric.value)) return tasks.value.filter((t) => dueKind(t) === workMetric.value)
  if (workMetric.value === 'codeReminder') return tasks.value.filter((t) => t.recoveryStatus === 'REMINDER_DUE')
  if (workMetric.value === 'appeal') return tasks.value.filter((t) => t.appealStatus === 'IN_PROGRESS')
  const aliases: Fields = { close: 'close' }
  return tasks.value.filter((t) => t.kind === (aliases[workMetric.value] || workMetric.value))
})
function openTask(t: Fields) {
  void router.push({ path: `/adm/cases/${t.caseId}`, query: { lineId: t.lineId } })
}
const canCreate = computed(() => !!auth.user?.isAdmin || !!config.value?.permissions.create),
  canOperatorWork = computed(() => !!auth.user?.isAdmin || !!config.value?.permissions.handle),
  exportableIds = computed(() =>
    tasks.value
      .filter((t) => ['PENDING_ACCEPT', 'PROCESSING'].includes(t.status) && Number(t.operatorId) === myId.value)
      .map((t) => t.lineId),
  )
async function claimAndExport() {
  if (!exportableIds.value.length) {
    void message.info('当前没有可接单或导出的本人订单')
    return
  }
  try {
    const task = await exportTasks.createBackground('adm_operator_excel', { lineIds: exportableIds.value })
    void message.success(
      task.reused ? '相同ADM导出任务正在进行，已打开导出任务' : '已接单并生成导出任务，请在页头“导出任务”下载',
    )
    await load()
  } catch (e) {
    void message.error(errorText(e))
  }
}
const operatorImportOpen = ref(false),
  operatorImportFile = ref<File | null>(null),
  operatorImportNotice = ref(''),
  operatorImportBusy = ref(false),
  operatorImportPreview = ref<Fields | null>(null)
function selectOperatorImport(e: Event) {
  operatorImportFile.value = (e.target as HTMLInputElement).files?.[0] || null
  operatorImportNotice.value = ''
  operatorImportPreview.value = null
}
async function previewOperatorImport() {
  if (!operatorImportFile.value) return
  operatorImportBusy.value = true
  try {
    operatorImportPreview.value = await admApi.operatorImport(operatorImportFile.value, true)
    operatorImportNotice.value = `预检通过，共 ${operatorImportPreview.value.totalRows} 行可提交`
  } catch (e) {
    operatorImportPreview.value = null
    operatorImportNotice.value = errorText(e)
  } finally {
    operatorImportBusy.value = false
  }
}
async function commitOperatorImport() {
  if (!operatorImportFile.value || !operatorImportPreview.value?.canCommit) return
  operatorImportBusy.value = true
  try {
    const result = await admApi.operatorImport(operatorImportFile.value, false)
    operatorImportOpen.value = false
    void message.success(`已导入 ${result.committed} 行处理结果`)
    await load()
  } catch (e) {
    operatorImportNotice.value = errorText(e)
    operatorImportPreview.value = null
  } finally {
    operatorImportBusy.value = false
  }
}
const allLines = computed(() => details.value.flatMap((x) => x.lines)),
  isPendingCase = (r: AdmCaseRow) =>
    ['DRAFT', 'PENDING'].includes(r.caseStatus) ||
    Number(r.pendingOperatorCount || 0) + Number(r.pendingAcceptCount || 0) > 0,
  isOpenCase = (r: AdmCaseRow) => !['CLOSED', 'VOIDED'].includes(r.caseStatus)
const masterMetrics = computed(() => [
  { key: 'range', title: '范围内主单', value: total.value },
  { key: 'pending', title: '待处理主单', value: rows.value.filter(isPendingCase).length },
  { key: 'open', title: '未结案主单', value: rows.value.filter(isOpenCase).length },
  { key: 'soon', title: '即将超时主单', value: rows.value.filter((r) => riskText(r) === '即将超时').length },
  { key: 'late', title: '已超时主单', value: rows.value.filter((r) => riskText(r) === '已超时').length },
])
const openLineCount = (r: AdmCaseRow) =>
  Math.max(
    0,
    Number(r.lineCount || 0) - Number(r.completedLineCount || 0) - Number(r.voidedLineCount || 0) -
      Number(r.historicalLineCount || 0),
  )
const sumRows = (selector: (row: AdmCaseRow) => number) => rows.value.reduce((sum, row) => sum + selector(row), 0)
const orderMetrics = computed(() => [
  { key: 'all', title: '订单明细', value: sumRows((r) => Number(r.lineCount || 0)) },
  {
    key: 'pending',
    title: '待处理订单明细',
    value: sumRows((r) => Number(r.pendingOperatorCount || 0) + Number(r.pendingAcceptCount || 0)),
  },
  {
    key: 'open',
    title: '未完成订单明细',
    value: sumRows(openLineCount),
  },
  {
    key: 'soon',
    title: '即将超时订单明细',
    value: sumRows((r) => (riskText(r) === '即将超时' ? openLineCount(r) : 0)),
  },
  {
    key: 'late',
    title: '已超时订单明细',
    value: sumRows((r) => (riskText(r) === '已超时' ? openLineCount(r) : 0)),
  },
])
const globalOrdersOpen = ref(false),
  globalOrders = computed(() =>
    details.value.flatMap((detail) =>
      detail.lines
        .filter(
          (line) =>
            orderMetric.value === 'all' ||
            (orderMetric.value === 'pending' && ['PENDING_OPERATOR', 'PENDING_ACCEPT'].includes(line.lineStatus)) ||
            (orderMetric.value === 'open' && !['COMPLETED', 'VOIDED', 'HISTORICAL'].includes(line.lineStatus)) ||
            (orderMetric.value === 'soon' &&
              riskText(detail.case) === '即将超时' &&
              !['COMPLETED', 'VOIDED', 'HISTORICAL'].includes(line.lineStatus)) ||
            (orderMetric.value === 'late' &&
              riskText(detail.case) === '已超时' &&
              !['COMPLETED', 'VOIDED', 'HISTORICAL'].includes(line.lineStatus)),
        )
        .map((line) => ({ detail, line })),
    ),
  )
async function openGlobalOrders(key: string) {
  orderMetric.value = key
  if (!details.value.length && rows.value.length) {
    try {
      details.value = await Promise.all(rows.value.map((item) => admApi.detail(item.id)))
    } catch (e) {
      void message.error(errorText(e))
      return
    }
  }
  globalOrdersOpen.value = true
}
function openGlobalLine(caseId: number, lineId: number) {
  globalOrdersOpen.value = false
  void router.push({ path: `/adm/cases/${caseId}`, query: { lineId } })
}
function lineStatusTone(status: string) {
  return status === 'COMPLETED'
    ? 'green'
    : status === 'VOIDED'
      ? 'red'
      : ['PENDING_REVIEW', 'WAITING_DIFF', 'WAITING_COLLECTION'].includes(status)
        ? 'amber'
        : 'blue'
}
function lineTask(status: string) {
  return (
    (
      {
        PENDING_OPERATOR: '组长分配操作人员',
        PENDING_ACCEPT: '操作人员确认接单',
        PROCESSING: '完成恢复、申诉或不申诉并提交审核',
        PENDING_REVIEW: 'ADM负责人审核',
        WAITING_DIFF: '匹配差异单',
        WAITING_COLLECTION: 'ADM负责人登记回款',
        COMPLETED: '已完成',
      } as Fields
    )[status] || '查看处理记录'
  )
}
function selectMetric(k: string) {
  metric.value = metric.value === k ? '' : k
}
const detailFor = (id: number) => details.value.find((d) => Number(d.case.id) === Number(id)),
  activeLineCount = (r: AdmCaseRow) => Math.max(0, Number(r.lineCount || 0) - Number(r.voidedLineCount || 0)),
  progressWidth = (r: AdmCaseRow) =>
    `${activeLineCount(r) ? Math.min(100, (Number(r.completedLineCount || 0) / activeLineCount(r)) * 100) : 100}%`
const visibleRows = computed(() =>
  rows.value.filter(
    (r) =>
      !metric.value ||
      metric.value === 'range' ||
      (metric.value === 'pending' && isPendingCase(r)) ||
      (metric.value === 'open' && isOpenCase(r)) ||
      (metric.value === 'soon' && riskText(r) === '即将超时') ||
      (metric.value === 'late' && riskText(r) === '已超时'),
  ),
)
function stageSummary(id: number) {
  const row = rows.value.find((item) => Number(item.id) === Number(id))
  if (!row) return []
  return [
    { label: '待办', count: Number(row.pendingLeaderCount || 0) + Number(row.pendingOperatorCount || 0) + Number(row.pendingAcceptCount || 0) },
    { label: '处理中', count: Number(row.processingCount || 0) },
    { label: '待审核', count: Number(row.pendingReviewCount || 0) },
    { label: '待差异/回款', count: Number(row.waitingDiffCount || 0) + Number(row.waitingCollectionCount || 0) },
    { label: '完成', count: Number(row.completedLineCount || 0) },
  ].filter((item) => item.count)
}
function blockerText(id: number) {
  const row = rows.value.find((item) => Number(item.id) === Number(id))
  if (!row || !openLineCount(row)) return '全部有效订单已完成'
  return [
    ['待分配组长', Number(row.pendingLeaderCount || 0)],
    ['待分配操作员', Number(row.pendingOperatorCount || 0)],
    ['待接单', Number(row.pendingAcceptCount || 0)],
    ['办理中', Number(row.processingCount || 0)],
    ['待负责人审核', Number(row.pendingReviewCount || 0)],
    ['待匹配差异单', Number(row.waitingDiffCount || 0)],
    ['待回款', Number(row.waitingCollectionCount || 0)],
  ]
    .filter(([, count]) => Number(count) > 0)
    .slice(0, 2)
    .map(([name, count]) => `${count}笔${name}`)
    .join('；')
}
function riskText(r: AdmCaseRow) {
  if (!r.replyDeadline) return '未设期限'
  const d = new Date(r.replyDeadline).getTime() - now()
  return d < 0 ? '已超时' : d < 86400000 ? '即将超时' : '正常'
}
function riskTone(r: AdmCaseRow) {
  return riskText(r) === '已超时' ? 'red' : riskText(r) === '即将超时' ? 'amber' : 'green'
}
function statusTone(s: string) {
  return s === 'VOIDED' ? 'red' : s === 'CLOSED' ? 'green' : s === 'DRAFT' ? 'amber' : 'blue'
}
function openCase(id: number) {
  void router.push(`/adm/cases/${id}`)
}
function canEditMasterRow(record: AdmCaseRow) {
  const allowed = !!auth.user?.isAdmin || !!(
    config.value?.permissions.create || config.value?.permissions.manage || config.value?.permissions.review
  )
  const owner = !!auth.user?.isAdmin || Number(record.coordinatorId) === Number(auth.user?.id)
  return allowed && owner && ['DRAFT', 'ACTIVE'].includes(record.caseStatus)
}
async function openMasterInfo(record: AdmCaseRow) {
  selectedMasterEditable.value = canEditMasterRow(record)
  masterInfoOpen.value = true
  selectedMasterDetail.value = null
  try {
    selectedMasterDetail.value = await admApi.detail(record.id)
  } catch (requestError) {
    masterInfoOpen.value = false
    void message.error(errorText(requestError))
  }
}
async function masterInfoSaved(detail: AdmCaseDetail) {
  selectedMasterDetail.value = detail
  masterInfoOpen.value = false
  await load()
}

const createOpen = ref(false),
  createStep = ref(1),
  saving = ref(false),
  createError = ref(''),
  referenceError = ref(''),
  fxLoading = ref(false),
  fxSnapshot = ref<FxSnapshot | null>(null),
  masterFiles = ref<File[]>([]),
  masters = reactive<Record<string, Option[]>>({ department: [], diffType: [], ota: [], supplier: [] }),
  form = reactive<Fields>({ lines: [] })
const issuerOptions = [
    { value: 'SUPPLIER', label: '供应商' },
    { value: 'PLATFORM', label: '平台' },
    { value: 'AIRLINE', label: '航司' },
  ],
  currencyOptions = ['CNY', 'USD', 'EUR', 'GBP', 'JPY'].map((value) => ({ value, label: value })),
  mapOptions = (x: Option[]) => x.map((i) => ({ value: i.code, label: `${i.name}（${i.code}）` })),
  departmentOptions = computed(() => mapOptions(masters.department)),
  diffTypeOptions = computed(() => masters.diffType.map((i) => ({ value: i.code, label: i.name }))),
  otaOptions = computed(() => mapOptions(masters.ota)),
  supplierOptions = computed(() => mapOptions(masters.supplier)),
  issuerMasterOptions = computed(() => (form.issuerType === 'PLATFORM' ? otaOptions.value : supplierOptions.value)),
  leaderOptions = computed(() => (config.value?.people.leader || []).map((i) => ({ value: i.id, label: i.name }))),
  filterOption = (input: string, o: Fields) =>
    String(o.label || '')
      .toLowerCase()
      .includes(input.toLowerCase())
const masterCnyAmount = computed(() => {
  const amount = Number(form.originalAmount || 0), rate = Number(fxSnapshot.value?.rateValue || 0)
  return Number.isFinite(amount * rate) ? `¥ ${(amount * rate).toFixed(2)}` : '—'
})
const lineCnyAmount = (index: number) => {
  const rate = Number(fxSnapshot.value?.rateValue || 0)
  if (!Number.isFinite(rate)) return '—'
  const rounded = form.lines.map((line: Fields) => Number((Number(line.originalAmount || 0) * rate).toFixed(2)))
  if (index === form.lines.length - 1) {
    const master = Number((Number(form.originalAmount || 0) * rate).toFixed(2))
    return `¥ ${(master - rounded.slice(0, -1).reduce((sum: number, value: number) => sum + value, 0)).toFixed(2)}`
  }
  return `¥ ${rounded[index].toFixed(2)}`
}
function blankLine() {
  return {
    key: createOperationIdentifier(),
    originalAmount: '',
    departmentCode: '',
    departmentName: '',
    leaderId: undefined,
    leaderName: '',
    diffTypeCode: '',
    diffTypeName: '',
    differenceReason: '',
    investigationNote: '',
    otaCode: undefined,
    otaName: '',
    otaOrderNo: '',
    supplierCode: undefined,
    supplierName: '',
    airlineName: '',
    ticketNo: '',
    pnr: '',
  }
}
function addLine() {
  form.lines.push(blankLine())
}
function pickMasterFiles(e: Event) {
  masterFiles.value = Array.from((e.target as HTMLInputElement).files || [])
}
async function openCreate() {
  createStep.value = 1
  masterFiles.value = []
  Object.assign(form, {
    admNo: '',
    issuerType: 'SUPPLIER',
    issuerCode: '',
    issuerName: '',
    currency: 'CNY',
    originalAmount: '',
    issuedDate: '',
    replyDeadline: '',
    remark: '',
    lines: [blankLine()],
  })
  createError.value = ''
  referenceError.value = ''
  fxSnapshot.value = null
  createOpen.value = true
  const kinds = ['department', 'diffType', 'ota', 'supplier'] as const
  const results = await Promise.allSettled(kinds.map((kind) => admApi.options(kind, '', 200)))
  const failures: string[] = []
  const labels = { department: '业务部门', diffType: '差异类型', ota: 'OTA平台', supplier: '供应商' }
  results.forEach((result, index) => {
    const kind = kinds[index]
    if (result.status === 'fulfilled') masters[kind] = result.value
    else {
      masters[kind] = []
      failures.push(`${labels[kind]}：${errorText(result.reason)}`)
    }
  })
  referenceError.value = failures.length ? `部分基础资料读取失败：${failures.join('；')}` : ''
  await loadExchangeRate()
}
async function loadExchangeRate() {
  fxLoading.value = true
  fxSnapshot.value = null
  try {
    fxSnapshot.value = await admApi.exchangeRate(String(form.currency || ''))
  } catch (e) {
    referenceError.value = `汇率读取失败：${errorText(e)}`
  } finally {
    fxLoading.value = false
  }
}
function issuerChanged() {
  form.issuerCode = ''
  form.issuerName = ''
}
function issuerSelected(code: string) {
  const i = (form.issuerType === 'PLATFORM' ? masters.ota : masters.supplier).find((v) => v.code === code)
  form.issuerName = i?.name || ''
}
function selectOption(line: Fields, kind: string, code?: string) {
  const i = masters[kind].find((v) => v.code === code),
    p = kind === 'diffType' ? 'diffType' : kind
  line[`${p}Code`] = code || null
  line[`${p}Name`] = i?.name || null
}
function selectLeader(line: Fields, id: string) {
  line.leaderName = config.value?.people.leader.find((v) => v.id === id)?.name || ''
}
async function createCase(saveAsDraft: boolean) {
  saving.value = true
  createError.value = ''
  try {
    const r = await admApi.create({ ...JSON.parse(JSON.stringify(form)), saveAsDraft }, createOperationIdentifier())
    const attachmentErrors: string[] = []
    for (const file of masterFiles.value) {
      try {
        await admApi.upload(Number(r.case.id), file, 'ADM_ORIGINAL')
      } catch (e) {
        attachmentErrors.push(`${file.name}：${errorText(e)}`)
      }
    }
    createOpen.value = false
    if (attachmentErrors.length) {
      void message.warning(
        `${saveAsDraft ? '草稿已保存' : '主单及订单已创建'}：${r.case.internalNo}；部分附件上传失败，可进入详情重新上传`,
      )
    } else {
      void message.success(saveAsDraft ? `草稿已保存：${r.case.internalNo}` : `已创建：${r.case.internalNo}`)
    }
    await router.push(`/adm/cases/${r.case.id}`)
  } catch (e) {
    createError.value = errorText(e)
  } finally {
    saving.value = false
  }
}
const importOpen = ref(false),
  importFile = ref<File | null>(null),
  importBusy = ref(false),
  preview = ref<Fields | null>(null),
  importError = ref('')
function openImport() {
  importOpen.value = true
  importFile.value = null
  preview.value = null
  importError.value = ''
}
function selectImport(e: Event) {
  importFile.value = (e.target as HTMLInputElement).files?.[0] || null
  preview.value = null
}
async function downloadTemplate() {
  try {
    const r = await admApi.template()
    saveBlob(r.data, 'ADM日常建单19列模板.xlsx')
  } catch (e) {
    void message.error(errorText(e))
  }
}
async function previewImport() {
  if (!importFile.value) return
  importBusy.value = true
  try {
    preview.value = await admApi.importPreview(importFile.value)
  } catch (e) {
    importError.value = errorText(e)
  } finally {
    importBusy.value = false
  }
}
async function commitImport() {
  if (!preview.value?.batchNo) return
  importBusy.value = true
  try {
    await admApi.importCommit(preview.value.batchNo)
    importOpen.value = false
    void message.success('导入完成')
    await load()
  } catch (e) {
    importError.value = errorText(e)
  } finally {
    importBusy.value = false
  }
}
onMounted(async () => {
  try {
    config.value = await admApi.config()
  } catch (e) {
    error.value = errorText(e)
  }
  await load()
  if (route.query.create === '1' && config.value?.permissions.create) {
    await router.replace({ path: '/adm/cases' })
    await openCreate()
  }
})
</script>
